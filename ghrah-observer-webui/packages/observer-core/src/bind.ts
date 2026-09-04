import type {
  ActionChainUpdatedPayload,
  ActionNode,
  AgentConfigPayload,
  AgentSpawnedPayload,
  AgentTerminatedPayload,
  CommandResultPayload,
  HITLRequestPayload,
  ManifestAbilityEventPayload,
  ManifestAgentEventPayload,
  ProjectAgentEventPayload,
  ProjectEventPayload,
  ProjectInfoPayload,
  RoomDeletedEventPayload,
  RoomEventPayload,
  RoomInfoPayload,
  RoomLogEntryPayload,
  RoomLogEventPayload,
  RoomMemberEventPayload,
  ServerMessage,
  TaskEventPayload,
} from "@ghrah/protocol";
import { CommandType, EventType, SystemType } from "@ghrah/protocol";
import type { ObserverClient } from "./client.js";
import { createFrameBatcher, type FrameBatcher } from "./frame-batcher.js";
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

type AgentListItem = {
  name: string;
  agent_id?: string;
  incarnation_id?: string;
  recovery_mode?: string;
  config: AgentConfigPayload;
};

export interface ConnectStoresOptions {
  /** 高频事件合帧 batcher（性能红线 4）；默认 rAF/微任务合帧。 */
  batcher?: FrameBatcher;
}

