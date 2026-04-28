import { afterEach, describe, expect, it } from "vitest";
import WebSocket from "ws";
import { createCommand, createPing } from "./builders.js";
import { GatewayClient } from "./client.js";
import { CommandType, SystemType } from "./enums.js";
import type { GatewayMessage } from "./message.js";

const GW_URL = process.env.GATEWAY_URL ?? "ws://localhost:8080/ws";
const RUN_INTEGRATION = process.env.RUN_INTEGRATION === "1";

describe.skipIf(!RUN_INTEGRATION)("GatewayClient Integration", () => {
  let client: GatewayClient;

  afterEach(async () => {
    if (client?.connected) {
      await client.disconnect();
    }
  });

  it("connects and receives welcome command_result", async () => {
    client = new GatewayClient(GW_URL, "observer", {
      wsFactory: (url: string) =>
        new WebSocket(url) as unknown as import("./client.js").WebSocketLike,
    });

    const welcomePromise = new Promise<GatewayMessage>((resolve) => {
      client.on(SystemType.COMMAND_RESULT, (msg) => {
        if (msg.payload && (msg.payload as Record<string, unknown>).session_id) {
          resolve(msg);
        }
      });
    });

    await client.connect();
    const welcome = await welcomePromise;

    expect(welcome.type).toBe(SystemType.COMMAND_RESULT);
    expect((welcome.payload as Record<string, unknown>).success).toBe(true);
  }, 10_000);

  it("ping/pong round-trip", async () => {
    client = new GatewayClient(GW_URL, "observer", {
      wsFactory: (url: string) =>
        new WebSocket(url) as unknown as import("./client.js").WebSocketLike,
    });

    await client.connect();

    const pongPromise = new Promise<GatewayMessage>((resolve) => {
      client.on(SystemType.PONG, resolve);
    });

    await client.send(createPing());
    const pong = await pongPromise;

    expect(pong.type).toBe(SystemType.PONG);
  }, 10_000);

  it("subscribe and receive command_result response", async () => {
    client = new GatewayClient(GW_URL, "observer", {
      wsFactory: (url: string) =>
        new WebSocket(url) as unknown as import("./client.js").WebSocketLike,
    });

    await client.connect();

    const subscribeMsg = createCommand(CommandType.SUBSCRIBE, {
      agent_names: ["*"],
    });

    const result = await client.request(subscribeMsg, 5000);

    expect(result.success).toBe(true);
    expect(result.request_id).toBeDefined();
  }, 10_000);

  it("list_agents returns command_result (may fail without subject)", async () => {
    client = new GatewayClient(GW_URL, "observer", {
      wsFactory: (url: string) =>
        new WebSocket(url) as unknown as import("./client.js").WebSocketLike,
    });

    await client.connect();

    const listMsg = createCommand(CommandType.LIST_AGENTS, {});

    const result = await client.request(listMsg, 5000);

    expect(result.request_id).toBeDefined();
  }, 10_000);
});
