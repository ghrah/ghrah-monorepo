import {
  type CommandResultPayload,
  CommandType,
  createCommand,
  createPing,
  EventType,
  type RoomInfoPayload,
  type RoomLogEntryPayload,
  ServerClient,
  type ServerMessage,
  SystemType,
  type WebSocketLike,
} from "@ghrah/protocol";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import WebSocket from "ws";
import { MockServer } from "./server.js";

let server: MockServer;
let url: string;

function wsFactory(u: string): WebSocketLike {
  return new WebSocket(u) as unknown as WebSocketLike;
}

async function makeClient(): Promise<ServerClient> {
  const client = new ServerClient(url, "observer", { wsFactory });
  await client.connect();
  return client;
}

function collect(client: ServerClient, type: string): ServerMessage[] {
  const msgs: ServerMessage[] = [];
  client.on(type, (m) => msgs.push(m));
  return msgs;
}

async function waitUntil(cond: () => boolean, timeoutMs = 3000): Promise<void> {
  const start = Date.now();
  while (!cond()) {
    if (Date.now() - start > timeoutMs) throw new Error("waitUntil timeout");
    await new Promise((r) => setTimeout(r, 10));
  }
}

async function request(
  client: ServerClient,
  type: CommandType,
  payload: Record<string, unknown>,
): Promise<CommandResultPayload> {
  return client.request(createCommand(type, payload), 5000);
}

async function requestWithId(
  client: ServerClient,
  type: CommandType,
  payload: Record<string, unknown>,
  requestId: string,
): Promise<CommandResultPayload> {
  return client.request(createCommand(type, payload, requestId), 5000);
}

/** 建一个 project + room，返回二者稳定身份。 */
async function setupProjectRoom(
  client: ServerClient,
  suffix = crypto.randomUUID().slice(0, 8),
): Promise<{ projectId: string; roomId: string }> {
  const project = await request(client, CommandType.PROJECT_CREATE, { name: `p-${suffix}` });
  const projectId = (project.data as { project: { project_id: string } }).project.project_id;
  const room = await request(client, CommandType.ROOM_CREATE, {
    project_id: projectId,
    name: `r-${suffix}`,
  });
  return {
    projectId,
    roomId: (room.data as { room: RoomInfoPayload }).room.room_id,
  };
}

async function setupRoom(client: ServerClient): Promise<string> {
  return (await setupProjectRoom(client)).roomId;
}

beforeEach(async () => {
  server = new MockServer({ port: 0 });
  await server.start();
  url = `ws://127.0.0.1:${server.port}/ws`;
});

afterEach(async () => {
  await server.close();
});

