import {
  type AbilityManifestInfo,
  type AgentManifestInfo,
  connectStores,
  extractAbilityList,
  extractAgentList,
  extractManifestEntry,
  extractValidationResult,
  ObserverClient,
  useActionChainsStore,
  useAgentsStore,
  useChangesStore,
  useChatStore,
  useConnectionStore,
  useHitlStore,
  useManifestsStore,
} from "@ghrah/observer-core";
import type { AgentConfigPayload } from "@ghrah/protocol";
import { ref, shallowRef } from "vue";

const client = shallowRef<ObserverClient | null>(null);
const error = ref<string | null>(null);
let unbind: (() => void) | null = null;

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

  async function sendMessage(content: string) {
    if (!agents.selectedAgentName) return null;
    return withClient((c) => c.sendMessage(agents.selectedAgentName!, content));
  }

  async function sendHitlResponse(promiseId: string, approved: boolean, reason?: string) {
    const result = await withClient((c) => c.sendHitlResponse(promiseId, approved, reason));
    if (result !== null) {
      hitl.removeRequest(promiseId);
    }
  }

  async function spawnAgent(config: AgentConfigPayload, manifestRef?: string | null) {
    return withClient((c) => c.spawnAgent(config, null, manifestRef ?? null));
  }

  async function terminateAgent(name: string) {
    return withClient((c) => c.terminateAgent(name));
  }

  async function createWorkspace(agentName: string) {
    return withClient((c) => c.createWorkspace(agentName));
  }

  async function workspaceSnapshot(agentName: string, message = "") {
    return withClient((c) => c.workspaceSnapshot(agentName, message));
  }

  async function workspaceDiff(agentName: string, snapshotId?: string | null) {
    return withClient((c) => c.workspaceDiff(agentName, snapshotId ?? undefined));
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
        errors: [result.error ?? "Validation failed"],
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
