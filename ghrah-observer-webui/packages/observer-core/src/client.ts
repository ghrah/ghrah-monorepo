import {
  type AbilityDefinitionPayload,
  type AgentConfigPayload,
  ClientType,
  type CommandResultPayload,
  CommandType,
  generateRequestId,
  type RoomSubjectType,
  ServerClient,
  type ServerMessage,
  type SubscribePayload,
  type TaskPriority,
} from "@ghrah/protocol";

export interface CreateProjectOptions {
  description?: string;
  manifestRef?: string | null;
  projectRootLocator?: string;
  writableWorkspaces?: Array<{
    locator: string;
    name?: string;
    role?: string | null;
    defaultForAgents?: boolean;
  }>;
}

export class ObserverClient extends ServerClient {
  async subscribe(agentNames?: string[] | null, eventTypes?: string[] | null): Promise<void> {
    const payload: SubscribePayload = {};
    if (agentNames != null) payload.agent_names = agentNames;
    if (eventTypes != null) payload.event_types = eventTypes;

    this._subscriptions.push(payload);

    const msg: ServerMessage = {
      type: CommandType.SUBSCRIBE,
      payload: payload as Record<string, unknown>,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    await this.send(msg);
  }

  async unsubscribe(agentNames?: string[] | null, eventTypes?: string[] | null): Promise<void> {
    const payload: Record<string, unknown> = {};
    if (agentNames != null) payload["agent_names"] = agentNames;
    if (eventTypes != null) payload["event_types"] = eventTypes;

    this._subscriptions = this._subscriptions.filter(
      (s) =>
        !(
          (agentNames == null || arraysEqual(s.agent_names, agentNames)) &&
          (eventTypes == null || arraysEqual(s.event_types, eventTypes))
        ),
    );

    const msg: ServerMessage = {
      type: CommandType.UNSUBSCRIBE,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    await this.send(msg);
  }

  async spawnAgent(
    config: AgentConfigPayload,
    abilities?: AbilityDefinitionPayload[] | null,
    manifestRef?: string | null,
  ): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { config };
    if (abilities != null) payload["abilities"] = abilities;
    if (manifestRef != null) payload["manifest_ref"] = manifestRef;

    const msg: ServerMessage = {
      type: CommandType.SPAWN_AGENT,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async terminateAgent(name: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.TERMINATE_AGENT,
      payload: { name },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async sendMessage(
    target: string,
    content: string,
    sender = "user",
  ): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.SEND_MESSAGE,
      payload: { target, content, sender },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 60_000);
  }

  async broadcastMessage(content: string, sender = "user"): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.BROADCAST_MESSAGE,
      payload: { content, sender },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async listAgents(): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.LIST_AGENTS,
      payload: {},
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async healthCheck(): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.HEALTH_CHECK,
      payload: {},
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async sendHitlResponse(promiseId: string, approved: boolean, reason?: string): Promise<void> {
    const payload: Record<string, unknown> = { promise_id: promiseId, approved };
    if (reason != null) payload["reason"] = reason;

    const msg: ServerMessage = {
      type: CommandType.HITL_RESPONSE,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    await this.send(msg);
  }

  async getAgentInfo(name: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.GET_AGENT_INFO,
      payload: { name },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async getChainHistory(
    agentName: string,
    limit?: number,
    projectId?: string,
  ): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { agent_name: agentName };
    if (limit != null) payload["limit"] = limit;
    if (projectId != null) payload["project_id"] = projectId;

    const msg: ServerMessage = {
      type: CommandType.GET_CHAIN_HISTORY,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async initCluster(
    clusterId: string,
    config?: Record<string, unknown>,
  ): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.INIT_CLUSTER,
      payload: { cluster_id: clusterId, config: config ?? {} },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async shutdownCluster(clusterId: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.SHUTDOWN_CLUSTER,
      payload: { cluster_id: clusterId, config: {} },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async clusterStatus(clusterId: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.CLUSTER_STATUS,
      payload: { cluster_id: clusterId },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async listClusters(): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.LIST_CLUSTERS,
      payload: {},
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async createWorkspace(agentName: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.CREATE_WORKSPACE,
      payload: { agent_name: agentName },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async destroyWorkspace(agentName: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.DESTROY_WORKSPACE,
      payload: { agent_name: agentName },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async workspaceSnapshot(agentName: string, message = ""): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.WORKSPACE_SNAPSHOT,
      payload: { agent_name: agentName, message },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async workspaceRollback(agentName: string, snapshotId: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.WORKSPACE_ROLLBACK,
      payload: { agent_name: agentName, snapshot_id: snapshotId },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async workspaceDiff(
    agentName: string,
    snapshotId?: string | null,
  ): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { agent_name: agentName };
    if (snapshotId != null) payload["snapshot_id"] = snapshotId;

    const msg: ServerMessage = {
      type: CommandType.WORKSPACE_DIFF,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async workspaceStatus(agentName: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.WORKSPACE_STATUS,
      payload: { agent_name: agentName },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  // ── Persist 操作 ──

  async persistSaveNode(
    key: string,
    data: Record<string, unknown>,
    namespace = "default",
  ): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.PERSIST_SAVE_NODE,
      payload: { key, data, namespace },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async persistLoadNode(key: string, namespace = "default"): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.PERSIST_LOAD_NODE,
      payload: { key, namespace },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async persistDeleteChain(key: string, namespace = "default"): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.PERSIST_DELETE_CHAIN,
      payload: { key, namespace },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async persistListAgents(namespace = "default", prefix?: string): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { namespace };
    if (prefix != null) payload["prefix"] = prefix;

    const msg: ServerMessage = {
      type: CommandType.PERSIST_LIST_AGENTS,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  // ── 能力管理 + 委托 ──

  async registerAbility(
    agentName: string,
    ability: AbilityDefinitionPayload,
  ): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.REGISTER_ABILITY,
      payload: { agent_name: agentName, ability },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async delegate(
    fromAgent: string,
    toAgent: string,
    content: string,
  ): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.DELEGATE,
      payload: { from_agent: fromAgent, to_agent: toAgent, content },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  // ── Manifest CRUD ──

  async listManifestAbilities(namespace?: string | null): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = {};
    if (namespace != null) payload["namespace"] = namespace;

    const msg: ServerMessage = {
      type: CommandType.MANIFEST_LIST_ABILITIES,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async getAbility(fullName: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.MANIFEST_GET_ABILITY,
      payload: { full_name: fullName },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async putAbility(
    fullName: string,
    content: string,
    overwrite?: boolean,
  ): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { full_name: fullName, content };
    if (overwrite != null) payload["overwrite"] = overwrite;

    const msg: ServerMessage = {
      type: CommandType.MANIFEST_PUT_ABILITY,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async deleteAbility(fullName: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.MANIFEST_DELETE_ABILITY,
      payload: { full_name: fullName },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async listManifestAgents(namespace?: string | null): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = {};
    if (namespace != null) payload["namespace"] = namespace;

    const msg: ServerMessage = {
      type: CommandType.MANIFEST_LIST_AGENTS,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async getAgent(fullName: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.MANIFEST_GET_AGENT,
      payload: { full_name: fullName },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async putAgent(
    fullName: string,
    content: string,
    overwrite?: boolean,
  ): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { full_name: fullName, content };
    if (overwrite != null) payload["overwrite"] = overwrite;

    const msg: ServerMessage = {
      type: CommandType.MANIFEST_PUT_AGENT,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async deleteAgent(fullName: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.MANIFEST_DELETE_AGENT,
      payload: { full_name: fullName },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async resolveAgent(
    agentFullName: string,
    runtimeName?: string | null,
  ): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { agent_full_name: agentFullName };
    if (runtimeName != null) payload["runtime_name"] = runtimeName;

    const msg: ServerMessage = {
      type: CommandType.MANIFEST_RESOLVE_AGENT,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async validateManifest(content: string, manifestType: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.MANIFEST_VALIDATE,
      payload: { content, manifest_type: manifestType },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  // ── Room ──

  async createRoom(projectId: string, name: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.ROOM_CREATE,
      payload: { project_id: projectId, name },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async listRooms(
    projectId?: string | null,
    status?: string | null,
  ): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = {};
    if (projectId != null) payload["project_id"] = projectId;
    if (status != null) payload["status"] = status;

    const msg: ServerMessage = {
      type: CommandType.ROOM_LIST,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async getRoom(roomId: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.ROOM_GET,
      payload: { room_id: roomId },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async updateRoom(
    roomId: string,
    name?: string | null,
    expectedVersion?: number | null,
  ): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { room_id: roomId };
    if (name != null) payload["name"] = name;
    if (expectedVersion != null) payload["expected_version"] = expectedVersion;

    const msg: ServerMessage = {
      type: CommandType.ROOM_UPDATE,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async deleteRoom(roomId: string, force?: boolean): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { room_id: roomId };
    if (force != null) payload["force"] = force;

    const msg: ServerMessage = {
      type: CommandType.ROOM_DELETE,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async joinRoom(
    roomId: string,
    subject: string,
    subjectType: RoomSubjectType,
  ): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.ROOM_JOIN,
      payload: { room_id: roomId, subject, subject_type: subjectType },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async leaveRoom(roomId: string, subject: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.ROOM_LEAVE,
      payload: { room_id: roomId, subject },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async getRoomMembers(roomId: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.ROOM_GET_MEMBERS,
      payload: { room_id: roomId },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async getRoomLog(
    roomId: string,
    sinceSeq?: number | null,
    limit?: number,
  ): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { room_id: roomId };
    if (sinceSeq != null) payload["since_seq"] = sinceSeq;
    if (limit != null) payload["limit"] = limit;

    const msg: ServerMessage = {
      type: CommandType.ROOM_GET_LOG,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async roomSend(
    roomId: string,
    data: Record<string, unknown>,
    author = "user",
    authorType: RoomSubjectType = "human",
  ): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.ROOM_SEND,
      payload: { room_id: roomId, author, author_type: authorType, data },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  // ── Project ──

  async createProject(name: string, options: CreateProjectOptions): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { name };
    if (options.description) payload["description"] = options.description;
    if (options.manifestRef != null) payload["manifest_ref"] = options.manifestRef;
    if (options.projectRootLocator) {
      payload["project_root_locator"] = options.projectRootLocator;
    }
    if (options.writableWorkspaces !== undefined) {
      payload["writable_workspaces"] = options.writableWorkspaces.map((workspace) => ({
        locator: workspace.locator,
        ...(workspace.name ? { name: workspace.name } : {}),
        ...(workspace.role !== undefined ? { role: workspace.role } : {}),
        ...(workspace.defaultForAgents !== undefined
          ? { default_for_agents: workspace.defaultForAgents }
          : {}),
      }));
    }
    const msg: ServerMessage = {
      type: CommandType.PROJECT_CREATE,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async listProjects(status?: string | null): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = {};
    if (status != null) payload["status"] = status;

    const msg: ServerMessage = {
      type: CommandType.PROJECT_LIST,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async getProject(projectId: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.PROJECT_GET,
      payload: { project_id: projectId },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async updateProject(
    projectId: string,
    fields: {
      name?: string | null;
      description?: string | null;
      manifestRef?: string | null;
      expectedVersion?: number | null;
    },
  ): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { project_id: projectId };
    if (fields.name != null) payload["name"] = fields.name;
    if (fields.description != null) payload["description"] = fields.description;
    if (fields.manifestRef != null) payload["manifest_ref"] = fields.manifestRef;
    if (fields.expectedVersion != null) payload["expected_version"] = fields.expectedVersion;

    const msg: ServerMessage = {
      type: CommandType.PROJECT_UPDATE,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async deleteProject(
    projectId: string,
    force?: boolean,
    purgeStorage?: boolean,
  ): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { project_id: projectId };
    if (force != null) payload["force"] = force;
    if (purgeStorage != null) payload["purge_storage"] = purgeStorage;

    const msg: ServerMessage = {
      type: CommandType.PROJECT_DELETE,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  // ── Task ──

  async createTask(
    title: string,
    projectId: string,
    opts?: {
      description?: string;
      agentName?: string | null;
      priority?: TaskPriority;
      parentId?: string | null;
    },
  ): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { title, project_id: projectId };
    if (opts?.description != null) payload["description"] = opts.description;
    if (opts?.agentName != null) payload["agent_name"] = opts.agentName;
    if (opts?.priority != null) payload["priority"] = opts.priority;
    if (opts?.parentId != null) payload["parent_id"] = opts.parentId;

    const msg: ServerMessage = {
      type: CommandType.TASK_CREATE,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async listTasks(filter?: {
    projectId?: string | null;
    agentName?: string | null;
    status?: string | string[] | null;
    limit?: number;
  }): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = {};
    if (filter?.projectId != null) payload["project_id"] = filter.projectId;
    if (filter?.agentName != null) payload["agent_name"] = filter.agentName;
    if (filter?.status != null) payload["status"] = filter.status;
    if (filter?.limit != null) payload["limit"] = filter.limit;

    const msg: ServerMessage = {
      type: CommandType.TASK_LIST,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async getTask(taskId: string): Promise<CommandResultPayload> {
    const msg: ServerMessage = {
      type: CommandType.TASK_GET,
      payload: { task_id: taskId },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  // ── 内部方法 ──

  protected async _syncInitialState(): Promise<void> {
    try {
      await this.listProjects();
    } catch {
      // 静默忽略初始同步失败
    }
    try {
      await this.listManifestAgents();
    } catch {
      // 静默忽略初始同步失败
    }
    try {
      await this.listAgents();
    } catch {
      // 静默忽略初始同步失败
    }
    try {
      await this.listRooms();
    } catch {
      // 静默忽略初始同步失败
    }
  }
}

function arraysEqual(a: string[] | null | undefined, b: string[]): boolean {
  if (a == null) return false;
  if (a.length !== b.length) return false;
  const sortedA = [...a].sort();
  const sortedB = [...b].sort();
  return sortedA.every((v, i) => v === sortedB[i]);
}