describe("mock-server 协议层", () => {
  it("COMMAND_RESULT 回执：request_id 匹配 + success/data", async () => {
    const client = await makeClient();
    try {
      const msg = createCommand(CommandType.HEALTH_CHECK, {});
      const result = await client.request(msg, 5000);
      expect(result.success).toBe(true);
      expect(result.request_id).toBe(msg.request_id);
      expect((result.data as Record<string, unknown>).status).toBe("ok");

      // ping/pong 心跳
      const pongPromise = new Promise<ServerMessage>((resolve) =>
        client.on(SystemType.PONG, resolve),
      );
      await client.send(createPing());
      expect((await pongPromise).type).toBe(SystemType.PONG);

      // 未识别命令
      const unknown = await client.request(
        createCommand("nonexistent_command" as CommandType, {}),
        5000,
      );
      expect(unknown.success).toBe(false);
      expect(unknown.error).toContain("unknown command");
    } finally {
      await client.disconnect();
    }
  }, 10_000);

  it("room_send → COMMAND_RESULT(entry 带 seq) → ROOM_LOG_APPENDED 广播闭环，seq 单调", async () => {
    const sender = await makeClient();
    const listener = await makeClient();
    try {
      const roomId = await setupRoom(sender);
      const events = collect(listener, EventType.ROOM_LOG_APPENDED);

      const r1 = await request(sender, CommandType.ROOM_SEND, {
        room_id: roomId,
        author: "human:user",
        author_type: "human",
        data: { message: "hello" },
      });
      expect(r1.success).toBe(true);
      const entry1 = (r1.data as { entry: RoomLogEntryPayload }).entry;
      expect(entry1.seq).toBe(1);
      expect(entry1.room_id).toBe(roomId);

      const r2 = await request(sender, CommandType.ROOM_SEND, {
        room_id: roomId,
        author: "human:second",
        author_type: "human",
        data: { message: "hi" },
      });
      const entry2 = (r2.data as { entry: RoomLogEntryPayload }).entry;
      expect(entry2.seq).toBe(2);
      expect(entry2.seq).toBeGreaterThan(entry1.seq);

      await waitUntil(() => events.length >= 2);
      const broadcast1 = events[0].payload as { entry: RoomLogEntryPayload };
      expect(broadcast1.entry.id).toBe(entry1.id);
      expect(broadcast1.entry.seq).toBe(1);
      expect((events[1].payload as { entry: RoomLogEntryPayload }).entry.seq).toBe(2);
      // 事件信封带单调 seq_id
      expect(events[0].seq_id).toBeTypeOf("number");
      expect(events[1].seq_id!).toBeGreaterThan(events[0].seq_id!);
    } finally {
      await sender.disconnect();
      await listener.disconnect();
    }
  }, 10_000);

  it("room_send targets：透传 + 非成员 target 拒绝 + 空 targets 广播放行", async () => {
    const client = await makeClient();
    try {
      const { projectId, roomId } = await setupProjectRoom(client, "targets");
      const frontendId = "frontend-agent-id";
      await request(client, CommandType.SPAWN_AGENT, {
        project_id: projectId,
        config: { name: "frontend", agent_id: frontendId },
      });
      await request(client, CommandType.ROOM_JOIN, {
        room_id: roomId,
        subject: frontendId,
        subject_type: "agent",
        subject_name: "frontend",
      });

      // 定向成员：透传 data.targets
      const targeted = await request(client, CommandType.ROOM_SEND, {
        room_id: roomId,
        author: "human:user",
        author_type: "human",
        data: { message: "hi frontend", targets: [frontendId] },
      });
      expect(targeted.success).toBe(true);
      expect((targeted.data as { entry: RoomLogEntryPayload }).entry.data.targets).toEqual([
        frontendId,
      ]);

      const authored = await request(client, CommandType.ROOM_SEND, {
        room_id: roomId,
        author: "frontend",
        author_type: "agent",
        data: { message: "agent reply" },
      });
      expect((authored.data as { entry: RoomLogEntryPayload }).entry.author).toBe(frontendId);

      // 非成员 target：拒绝
      const bad = await request(client, CommandType.ROOM_SEND, {
        room_id: roomId,
        author: "human:user",
        author_type: "human",
        data: { message: "hi stranger", targets: ["ghost"] },
      });
      expect(bad.success).toBe(false);
      expect(bad.error).toContain("target not in room: ghost");

      // targets 非 string[]：拒绝
      const malformed = await request(client, CommandType.ROOM_SEND, {
        room_id: roomId,
        author: "human:user",
        author_type: "human",
        data: { message: "m", targets: "frontend" },
      });
      expect(malformed.success).toBe(false);
      expect(malformed.error).toContain("invalid targets");

      // 空 targets / 缺省：广播放行
      const broadcast = await request(client, CommandType.ROOM_SEND, {
        room_id: roomId,
        author: "human:user",
        author_type: "human",
        data: { message: "to all", targets: [] },
      });
      expect(broadcast.success).toBe(true);
    } finally {
      await client.disconnect();
    }
  }, 10_000);

  it("订阅过滤：订阅指定 event_types 的连接只收该类事件", async () => {
    const subscribed = await makeClient();
    const sender = await makeClient();
    try {
      const subResult = await request(subscribed, CommandType.SUBSCRIBE, {
        event_types: [EventType.ROOM_LOG_APPENDED],
      });
      expect(subResult.success).toBe(true);

      const logEvents = collect(subscribed, EventType.ROOM_LOG_APPENDED);
      const roomEvents = collect(subscribed, EventType.ROOM_CREATED);

      const roomId = await setupRoom(sender);
      await request(sender, CommandType.ROOM_SEND, {
        room_id: roomId,
        author: "human:user",
        author_type: "human",
        data: { message: "filtered?" },
      });

      await waitUntil(() => logEvents.length >= 1);
      await new Promise((r) => setTimeout(r, 200));
      expect(logEvents.length).toBe(1);
      expect(roomEvents.length).toBe(0);

      // 未订阅的连接默认全发（protocol 未定义默认语义，mock 取「未订阅=全发」）
      const unsubscribed = await makeClient();
      try {
        const allRoomEvents = collect(unsubscribed, EventType.ROOM_CREATED);
        await request(sender, CommandType.ROOM_CREATE, {
          project_id: (
            (await request(sender, CommandType.PROJECT_LIST, {})).data as {
              projects: { project_id: string }[];
            }
          ).projects[0].project_id,
          name: "r2",
        });
        await waitUntil(() => allRoomEvents.length >= 1);
      } finally {
        await unsubscribed.disconnect();
      }
    } finally {
      await subscribed.disconnect();
      await sender.disconnect();
    }
  }, 10_000);

  it("room_update 乐观锁：错误 expected_version → success:false", async () => {
    const client = await makeClient();
    try {
      const roomId = await setupRoom(client);
      const conflict = await request(client, CommandType.ROOM_UPDATE, {
        room_id: roomId,
        name: "renamed",
        expected_version: 99,
      });
      expect(conflict.success).toBe(false);
      expect(conflict.error).toBe("room_version_conflict");
      expect(conflict.error_detail).toContain("expected 99");

      const okResult = await request(client, CommandType.ROOM_UPDATE, {
        room_id: roomId,
        name: "renamed",
        expected_version: 1,
      });
      expect(okResult.success).toBe(true);
      expect((okResult.data as { room: RoomInfoPayload }).room.version).toBe(2);
    } finally {
      await client.disconnect();
    }
  }, 10_000);

  it("重连 resume：带 last_seq_id 重连只收增量、不重复", async () => {
    const clientA = await makeClient();
    const roomId = await setupRoom(clientA);
    const receivedA = collect(clientA, EventType.ROOM_LOG_APPENDED);

    const send = (msg: string) =>
      request(clientA, CommandType.ROOM_SEND, {
        room_id: roomId,
        author: "human:user",
        author_type: "human",
        data: { message: msg },
      });

    await send("m1");
    await send("m2");
    await waitUntil(() => receivedA.length >= 2);
    const lastSeq = clientA.lastSeqId;
    expect(lastSeq).toBeGreaterThan(0);
    await clientA.disconnect();

    // 离线期间再产生 2 条
    const clientB = await makeClient();
    await request(clientB, CommandType.ROOM_SEND, {
      room_id: roomId,
      author: "human:user",
      author_type: "human",
      data: { message: "m3" },
    });
    await request(clientB, CommandType.ROOM_SEND, {
      room_id: roomId,
      author: "human:user",
      author_type: "human",
      data: { message: "m4" },
    });
    await clientB.disconnect();

    // 带 last_seq_id 重连（raw ws，对齐 ServerClient._buildUrl 的 query 形态）
    const replayed: ServerMessage[] = [];
    const ws = new WebSocket(
      `${url}?client_type=observer&client_id=resume-test&last_seq_id=${lastSeq}`,
    );
    ws.on("message", (data) => replayed.push(JSON.parse(data.toString())));
    await new Promise<void>((resolve) => ws.on("open", () => resolve()));
    await waitUntil(() => replayed.length >= 2);
    await new Promise((r) => setTimeout(r, 200));
    ws.close();

    const seqIds = replayed.map((m) => m.seq_id as number);
    expect(seqIds.every((s) => s > lastSeq)).toBe(true);
    expect(new Set(seqIds).size).toBe(seqIds.length);
    const entries = replayed.map((m) => (m.payload as { entry: RoomLogEntryPayload }).entry);
    expect(entries.map((e) => (e.data as { message: string }).message)).toEqual(["m3", "m4"]);
  }, 10_000);

  it("HITL：hitl_request → hitl_response(approved) 成功；未知 promise_id 失败", async () => {
    const client = await makeClient();
    try {
      const project = await request(client, CommandType.PROJECT_CREATE, { name: "hitl-project" });
      const projectId = (project.data as { project: { project_id: string } }).project.project_id;
      await request(client, CommandType.SPAWN_AGENT, {
        project_id: projectId,
        config: { name: "backend", agent_id: "backend-agent-id" },
      });
      const hitlEvents = collect(client, EventType.HITL_REQUEST);
      const triggered = server.state.triggerHitl(
        "backend",
        "deploy",
        { target: "staging" },
        {},
        projectId,
      );

      await waitUntil(() => hitlEvents.length >= 1);
      const payload = hitlEvents[0].payload as { promise_id: string; agent_name: string };
      expect(payload.promise_id).toBe(triggered.promise_id);
      expect(payload.agent_name).toBe("backend");

      const approved = await request(client, CommandType.HITL_RESPONSE, {
        promise_id: payload.promise_id,
        approved: true,
      });
      expect(approved.success).toBe(true);
      expect((approved.data as { status: string }).status).toBe("approved");
      expect(server.state.pendingHitl.get(payload.promise_id)?.status).toBe("approved");

      const unknown = await request(client, CommandType.HITL_RESPONSE, {
        promise_id: "hitl-does-not-exist",
        approved: true,
      });
      expect(unknown.success).toBe(false);
      expect(unknown.error).toContain("unknown hitl request");
    } finally {
      await client.disconnect();
    }
  }, 10_000);

  it("初始同步形态：list_agents / room_list / project_list / room_get_log 与 bind.ts 消费端一致", async () => {
    const client = await makeClient();
    try {
      const { projectId, roomId } = await setupProjectRoom(client, "sync");
      const spawned = await request(client, CommandType.SPAWN_AGENT, {
        project_id: projectId,
        config: { name: "architect", description: "架构师" },
      });
      expect(spawned.success).toBe(true);
      await request(client, CommandType.ROOM_SEND, {
        room_id: roomId,
        author: "human:user",
        author_type: "human",
        data: { message: "sync check" },
      });

      // LIST_AGENTS → data.agents: [{name, config}]
      const agents = await request(client, CommandType.LIST_AGENTS, { project_id: projectId });
      const agentList = (
        agents.data as {
          agents: { project_id: string; agent_id: string; name: string; config: unknown }[];
        }
      ).agents;
      expect(Array.isArray(agentList)).toBe(true);
      expect(agentList[0].project_id).toBe(projectId);
      expect(agentList[0].agent_id).toBeTypeOf("string");
      expect(agentList[0].name).toBe("architect");
      expect(agentList[0].config).toBeTypeOf("object");

      // ROOM_LIST → data.rooms: RoomInfoPayload[]
      const rooms = await request(client, CommandType.ROOM_LIST, {});
      const roomList = (rooms.data as { rooms: RoomInfoPayload[]; count: number }).rooms;
      expect(Array.isArray(roomList)).toBe(true);
      expect(roomList[0].room_id).toBe(roomId);
      expect(roomList[0].members).toEqual([]);
      expect(roomList[0].version).toBe(1);

      // PROJECT_LIST → data.projects: ProjectInfoPayload[]
      const projects = await request(client, CommandType.PROJECT_LIST, {});
      const projectList = (projects.data as { projects: { project_id: string; name: string }[] })
        .projects;
      expect(Array.isArray(projectList)).toBe(true);
      expect(projectList[0].name).toBe("p-sync");

      // ROOM_GET_LOG → data.entries: RoomLogEntryPayload[]（bind 从 data.room_id 或 entry.room_id 取）
      const log = await request(client, CommandType.ROOM_GET_LOG, { room_id: roomId });
      const logData = log.data as { room_id: string; entries: RoomLogEntryPayload[] };
      expect(logData.room_id).toBe(roomId);
      expect(logData.entries.length).toBe(1);
      expect(logData.entries[0].room_id).toBe(roomId);
      expect(logData.entries[0].seq).toBe(1);
    } finally {
      await client.disconnect();
    }
  }, 10_000);

  it("Agent 身份按 Project 隔离：同名实例、运行态和历史互不串线", async () => {
    const client = await makeClient();
    try {
      const firstProject = await request(client, CommandType.PROJECT_CREATE, { name: "alpha" });
      const secondProject = await request(client, CommandType.PROJECT_CREATE, { name: "beta" });
      const firstProjectId = (firstProject.data as { project: { project_id: string } }).project
        .project_id;
      const secondProjectId = (secondProject.data as { project: { project_id: string } }).project
        .project_id;
      const firstAgentId = "alpha-architect";
      const secondAgentId = "beta-architect";

      expect(
        (
          await request(client, CommandType.SPAWN_AGENT, {
            project_id: firstProjectId,
            config: { name: "architect", agent_id: firstAgentId },
          })
        ).success,
      ).toBe(true);
      expect(
        (
          await request(client, CommandType.SPAWN_AGENT, {
            project_id: secondProjectId,
            config: { name: "architect", agent_id: secondAgentId },
          })
        ).success,
      ).toBe(true);

      const firstList = await request(client, CommandType.LIST_AGENTS, {
        project_id: firstProjectId,
      });
      const secondList = await request(client, CommandType.LIST_AGENTS, {
        project_id: secondProjectId,
      });
      expect((firstList.data as { agents: { agent_id: string }[] }).agents).toHaveLength(1);
      expect((firstList.data as { agents: { agent_id: string }[] }).agents[0].agent_id).toBe(
        firstAgentId,
      );
      expect((secondList.data as { agents: { agent_id: string }[] }).agents[0].agent_id).toBe(
        secondAgentId,
      );

      const firstSessions = await request(client, CommandType.SESSION_LIST, {
        project_id: firstProjectId,
        agent_id: firstAgentId,
        agent_name: "architect",
      });
      const secondSessions = await request(client, CommandType.SESSION_LIST, {
        project_id: secondProjectId,
        agent_id: secondAgentId,
        agent_name: "architect",
      });
      const firstSessionId = (firstSessions.data as { sessions: { session_id: string }[] })
        .sessions[0].session_id;
      const secondSessionId = (secondSessions.data as { sessions: { session_id: string }[] })
        .sessions[0].session_id;
      expect(firstSessionId).not.toBe(secondSessionId);

      const terminated = await request(client, CommandType.TERMINATE_AGENT, {
        project_id: firstProjectId,
        agent_id: firstAgentId,
        name: "architect",
      });
      expect(terminated.success).toBe(true);
      expect(
        (
          (
            await request(client, CommandType.LIST_AGENTS, {
              project_id: firstProjectId,
            })
          ).data as { agents: unknown[] }
        ).agents,
      ).toEqual([]);
      expect(
        (
          (
            await request(client, CommandType.LIST_AGENTS, {
              project_id: secondProjectId,
            })
          ).data as { agents: unknown[] }
        ).agents,
      ).toHaveLength(1);
      expect(server.state.projects.get(firstProjectId)?.agents[0].runtime_status).toBe("stopped");
      expect(server.state.projects.get(secondProjectId)?.agents[0].runtime_status).toBe("running");
    } finally {
      await client.disconnect();
    }
  }, 10_000);

  it("Room 生命周期：归档冻结日志操作，恢复保留日志，删除仅清日志不删 Agent", async () => {
    const client = await makeClient();
    try {
      const { projectId, roomId } = await setupProjectRoom(client, "room-lifecycle");
      const agentId = "room-agent-id";
      await request(client, CommandType.SPAWN_AGENT, {
        project_id: projectId,
        config: { name: "worker", agent_id: agentId },
      });
      await request(client, CommandType.ROOM_SEND, {
        room_id: roomId,
        author: "human:user",
        author_type: "human",
        data: { message: "persist me" },
      });

      const conflict = await request(client, CommandType.ROOM_ARCHIVE, {
        room_id: roomId,
        expected_version: 99,
      });
      expect(conflict.error).toBe("room_version_conflict");
      expect(conflict.error_detail).toContain("current 1");

      const archived = await request(client, CommandType.ROOM_ARCHIVE, {
        room_id: roomId,
        expected_version: 1,
      });
      expect(archived.success).toBe(true);
      expect((archived.data as { room: RoomInfoPayload }).room.version).toBe(2);
      expect(
        (
          await request(client, CommandType.ROOM_SEND, {
            room_id: roomId,
            author: "human:user",
            author_type: "human",
            data: { message: "blocked" },
          })
        ).error,
      ).toBe("resource_archived");
      const activeRooms = await request(client, CommandType.ROOM_LIST, {
        project_id: projectId,
        status: "active",
      });
      const archivedRooms = await request(client, CommandType.ROOM_LIST, {
        project_id: projectId,
        status: "archived",
      });
      expect((activeRooms.data as { rooms: unknown[] }).rooms).toEqual([]);
      expect((archivedRooms.data as { rooms: RoomInfoPayload[] }).rooms[0].room_id).toBe(roomId);

      const restored = await request(client, CommandType.ROOM_RESTORE, {
        room_id: roomId,
        expected_version: 2,
      });
      expect((restored.data as { room: RoomInfoPayload }).room.version).toBe(3);
      const log = await request(client, CommandType.ROOM_GET_LOG, { room_id: roomId });
      expect((log.data as { entries: RoomLogEntryPayload[] }).entries).toHaveLength(1);

      const deleted = await request(client, CommandType.ROOM_DELETE, {
        room_id: roomId,
        expected_version: 3,
      });
      expect(deleted.success).toBe(true);
      expect(server.state.rooms.has(roomId)).toBe(false);
      expect(server.state.roomLogs.has(roomId)).toBe(false);
      const agents = await request(client, CommandType.LIST_AGENTS, { project_id: projectId });
      expect((agents.data as { agents: { agent_id: string }[] }).agents[0].agent_id).toBe(agentId);
    } finally {
      await client.disconnect();
    }
  }, 10_000);

  it("Project 生命周期：归档停 Agent，恢复不复活，删除需显式级联且只发 Project 事件", async () => {
    const client = await makeClient();
    try {
      const { projectId, roomId } = await setupProjectRoom(client, "project-lifecycle");
      const agentId = "project-agent-id";
      await request(client, CommandType.SPAWN_AGENT, {
        project_id: projectId,
        config: { name: "worker", agent_id: agentId },
      });
      const roomDeleted = collect(client, EventType.ROOM_DELETED);
      const projectDeleted = collect(client, EventType.PROJECT_DELETED);

      const conflict = await request(client, CommandType.PROJECT_ARCHIVE, {
        project_id: projectId,
        expected_version: 99,
      });
      expect(conflict.error).toBe("project_version_conflict");

      const archived = await request(client, CommandType.PROJECT_ARCHIVE, {
        project_id: projectId,
        expected_version: 2,
      });
      expect(
        (archived.data as { project: { status: string; version: number } }).project,
      ).toMatchObject({ status: "stopped", version: 3 });
      expect(server.state.projects.get(projectId)?.agents[0].runtime_status).toBe("stopped");
      expect(
        (
          (await request(client, CommandType.PROJECT_LIST, { archived: false })).data as {
            projects: { project_id: string }[];
          }
        ).projects.some((project) => project.project_id === projectId),
      ).toBe(false);
      expect(
        (
          (await request(client, CommandType.PROJECT_LIST, { archived: true })).data as {
            projects: { project_id: string }[];
          }
        ).projects.some((project) => project.project_id === projectId),
      ).toBe(true);

      const restored = await request(client, CommandType.PROJECT_RESTORE, {
        project_id: projectId,
        expected_version: 3,
      });
      expect(
        (restored.data as { project: { status: string; version: number } }).project,
      ).toMatchObject({ status: "stopped", version: 4 });
      await request(client, CommandType.PROJECT_RESUME, { project_id: projectId });
      const agentsAfterResume = await request(client, CommandType.LIST_AGENTS, {
        project_id: projectId,
      });
      expect((agentsAfterResume.data as { agents: unknown[] }).agents).toEqual([]);

      const refused = await request(client, CommandType.PROJECT_DELETE, {
        project_id: projectId,
        expected_version: 5,
        cascade_rooms: false,
      });
      expect(refused.error).toBe("project_has_rooms");
      expect(server.state.rooms.has(roomId)).toBe(true);

      const deleted = await request(client, CommandType.PROJECT_DELETE, {
        project_id: projectId,
        expected_version: 5,
        cascade_rooms: true,
      });
      expect(deleted.success).toBe(true);
      await waitUntil(() => projectDeleted.length === 1);
      expect(roomDeleted).toHaveLength(0);
      expect(server.state.projects.has(projectId)).toBe(false);
      expect(server.state.rooms.has(roomId)).toBe(false);
      expect([...server.state.agents.values()].some((agent) => agent.projectId === projectId)).toBe(
        false,
      );
    } finally {
      await client.disconnect();
    }
  }, 10_000);

  it("生命周期 request_id 幂等重放：不重复变更或发事件，复用到不同请求会拒绝", async () => {
    const client = await makeClient();
    try {
      const { roomId } = await setupProjectRoom(client, "idempotency");
      const archivedEvents = collect(client, EventType.ROOM_ARCHIVED);
      const payload = { room_id: roomId, expected_version: 1 };
      const first = await requestWithId(
        client,
        CommandType.ROOM_ARCHIVE,
        payload,
        "room-archive-idempotent",
      );
      const replay = await requestWithId(
        client,
        CommandType.ROOM_ARCHIVE,
        payload,
        "room-archive-idempotent",
      );
      expect(first).toEqual(replay);
      expect(server.state.rooms.get(roomId)?.version).toBe(2);
      expect(archivedEvents).toHaveLength(1);

      const reused = await requestWithId(
        client,
        CommandType.ROOM_RESTORE,
        { room_id: roomId, expected_version: 2 },
        "room-archive-idempotent",
      );
      expect(reused.success).toBe(false);
      expect(reused.error).toBe("request_id_conflict");
    } finally {
      await client.disconnect();
    }
  }, 10_000);

  it("ActionChain v2：独立 Root Session、稳定 Branch ID 与显式历史路由", async () => {
    const client = await makeClient();
    try {
      const project = await request(client, CommandType.PROJECT_CREATE, { name: "chain-project" });
      const projectId = (project.data as { project: { project_id: string } }).project.project_id;
      const agentId = "mock-agent-id";
      await request(client, CommandType.SPAWN_AGENT, {
        project_id: projectId,
        config: { name: "planner", agent_id: agentId },
      });
      const scope = { project_id: projectId, agent_id: agentId, agent_name: "planner" };

      const listed = await request(client, CommandType.SESSION_LIST, scope);
      const [first] = (listed.data as { sessions: { session_id: string; root_node_id: string }[] })
        .sessions;
      const created = await request(client, CommandType.SESSION_CREATE, {
        ...scope,
        origin_session_id: first.session_id,
        origin_node_id: first.root_node_id,
      });
      const second = created.data as {
        session_id: string;
        root_node_id: string;
        active_branch_id: string;
      };
      expect(second.root_node_id).not.toBe(first.root_node_id);

      await request(client, CommandType.SESSION_ACTIVATE, {
        ...scope,
        session_id: second.session_id,
      });
      const branchResult = await request(client, CommandType.BRANCH_CREATE, {
        ...scope,
        session_id: second.session_id,
        name: "retry-1",
        from_node_id: second.root_node_id,
      });
      const retry = branchResult.data as { branch_id: string };
      await request(client, CommandType.BRANCH_ACTIVATE, {
        ...scope,
        session_id: second.session_id,
        branch_id: retry.branch_id,
      });

      const history = await request(client, CommandType.GET_CHAIN_HISTORY, {
        ...scope,
        session_id: second.session_id,
        branch_id: retry.branch_id,
        limit: -1,
      });
      const nodes = (history.data as { nodes: { id: string; parent_id: string | null }[] }).nodes;
      expect(nodes.map(({ id, parent_id }) => ({ id, parent_id }))).toEqual([
        { id: second.root_node_id, parent_id: null },
      ]);
    } finally {
      await client.disconnect();
    }
  }, 10_000);
});
