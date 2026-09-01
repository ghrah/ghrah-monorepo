import type { AddressInfo } from "node:net";
import {
  CommandType,
  createCommandResult,
  createError,
  createEvent,
  createPong,
  type EventType,
  parseMessage,
  type ServerMessage,
  type SubscribePayload,
  SubscribePayloadSchema,
  SystemType,
  serializeMessage,
} from "@ghrah/protocol";
import { type WebSocket, WebSocketServer } from "ws";
import { MockState } from "./state.js";

export interface MockServerOptions {
  /** 监听端口；0 = 随机端口（测试用）。 */
  port: number;
  /** 监听路径，默认 /ws（对齐前端默认 URL ws://localhost:4112/ws 的路径约定）。 */
  path?: string;
  host?: string;
  /** 事件 ring buffer 容量，供重连 last_seq_id 回放。默认 1000。 */
  replayBufferSize?: number;
  /** 外部注入的 state（默认内部新建）。 */
  state?: MockState;
  logger?: (line: string) => void;
}

interface ConnectionContext {
  socket: WebSocket;
  clientType: string;
  clientId: string;
  subscriptions: SubscribePayload[];
}

interface BufferedEvent {
  seqId: number;
  raw: string;
}

/**
 * WS 协议层 mock server：@ghrah/protocol 的 ServerClient/ObserverClient 的对端。
 * - 入站 parseMessage → 命令路由到 MockState → COMMAND_RESULT 回执（回带 request_id）
 * - 收 PING 回 PONG（client 侧 30s 周期 PING；server 不主动发 PING）
 * - 下行事件带单调 seq_id + ring buffer，供重连 last_seq_id 增量回放
 * - 订阅语义：**未订阅 = 全发**（protocol 未定义默认语义，取宽容策略）；
 *   订阅后按 agent_names / event_types 过滤（"*" 通配）
 */
export class MockServer {
  readonly state: MockState;

  private readonly _options: Required<Omit<MockServerOptions, "state" | "host" | "logger">> & {
    host?: string;
    logger?: (line: string) => void;
  };
  private _wss: WebSocketServer | null = null;
  private readonly _connections = new Set<ConnectionContext>();
  private _seqId = 0;
  private readonly _ring: BufferedEvent[] = [];

  constructor(options: MockServerOptions) {
    this._options = {
      port: options.port,
      path: options.path ?? "/ws",
      replayBufferSize: options.replayBufferSize ?? 1000,
      host: options.host,
      logger: options.logger,
    };
    this.state = options.state ?? new MockState();
    this.state.emit = (eventType, payload) => this.broadcastEvent(eventType, payload);
  }

  /** 当前已分配的最大事件 seq_id。 */
  get lastSeqId(): number {
    return this._seqId;
  }

  get connectionCount(): number {
    return this._connections.size;
  }

  /** 实际监听端口（port=0 时启动后可用）。 */
  get port(): number {
    const addr = this._wss?.address();
    return typeof addr === "object" && addr !== null ? (addr as AddressInfo).port : 0;
  }

  start(): Promise<void> {
    return new Promise((resolve, reject) => {
      const wss = new WebSocketServer({
        port: this._options.port,
        path: this._options.path,
        host: this._options.host,
      });
      this._wss = wss;
      wss.on("listening", () => {
        this._log(
          `mock-server listening on ws://${this._options.host ?? "localhost"}:${this.port}${this._options.path}`,
        );
        resolve();
      });
      wss.on("error", reject);
      wss.on("connection", (socket, request) => this._onConnection(socket, request.url ?? ""));
    });
  }

  async close(): Promise<void> {
    this.state.dispose();
    for (const conn of this._connections) {
      try {
        conn.socket.terminate();
      } catch {
        // ignore
      }
    }
    this._connections.clear();
    const wss = this._wss;
    this._wss = null;
    if (wss) {
      await new Promise<void>((resolve) => wss.close(() => resolve()));
    }
  }

  /** 分配单调 seq_id、写 ring buffer、按订阅过滤广播事件。 */
  broadcastEvent(eventType: EventType, payload: Record<string, unknown>): void {
    this._seqId += 1;
    const message: ServerMessage = { ...createEvent(eventType, payload), seq_id: this._seqId };
    const raw = serializeMessage(message);
    this._ring.push({ seqId: this._seqId, raw });
    if (this._ring.length > this._options.replayBufferSize) {
      this._ring.splice(0, this._ring.length - this._options.replayBufferSize);
    }
    for (const conn of this._connections) {
      if (conn.socket.readyState !== conn.socket.OPEN) continue;
      if (!this._matchesSubscription(conn, eventType, payload)) continue;
      conn.socket.send(raw);
    }
  }

