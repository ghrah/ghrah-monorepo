import {
  type AbilityDefinitionPayload,
  type AgentConfigPayload,
  ClientType,
  type CommandResultPayload,
  CommandType,
  GatewayClient,
  type GatewayMessage,
  generateRequestId,
  type SubscribePayload,
} from "@ghrah/protocol";

export class ObserverClient extends GatewayClient {
  async subscribe(agentNames?: string[] | null, eventTypes?: string[] | null): Promise<void> {
    const payload: SubscribePayload = {};
    if (agentNames != null) payload.agent_names = agentNames;
    if (eventTypes != null) payload.event_types = eventTypes;

    this._subscriptions.push(payload);

    const msg: GatewayMessage = {
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

    const msg: GatewayMessage = {
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
  ): Promise<CommandResultPayload> {
    const payload: Record<string, unknown> = { config };
    if (abilities != null) payload["abilities"] = abilities;

    const msg: GatewayMessage = {
      type: CommandType.SPAWN_AGENT,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async terminateAgent(name: string): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
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
    const msg: GatewayMessage = {
      type: CommandType.SEND_MESSAGE,
      payload: { target, content, sender },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 60_000);
  }

  async broadcastMessage(content: string, sender = "user"): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
      type: CommandType.BROADCAST_MESSAGE,
      payload: { content, sender },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async listAgents(): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
      type: CommandType.LIST_AGENTS,
      payload: {},
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async healthCheck(): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
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

    const msg: GatewayMessage = {
      type: CommandType.HITL_RESPONSE,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    await this.send(msg);
  }

  async getAgentInfo(name: string): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
      type: CommandType.GET_AGENT_INFO,
      payload: { name },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async initCluster(config?: Record<string, unknown>): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
      type: CommandType.INIT_CLUSTER,
      payload: { config: config ?? {} },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async shutdownCluster(): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
      type: CommandType.SHUTDOWN_CLUSTER,
      payload: {},
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async clusterStatus(): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
      type: CommandType.CLUSTER_STATUS,
      payload: {},
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async createWorkspace(agentName: string): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
      type: CommandType.CREATE_WORKSPACE,
      payload: { agent_name: agentName },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async destroyWorkspace(agentName: string): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
      type: CommandType.DESTROY_WORKSPACE,
      payload: { agent_name: agentName },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async workspaceSnapshot(agentName: string, message = ""): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
      type: CommandType.WORKSPACE_SNAPSHOT,
      payload: { agent_name: agentName, message },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async workspaceRollback(agentName: string, snapshotId: string): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
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

    const msg: GatewayMessage = {
      type: CommandType.WORKSPACE_DIFF,
      payload,
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async workspaceStatus(agentName: string): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
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
    const msg: GatewayMessage = {
      type: CommandType.PERSIST_SAVE_NODE,
      payload: { key, data, namespace },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async persistLoadNode(key: string, namespace = "default"): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
      type: CommandType.PERSIST_LOAD_NODE,
      payload: { key, namespace },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  async persistDeleteChain(key: string, namespace = "default"): Promise<CommandResultPayload> {
    const msg: GatewayMessage = {
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

    const msg: GatewayMessage = {
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
    const msg: GatewayMessage = {
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
    const msg: GatewayMessage = {
      type: CommandType.DELEGATE,
      payload: { from_agent: fromAgent, to_agent: toAgent, content },
      request_id: generateRequestId(),
      client_type: ClientType.OBSERVER,
    };
    return this.request(msg, 30_000);
  }

  // ── 内部方法 ──

  protected async _syncInitialState(): Promise<void> {
    try {
      await this.listAgents();
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
