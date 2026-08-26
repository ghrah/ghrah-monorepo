import {
  type AbilityDefinitionPayload,
  type ActionNode,
  type AgentConfigPayload,
  CommandType,
  EventType,
  type HITLRequestPayload,
  HITLResponsePayloadSchema,
  ProjectCreatePayloadSchema,
  ProjectIdPayloadSchema,
  type ProjectInfoPayload,
  ProjectListPayloadSchema,
  RoomCreatePayloadSchema,
  RoomDeletePayloadSchema,
  RoomGetLogPayloadSchema,
  RoomIdPayloadSchema,
  type RoomInfoPayload,
  RoomJoinPayloadSchema,
  RoomLeavePayloadSchema,
  RoomListPayloadSchema,
  type RoomLogEntryPayload,
  type RoomMember,
  RoomSendPayloadSchema,
  RoomUpdatePayloadSchema,
  SpawnAgentPayloadSchema,
  TaskCreatePayloadSchema,
  TaskIdPayloadSchema,
  type TaskInfoPayload,
  TaskListPayloadSchema,
  TerminateAgentPayloadSchema,
} from "@ghrah/protocol";
import { ZodError, type z } from "zod";

export interface CommandOutcome {
  success: boolean;
  data?: unknown;
  error?: string;
}

export type EmitFn = (eventType: EventType, payload: Record<string, unknown>) => void;

export interface MockStateOptions {
  /** HITL 审批超时（ms），超时自动拒绝。默认 30s。 */
  hitlTimeoutMs?: number;
  /** spawn_agent 后 ACTION_CHAIN_UPDATED 周期（ms）。默认 2s。 */
  chainIntervalMs?: number;
  /** 是否模拟 agent 认知轨迹（周期性 ACTION_CHAIN_UPDATED）。默认 false。 */
  simulateChains?: boolean;
}

interface AgentRecord {
  name: string;
  config: AgentConfigPayload;
  abilities: AbilityDefinitionPayload[];
}

export interface PendingHitl {
  payload: HITLRequestPayload;
  status: "pending" | "approved" | "rejected";
  reason: string | null;
}

const ok = (data?: unknown): CommandOutcome => ({ success: true, data: data ?? null });
const fail = (error: string): CommandOutcome => ({ success: false, error });

function isoNow(): string {
  return new Date().toISOString();
}

function uuid(): string {
  return crypto.randomUUID();
}

/**
 * 模拟 Subject 状态机。命令/事件面严格对齐「Room Unit 形态契约」：
 * 同 payload schema、同事件名、同 seq 分配语义（room 内 seq 单点分配、单调递增）。
 */
export class MockState {
  readonly projects = new Map<string, ProjectInfoPayload>();
  readonly rooms = new Map<string, RoomInfoPayload>();
  readonly agents = new Map<string, AgentRecord>();
  readonly roomLogs = new Map<string, RoomLogEntryPayload[]>();
  readonly tasks = new Map<string, TaskInfoPayload>();
  readonly pendingHitl = new Map<string, PendingHitl>();

  /** 由 server 注入：广播事件（带 seq_id 分配与订阅过滤）。 */
  emit: EmitFn = () => {};

  private readonly _hitlTimeoutMs: number;
  private readonly _chainIntervalMs: number;
  private readonly _simulateChains: boolean;
  private readonly _chainTimers = new Map<string, ReturnType<typeof setInterval>>();
  private readonly _chainIterations = new Map<string, number>();
  private readonly _hitlTimers = new Map<string, ReturnType<typeof setTimeout>>();

  constructor(options: MockStateOptions = {}) {
    this._hitlTimeoutMs = options.hitlTimeoutMs ?? 30_000;
    this._chainIntervalMs = options.chainIntervalMs ?? 2_000;
    this._simulateChains = options.simulateChains ?? false;
  }

  /** 清理所有定时器（chain 模拟 + HITL 超时）。 */
  dispose(): void {
    for (const timer of this._chainTimers.values()) clearInterval(timer);
    this._chainTimers.clear();
    for (const timer of this._hitlTimers.values()) clearTimeout(timer);
    this._hitlTimers.clear();
  }

  // ─── 命令路由 ───

