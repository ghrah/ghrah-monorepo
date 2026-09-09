import {
  type AbilityManifestInfo,
  type AgentManifestInfo,
  type AgentTarget,
  type CreateProjectOptions,
  connectStores,
  extractAbilityList,
  extractAgentList,
  extractManifestEntry,
  extractValidationResult,
  type ListProjectsOptions,
  ObserverClient,
  useActionChainsStore,
  useAgentsStore,
  useChangesStore,
  useChatStore,
  useConnectionStore,
  useHitlStore,
  useManifestsStore,
  useProjectsStore,
  useRoomsStore,
} from "@ghrah/observer-core";
import type { AgentConfigPayload } from "@ghrah/protocol";
import { ref, shallowRef, watch } from "vue";
import { i18n } from "@/i18n";

const client = shallowRef<ObserverClient | null>(null);
const error = ref<string | null>(null);
let unbind: (() => void) | null = null;

// ── 导航状态持久化（active project/room → localStorage） ──

const NAV_STORAGE_KEY = "ghrah-nav";
let navPersistenceStarted = false;

interface NavState {
  projectId: string | null;
  roomId: string | null;
}

function readNavState(): NavState | null {
  try {
    const raw = localStorage.getItem(NAV_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<NavState>;
    return {
      projectId: typeof parsed.projectId === "string" ? parsed.projectId : null,
      roomId: typeof parsed.roomId === "string" ? parsed.roomId : null,
    };
  } catch {
    return null;
  }
}

async function withClient<T>(fn: (c: ObserverClient) => Promise<T>): Promise<T | null> {
  if (!client.value) return null;
  try {
    return await fn(client.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    return null;
  }
}

export function useObserver() {
  const connection = useConnectionStore();
  const agents = useAgentsStore();
  const actionChains = useActionChainsStore();
  const hitl = useHitlStore();
  const chat = useChatStore();
  const changes = useChangesStore();
  const manifests = useManifestsStore();
  const rooms = useRoomsStore();
  const projects = useProjectsStore();

  // 首次使用时注册持久化 watch（需在 active pinia 语境下调用）。
  if (!navPersistenceStarted && typeof localStorage !== "undefined") {
    navPersistenceStarted = true;
    watch([() => projects.activeProjectId, () => rooms.activeRoomId], ([projectId, roomId]) => {
      try {
        localStorage.setItem(NAV_STORAGE_KEY, JSON.stringify({ projectId, roomId }));
      } catch {
        // 忽略存储失败（如隐私模式）
      }
    });
  }

  async function connect(serverUrl?: string) {
    const url = serverUrl ?? connection.serverUrl;

    if (client.value) {
      unbind?.();
      unbind = null;
      await client.value.disconnect();
      client.value = null;
    }

    connection.setConnecting();
    error.value = null;

    try {
      const obsClient = new ObserverClient(url);
      unbind = connectStores(obsClient);

      await obsClient.connect();
      client.value = obsClient;

      // 初始同步完成后恢复持久化的 active project/room。
      const saved = readNavState();
      if (saved?.projectId && projects.projects.has(saved.projectId)) {
        projects.setActiveProject(saved.projectId);
      }
      if (saved?.roomId && rooms.rooms.has(saved.roomId)) {
        await switchRoom(saved.roomId);
      }
    } catch (err) {
      connection.setDisconnected();
      error.value = err instanceof Error ? err.message : String(err);
    }
  }

  async function disconnect() {
    if (client.value) {
      unbind?.();
      unbind = null;
      await client.value.disconnect();
      client.value = null;
    }
    connection.setDisconnected();
  }

  async function autoConnect() {
    return connect(connection.serverUrl);
  }

  async function sendMessage(target: string, content: string) {
    if (!target) return null;
    const agentTarget = resolveAgentTarget(target);
    if (!agentTarget) return null;
    return withClient((c) => c.sendMessage(agentTarget, content));
  }

  async function sendHitlResponse(promiseId: string, approved: boolean, reason?: string) {
    const result = await withClient((c) => c.sendHitlResponse(promiseId, approved, reason));
    if (result !== null) {
      hitl.removeRequest(promiseId);
    }
  }

  async function spawnAgent(config: AgentConfigPayload, manifestRef?: string | null) {
    const projectId = projects.activeProjectId;
    if (!projectId) return null;
    return withClient((c) => c.spawnAgent(projectId, config, null, manifestRef ?? null));
  }

  async function terminateAgent(name: string) {
    const target = resolveAgentTarget(name);
    return target ? withClient((c) => c.terminateAgent(target)) : null;
  }

  async function createWorkspace(agentName: string) {
    const target = resolveAgentTarget(agentName);
    return target ? withClient((c) => c.createWorkspace(target)) : null;
  }

  async function workspaceSnapshot(agentName: string, message = "") {
    const target = resolveAgentTarget(agentName);
    return target ? withClient((c) => c.workspaceSnapshot(target, message)) : null;
  }

  async function workspaceDiff(agentName: string, snapshotId?: string | null) {
    const target = resolveAgentTarget(agentName);
    return target ? withClient((c) => c.workspaceDiff(target, snapshotId ?? undefined)) : null;
  }

  function resolveAgentTarget(agentName: string): AgentTarget | null {
    const projectId = projects.activeProjectId;
    const agent = agents.agents.get(agentName);
    const agentId = agent?.agentId || agent?.config.agent_id;
    if (!projectId || !agentId) return null;
    return { projectId, agentId, agentName };
  }

  // ── Room / Project / 导航 ──

  /** 人类向 room 发消息（author 默认对齐 DEFAULT_HUMAN_AUTHOR）。 */
  async function roomSend(roomId: string, content: string, targets?: string[]) {
    return withClient((c) =>
      c.roomSend(roomId, {
        message: content,
        ...(targets && targets.length > 0 ? { targets } : {}),
      }),
    );
  }

  async function listRooms(projectId?: string | null) {
    return withClient((c) => c.listRooms(projectId ?? undefined));
  }

  async function createRoom(projectId: string, name: string) {
    return withClient((c) => c.createRoom(projectId, name));
  }

  async function joinRoom(
    roomId: string,
    subject: string,
    subjectType: "agent" | "human",
    subjectName?: string,
  ) {
    return withClient((c) => c.joinRoom(roomId, subject, subjectType, subjectName));
  }

  async function leaveRoom(roomId: string, subject: string) {
    return withClient((c) => c.leaveRoom(roomId, subject));
  }

  /** 拉取 room 历史；bind 的 ROOM_GET_LOG 处理会把结果灌入 rooms store。 */
  async function getRoomLog(roomId: string) {
    const result = await withClient((c) => c.getRoomLog(roomId));
    // 空历史时 bind 无法从 entries 反推 room_id，这里补灌空缓存避免重复拉取。
    if (result?.success && !rooms.logs.has(roomId)) {
      rooms.setRoomLog(roomId, []);
    }
    return result;
  }

  async function listProjects(options: ListProjectsOptions = {}) {
    return withClient((c) => c.listProjects(options));
  }

  async function createProject(name: string, options: CreateProjectOptions) {
    return withClient((c) => c.createProject(name, options));
  }

  /** 切换 active room；缓存缺失时拉历史。 */
  async function switchRoom(roomId: string | null) {
    rooms.setActiveRoom(roomId);
    if (roomId !== null && !rooms.logs.has(roomId)) {
      await getRoomLog(roomId);
    }
  }

  function switchProject(projectId: string | null) {
    projects.setActiveProject(projectId);
  }

  function selectAgent(name: string | null) {
    agents.selectAgent(name);
  }

  // ── Manifest: Ability ──

  async function listManifestAbilities(namespace?: string | null) {
    const result = await withClient((c) => c.listManifestAbilities(namespace));
    if (result?.success) {
      const abilities = extractAbilityList(result.data);
      if (abilities) manifests.setAbilities(abilities);
    }
    return result;
  }

  async function getAbility(fullName: string) {
    const result = await withClient((c) => c.getAbility(fullName));
    if (result?.success) {
      const entry = extractManifestEntry(result.data);
      if (entry) manifests.upsertAbility(entry as AbilityManifestInfo);
    }
    return result;
  }

  async function putAbility(fullName: string, content: string, overwrite?: boolean) {
    const result = await withClient((c) => c.putAbility(fullName, content, overwrite));
    if (result?.success) {
      const entry = extractManifestEntry(result.data);
      if (entry) manifests.upsertAbility(entry as AbilityManifestInfo);
    }
    return result;
  }

  async function deleteAbility(fullName: string) {
    const result = await withClient((c) => c.deleteAbility(fullName));
    if (result?.success) manifests.removeAbility(fullName);
    return result;
  }

  // ── Manifest: Agent ──

  async function listManifestAgents(namespace?: string | null) {
    manifests.agentsLoading = true;
    try {
      const result = await withClient((c) => c.listManifestAgents(namespace));
      if (result?.success) {
        const agents = extractAgentList(result.data);
        if (agents) manifests.setAgents(agents);
      }
      return result;
    } finally {
      manifests.agentsLoading = false;
    }
  }

  async function getAgent(fullName: string) {
    const result = await withClient((c) => c.getAgent(fullName));
    if (result?.success) {
      const entry = extractManifestEntry(result.data);
      if (entry) manifests.upsertAgent(entry as AgentManifestInfo);
    }
    return result;
  }

  async function putAgent(fullName: string, content: string, overwrite?: boolean) {
    const result = await withClient((c) => c.putAgent(fullName, content, overwrite));
    if (result?.success) {
      const entry = extractManifestEntry(result.data);
      if (entry) manifests.upsertAgent(entry as AgentManifestInfo);
    }
    return result;
  }

  async function deleteAgent(fullName: string) {
    const result = await withClient((c) => c.deleteAgent(fullName));
    if (result?.success) manifests.removeAgent(fullName);
    return result;
  }

  // ── Manifest: Utility ──

  async function resolveAgent(agentFullName: string, runtimeName?: string | null) {
    return withClient((c) => c.resolveAgent(agentFullName, runtimeName));
  }

  async function validateManifest(content: string, manifestType: string) {
    manifests.setValidating(true);
    manifests.setValidationResult(null);
    const result = await withClient((c) => c.validateManifest(content, manifestType));
    manifests.setValidating(false);
    if (result?.success) {
      const vr = extractValidationResult(result.data);
      if (vr) {
        manifests.setValidationResult(vr);
      }
    } else if (result && !result.success) {
      manifests.setValidationResult({
        is_valid: false,
        errors: [result.error ?? i18n.global.t("common.validationFailed")],
      });
    }
    return result;
  }

  return {
    client,
    connection,
    agents,
    actionChains,
    hitl,
    chat,
    changes,
    manifests,
    rooms,
    projects,
    error,
    connect,
    disconnect,
    autoConnect,
    sendMessage,
    sendHitlResponse,
    spawnAgent,
    terminateAgent,
    createWorkspace,
    workspaceSnapshot,
    workspaceDiff,
    roomSend,
    listRooms,
    createRoom,
    joinRoom,
    leaveRoom,
    getRoomLog,
    listProjects,
    createProject,
    switchRoom,
    switchProject,
    selectAgent,
    listManifestAbilities,
    getAbility,
    putAbility,
    deleteAbility,
    listManifestAgents,
    getAgent,
    putAgent,
    deleteAgent,
    resolveAgent,
    validateManifest,
  };
}
