import type { AbilityDefinitionPayload } from "@ghrah/protocol";
import { ClientType, CommandType, type WebSocketLike } from "@ghrah/protocol";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ObserverClient } from "./client.js";

const WS_OPEN = 1;

interface MockWebSocket extends WebSocketLike {
  sent: string[];
}

function createMockWs(): MockWebSocket {
  const ws: MockWebSocket = {
    readyState: WS_OPEN,
    sent: [],
    onopen: null,
    onmessage: null,
    onclose: null,
    onerror: null,
    send(data: string) {
      ws.sent.push(data);
    },
    close() {},
  };
  return ws;
}

function createClient(mockWs: MockWebSocket): ObserverClient {
  return new ObserverClient("ws://localhost:4111/ws", "observer", {
    wsFactory: () => mockWs,
  });
}

async function connectClient(client: ObserverClient, mockWs: MockWebSocket): Promise<void> {
  const connectPromise = client.connect();
  mockWs.onopen!();
  await connectPromise;
}

describe("ObserverClient", () => {
  let client: ObserverClient;
  let mockWs: MockWebSocket;

  beforeEach(() => {
    vi.useFakeTimers();
    mockWs = createMockWs();
    client = createClient(mockWs);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    if (client.connected) {
      client.disconnect();
    }
  });

  describe("subscribe", () => {
    it("sends subscribe command with correct payload", async () => {
      await connectClient(client, mockWs);
      mockWs.sent.length = 0;

      await client.subscribe(["agent-1", "agent-2"], ["agent_response"]);

      const parsed = JSON.parse(mockWs.sent[0]);
      expect(parsed.type).toBe(CommandType.SUBSCRIBE);
      expect(parsed.payload.agent_names).toEqual(["agent-1", "agent-2"]);
      expect(parsed.payload.event_types).toEqual(["agent_response"]);
    });

    it("sends subscribe with null agentNames to subscribe all", async () => {
      await connectClient(client, mockWs);
      mockWs.sent.length = 0;

      await client.subscribe(null, null);

      const parsed = JSON.parse(mockWs.sent[0]);
      expect(parsed.type).toBe(CommandType.SUBSCRIBE);
      expect(parsed.payload.agent_names).toBeUndefined();
      expect(parsed.payload.event_types).toBeUndefined();
    });
  });

  describe("unsubscribe", () => {
    it("sends unsubscribe command with correct payload", async () => {
      await connectClient(client, mockWs);
      mockWs.sent.length = 0;

      await client.unsubscribe(["agent-1"], ["agent_response"]);

      const parsed = JSON.parse(mockWs.sent[0]);
      expect(parsed.type).toBe(CommandType.UNSUBSCRIBE);
      expect(parsed.payload.agent_names).toEqual(["agent-1"]);
    });
  });

  describe("spawnAgent", () => {
    it("sends spawn_agent with config and abilities", async () => {
      await connectClient(client, mockWs);
      const ab: AbilityDefinitionPayload = { ability_type: "read_file", params: {} };
      const spawnPromise = client.spawnAgent(
        {
          name: "test-agent",
          description: "",
          system_prompt: "You are helpful",
          max_iterations: 10,
        },
        [ab],
      );

      const parsed = JSON.parse(mockWs.sent[0]);
      expect(parsed.type).toBe(CommandType.SPAWN_AGENT);
      expect(parsed.payload.config.name).toBe("test-agent");
      expect(parsed.payload.abilities).toHaveLength(1);

      mockWs.onmessage!({
        data: JSON.stringify({
          type: "command_result",
          payload: { request_id: parsed.request_id, success: true, data: {} },
          request_id: parsed.request_id,
        }),
      });

      const result = await spawnPromise;
      expect(result.success).toBe(true);
    });
  });

  describe("sendMessage", () => {
    it("builds correct send_message payload", async () => {
      await connectClient(client, mockWs);
      const msgPromise = client.sendMessage("agent-1", "Hello", "user");

      const parsed = JSON.parse(mockWs.sent[0]);
      expect(parsed.type).toBe(CommandType.SEND_MESSAGE);
      expect(parsed.payload.target).toBe("agent-1");
      expect(parsed.payload.content).toBe("Hello");
      expect(parsed.payload.sender).toBe("user");

      mockWs.onmessage!({
        data: JSON.stringify({
          type: "command_result",
          payload: { request_id: parsed.request_id, success: true, data: {} },
          request_id: parsed.request_id,
        }),
      });

      await expect(msgPromise).resolves.toBeDefined();
    });
  });

  describe("sendHitlResponse", () => {
    it("sends hitl_response without waiting for result", async () => {
      await connectClient(client, mockWs);
      mockWs.sent.length = 0;

      const response = client.sendHitlResponse("p1", true, "approved");
      // It should not reject - fire and forget
      await expect(response).resolves.toBeUndefined();

      const parsed = JSON.parse(mockWs.sent[0]);
      expect(parsed.type).toBe(CommandType.HITL_RESPONSE);
      expect(parsed.payload.promise_id).toBe("p1");
      expect(parsed.payload.approved).toBe(true);
      expect(parsed.payload.reason).toBe("approved");
    });
  });

  describe("listAgents", () => {
    it("sends list_agents command", async () => {
      await connectClient(client, mockWs);
      const listPromise = client.listAgents();

      const parsed = JSON.parse(mockWs.sent[0]);
      expect(parsed.type).toBe(CommandType.LIST_AGENTS);
      expect(parsed.client_type).toBe(ClientType.OBSERVER);

      mockWs.onmessage!({
        data: JSON.stringify({
          type: "command_result",
          payload: { request_id: parsed.request_id, success: true, data: { agents: [] } },
          request_id: parsed.request_id,
        }),
      });

      await expect(listPromise).resolves.toBeDefined();
    });
  });

  describe("persist methods", () => {
    it("persistSaveNode sends persist_save_node command", async () => {
      await connectClient(client, mockWs);
      const savePromise = client.persistSaveNode("config", { apiKey: "test" });

      const parsed = JSON.parse(mockWs.sent[0]);
      expect(parsed.type).toBe(CommandType.PERSIST_SAVE_NODE);
      expect(parsed.payload.key).toBe("config");
      expect(parsed.payload.data).toEqual({ apiKey: "test" });
      expect(parsed.payload.namespace).toBe("default");

      mockWs.onmessage!({
        data: JSON.stringify({
          type: "command_result",
          payload: { request_id: parsed.request_id, success: true, data: {} },
          request_id: parsed.request_id,
        }),
      });

      await expect(savePromise).resolves.toBeDefined();
    });

    it("persistLoadNode sends persist_load_node command", async () => {
      await connectClient(client, mockWs);
      const loadPromise = client.persistLoadNode("config", "custom_ns");

      const parsed = JSON.parse(mockWs.sent[0]);
      expect(parsed.type).toBe(CommandType.PERSIST_LOAD_NODE);
      expect(parsed.payload.key).toBe("config");
      expect(parsed.payload.namespace).toBe("custom_ns");

      mockWs.onmessage!({
        data: JSON.stringify({
          type: "command_result",
          payload: { request_id: parsed.request_id, success: true, data: {} },
          request_id: parsed.request_id,
        }),
      });

      await expect(loadPromise).resolves.toBeDefined();
    });
  });

  describe("registerAbility", () => {
    it("sends register_ability command", async () => {
      await connectClient(client, mockWs);
      const ability: AbilityDefinitionPayload = { ability_type: "write_file", params: {} };
      const regPromise = client.registerAbility("agent-1", ability);

      const parsed = JSON.parse(mockWs.sent[0]);
      expect(parsed.type).toBe(CommandType.REGISTER_ABILITY);
      expect(parsed.payload.agent_name).toBe("agent-1");
      expect(parsed.payload.ability.ability_type).toBe("write_file");

      mockWs.onmessage!({
        data: JSON.stringify({
          type: "command_result",
          payload: { request_id: parsed.request_id, success: true, data: {} },
          request_id: parsed.request_id,
        }),
      });

      await expect(regPromise).resolves.toBeDefined();
    });
  });

  describe("delegate", () => {
    it("sends delegate command", async () => {
      await connectClient(client, mockWs);
      const delPromise = client.delegate("agent-1", "agent-2", "Review this");

      const parsed = JSON.parse(mockWs.sent[0]);
      expect(parsed.type).toBe(CommandType.DELEGATE);
      expect(parsed.payload.from_agent).toBe("agent-1");
      expect(parsed.payload.to_agent).toBe("agent-2");
      expect(parsed.payload.content).toBe("Review this");

      mockWs.onmessage!({
        data: JSON.stringify({
          type: "command_result",
          payload: { request_id: parsed.request_id, success: true, data: {} },
          request_id: parsed.request_id,
        }),
      });

      await expect(delPromise).resolves.toBeDefined();
    });
  });

  describe("workspace methods", () => {
    it("createWorkspace sends create_workspace command", async () => {
      await connectClient(client, mockWs);
      const wpPromise = client.createWorkspace("agent-1");

      const parsed = JSON.parse(mockWs.sent[0]);
      expect(parsed.type).toBe(CommandType.CREATE_WORKSPACE);
      expect(parsed.payload.agent_name).toBe("agent-1");

      mockWs.onmessage!({
        data: JSON.stringify({
          type: "command_result",
          payload: { request_id: parsed.request_id, success: true, data: {} },
          request_id: parsed.request_id,
        }),
      });

      await expect(wpPromise).resolves.toBeDefined();
    });
  });
});