  handleCommand(commandType: string, rawPayload: Record<string, unknown>): CommandOutcome {
    switch (commandType) {
      // Room
      case CommandType.ROOM_CREATE:
        return this._parse(RoomCreatePayloadSchema, rawPayload, (p) => this._roomCreate(p));
      case CommandType.ROOM_LIST:
        return this._parse(RoomListPayloadSchema, rawPayload, (p) => this._roomList(p));
      case CommandType.ROOM_GET:
        return this._parse(RoomIdPayloadSchema, rawPayload, (p) => {
          const room = this.rooms.get(p.room_id);
          return room ? ok({ room }) : fail(`room not found: ${p.room_id}`);
        });
      case CommandType.ROOM_UPDATE:
        return this._parse(RoomUpdatePayloadSchema, rawPayload, (p) => this._roomUpdate(p));
      case CommandType.ROOM_DELETE:
        return this._parse(RoomDeletePayloadSchema, rawPayload, (p) => this._roomDelete(p));
      case CommandType.ROOM_JOIN:
        return this._parse(RoomJoinPayloadSchema, rawPayload, (p) => this._roomJoin(p));
      case CommandType.ROOM_LEAVE:
        return this._parse(RoomLeavePayloadSchema, rawPayload, (p) => this._roomLeave(p));
      case CommandType.ROOM_GET_MEMBERS:
        return this._parse(RoomIdPayloadSchema, rawPayload, (p) => {
          const room = this.rooms.get(p.room_id);
          return room
            ? ok({ room_id: room.room_id, members: room.members, count: room.members.length })
            : fail(`room not found: ${p.room_id}`);
        });
      case CommandType.ROOM_GET_LOG:
        return this._parse(RoomGetLogPayloadSchema, rawPayload, (p) => this._roomGetLog(p));
      case CommandType.ROOM_SEND:
        return this._parse(RoomSendPayloadSchema, rawPayload, (p) => this._roomSend(p));

      // Project（最小实现）
      case CommandType.PROJECT_CREATE:
        return this._parse(ProjectCreatePayloadSchema, rawPayload, (p) => this._projectCreate(p));
      case CommandType.PROJECT_LIST:
        return this._parse(ProjectListPayloadSchema, rawPayload, (p) => {
          let list = [...this.projects.values()];
          if (p.status != null) list = list.filter((proj) => proj.status === p.status);
          return ok({ projects: list, count: list.length });
        });
      case CommandType.PROJECT_GET:
        return this._parse(ProjectIdPayloadSchema, rawPayload, (p) => {
          const project = this.projects.get(p.project_id);
          return project ? ok({ project }) : fail(`project not found: ${p.project_id}`);
        });

      // Task（最小实现）
      case CommandType.TASK_CREATE:
        return this._parse(TaskCreatePayloadSchema, rawPayload, (p) => this._taskCreate(p));
      case CommandType.TASK_LIST:
        return this._parse(TaskListPayloadSchema, rawPayload, (p) => {
          let list = [...this.tasks.values()];
          if (p.project_id != null) list = list.filter((t) => t.project_id === p.project_id);
          if (p.agent_name != null) list = list.filter((t) => t.agent_name === p.agent_name);
          list = list.slice(0, p.limit);
          return ok({ tasks: list, count: list.length });
        });
      case CommandType.TASK_GET:
        return this._parse(TaskIdPayloadSchema, rawPayload, (p) => {
          const task = this.tasks.get(p.task_id);
          return task ? ok({ task }) : fail(`task not found: ${p.task_id}`);
        });

      // Agent / Core
      case CommandType.SPAWN_AGENT:
        return this._parse(SpawnAgentPayloadSchema, rawPayload, (p) =>
          this.spawnAgent(p.config, p.abilities ?? []),
        );
      case CommandType.TERMINATE_AGENT:
        return this._parse(TerminateAgentPayloadSchema, rawPayload, (p) =>
          this.terminateAgent(p.name),
        );
      case CommandType.LIST_AGENTS:
        return ok({
          agents: [...this.agents.values()].map((a) => ({ name: a.name, config: a.config })),
        });
      case CommandType.HEALTH_CHECK:
        return ok({ status: "ok" });

      // HITL 单路径（core 侧）：按 promise_id 匹配 pending（协议 HITLResponsePayload 无 tool_call_id 字段）
      case CommandType.HITL_RESPONSE:
        return this._parse(HITLResponsePayloadSchema, rawPayload, (p) =>
          this.resolveHitl(p.promise_id, p.approved, p.reason ?? null),
        );

      default:
        return fail(`unknown command: ${commandType}`);
    }
  }

