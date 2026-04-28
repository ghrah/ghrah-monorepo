import type { GatewayMessage } from "@ghrah/protocol";
import { EventType, SystemType, type WebSocketLike } from "@ghrah/protocol";
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

const WS_OPEN = 1;

interface MockWebSocket extends WebSocketLike {
  sent: string[];
}

interface ClientInternals {
  _dispatch: (msgType: string, message: GatewayMessage) => void;
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
  extra?: Partial<GatewayMessage>,
): GatewayMessage {
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
  gateway_url: null,
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
    if (disconnect) disconnect();
    if (client.connected) {
      client.disconnect();
    }
  });

  async function connectClient() {
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

  describe("chat events", () => {
    it("adds message on agent_response", async () => {
      await connectClient();
      const store = useChatStore();

      internals(client)._dispatch(
        EventType.AGENT_RESPONSE,
        makeMsg(EventType.AGENT_RESPONSE, {
          sender: "agent-1",
          recipient: "user",
          content: "Hello",
          message_type: "result",
          metadata: {},
        }),
      );

      expect(store.getMessages("agent-1")).toHaveLength(1);
      expect(store.getMessages("agent-1")[0].content).toBe("Hello");
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
            ability_name: "read_file",
            tool_args: { file_path: "/tmp/test.txt" },
            request_id: "r1",
          },
        }),
      );

      expect(store.getChain("agent-1")).toHaveLength(1);
    });
  });

  describe("changes events", () => {
    it("adds file change on ability_result for write_file with tool_args", async () => {
      await connectClient();
      const store = useChangesStore();

      internals(client)._dispatch(
        EventType.ACTION_CHAIN_UPDATED,
        makeMsg(EventType.ACTION_CHAIN_UPDATED, {
          agent_name: "agent-1",
          node: {
            ability_name: "write_file",
            tool_args: { file_path: "/tmp/test.txt" },
            request_id: "r1",
          },
        }),
      );
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

      expect(store.changes).toHaveLength(1);
      expect(store.changes[0].filePath).toBe("/tmp/test.txt");
    });

    it("ignores non-file-change ability_results", async () => {
      await connectClient();
      const store = useChangesStore();

      internals(client)._dispatch(
        EventType.ABILITY_RESULT,
        makeMsg(EventType.ABILITY_RESULT, {
          request_id: "r1",
          agent_name: "agent-1",
          ability_name: "read_file",
          success: true,
          result: "Content",
        }),
      );

      expect(store.changes).toHaveLength(0);
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
  });

  describe("disconnect", () => {
    it("disconnect function stops event routing", async () => {
      await connectClient();
      const chatStore = useChatStore();

      disconnect();

      internals(client)._dispatch(
        EventType.AGENT_RESPONSE,
        makeMsg(EventType.AGENT_RESPONSE, {
          sender: "agent-1",
          recipient: "user",
          content: "Hello",
          message_type: "result",
          metadata: {},
        }),
      );

      expect(chatStore.getMessages("agent-1")).toHaveLength(0);
    });
  });
});
