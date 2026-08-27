import type { CommandResultPayload, ServerMessage } from "@ghrah/protocol";
import { CommandType, EventType, SystemType, type WebSocketLike } from "@ghrah/protocol";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { connectStores } from "./bind.js";
import { ObserverClient } from "./client.js";
import { createFrameBatcher, createSyncBatcher, type FrameBatcher } from "./frame-batcher.js";
import { useActionChainsStore } from "./stores/action-chains.js";
import { useAgentsStore } from "./stores/agents.js";
import { useChangesStore } from "./stores/changes.js";
import { useChatStore } from "./stores/chat.js";
import { useConnectionStore } from "./stores/connection.js";
import { useHitlStore } from "./stores/hitl.js";
import { useManifestsStore } from "./stores/manifests.js";
import { useProjectsStore } from "./stores/projects.js";
import { useRoomsStore } from "./stores/rooms.js";
import { useTasksStore } from "./stores/tasks.js";

const WS_OPEN = 1;

interface MockWebSocket extends WebSocketLike {
  sent: string[];
}

interface ClientInternals {
  _dispatch: (msgType: string, message: ServerMessage) => void;
  _notifyReconnecting: () => void;
  _notifyDisconnected: () => void;
}

function createMockWs(): MockWebSocket {
  const ws: MockWebSocket = {
    readyState: WS_OPEN,
    sent: [],
    onopen: null,
    onmessage: null,
    onclose: null,
    onerror: null,
    send(_data: string) {},
    close() {},
  };
  return ws;
}

function makeMsg(
  type: string,
  payload: Record<string, unknown>,
  extra?: Partial<ServerMessage>,
): ServerMessage {
  return { type, payload, ...extra };
}

function internals(c: ObserverClient): ClientInternals {
  return c as unknown as ClientInternals;
}

const DEFAULT_CONFIG = {
  name: "",
  description: "",
  system_prompt: "",
  max_iterations: 10,
  agent_config_name: null,
} as const;