  private _parse<S extends z.ZodTypeAny>(
    schema: S,
    raw: Record<string, unknown>,
    handler: (payload: z.output<S>) => CommandOutcome,
  ): CommandOutcome {
    try {
      return handler(schema.parse(raw));
    } catch (err) {
      if (err instanceof ZodError) {
        return fail(`invalid payload: ${err.issues.map((i) => i.message).join("; ")}`);
      }
      throw err;
    }
  }

  // ─── Room ───

  private _roomCreate(p: { project_id: string; name: string }): CommandOutcome {
    if (!this.projects.has(p.project_id)) {
      return fail(`project not found: ${p.project_id}`);
    }
    const room: RoomInfoPayload = {
      room_id: uuid(),
      project_id: p.project_id,
      name: p.name,
      status: "active",
      members: [],
      seq_watermark: 0,
      version: 1,
      created_at: isoNow(),
      updated_at: isoNow(),
    };
    this.rooms.set(room.room_id, room);
    this.roomLogs.set(room.room_id, []);
    this.emit(EventType.ROOM_CREATED, { room });
    return ok({ room });
  }

  private _roomList(p: {
    project_id?: string | null;
    status?: "active" | "archived" | null;
  }): CommandOutcome {
    let list = [...this.rooms.values()];
    if (p.project_id != null) list = list.filter((r) => r.project_id === p.project_id);
    if (p.status != null) list = list.filter((r) => r.status === p.status);
    return ok({ rooms: list, count: list.length });
  }

  private _roomUpdate(p: {
    room_id: string;
    name?: string | null;
    expected_version?: number | null;
  }): CommandOutcome {
    const room = this.rooms.get(p.room_id);
    if (!room) return fail(`room not found: ${p.room_id}`);
    if (p.expected_version != null && p.expected_version !== room.version) {
      return fail(`version conflict: expected ${p.expected_version}, current ${room.version}`);
    }
    if (p.name != null) room.name = p.name;
    room.version += 1;
    room.updated_at = isoNow();
    this.emit(EventType.ROOM_UPDATED, { room });
    return ok({ room });
  }

  private _roomDelete(p: { room_id: string; force?: boolean }): CommandOutcome {
    const room = this.rooms.get(p.room_id);
    if (!room) return fail(`room not found: ${p.room_id}`);
    const log = this.roomLogs.get(p.room_id) ?? [];
    if (log.length > 0 && !p.force) {
      return fail(`room has ${log.length} log entries; pass force=true to delete`);
    }
    this.rooms.delete(p.room_id);
    this.roomLogs.delete(p.room_id);
    this.emit(EventType.ROOM_DELETED, {
      room_id: room.room_id,
      project_id: room.project_id,
    });
    return ok({ room_id: room.room_id, project_id: room.project_id });
  }

  private _roomJoin(p: {
    room_id: string;
    subject: string;
    subject_type: "agent" | "human";
  }): CommandOutcome {
    const room = this.rooms.get(p.room_id);
    if (!room) return fail(`room not found: ${p.room_id}`);
    if (!room.members.some((m) => m.subject === p.subject)) {
      const member: RoomMember = {
        subject: p.subject,
        subject_type: p.subject_type,
        joined_at: isoNow(),
      };
      room.members.push(member);
      room.updated_at = isoNow();
      this.emit(EventType.ROOM_MEMBER_JOINED, { room, member });
    }
    return ok({ room });
  }

  private _roomLeave(p: { room_id: string; subject: string }): CommandOutcome {
    const room = this.rooms.get(p.room_id);
    if (!room) return fail(`room not found: ${p.room_id}`);
    const idx = room.members.findIndex((m) => m.subject === p.subject);
    if (idx < 0) return fail(`subject not in room: ${p.subject}`);
    room.members.splice(idx, 1);
    room.updated_at = isoNow();
    this.emit(EventType.ROOM_MEMBER_LEFT, { room, subject: p.subject });
    return ok({ room });
  }

