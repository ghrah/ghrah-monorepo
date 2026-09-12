import type {
  ActionChainUpdatedPayload,
  ActionNode,
  AgentSpawnedPayload,
  AgentTerminatedPayload,
  BranchEventPayload,
  BranchInfoPayload,
  BranchLifecyclePayload,
  BranchListResultPayload,
  CommandResultPayload,
  ContextUsageUpdatedPayload,
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
  SessionActivatedPayload,
  SessionArchivedPayload,
  SessionCreatedPayload,
  SessionDeletedPayload,
  SessionInfoPayload,
  SessionListResultPayload,
  TaskEventPayload,
} from "@ghrah/protocol";
import { CommandType, EventType, SystemType } from "@ghrah/protocol";
import { clearAgentDerived, clearProjectDerived, clearRoomDerived } from "./clear-derived.js";
import type { ObserverClient } from "./client.js";
import { createFrameBatcher, type FrameBatcher } from "./frame-batcher.js";
import type { AgentTarget, ChainTarget, SessionTarget } from "./scope.js";
import { useActionChainsStore } from "./stores/action-chains.js";
import { type AgentListItem, useAgentsStore } from "./stores/agents.js";
import { useBranchesStore } from "./stores/branches.js";
import { useChangesStore } from "./stores/changes.js";
import { useChatStore } from "./stores/chat.js";
import { useConnectionStore } from "./stores/connection.js";
import { useContextUsageStore } from "./stores/context-usage.js";
import { useHitlStore } from "./stores/hitl.js";
import { useManifestsStore } from "./stores/manifests.js";
import { useProjectsStore } from "./stores/projects.js";
import { useRoomsStore } from "./stores/rooms.js";
import { useSessionsStore } from "./stores/sessions.js";
import { useTasksStore } from "./stores/tasks.js";

export interface ConnectStoresOptions {
  /** High-volume event batcher; defaults to requestAnimationFrame/microtask batching. */
  batcher?: FrameBatcher;
}