describe("connectStores", () => {
  let client: ObserverClient;
  let mockWs: MockWebSocket;
  let disconnect: () => void;

  beforeEach(() => {
    vi.useFakeTimers();
    setActivePinia(createPinia());
    mockWs = createMockWs();
    client = new ObserverClient("ws://localhost:4111/ws", "observer", {
      wsFactory: () => mockWs,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    if (skipSyncInitialState) {
      skipSyncInitialState.mockRestore();
      skipSyncInitialState = null;
    }
    if (disconnect) disconnect();
    if (client.connected) {
      client.disconnect();
    }
  });

  let skipSyncInitialState: ReturnType<typeof vi.spyOn<any, any>> | null = null;

  async function connectClient(opts: { skipSync?: boolean; batcher?: FrameBatcher } = {}) {
    const { skipSync = true } = opts;
    if (skipSync) {
      skipSyncInitialState = vi
        .spyOn(client as any, "_syncInitialState")
        .mockResolvedValue(undefined);
    }
    disconnect = connectStores(client, { batcher: opts.batcher ?? createSyncBatcher() });
    const connectPromise = client.connect();
    mockWs.onopen!();
    await connectPromise;
  }

  describe("connection state", () => {
    it("sets connection to connected on connect", async () => {
      await connectClient();
      expect(useConnectionStore().state).toBe("connected");
    });

    it("sets connection to reconnecting on reconnect", () => {
      const store = useConnectionStore();
      disconnect = connectStores(client, { batcher: createSyncBatcher() });
      client.onReconnecting(() => store.setReconnecting());
      internals(client)._notifyReconnecting();
      expect(store.state).toBe("reconnecting");
    });

    it("sets connection to disconnected", () => {
      const store = useConnectionStore();
      client.onDisconnected(() => store.setDisconnected());
      internals(client)._notifyDisconnected();
      expect(store.state).toBe("disconnected");
    });
  });

  describe("agent events", () => {
    it("adds agent on agent_spawned", async () => {
      await connectClient();
      const store = useAgentsStore();

      internals(client)._dispatch(
        EventType.AGENT_SPAWNED,
        makeMsg(EventType.AGENT_SPAWNED, {
          name: "agent-1",
          config: { ...DEFAULT_CONFIG, name: "agent-1", system_prompt: "test" },
        }),
      );

      expect(store.agents.has("agent-1")).toBe(true);
      expect(store.agents.get("agent-1")?.status).toBe("active");
    });

    it("marks agent terminated on agent_terminated", async () => {
      await connectClient();
      const store = useAgentsStore();
      store.onAgentSpawned({
        name: "agent-1",
        config: { ...DEFAULT_CONFIG, name: "agent-1" },
      });

      internals(client)._dispatch(
        EventType.AGENT_TERMINATED,
        makeMsg(EventType.AGENT_TERMINATED, { name: "agent-1" }),
      );

      expect(store.agents.get("agent-1")?.status).toBe("terminated");
    });
  });

  describe("room events", () => {
    function makeRoom(roomId: string, overrides: Record<string, unknown> = {}) {
      return {
        room_id: roomId,
        project_id: "p1",
        name: roomId,
        status: "active",
        members: [],
        seq_watermark: 0,
        version: 1,
        created_at: "",
        updated_at: "",
        ...overrides,
      };
    }

    function makeLogEntry(roomId: string, overrides: Record<string, unknown> = {}) {
      return {
        id: `${roomId}-e1`,
        room_id: roomId,
        seq: 1,
        author: "agent-1",
        author_type: "agent",
        timestamp: 1750000000,
        data: { message: "hi" },
        ...overrides,
      };
    }

    it("room_created / room_updated upsert rooms store", async () => {
      await connectClient();
      const store = useRoomsStore();

      internals(client)._dispatch(
        EventType.ROOM_CREATED,
        makeMsg(EventType.ROOM_CREATED, { room: makeRoom("r1") }),
      );
      expect(store.rooms.has("r1")).toBe(true);

      internals(client)._dispatch(
        EventType.ROOM_UPDATED,
        makeMsg(EventType.ROOM_UPDATED, { room: makeRoom("r1", { name: "renamed" }) }),
      );
      expect(store.rooms.get("r1")?.name).toBe("renamed");
    });

    it("room_deleted removes room", async () => {
      await connectClient();
      const store = useRoomsStore();
      store.onRoomCreated({ room: makeRoom("r1") as never });

      internals(client)._dispatch(
        EventType.ROOM_DELETED,
        makeMsg(EventType.ROOM_DELETED, { room_id: "r1", project_id: "p1" }),
      );
      expect(store.rooms.has("r1")).toBe(false);
    });

    it("room_member_joined / room_member_left upsert envelope room", async () => {
      await connectClient();
      const store = useRoomsStore();
      store.onRoomCreated({ room: makeRoom("r1") as never });

      internals(client)._dispatch(
        EventType.ROOM_MEMBER_JOINED,
        makeMsg(EventType.ROOM_MEMBER_JOINED, {
          room: makeRoom("r1", {
            members: [{ subject: "agent-1", subject_type: "agent", joined_at: "" }],
          }),
          member: { subject: "agent-1", subject_type: "agent", joined_at: "" },
        }),
      );
      expect(store.rooms.get("r1")?.members).toHaveLength(1);

      internals(client)._dispatch(
        EventType.ROOM_MEMBER_LEFT,
        makeMsg(EventType.ROOM_MEMBER_LEFT, {
          room: makeRoom("r1", { members: [] }),
          subject: "agent-1",
        }),
      );
      expect(store.rooms.get("r1")?.members).toHaveLength(0);
    });

    it("room_log_appended appends to rooms store and dedups replay", async () => {
      await connectClient();
      const store = useRoomsStore();

      const msg = makeMsg(EventType.ROOM_LOG_APPENDED, { entry: makeLogEntry("r1") });
      internals(client)._dispatch(EventType.ROOM_LOG_APPENDED, msg);
      internals(client)._dispatch(EventType.ROOM_LOG_APPENDED, msg);

      expect(store.logs.get("r1")).toHaveLength(1);
    });

    it("room_log_appended confirms matching human pending in chat store", async () => {
      await connectClient();
      const chatStore = useChatStore();
      chatStore.addPendingEntry({ to: "r1", content: "hello", agentName: "", roomId: "r1" });
      expect(chatStore.allEntries).toHaveLength(1);

      internals(client)._dispatch(
        EventType.ROOM_LOG_APPENDED,
        makeMsg(EventType.ROOM_LOG_APPENDED, {
          entry: makeLogEntry("r1", {
            author: "user",
            author_type: "human",
            data: { message: "hello" },
          }),
        }),
      );

      expect(chatStore.allEntries).toHaveLength(0);
    });

    it("action_chain_updated no longer feeds chat store", async () => {
      await connectClient();
      const chatStore = useChatStore();

      internals(client)._dispatch(
        EventType.ACTION_CHAIN_UPDATED,
        makeMsg(EventType.ACTION_CHAIN_UPDATED, {
          agent_name: "agent-1",
          node: {
            id: "node-1",
            agent_name: "agent-1",
            ability_names: ["conversation"],
            messages_delta: [
              { role: "ai", content_blocks: [{ type: "text", text: "Hello" }], metadata: {} },
            ],
          },
        }),
      );

      expect(chatStore.allEntries).toHaveLength(0);
    });
  });

  describe("project events", () => {
    function makeProject(projectId: string, overrides: Record<string, unknown> = {}) {
      return {
        project_id: projectId,
        name: projectId,
        manifest_ref: "",
        cluster_ids: [],
        workspaces: [],
        agents: [],
        task_ids: [],
        status: "active",
        recovery: "resume",
        version: 1,
        created_at: "",
        updated_at: "",
        ...overrides,
      };
    }

    it("project_created / project_paused upsert projects store", async () => {
      await connectClient();
      const store = useProjectsStore();

      internals(client)._dispatch(
        EventType.PROJECT_CREATED,
        makeMsg(EventType.PROJECT_CREATED, { project: makeProject("p1") }),
      );
      expect(store.projects.has("p1")).toBe(true);

      internals(client)._dispatch(
        EventType.PROJECT_PAUSED,
        makeMsg(EventType.PROJECT_PAUSED, { project: makeProject("p1", { status: "paused" }) }),
      );
      expect(store.projects.get("p1")?.status).toBe("paused");
    });

    it("project_agent_added upserts with agent_name envelope", async () => {
      await connectClient();
      const store = useProjectsStore();
      store.onProjectEvent({ project: makeProject("p1") as never });

      internals(client)._dispatch(
        EventType.PROJECT_AGENT_ADDED,
        makeMsg(EventType.PROJECT_AGENT_ADDED, {
          project: makeProject("p1", {
            agents: [
              {
                name: "agent-1",
                cluster_id: "c1",
                manifest_ref: "",
                instance_manifest_path: "",
                system_prompt: "",
                path_grants: [],
              },
            ],
          }),
          agent_name: "agent-1",
        }),
      );
      expect(store.projects.get("p1")?.agents).toHaveLength(1);
    });

    it("project_deleted removes project", async () => {
      await connectClient();
      const store = useProjectsStore();
      store.onProjectEvent({ project: makeProject("p1") as never });

      internals(client)._dispatch(
        EventType.PROJECT_DELETED,
        makeMsg(EventType.PROJECT_DELETED, { project: makeProject("p1") }),
      );
      expect(store.projects.has("p1")).toBe(false);
    });
  });

  describe("task events", () => {
    function makeTask(taskId: string, overrides: Record<string, unknown> = {}) {
      return {
        task_id: taskId,
        project_id: "p1",
        title: taskId,
        description: "",
        status: "pending",
        priority: "normal",
        dependencies: [],
        created_at: "",
        updated_at: "",
        metadata: {},
        ...overrides,
      };
    }

    it("task_created upserts, task_deleted removes", async () => {
      await connectClient();
      const store = useTasksStore();

      internals(client)._dispatch(
        EventType.TASK_CREATED,
        makeMsg(EventType.TASK_CREATED, { task: makeTask("t1") }),
      );
      expect(store.tasks.has("t1")).toBe(true);

      internals(client)._dispatch(
        EventType.TASK_UPDATED,
        makeMsg(EventType.TASK_UPDATED, {
          task: makeTask("t1", { status: "in_progress" }),
          previous_status: "pending",
        }),
      );
      expect(store.tasks.get("t1")?.status).toBe("in_progress");

      internals(client)._dispatch(
        EventType.TASK_DELETED,
        makeMsg(EventType.TASK_DELETED, { task: makeTask("t1"), reason: "cleanup" }),
      );
      expect(store.tasks.has("t1")).toBe(false);
    });
  });

  describe("hitl events", () => {
    it("adds hitl request on hitl_request", async () => {
      await connectClient();
      const store = useHitlStore();

      internals(client)._dispatch(
        EventType.HITL_REQUEST,
        makeMsg(EventType.HITL_REQUEST, {
          promise_id: "p1",
          agent_name: "agent-1",
          ability_name: "write_file",
          tool_args: { file_path: "/tmp/test.txt" },
          context: {},
        }),
      );

      expect(store.requests).toHaveLength(1);
      expect(store.requests[0].promiseId).toBe("p1");
      expect(store.requests[0].abilityName).toBe("write_file");
    });
  });

  describe("action chain events", () => {
    it("adds chain node on action_chain_updated", async () => {
      await connectClient();
      const store = useActionChainsStore();

      internals(client)._dispatch(
        EventType.ACTION_CHAIN_UPDATED,
        makeMsg(EventType.ACTION_CHAIN_UPDATED, {
          agent_name: "agent-1",
          node: {
            id: "node-1",
            ability_names: ["read_file"],
            action_results: [
              {
                ability_name: "read_file",
                action_result: { outcome: "success", data: { file_path: "/tmp/test.txt" } },
              },
            ],
          },
        }),
      );

      expect(store.getChain("agent-1")).toHaveLength(1);
    });
  });

  describe("changes events (node projection)", () => {
    it("adds file change on action_chain_updated for write_file", async () => {
      await connectClient();
      const store = useChangesStore();

      internals(client)._dispatch(
        EventType.ACTION_CHAIN_UPDATED,
        makeMsg(EventType.ACTION_CHAIN_UPDATED, {
          agent_name: "agent-1",
          node: {
            id: "node-1",
            agent_name: "agent-1",
            action_results: [
              {
                ability_name: "write_file",
                action_result: { outcome: "success", data: { file_path: "/tmp/test.txt" } },
              },
            ],
          },
        }),
      );

      expect(store.changes).toHaveLength(1);
      expect(store.changes[0].filePath).toBe("/tmp/test.txt");
      expect(store.changes[0].abilityName).toBe("write_file");
    });

    it("ignores non-file-change abilities (no entry)", async () => {
      await connectClient();
      const store = useChangesStore();

      internals(client)._dispatch(
        EventType.ACTION_CHAIN_UPDATED,
        makeMsg(EventType.ACTION_CHAIN_UPDATED, {
          agent_name: "agent-1",
          node: {
            id: "node-2",
            agent_name: "agent-1",
            action_results: [
              { ability_name: "read_file", action_result: { outcome: "success", data: {} } },
            ],
          },
        }),
      );

      expect(store.changes).toHaveLength(0);
    });

    it("ABILITY_RESULT no longer feeds changes store (join removed, zero residual)", async () => {
      await connectClient();
      const store = useChangesStore();

      internals(client)._dispatch(
        EventType.ABILITY_RESULT,
        makeMsg(EventType.ABILITY_RESULT, {
          request_id: "r1",
          agent_name: "agent-1",
          ability_name: "write_file",
          success: true,
          result: "OK",
        }),
      );

      expect(store.changes).toHaveLength(0);
    });

    it("reconnect replay dedup: same ACTION_CHAIN_UPDATED node dispatched twice = single entries", async () => {
      await connectClient();
      const chainStore = useActionChainsStore();
      const changesStore = useChangesStore();

      const node = {
        id: "node-r1",
        agent_name: "agent-1",
        ability_names: ["write_file", "conversation"],
        messages_delta: [
          { role: "ai", content_blocks: [{ type: "text", text: "reply" }], metadata: {} },
        ],
        action_results: [
          {
            ability_name: "write_file",
            action_result: { outcome: "success", data: { file_path: "/x" } },
          },
        ],
      };

      internals(client)._dispatch(
        EventType.ACTION_CHAIN_UPDATED,
        makeMsg(EventType.ACTION_CHAIN_UPDATED, { agent_name: "agent-1", node }),
      );
      internals(client)._dispatch(
        EventType.ACTION_CHAIN_UPDATED,
        makeMsg(EventType.ACTION_CHAIN_UPDATED, { agent_name: "agent-1", node }),
      );

      expect(chainStore.getChain("agent-1")).toHaveLength(1);
      expect(changesStore.changes).toHaveLength(1);
    });

    it("reconnect replay dedup: same ROOM_LOG_APPENDED entry dispatched twice = single log entry", async () => {
      await connectClient();
      const roomsStore = useRoomsStore();

      const entry = {
        id: "e1",
        room_id: "r1",
        seq: 1,
        author: "agent-1",
        author_type: "agent",
        timestamp: 1750000000,
        data: { message: "hi" },
      };

      internals(client)._dispatch(
        EventType.ROOM_LOG_APPENDED,
        makeMsg(EventType.ROOM_LOG_APPENDED, { entry }),
      );
      internals(client)._dispatch(
        EventType.ROOM_LOG_APPENDED,
        makeMsg(EventType.ROOM_LOG_APPENDED, { entry }),
      );

      expect(roomsStore.logs.get("r1")).toHaveLength(1);
    });

    it("reconnect replay dedup across multiple agents: chain buckets both deduped", async () => {
      await connectClient();
      const chainStore = useActionChainsStore();

      const nodeA = {
        id: "node-a",
        agent_name: "agent-A",
        ability_names: ["conversation"],
        messages_delta: [
          { role: "ai", content_blocks: [{ type: "text", text: "from-A" }], metadata: {} },
        ],
      };
      const nodeB = {
        id: "node-b",
        agent_name: "agent-B",
        ability_names: ["conversation"],
        messages_delta: [
          { role: "ai", content_blocks: [{ type: "text", text: "from-B" }], metadata: {} },
        ],
      };

      internals(client)._dispatch(
        EventType.ACTION_CHAIN_UPDATED,
        makeMsg(EventType.ACTION_CHAIN_UPDATED, { agent_name: "agent-A", node: nodeA }),
      );
      internals(client)._dispatch(
        EventType.ACTION_CHAIN_UPDATED,
        makeMsg(EventType.ACTION_CHAIN_UPDATED, { agent_name: "agent-B", node: nodeB }),
      );
      // 重连 replay：相同节点再次派发
      internals(client)._dispatch(
        EventType.ACTION_CHAIN_UPDATED,
        makeMsg(EventType.ACTION_CHAIN_UPDATED, { agent_name: "agent-A", node: nodeA }),
      );
      internals(client)._dispatch(
        EventType.ACTION_CHAIN_UPDATED,
        makeMsg(EventType.ACTION_CHAIN_UPDATED, { agent_name: "agent-B", node: nodeB }),
      );

      // chain 分桶：每 agent 1 条
      expect(chainStore.getChain("agent-A")).toHaveLength(1);
      expect(chainStore.getChain("agent-B")).toHaveLength(1);
    });
  });

  describe("command_result routing", () => {
    it("sets agents on list_agents command_result", async () => {
      await connectClient();
      const agentsStore = useAgentsStore();

      internals(client)._dispatch(
        SystemType.COMMAND_RESULT,
        makeMsg(SystemType.COMMAND_RESULT, {
          request_id: "r1",
          success: true,
          original_command: CommandType.LIST_AGENTS,
          data: {
            agents: [
              { name: "agent-1", config: { ...DEFAULT_CONFIG, name: "agent-1" } },
              { name: "agent-2", config: { ...DEFAULT_CONFIG, name: "agent-2" } },
            ],
          },
        }),
      );

      expect(agentsStore.agents.size).toBe(2);
      expect(agentsStore.agents.has("agent-1")).toBe(true);
      expect(agentsStore.agents.has("agent-2")).toBe(true);
    });

    it("F2: list_agents command_result triggers chain history initial sync", async () => {
      await connectClient();
      const chainStore = useActionChainsStore();
      const nodeA = { id: "na", ability_names: ["conversation"] };
      const nodeB = { id: "nb", ability_names: ["send"] };

      const spy = vi.spyOn(client, "getChainHistory").mockImplementation((name: string) => {
        const nodes = name === "agent-1" ? [nodeA] : [nodeB];
        return Promise.resolve({
          request_id: "r",
          success: true,
          original_command: CommandType.GET_CHAIN_HISTORY,
          data: { nodes },
        } as Awaited<ReturnType<typeof client.getChainHistory>>);
      });

      internals(client)._dispatch(
        SystemType.COMMAND_RESULT,
        makeMsg(SystemType.COMMAND_RESULT, {
          request_id: "r1",
          success: true,
          original_command: CommandType.LIST_AGENTS,
          data: {
            agents: [
              { name: "agent-1", config: { ...DEFAULT_CONFIG, name: "agent-1" } },
              { name: "agent-2", config: { ...DEFAULT_CONFIG, name: "agent-2" } },
            ],
          },
        }),
      );

      // fire-and-forget：等待两个 getChainHistory 完成
      await vi.waitFor(() => {
        expect(spy).toHaveBeenCalledWith("agent-1");
        expect(spy).toHaveBeenCalledWith("agent-2");
      });
      expect(chainStore.getChain("agent-1")).toHaveLength(1);
      expect(chainStore.getChain("agent-1")[0].id).toBe("na");
      expect(chainStore.getChain("agent-2")[0].id).toBe("nb");
    });

    it("F2: initial chain sync uses stable agent_id before project list arrives", async () => {
      await connectClient();
      const spy = vi.spyOn(client, "getChainHistory").mockResolvedValue({
        request_id: "r",
        success: true,
        original_command: CommandType.GET_CHAIN_HISTORY,
        data: { nodes: [] },
      } as Awaited<ReturnType<typeof client.getChainHistory>>);

      internals(client)._dispatch(
        SystemType.COMMAND_RESULT,
        makeMsg(SystemType.COMMAND_RESULT, {
          request_id: "r1",
          success: true,
          original_command: CommandType.LIST_AGENTS,
          data: {
            agents: [
              {
                name: "shuoxi",
                agent_id: "stable-shuoxi",
                config: { ...DEFAULT_CONFIG, name: "shuoxi", agent_id: "stable-shuoxi" },
              },
            ],
          },
        }),
      );

      await vi.waitFor(() => {
        expect(spy).toHaveBeenCalledWith(
          "shuoxi",
          undefined,
          undefined,
          "stable-shuoxi",
        );
      });
    });

    it("sets rooms on room_list command_result", async () => {
      await connectClient();
      const roomsStore = useRoomsStore();

      internals(client)._dispatch(
        SystemType.COMMAND_RESULT,
        makeMsg(SystemType.COMMAND_RESULT, {
          request_id: "r1",
          success: true,
          original_command: CommandType.ROOM_LIST,
          data: {
            rooms: [
              {
                room_id: "r1",
                project_id: "p1",
                name: "general",
                status: "active",
                members: [],
                seq_watermark: 0,
                version: 1,
                created_at: "",
                updated_at: "",
              },
            ],
            count: 1,
          },
        }),
      );

      expect(roomsStore.rooms.size).toBe(1);
      expect(roomsStore.rooms.get("r1")?.name).toBe("general");
    });

    it("sets projects on project_list command_result", async () => {
      await connectClient();
      const projectsStore = useProjectsStore();

      internals(client)._dispatch(
        SystemType.COMMAND_RESULT,
        makeMsg(SystemType.COMMAND_RESULT, {
          request_id: "r1",
          success: true,
          original_command: CommandType.PROJECT_LIST,
          data: {
            projects: [
              {
                project_id: "p1",
                name: "proj",
                manifest_ref: "",
                cluster_ids: [],
                workspaces: [],
                agents: [],
                task_ids: [],
                status: "active",
                recovery: "resume",
                version: 1,
                created_at: "",
                updated_at: "",
              },
            ],
            count: 1,
          },
        }),
      );

      expect(projectsStore.projects.size).toBe(1);
      expect(projectsStore.projects.get("p1")?.name).toBe("proj");
    });

    it("sets room log on room_get_log command_result (room_id from entries)", async () => {
      await connectClient();
      const roomsStore = useRoomsStore();

      internals(client)._dispatch(
        SystemType.COMMAND_RESULT,
        makeMsg(SystemType.COMMAND_RESULT, {
          request_id: "r1",
          success: true,
          original_command: CommandType.ROOM_GET_LOG,
          data: {
            entries: [
              {
                id: "e2",
                room_id: "r1",
                seq: 2,
                author: "agent-1",
                author_type: "agent",
                timestamp: 1750000001,
                data: { message: "second" },
              },
              {
                id: "e1",
                room_id: "r1",
                seq: 1,
                author: "user",
                author_type: "human",
                timestamp: 1750000000,
                data: { message: "first" },
              },
            ],
            count: 2,
          },
        }),
      );

      expect(roomsStore.logs.get("r1")?.map((e) => e.seq)).toEqual([1, 2]);
    });

    it("ignores non-agents command_result", async () => {
      await connectClient();
      const agentsStore = useAgentsStore();

      internals(client)._dispatch(
        SystemType.COMMAND_RESULT,
        makeMsg(SystemType.COMMAND_RESULT, {
          request_id: "r1",
          success: true,
          data: { some_other: "value" },
        }),
      );

      expect(agentsStore.agents.size).toBe(0);
    });

    it("ignores failed command_result", async () => {
      await connectClient();
      const agentsStore = useAgentsStore();

      internals(client)._dispatch(
        SystemType.COMMAND_RESULT,
        makeMsg(SystemType.COMMAND_RESULT, {
          request_id: "r1",
          success: false,
          data: { agents: [] },
          error: "some error",
        }),
      );

      expect(agentsStore.agents.size).toBe(0);
    });

    it("does not pollute agents store with manifest_list_agents result", async () => {
      await connectClient();
      const agentsStore = useAgentsStore();

      internals(client)._dispatch(
        SystemType.COMMAND_RESULT,
        makeMsg(SystemType.COMMAND_RESULT, {
          request_id: "r1",
          success: true,
          original_command: CommandType.MANIFEST_LIST_AGENTS,
          data: {
            agents: [
              {
                full_name: "my_project.dev_agent",
                namespace: "my_project",
                name: "dev_agent",
                title: "Dev Agent",
                description: "A dev agent",
                tags: [],
                agent_config_name: "gpt-4o",
                system_prompt: "You are a dev agent.",
                ability_refs: [],
                max_iterations: 10,
              },
            ],
          },
        }),
      );

      expect(agentsStore.agents.size).toBe(0);
    });

    it("ignores command_result without original_command", async () => {
      await connectClient();
      const agentsStore = useAgentsStore();

      internals(client)._dispatch(
        SystemType.COMMAND_RESULT,
        makeMsg(SystemType.COMMAND_RESULT, {
          request_id: "r1",
          success: true,
          data: {
            agents: [{ name: "agent-1", config: { ...DEFAULT_CONFIG, name: "agent-1" } }],
          },
        }),
      );

      expect(agentsStore.agents.size).toBe(0);
    });
  });

  describe("disconnect", () => {
    it("disconnect function stops event routing", async () => {
      await connectClient();
      const roomsStore = useRoomsStore();

      disconnect();

      internals(client)._dispatch(
        EventType.ROOM_LOG_APPENDED,
        makeMsg(EventType.ROOM_LOG_APPENDED, {
          entry: {
            id: "e1",
            room_id: "r1",
            seq: 1,
            author: "agent-1",
            author_type: "agent",
            timestamp: 1750000000,
            data: { message: "hi" },
          },
        }),
      );

      expect(roomsStore.logs.size).toBe(0);
    });
  });

  describe("manifest agent sync on connect", () => {
    function mockSyncMethods(c: ObserverClient) {
      vi.spyOn(c, "listAgents").mockResolvedValue({
        request_id: "r0",
        success: true,
        data: { agents: [] },
      } satisfies CommandResultPayload);
      const listManifestSpy = vi.spyOn(c, "listManifestAgents").mockResolvedValue({
        request_id: "r1",
        success: true,
        data: { agents: [] },
      } satisfies CommandResultPayload);
      const listProjectsSpy = vi.spyOn(c, "listProjects").mockResolvedValue({
        request_id: "r2",
        success: true,
        data: { projects: [] },
      } satisfies CommandResultPayload);
      const listRoomsSpy = vi.spyOn(c, "listRooms").mockResolvedValue({
        request_id: "r3",
        success: true,
        data: { rooms: [] },
      } satisfies CommandResultPayload);
      return { listManifestSpy, listProjectsSpy, listRoomsSpy };
    }

    it("runs _syncInitialState (listManifestAgents + listProjects + listRooms) on connect", async () => {
      const { listManifestSpy, listProjectsSpy, listRoomsSpy } = mockSyncMethods(client);

      await connectClient({ skipSync: false });

      // _syncInitialState is the real sync path (not the onConnected callback,
      // which only sets connection state).
      expect(listManifestSpy).toHaveBeenCalled();
      expect(listProjectsSpy).toHaveBeenCalled();
      expect(listRoomsSpy).toHaveBeenCalled();
    });

    it("handles listManifestAgents failure gracefully", async () => {
      // 走真实 _syncInitialState 吞错路径（skipSync:false），listManifestAgents 的
      // mockRejectedValue 实际触发并被 try/catch 吞掉，connect 仍成功、store 为空。
      const { listProjectsSpy, listRoomsSpy } = mockSyncMethods(client);
      vi.spyOn(client, "listManifestAgents").mockRejectedValue(new Error("connection failed"));

      await connectClient({ skipSync: false });

      // 后续同步项不受前项失败影响
      expect(listProjectsSpy).toHaveBeenCalled();
      expect(listRoomsSpy).toHaveBeenCalled();
      const manifestsStore = useManifestsStore();
      expect(manifestsStore.agents.size).toBe(0);
    });
  });

  // ── 性能红线 4：高频事件合帧分发 ──
  describe("high-frequency frame batching", () => {
    function makeManualBatcher(): { batcher: FrameBatcher; drain: () => void } {
      const pending: Array<() => void> = [];
      const batcher = createFrameBatcher((flush) => {
        pending.push(flush);
      });
      return {
        batcher,
        drain: () => {
          const fns = pending.splice(0, pending.length);
          for (const fn of fns) fn();
        },
      };
    }

    it("coalesces a burst of room_log_appended into one flush (order preserved)", async () => {
      const manual = makeManualBatcher();
      await connectClient({ batcher: manual.batcher });
      const roomsStore = useRoomsStore();
      roomsStore.setRoomsFromList([
        {
          room_id: "r1",
          project_id: "p1",
          name: "arch",
          members: [],
        } as never,
      ]);

      for (let i = 1; i <= 20; i++) {
        internals(client)._dispatch(
          EventType.ROOM_LOG_APPENDED,
          makeMsg(EventType.ROOM_LOG_APPENDED, {
            entry: {
              id: `e${i}`,
              room_id: "r1",
              seq: i,
              author: "agent-1",
              author_type: "agent",
              timestamp: 1750000000 + i,
              data: { message: `m${i}` },
            },
          }),
        );
      }
      // 未 flush 前 store 不更新（合帧：一条不漏但只渲染一帧）
      expect(roomsStore.logs.get("r1")).toBeUndefined();

      manual.drain();

      const log = roomsStore.logs.get("r1") ?? [];
      expect(log).toHaveLength(20);
      // FIFO 顺序保持（seq 递增）
      expect(log.map((e) => e.seq)).toEqual(Array.from({ length: 20 }, (_, i) => i + 1));
    });

    it("coalesces action_chain_updated bursts per frame", async () => {
      const manual = makeManualBatcher();
      await connectClient({ batcher: manual.batcher });
      const chainsStore = useActionChainsStore();

      for (let i = 0; i < 10; i++) {
        internals(client)._dispatch(
          EventType.ACTION_CHAIN_UPDATED,
          makeMsg(EventType.ACTION_CHAIN_UPDATED, {
            agent_name: "agent-1",
            node: { id: `n${i}`, parent_id: null, timestamp: `2026-08-25T00:00:${i}Z` },
          }),
        );
      }
      expect(chainsStore.getChain("agent-1")).toHaveLength(0);
      manual.drain();
      expect(chainsStore.getChain("agent-1")).toHaveLength(10);
    });

    it("unbind cancels pending batched events (no store writes after disconnect)", async () => {
      const manual = makeManualBatcher();
      await connectClient({ batcher: manual.batcher });
      const roomsStore = useRoomsStore();

      internals(client)._dispatch(
        EventType.ROOM_LOG_APPENDED,
        makeMsg(EventType.ROOM_LOG_APPENDED, {
          entry: {
            id: "e1",
            room_id: "r1",
            seq: 1,
            author: "a",
            author_type: "agent",
            timestamp: 1750000000,
            data: {},
          },
        }),
      );
      disconnect();
      manual.drain();
      expect(roomsStore.logs.size).toBe(0);
    });

    it("setRoomLog union-merges with entries already landed this frame", () => {
      const roomsStore = useRoomsStore();
      roomsStore.setRoomLog("r1", [
        {
          id: "e6",
          room_id: "r1",
          seq: 6,
          author: "a",
          author_type: "agent",
          timestamp: 6,
          data: {},
        },
      ]);
      // get_log 回执只覆盖 1-5：并集保留已见 6
      roomsStore.setRoomLog("r1", [
        {
          id: "e1",
          room_id: "r1",
          seq: 1,
          author: "a",
          author_type: "agent",
          timestamp: 1,
          data: {},
        },
      ]);
      const log = roomsStore.logs.get("r1") ?? [];
      expect(log.map((e) => e.seq)).toEqual([1, 6]);
    });
  });
});