  private _roomGetLog(p: {
    room_id: string;
    since_seq?: number | null;
    limit?: number;
  }): CommandOutcome {
    const room = this.rooms.get(p.room_id);
    if (!room) return fail(`room not found: ${p.room_id}`);
    let entries = this.roomLogs.get(p.room_id) ?? [];
    if (p.since_seq != null) entries = entries.filter((e) => e.seq > p.since_seq!);
    const limit = p.limit ?? 100;
    entries = entries.slice(-limit);
    return ok({ room_id: p.room_id, entries, count: entries.length });
  }

  /** room_send：room 内 seq 单点分配 + 追加 RoomLog + 广播 ROOM_LOG_APPENDED；同步返回 {entry}。 */
  private _roomSend(p: {
    room_id: string;
    author: string;
    author_type: "agent" | "human";
    data?: Record<string, unknown>;
  }): CommandOutcome {
    const room = this.rooms.get(p.room_id);
    if (!room) return fail(`room not found: ${p.room_id}`);
    // 写时校验：data.targets（{message, targets?} 约定）须 ⊆ 该 room 的 agent 成员；
    // 缺省/空 = 整室广播。
    const targets = p.data?.targets;
    if (targets !== undefined) {
      if (!Array.isArray(targets) || !targets.every((t) => typeof t === "string")) {
        return fail("invalid targets: expected string[]");
      }
      for (const t of targets as string[]) {
        const isMember = room.members.some(
          (m) => m.subject === t && m.subject_type === "agent",
        );
        if (!isMember) return fail(`target not in room: ${t}`);
      }
    }
    const seq = room.seq_watermark + 1;
    room.seq_watermark = seq;
    room.updated_at = isoNow();
    const entry: RoomLogEntryPayload = {
      id: uuid(),
      room_id: room.room_id,
      seq,
      author: p.author,
      author_type: p.author_type,
      timestamp: Date.now() / 1000,
      data: p.data ?? {},
    };
    this.roomLogs.get(room.room_id)!.push(entry);
    this.emit(EventType.ROOM_LOG_APPENDED, { entry });
    return ok({ entry });
  }

  // ─── Project / Task（最小实现） ───

  private _projectCreate(p: {
    name: string;
    description?: string;
    project_root_locator?: string;
    manifest_ref?: string;
  }): CommandOutcome {
    const project: ProjectInfoPayload = {
      project_id: uuid(),
      name: p.name,
      description: p.description ?? "",
      project_root_locator: p.project_root_locator ?? "",
      manifest_ref: p.manifest_ref ?? "",
      cluster_ids: [],
      workspaces: [],
      agents: [],
      task_ids: [],
      status: "active",
      recovery: "resume",
      version: 1,
      created_at: isoNow(),
      updated_at: isoNow(),
      deleted_at: null,
    };
    this.projects.set(project.project_id, project);
    this.emit(EventType.PROJECT_CREATED, { project });
    return ok({ project });
  }

  private _taskCreate(p: {
    title: string;
    project_id: string;
    description?: string;
    agent_name?: string | null;
    priority?: "low" | "normal" | "high" | "urgent";
    parent_id?: string | null;
    dependencies?: string[];
    metadata?: Record<string, unknown>;
  }): CommandOutcome {
    if (!this.projects.has(p.project_id)) {
      return fail(`project not found: ${p.project_id}`);
    }
    const task: TaskInfoPayload = {
      task_id: uuid(),
      project_id: p.project_id,
      title: p.title,
      description: p.description ?? "",
      agent_name: p.agent_name ?? null,
      status: "pending",
      priority: p.priority ?? "normal",
      parent_id: p.parent_id ?? null,
      dependencies: p.dependencies ?? [],
      result: null,
      error: null,
      created_at: isoNow(),
      updated_at: isoNow(),
      started_at: null,
      completed_at: null,
      metadata: p.metadata ?? {},
    };
    this.tasks.set(task.task_id, task);
    this.projects.get(p.project_id)!.task_ids.push(task.task_id);
    this.emit(EventType.TASK_CREATED, { task });
    return ok({ task });
  }

