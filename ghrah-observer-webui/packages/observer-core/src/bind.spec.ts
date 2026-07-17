import type { CommandResultPayload, ServerMessage } from "@ghrah/protocol";
import { CommandType, EventType, SystemType, type WebSocketLike } from "@ghrah/protocol";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { connectStores } from "./bind.js";
import { ObserverClient } from "./client.js";
import { useActionChainsStore } from "./stores/action-chains.js";
import { useAgentsStore } from "./stores/agents.js";
import { useChangesStore } from "./stores/changes.js";
import { useChatStore } from "./stores/chat.js";
import { useConnectionStore } from "./stores/connection.js";
import { useHitlStore } from "./stores/hitl.js";
import { useManifestsStore } from "./stores/manifests.js";

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

  async function connectClient(opts: { skipSync?: boolean } = {}) {
    const { skipSync = true } = opts;
    if (skipSync) {
      skipSyncInitialState = vi
        .spyOn(client as any, "_syncInitialState")
        .mockResolvedValue(undefined);
    }
    disconnect = connectStores(client);
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
      disconnect = connectStores(client);
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

  describe("chat events (projection-driven from action_chain_updated)", () => {
    it("projects conversation entry from action_chain_updated", async () => {
      await connectClient();
      const store = useChatStore();

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

      const entries = store.getEntries("agent-1");
      expect(entries).toHaveLength(1);
      expect(entries[0].content).toBe("Hello");
      expect(entries[0].kind).toBe("conversation");
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
      const chatStore = useChatStore();
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
      expect(chatStore.getEntries("agent-1")).toHaveLength(1);
      expect(changesStore.changes).toHaveLength(1);
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
      const chatStore = useChatStore();

      disconnect();

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

      expect(chatStore.getEntries("agent-1")).toHaveLength(0);
    });
  });

  describe("manifest agent sync on connect", () => {
    it("runs _syncInitialState (listManifestAgents) on connect", async () => {
      vi.spyOn(client, "listAgents").mockResolvedValue({
        request_id: "r0",
        success: true,
        data: { agents: [] },
      } satisfies CommandResultPayload);
      const listManifestSpy = vi.spyOn(client, "listManifestAgents").mockResolvedValue({
        request_id: "r1",
        success: true,
        data: { agents: [] },
      } satisfies CommandResultPayload);

      await connectClient({ skipSync: false });

      // _syncInitialState is the real sync path (not the onConnected callback,
      // which only sets connection state). listManifestAgents is invoked by it.
      expect(listManifestSpy).toHaveBeenCalled();
      listManifestSpy.mockRestore();
    });

    it("handles listManifestAgents failure gracefully", async () => {
      // 走真实 _syncInitialState 吞错路径（skipSync:false），listManifestAgents 的
      // mockRejectedValue 实际触发并被 try/catch 吞掉，connect 仍成功、store 为空。
      vi.spyOn(client, "listAgents").mockResolvedValue({
        request_id: "r0",
        success: true,
        data: { agents: [] },
      } satisfies CommandResultPayload);
      vi.spyOn(client, "listManifestAgents").mockRejectedValue(new Error("connection failed"));

      await connectClient({ skipSync: false });

      const manifestsStore = useManifestsStore();
      expect(manifestsStore.agents.size).toBe(0);
    });
  });
});
