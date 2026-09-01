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

/** 建一个 project + room，返回 room_id。 */
async function setupRoom(client: ServerClient): Promise<string> {
  const project = await request(client, CommandType.PROJECT_CREATE, { name: "p1" });
  const projectId = (project.data as { project: { project_id: string } }).project.project_id;
  const room = await request(client, CommandType.ROOM_CREATE, {
    project_id: projectId,
    name: "r1",
  });
  return (room.data as { room: RoomInfoPayload }).room.room_id;
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
        author: "architect",
        author_type: "agent",
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
      const roomId = await setupRoom(client);
      await request(client, CommandType.ROOM_JOIN, {
        room_id: roomId,
        subject: "frontend",
        subject_type: "agent",
      });

      // 定向成员：透传 data.targets
      const targeted = await request(client, CommandType.ROOM_SEND, {
        room_id: roomId,
        author: "human:user",
        author_type: "human",
        data: { message: "hi frontend", targets: ["frontend"] },
      });
      expect(targeted.success).toBe(true);
      expect((targeted.data as { entry: RoomLogEntryPayload }).entry.data.targets).toEqual([
        "frontend",
      ]);

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
      expect(conflict.error).toContain("version conflict");

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
      const hitlEvents = collect(client, EventType.HITL_REQUEST);
      const triggered = server.state.triggerHitl("backend", "deploy", { target: "staging" });

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
      await request(client, CommandType.SPAWN_AGENT, {
        config: { name: "architect", description: "架构师" },
      });
      const roomId = await setupRoom(client);
      await request(client, CommandType.ROOM_SEND, {
        room_id: roomId,
        author: "human:user",
        author_type: "human",
        data: { message: "sync check" },
      });

      // LIST_AGENTS → data.agents: [{name, config}]
      const agents = await request(client, CommandType.LIST_AGENTS, {});
      const agentList = (agents.data as { agents: { name: string; config: unknown }[] }).agents;
      expect(Array.isArray(agentList)).toBe(true);
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
      expect(projectList[0].name).toBe("p1");

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
});