export function connectStores(
  client: ObserverClient,
  options: ConnectStoresOptions = {},
): () => void {
  const connection = useConnectionStore();
  const agents = useAgentsStore();
  const chains = useActionChainsStore();
  const hitl = useHitlStore();
  const chat = useChatStore();
  const changes = useChangesStore();
  const manifests = useManifestsStore();
  const rooms = useRoomsStore();
  const projects = useProjectsStore();
  const tasks = useTasksStore();
  // 高频事件（ACTION_CHAIN_UPDATED / ROOM_LOG_APPENDED）经 batcher 合帧分发
  const batcher = options.batcher ?? createFrameBatcher();

  client.onConnected(() => {
    connection.setConnected();
  });
  client.onDisconnected(() => connection.setDisconnected());
  client.onReconnecting(() => connection.setReconnecting());
  client.onReconnected(() => {
    connection.setConnected();
  });

  client.on(EventType.AGENT_SPAWNED, (msg: ServerMessage) =>
    agents.onAgentSpawned(msg.payload as AgentSpawnedPayload),
  );
  client.on(EventType.AGENT_TERMINATED, (msg: ServerMessage) =>
    agents.onAgentTerminated(msg.payload as AgentTerminatedPayload),
  );

  client.on(EventType.ACTION_CHAIN_UPDATED, (msg: ServerMessage) => {
    const payload = msg.payload as ActionChainUpdatedPayload;
    const node = payload.node;
    if (!node) return;
    batcher.add(() => {
      chains.onActionChainUpdated(payload);
      changes.onActionChainNode(payload.agent_name, node);
    });
  });

  client.on(EventType.HITL_REQUEST, (msg: ServerMessage) => {
    const payload = msg.payload as HITLRequestPayload;
    hitl.onHitlRequest(payload);
  });

  client.on(SystemType.COMMAND_RESULT, (msg: ServerMessage) => {
    const payload = msg.payload as CommandResultPayload;
    if (!payload.success || !payload.data) return;
    const data = payload.data as Record<string, unknown>;
    const originalCommand = (payload as Record<string, unknown>).original_command as
      | string
      | undefined;
    if (originalCommand === CommandType.LIST_AGENTS && Array.isArray(data.agents)) {
      const agentList = data.agents as AgentListItem[];
      agents.setAgentsFromList(agentList);
      // F2 初始同步：刷新后 ActionChain 面板恢复——为每个 agent 读回链历史，
      // 与增量 onActionChainUpdated 幂等合并（store setChain 以 node id 去重）。
      // fire-and-forget：不阻塞回执/连接流程；单个失败仅记日志。
      void syncActionChains(agentList);
    }
    if (originalCommand === CommandType.ROOM_LIST && Array.isArray(data.rooms)) {
      rooms.setRoomsFromList(data.rooms as RoomInfoPayload[]);
    }
    if (originalCommand === CommandType.ROOM_GET_LOG && Array.isArray(data.entries)) {
      // RoomLogResultPayload = { entries, count }，不含 room_id；从 entry 自身取
      const entries = data.entries as RoomLogEntryPayload[];
      const roomId =
        (typeof data.room_id === "string" ? data.room_id : null) ?? entries[0]?.room_id ?? null;
      if (roomId) {
        rooms.setRoomLog(roomId, entries);
      }
    }
    if (originalCommand === CommandType.PROJECT_LIST && Array.isArray(data.projects)) {
      projects.setProjectsFromList(data.projects as ProjectInfoPayload[]);
    }
  });

  client.on(EventType.AGENT_ERROR, (_msg: ServerMessage) => {
    // Agent error: 后续可扩展 ErrorStore
  });

  client.on(EventType.MANIFEST_ABILITY_CREATED, (msg: ServerMessage) =>
    manifests.onManifestAbilityCreated(msg.payload as ManifestAbilityEventPayload),
  );
  client.on(EventType.MANIFEST_ABILITY_UPDATED, (msg: ServerMessage) =>
    manifests.onManifestAbilityInvalidated(msg.payload as ManifestAbilityEventPayload),
  );
  client.on(EventType.MANIFEST_ABILITY_DELETED, (msg: ServerMessage) =>
    manifests.onManifestAbilityDeleted(msg.payload as ManifestAbilityEventPayload),
  );
  client.on(EventType.MANIFEST_AGENT_CREATED, (msg: ServerMessage) =>
    manifests.onManifestAgentCreated(msg.payload as ManifestAgentEventPayload),
  );
  client.on(EventType.MANIFEST_AGENT_UPDATED, (msg: ServerMessage) =>
    manifests.onManifestAgentInvalidated(msg.payload as ManifestAgentEventPayload),
  );
  client.on(EventType.MANIFEST_AGENT_DELETED, (msg: ServerMessage) =>
    manifests.onManifestAgentDeleted(msg.payload as ManifestAgentEventPayload),
  );

  // ── Room 事件 ──
  client.on(EventType.ROOM_CREATED, (msg: ServerMessage) =>
    rooms.onRoomCreated(msg.payload as RoomEventPayload),
  );
  client.on(EventType.ROOM_UPDATED, (msg: ServerMessage) =>
    rooms.onRoomUpdated(msg.payload as RoomEventPayload),
  );
  client.on(EventType.ROOM_DELETED, (msg: ServerMessage) =>
    rooms.onRoomDeleted(msg.payload as RoomDeletedEventPayload),
  );
  client.on(EventType.ROOM_MEMBER_JOINED, (msg: ServerMessage) =>
    rooms.onRoomMemberJoined(msg.payload as RoomMemberEventPayload),
  );
  client.on(EventType.ROOM_MEMBER_LEFT, (msg: ServerMessage) =>
    rooms.onRoomMemberLeft(msg.payload as RoomMemberEventPayload),
  );
  client.on(EventType.ROOM_LOG_APPENDED, (msg: ServerMessage) => {
    const payload = msg.payload as RoomLogEventPayload;
    if (!payload.entry) return;
    batcher.add(() => {
      rooms.onRoomLogAppended(payload);
      chat.onRoomLogAppended(payload.entry);
    });
  });

  // ── Project 事件 ──
  const projectEvent = (msg: ServerMessage) =>
    projects.onProjectEvent(msg.payload as ProjectEventPayload | ProjectAgentEventPayload);
  client.on(EventType.PROJECT_CREATED, projectEvent);
  client.on(EventType.PROJECT_UPDATED, projectEvent);
  client.on(EventType.PROJECT_PAUSED, projectEvent);
  client.on(EventType.PROJECT_RESUMED, projectEvent);
  client.on(EventType.PROJECT_STOPPED, projectEvent);
  client.on(EventType.PROJECT_RECOVERY_SET, projectEvent);
  client.on(EventType.PROJECT_AGENT_ADDED, projectEvent);
  client.on(EventType.PROJECT_AGENT_REMOVED, projectEvent);
  client.on(EventType.PROJECT_DELETED, (msg: ServerMessage) =>
    projects.onProjectDeleted(msg.payload as ProjectEventPayload),
  );

  // ── Task 事件（信封统一 {task, previous_status?, reason?}，删除语义按事件类型分发）──
  const taskEventTypes = [
    EventType.TASK_CREATED,
    EventType.TASK_UPDATED,
    EventType.TASK_ASSIGNED,
    EventType.TASK_STARTED,
    EventType.TASK_COMPLETED,
    EventType.TASK_FAILED,
    EventType.TASK_CANCELED,
    EventType.TASK_BLOCKED,
    EventType.TASK_DELETED,
  ] as const;
  for (const et of taskEventTypes) {
    client.on(et, (msg: ServerMessage) => tasks.onTaskEvent(et, msg.payload as TaskEventPayload));
  }

  const eventTypes = [
    EventType.AGENT_SPAWNED,
    EventType.AGENT_TERMINATED,
    EventType.ACTION_CHAIN_UPDATED,
    EventType.HITL_REQUEST,
    EventType.AGENT_ERROR,
    EventType.MANIFEST_ABILITY_CREATED,
    EventType.MANIFEST_ABILITY_UPDATED,
    EventType.MANIFEST_ABILITY_DELETED,
    EventType.MANIFEST_AGENT_CREATED,
    EventType.MANIFEST_AGENT_UPDATED,
    EventType.MANIFEST_AGENT_DELETED,
    EventType.ROOM_CREATED,
    EventType.ROOM_UPDATED,
    EventType.ROOM_DELETED,
    EventType.ROOM_MEMBER_JOINED,
    EventType.ROOM_MEMBER_LEFT,
    EventType.ROOM_LOG_APPENDED,
    EventType.PROJECT_CREATED,
    EventType.PROJECT_UPDATED,
    EventType.PROJECT_PAUSED,
    EventType.PROJECT_RESUMED,
    EventType.PROJECT_STOPPED,
    EventType.PROJECT_RECOVERY_SET,
    EventType.PROJECT_AGENT_ADDED,
    EventType.PROJECT_AGENT_REMOVED,
    EventType.PROJECT_DELETED,
    ...taskEventTypes,
  ] as const;

  /** F2：对每个 agent 并行读回链历史 → store.setChain（幂等合并）。 */
  async function syncActionChains(agentList: AgentListItem[]) {
    await Promise.all(
      agentList.map(async (agent) => {
        const name = agent.name;
        try {
          const projectId = projects.projectList.find((project) =>
            project.agents.some((agent) => agent.name === name),
          )?.project_id;
          const agentId = agent.agent_id ?? agent.config.agent_id;
          if (!projectId || !agentId) return;
          const sessionsResult = await client.listSessions(name, projectId, agentId);
          const sessions = (sessionsResult.data as Record<string, unknown> | null)?.sessions;
          if (!sessionsResult.success || !Array.isArray(sessions)) return;
          const histories = await Promise.all(
            sessions.flatMap((session) => {
              const sessionId = (session as Record<string, unknown>).session_id;
              if (typeof sessionId !== "string") return [];
              return [
                client.listBranches(name, projectId, agentId, sessionId).then(async (result) => {
                  const branches = (result.data as Record<string, unknown> | null)?.branches;
                  if (!result.success || !Array.isArray(branches)) return [];
                  const branchHistories = await Promise.all(
                    branches.flatMap((branch) => {
                      const branchId = (branch as Record<string, unknown>).branch_id;
                      return typeof branchId === "string"
                        ? [client.getChainHistory(name, projectId, agentId, sessionId, branchId)]
                        : [];
                    }),
                  );
                  return branchHistories.flatMap((history) => {
                    const nodes = (history.data as Record<string, unknown> | null)?.nodes;
                    return history.success && Array.isArray(nodes) ? (nodes as ActionNode[]) : [];
                  });
                }),
              ];
            }),
          );
          const nodes = histories.flat();
          if (nodes.length > 0) {
            chains.setChain(name, nodes);
          }
        } catch {
          // 单个 agent 链读失败不影响其余；增量事件会兜底
        }
      }),
    );
  }

  return () => {
    for (const et of eventTypes) client.off(et);
    client.off(SystemType.COMMAND_RESULT);
    client.clearLifecycleCallbacks();
    batcher.cancel();
  };
}
