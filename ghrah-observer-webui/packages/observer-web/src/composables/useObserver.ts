import {
  connectStores,
  ObserverClient,
  useActionChainsStore,
  useAgentsStore,
  useChangesStore,
  useChatStore,
  useConnectionStore,
  useHitlStore,
} from "@ghrah/observer-core";
import type { AbilityDefinitionPayload, AgentConfigPayload } from "@ghrah/protocol";
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

  async function connect(gatewayUrl?: string) {
    const url = gatewayUrl ?? connection.gatewayUrl;
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
    return connect(connection.gatewayUrl);
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

  async function spawnAgent(config: AgentConfigPayload, abilities?: AbilityDefinitionPayload[]) {
    return withClient((c) => c.spawnAgent(config, abilities ?? null));
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

  return {
    client,
    connection,
    agents,
    actionChains,
    hitl,
    chat,
    changes,
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
  };
}