function stringField(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function boolField(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

export function connectStores(
  client: ObserverClient,
  options: ConnectStoresOptions = {},
): () => void {
  const connection = useConnectionStore();
  const agents = useAgentsStore();
  const chains = useActionChainsStore();
  const sessions = useSessionsStore();
  const branches = useBranchesStore();
  const hitl = useHitlStore();
  const chat = useChatStore();
  const changes = useChangesStore();
  const contextUsage = useContextUsageStore();
  const manifests = useManifestsStore();
  const rooms = useRoomsStore();
  const projects = useProjectsStore();
  const tasks = useTasksStore();
  const batcher = options.batcher ?? createFrameBatcher();

  client.onConnected(() => connection.setConnected());
  client.onDisconnected(() => connection.setDisconnected());
  client.onReconnecting(() => connection.setReconnecting());
  client.onReconnected(() => connection.setConnected());

  client.on(EventType.AGENT_SPAWNED, (msg: ServerMessage) => {
    const payload = msg.payload as AgentSpawnedPayload;
    const project = projects.projects.get(payload.project_id);
    if (project?.archived_at != null) return;
    agents.onAgentSpawned(payload, project);
  });
  client.on(EventType.AGENT_TERMINATED, (msg: ServerMessage) => {
    const target = agents.onAgentTerminated(msg.payload as AgentTerminatedPayload);
    if (target) clearAgentDerived(target);
  });

  client.on(EventType.ACTION_CHAIN_UPDATED, (msg: ServerMessage) => {
    const payload = msg.payload as ActionChainUpdatedPayload;
    const node = payload.node;
    if (!node) return;
    batcher.add(() => {
      if (!chains.onActionChainUpdated(payload)) return;
      const target: ChainTarget = {
        projectId: payload.project_id,
        agentId: payload.agent_id,
        agentName: payload.agent_name,
        sessionId: node.session_id,
        branchId: node.created_on_branch_id,
      };
      changes.onActionChainNode(target, node);
    });
  });

  client.on(EventType.HITL_REQUEST, (msg: ServerMessage) =>
    hitl.onHitlRequest(msg.payload as HITLRequestPayload),
  );

  client.on(EventType.CONTEXT_USAGE_UPDATED, (msg: ServerMessage) =>
    batcher.add(() =>
      contextUsage.onContextUsageUpdated(
        msg.payload as ContextUsageUpdatedPayload,
        msg.timestamp ?? null,
      ),
    ),
  );

  client.on(SystemType.COMMAND_RESULT, (msg: ServerMessage) => {
    const payload = msg.payload as CommandResultPayload;
    if (!payload.success || !payload.data) return;
    const data = payload.data as Record<string, unknown>;
    const context = client.getRequestContext(payload.request_id);
    const command =
      context?.command ??
      stringField((payload as unknown as Record<string, unknown>).original_command);

    if (command === CommandType.LIST_AGENTS && Array.isArray(data.agents)) {
      const list = data.agents as AgentListItem[];
      const projectId =
        stringField(context?.payload.project_id) ?? stringField(list[0]?.project_id);
      if (!projectId) return;
      const removed = agents.replaceProjectAgents(
        projectId,
        list,
        projects.projects.get(projectId),
      );
      for (const target of removed) clearAgentDerived(target);
      void syncAgentActionState(
        agents.agentsForProject(projectId).map(({ projectId, agentId, agentName }) => ({
          projectId,
          agentId,
          agentName,
        })),
      );
    }

    if (command === CommandType.ROOM_LIST && Array.isArray(data.rooms)) {
      const list = data.rooms as RoomInfoPayload[];
      const projectId =
        stringField(context?.payload.project_id) ?? stringField(list[0]?.project_id);
      const requestedStatus = stringField(context?.payload.status);
      const status =
        requestedStatus === "archived" || requestedStatus === "active"
          ? requestedStatus
          : (list[0]?.status ?? "active");
      if (projectId) {
        const removed = rooms.replaceProjectRooms(projectId, list, status);
        for (const target of removed) clearRoomDerived(target, false);
      }
    }

    if (command === CommandType.ROOM_GET_LOG && Array.isArray(data.entries)) {
      const entries = data.entries as RoomLogEntryPayload[];
      const roomId =
        stringField(context?.payload.room_id) ??
        stringField(data.room_id) ??
        stringField(entries[0]?.room_id);
      if (roomId) rooms.setRoomLog(roomId, entries);
    }

    if (command === CommandType.PROJECT_LIST && Array.isArray(data.projects)) {
      const list = data.projects as ProjectInfoPayload[];
      const archived = boolField(context?.payload.archived) ?? false;
      const previous = new Set(
        (archived ? projects.archivedProjectList : projects.projectList).map(
          (project) => project.project_id,
        ),
      );
      projects.replaceProjects(list, archived);
      const retained = new Set(
        list
          .filter((project) => (project.archived_at != null) === archived)
          .map((project) => project.project_id),
      );
      for (const projectId of previous) {
        if (!retained.has(projectId)) clearProjectDerived(projectId);
      }
    }
  });

  client.on(EventType.AGENT_ERROR, () => {
    // A dedicated runtime error projection can consume this later.
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

  client.on(EventType.ROOM_CREATED, (msg: ServerMessage) =>
    rooms.onRoomCreated(msg.payload as RoomEventPayload),
  );
  client.on(EventType.ROOM_UPDATED, (msg: ServerMessage) =>
    rooms.onRoomUpdated(msg.payload as RoomEventPayload),
  );
  client.on(EventType.ROOM_ARCHIVED, (msg: ServerMessage) => {
    const payload = msg.payload as RoomEventPayload;
    rooms.onRoomArchived(payload);
    clearRoomDerived({ projectId: payload.room.project_id, roomId: payload.room.room_id }, false);
  });
  client.on(EventType.ROOM_RESTORED, (msg: ServerMessage) => {
    const payload = msg.payload as RoomEventPayload;
    rooms.onRoomRestored(payload, projects.isProjectOperable(payload.room.project_id));
  });
  client.on(EventType.ROOM_DELETED, (msg: ServerMessage) => {
    const payload = msg.payload as RoomDeletedEventPayload;
    clearRoomDerived({ projectId: payload.project_id, roomId: payload.room_id });
  });
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
      const room =
        rooms.activeRooms.get(payload.entry.room_id) ??
        rooms.archivedRooms.get(payload.entry.room_id);
      rooms.onRoomLogAppended(payload);
      if (room) chat.onRoomLogAppended(payload.entry, room.project_id);
    });
  });

  const ordinaryProjectEvent = (msg: ServerMessage) => {
    const payload = msg.payload as ProjectEventPayload | ProjectAgentEventPayload;
    projects.onProjectEvent(payload);
    agents.applyProjectRuntimeState(payload.project);
    if (msg.type === EventType.PROJECT_RESUMED) void syncProject(payload.project.project_id);
  };
  client.on(EventType.PROJECT_CREATED, ordinaryProjectEvent);
  client.on(EventType.PROJECT_UPDATED, ordinaryProjectEvent);
  client.on(EventType.PROJECT_PAUSED, ordinaryProjectEvent);
  client.on(EventType.PROJECT_RESUMED, ordinaryProjectEvent);
  client.on(EventType.PROJECT_STOPPED, ordinaryProjectEvent);
  client.on(EventType.PROJECT_RECOVERY_SET, ordinaryProjectEvent);
  client.on(EventType.PROJECT_AGENT_ADDED, (msg: ServerMessage) => {
    const payload = msg.payload as ProjectAgentEventPayload;
    projects.onProjectEvent(payload);
    void syncProject(payload.project.project_id);
  });
  client.on(EventType.PROJECT_AGENT_REMOVED, (msg: ServerMessage) => {
    const payload = msg.payload as ProjectAgentEventPayload;
    projects.onProjectEvent(payload);
    if (!payload.agent_id) return;
    const target: AgentTarget = {
      projectId: payload.project.project_id,
      agentId: payload.agent_id,
      agentName: payload.agent_name,
    };
    agents.removeAgent(target);
    clearAgentDerived(target);
  });
  client.on(EventType.PROJECT_ARCHIVED, (msg: ServerMessage) => {
    const payload = msg.payload as ProjectEventPayload;
    projects.onProjectEvent(payload);
    clearProjectDerived(payload.project.project_id);
  });
  client.on(EventType.PROJECT_RESTORED, (msg: ServerMessage) => {
    const payload = msg.payload as ProjectEventPayload;
    projects.onProjectEvent(payload);
    clearProjectDerived(payload.project.project_id);
    void syncProject(payload.project.project_id);
  });
  client.on(EventType.PROJECT_DELETED, (msg: ServerMessage) => {
    const payload = msg.payload as ProjectEventPayload;
    clearProjectDerived(payload.project.project_id);
    projects.onProjectDeleted(payload);
  });

  client.on(EventType.SESSION_CREATED, (msg: ServerMessage) =>
    sessions.onSessionCreated(msg.payload as SessionCreatedPayload),
  );
  client.on(EventType.SESSION_ACTIVATED, (msg: ServerMessage) =>
    sessions.onSessionActivated(msg.payload as SessionActivatedPayload),
  );
  const removeSession = (msg: ServerMessage) => {
    const target = sessions.removeSession(
      msg.payload as SessionArchivedPayload | SessionDeletedPayload,
    );
    if (!target) return;
    branches.clearSession(target);
    chains.clearSession(target);
  };
  client.on(EventType.SESSION_ARCHIVED, removeSession);
  client.on(EventType.SESSION_DELETED, removeSession);
  client.on(EventType.SESSION_LIST_RESULT, (msg: ServerMessage) => {
    const payload = msg.payload as SessionListResultPayload;
    if (!payload.project_id || !payload.agent_id || !payload.agent_name) return;
    sessions.replaceAgentSessions(
      {
        projectId: payload.project_id,
        agentId: payload.agent_id,
        agentName: payload.agent_name,
      },
      payload.sessions,
    );
  });

  client.on(EventType.BRANCH_CREATED, (msg: ServerMessage) =>
    branches.onBranchCreated(msg.payload as BranchEventPayload),
  );
  client.on(EventType.BRANCH_ACTIVATED, (msg: ServerMessage) =>
    branches.onBranchActivated(msg.payload as BranchEventPayload),
  );
  const removeBranch = (msg: ServerMessage) => {
    const target = branches.removeBranch(msg.payload as BranchLifecyclePayload);
    if (target) chains.clearChain(target);
  };
  client.on(EventType.BRANCH_ARCHIVED, removeBranch);
  client.on(EventType.BRANCH_DELETED, removeBranch);
  client.on(EventType.BRANCH_LIST_RESULT, (msg: ServerMessage) => {
    const payload = msg.payload as BranchListResultPayload;
    if (!payload.project_id || !payload.agent_id || !payload.agent_name || !payload.session_id) {
      return;
    }
    branches.replaceSessionBranches(
      {
        projectId: payload.project_id,
        agentId: payload.agent_id,
        agentName: payload.agent_name,
        sessionId: payload.session_id,
      },
      payload.branches,
    );
  });

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
  for (const eventType of taskEventTypes) {
    client.on(eventType, (msg: ServerMessage) =>
      tasks.onTaskEvent(eventType, msg.payload as TaskEventPayload),
    );
  }

  const eventTypes = [
    EventType.AGENT_SPAWNED,
    EventType.AGENT_TERMINATED,
    EventType.ACTION_CHAIN_UPDATED,
    EventType.CONTEXT_USAGE_UPDATED,
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
    EventType.ROOM_ARCHIVED,
    EventType.ROOM_RESTORED,
    EventType.ROOM_DELETED,
    EventType.ROOM_MEMBER_JOINED,
    EventType.ROOM_MEMBER_LEFT,
    EventType.ROOM_LOG_APPENDED,
    EventType.PROJECT_CREATED,
    EventType.PROJECT_UPDATED,
    EventType.PROJECT_ARCHIVED,
    EventType.PROJECT_RESTORED,
    EventType.PROJECT_PAUSED,
    EventType.PROJECT_RESUMED,
    EventType.PROJECT_STOPPED,
    EventType.PROJECT_RECOVERY_SET,
    EventType.PROJECT_AGENT_ADDED,
    EventType.PROJECT_AGENT_REMOVED,
    EventType.PROJECT_DELETED,
    EventType.SESSION_CREATED,
    EventType.SESSION_ACTIVATED,
    EventType.SESSION_ARCHIVED,
    EventType.SESSION_DELETED,
    EventType.SESSION_LIST_RESULT,
    EventType.BRANCH_CREATED,
    EventType.BRANCH_ACTIVATED,
    EventType.BRANCH_ARCHIVED,
    EventType.BRANCH_DELETED,
    EventType.BRANCH_LIST_RESULT,
    ...taskEventTypes,
  ] as const;

  async function syncProject(projectId: string) {
    if (!projects.isProjectOperable(projectId)) return;
    await Promise.all([
      client.listAgents(projectId).catch(() => undefined),
      client.listRooms(projectId, "active").catch(() => undefined),
    ]);
  }

  async function syncAgentActionState(agentList: AgentTarget[]) {
    await Promise.all(
      agentList.map(async (agentTarget) => {
        try {
          const sessionResult = await client.listSessions(agentTarget);
          const sessionData = sessionResult.data as Record<string, unknown> | null;
          if (!sessionResult.success || !Array.isArray(sessionData?.sessions)) return;
          const oldSessions = sessions.sessionsForAgent(agentTarget);
          const sessionList = sessionData.sessions as SessionInfoPayload[];
          sessions.replaceAgentSessions(agentTarget, sessionList);
          const sessionIds = new Set(sessionList.map((session) => session.session_id));
          for (const stale of oldSessions) {
            if (sessionIds.has(stale.target.sessionId)) continue;
            branches.clearSession(stale.target);
            chains.clearSession(stale.target);
          }

          await Promise.all(
            sessionList.map(async (sessionInfo) => {
              const sessionTarget: SessionTarget = {
                ...agentTarget,
                sessionId: sessionInfo.session_id,
              };
              const branchResult = await client.listBranches(sessionTarget);
              const branchData = branchResult.data as Record<string, unknown> | null;
              if (!branchResult.success || !Array.isArray(branchData?.branches)) return;
              const oldBranches = branches.branchesForSession(sessionTarget);
              const branchList = branchData.branches as BranchInfoPayload[];
              branches.replaceSessionBranches(
                sessionTarget,
                branchList,
                sessionInfo.active_branch_id || null,
              );
              const branchIds = new Set(branchList.map((branch) => branch.branch_id));
              for (const stale of oldBranches) {
                if (!branchIds.has(stale.target.branchId)) chains.clearChain(stale.target);
              }

              await Promise.all(
                branchList.map(async (branchInfo) => {
                  const target: ChainTarget = {
                    ...sessionTarget,
                    branchId: branchInfo.branch_id,
                  };
                  const history = await client.getChainHistory(target);
                  const historyData = history.data as Record<string, unknown> | null;
                  if (!history.success || !Array.isArray(historyData?.nodes)) return;
                  chains.setChain(target, historyData.nodes as ActionNode[]);
                  const activeSessionId = stringField(historyData.active_session_id);
                  if (activeSessionId) sessions.setActiveSession(agentTarget, activeSessionId);
                }),
              );
            }),
          );
        } catch {
          // One Agent read failure does not invalidate already projected state.
        }
      }),
    );
  }

  return () => {
    for (const eventType of eventTypes) client.off(eventType);
    client.off(SystemType.COMMAND_RESULT);
    client.clearLifecycleCallbacks();
    batcher.cancel();
  };
}