  private _onConnection(socket: WebSocket, rawUrl: string): void {
    const query = new URL(rawUrl, "http://localhost").searchParams;
    const conn: ConnectionContext = {
      socket,
      clientType: query.get("client_type") ?? "unknown",
      clientId: query.get("client_id") ?? "unknown",
      subscriptions: [],
    };
    this._connections.add(conn);
    this._log(`client connected: ${conn.clientId} (${conn.clientType})`);

    socket.on("message", (data) => this._onMessage(conn, data.toString()));
    socket.on("close", () => {
      this._connections.delete(conn);
      this._log(`client disconnected: ${conn.clientId}`);
    });
    socket.on("error", () => {
      this._connections.delete(conn);
    });

    // 重连 resume：回放 ring buffer 内 > last_seq_id 的事件（不重复）
    const lastSeqId = Number(query.get("last_seq_id") ?? "0");
    if (Number.isFinite(lastSeqId) && lastSeqId > 0) {
      for (const entry of this._ring) {
        if (entry.seqId > lastSeqId) socket.send(entry.raw);
      }
      this._log(`resumed ${conn.clientId} from seq_id=${lastSeqId}`);
    }
  }

  private _onMessage(conn: ConnectionContext, raw: string): void {
    let message: ServerMessage;
    try {
      message = parseMessage(raw);
    } catch {
      this._send(conn, createError("bad_message", "failed to parse inbound message"));
      return;
    }

    switch (message.type) {
      case SystemType.PING:
        this._send(conn, createPong());
        return;
      case SystemType.PONG:
        return;
      case CommandType.SUBSCRIBE: {
        const parsed = SubscribePayloadSchema.safeParse(message.payload);
        if (!parsed.success) {
          this._sendResult(conn, message, false, null, "invalid subscribe payload");
          return;
        }
        conn.subscriptions.push(parsed.data);
        this._sendResult(conn, message, true, { subscribed: true });
        return;
      }
      case CommandType.UNSUBSCRIBE: {
        const parsed = SubscribePayloadSchema.safeParse(message.payload);
        if (!parsed.success) {
          this._sendResult(conn, message, false, null, "invalid unsubscribe payload");
          return;
        }
        conn.subscriptions = conn.subscriptions.filter((s) => !subscriptionEquals(s, parsed.data));
        this._sendResult(conn, message, true, { unsubscribed: true });
        return;
      }
      default: {
        const outcome = this.state.handleCommand(message.type, message.payload);
        this._sendResult(conn, message, outcome.success, outcome.data, outcome.error);
      }
    }
  }

  private _sendResult(
    conn: ConnectionContext,
    request: ServerMessage,
    success: boolean,
    data?: unknown,
    error?: string,
  ): void {
    this._send(conn, createCommandResult(request.request_id ?? "", success, data, error));
  }

  private _send(conn: ConnectionContext, message: ServerMessage): void {
    if (conn.socket.readyState === conn.socket.OPEN) {
      conn.socket.send(serializeMessage(message));
    }
  }

  /**
   * 订阅过滤：未订阅 = 全发；有订阅时任一订阅命中即放行。
   * event_types 空/null = 全部事件类型；agent_names 空/null = 全部 agent；"*" 通配。
   * 事件 agent 身份提取顺序：payload.agent_name → payload.name → payload.sender → payload.entry.author。
   */
  private _matchesSubscription(
    conn: ConnectionContext,
    eventType: string,
    payload: Record<string, unknown>,
  ): boolean {
    if (conn.subscriptions.length === 0) return true;
    const agentName = extractAgentName(payload);
    return conn.subscriptions.some((sub) => {
      const types = sub.event_types;
      const typeMatch =
        types == null || types.length === 0 || types.includes("*") || types.includes(eventType);
      if (!typeMatch) return false;
      const names = sub.agent_names;
      if (names == null || names.length === 0 || names.includes("*")) return true;
      return agentName != null && names.includes(agentName);
    });
  }

  private _log(line: string): void {
    this._options.logger?.(line);
  }
}

function extractAgentName(payload: Record<string, unknown>): string | null {
  for (const key of ["agent_name", "name", "sender"] as const) {
    const value = payload[key];
    if (typeof value === "string" && value) return value;
  }
  const entry = payload.entry;
  if (entry && typeof entry === "object") {
    const author = (entry as Record<string, unknown>).author;
    if (typeof author === "string" && author) return author;
  }
  return null;
}

function subscriptionEquals(a: SubscribePayload, b: SubscribePayload): boolean {
  return arrayEquals(a.agent_names, b.agent_names) && arrayEquals(a.event_types, b.event_types);
}

function arrayEquals(a: string[] | null | undefined, b: string[] | null | undefined): boolean {
  const normA = a == null ? null : [...a].sort().join("");
  const normB = b == null ? null : [...b].sort().join("");
  return normA === normB;
}