  // ─── Agent ───

  spawnAgent(
    config: AgentConfigPayload,
    abilities: AbilityDefinitionPayload[] = [],
  ): CommandOutcome {
    if (this.agents.has(config.name)) {
      return fail(`agent already exists: ${config.name}`);
    }
    this.agents.set(config.name, { name: config.name, config, abilities });
    this.emit(EventType.AGENT_SPAWNED, { name: config.name, config });
    if (this._simulateChains) this._startChainSimulation(config.name);
    return ok({ name: config.name, config });
  }

  terminateAgent(name: string): CommandOutcome {
    if (!this.agents.has(name)) return fail(`agent not found: ${name}`);
    this._stopChainSimulation(name);
    this.agents.delete(name);
    this.emit(EventType.AGENT_TERMINATED, { name });
    return ok({ name });
  }

  private _startChainSimulation(agentName: string): void {
    this._chainIterations.set(agentName, 0);
    const timer = setInterval(() => {
      if (!this.agents.has(agentName)) {
        this._stopChainSimulation(agentName);
        return;
      }
      const iteration = (this._chainIterations.get(agentName) ?? 0) + 1;
      this._chainIterations.set(agentName, iteration);
      const node: ActionNode = {
        id: uuid(),
        parent_id: null,
        agent_name: agentName,
        timestamp: isoNow(),
        iteration,
        ability_names: ["think"],
        agent_state: {},
        messages_delta: [
          {
            role: "ai",
            content_blocks: [
              { type: "text", text: `${agentName} iteration ${iteration}: working...` },
            ],
            metadata: {},
          },
        ],
        messages_snapshot: null,
        is_snapshot: false,
        action_results: [],
        metadata: {},
        branch_name: "main",
        session_id: "",
      };
      this.emit(EventType.ACTION_CHAIN_UPDATED, { agent_name: agentName, node });
    }, this._chainIntervalMs);
    this._chainTimers.set(agentName, timer);
  }

  private _stopChainSimulation(agentName: string): void {
    const timer = this._chainTimers.get(agentName);
    if (timer != null) clearInterval(timer);
    this._chainTimers.delete(agentName);
    this._chainIterations.delete(agentName);
  }

  // ─── HITL 单路径（core 侧，不模拟 notary） ───

  /** 广播 HITL_REQUEST 并挂起审批；超时（hitlTimeoutMs，默认 30s）自动拒绝。 */
  triggerHitl(
    agentName: string,
    abilityName: string,
    toolArgs: Record<string, unknown> = {},
    context: Record<string, unknown> = {},
  ): HITLRequestPayload {
    const payload: HITLRequestPayload = {
      promise_id: `hitl-${uuid().replace(/-/g, "").slice(0, 12)}`,
      agent_name: agentName,
      ability_name: abilityName,
      tool_args: toolArgs,
      context,
    };
    this.pendingHitl.set(payload.promise_id, { payload, status: "pending", reason: null });
    const timer = setTimeout(() => {
      const pending = this.pendingHitl.get(payload.promise_id);
      if (pending && pending.status === "pending") {
        pending.status = "rejected";
        pending.reason = "hitl timeout";
      }
      this._hitlTimers.delete(payload.promise_id);
    }, this._hitlTimeoutMs);
    this._hitlTimers.set(payload.promise_id, timer);
    this.emit(EventType.HITL_REQUEST, payload as unknown as Record<string, unknown>);
    return payload;
  }

  resolveHitl(promiseId: string, approved: boolean, reason: string | null): CommandOutcome {
    const pending = this.pendingHitl.get(promiseId);
    if (!pending || pending.status !== "pending") {
      return fail(`unknown hitl request: ${promiseId}`);
    }
    pending.status = approved ? "approved" : "rejected";
    pending.reason = reason;
    const timer = this._hitlTimers.get(promiseId);
    if (timer != null) clearTimeout(timer);
    this._hitlTimers.delete(promiseId);
    return ok({ promise_id: promiseId, status: pending.status, reason });
  }
}
