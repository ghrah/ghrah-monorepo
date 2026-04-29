import type {
  AbilityResultPayload,
  ActionChainUpdatedPayload,
  AgentConfigPayload,
  AgentResponsePayload,
  AgentSpawnedPayload,
  AgentTerminatedPayload,
  CommandResultPayload,
  GatewayMessage,
  HITLRequestPayload,
  ManifestAbilityEventPayload,
  ManifestAgentEventPayload,
} from "@ghrah/protocol";
import { EventType, SystemType } from "@ghrah/protocol";
import type { ObserverClient } from "./client.js";
import { useActionChainsStore } from "./stores/action-chains.js";
import { useAgentsStore } from "./stores/agents.js";
import { useChangesStore } from "./stores/changes.js";
import { useChatStore } from "./stores/chat.js";
import { useConnectionStore } from "./stores/connection.js";
import { useHitlStore } from "./stores/hitl.js";
import { useManifestsStore } from "./stores/manifests.js";

type AgentListItem = { name: string; config: AgentConfigPayload };

export function connectStores(client: ObserverClient): () => void {
  const connection = useConnectionStore();
  const agents = useAgentsStore();
  const chains = useActionChainsStore();
  const hitl = useHitlStore();
  const chat = useChatStore();
  const changes = useChangesStore();
  const manifests = useManifestsStore();

  const pendingToolArgs = new Map<string, Record<string, unknown>>();

  client.onConnected(() => {
    connection.setConnected();
    client.listAgents();
  });
  client.onDisconnected(() => connection.setDisconnected());
  client.onReconnecting(() => connection.setReconnecting());
  client.onReconnected(() => connection.setConnected());

  client.on(EventType.AGENT_SPAWNED, (msg: GatewayMessage) =>
    agents.onAgentSpawned(msg.payload as AgentSpawnedPayload),
  );
  client.on(EventType.AGENT_TERMINATED, (msg: GatewayMessage) =>
    agents.onAgentTerminated(msg.payload as AgentTerminatedPayload),
  );

  client.on(EventType.ACTION_CHAIN_UPDATED, (msg: GatewayMessage) => {
    const payload = msg.payload as ActionChainUpdatedPayload;
    chains.onActionChainUpdated(payload);
    const node = payload.node as Record<string, unknown> | undefined;
    if (node?.request_id) {
      pendingToolArgs.set(
        node.request_id as string,
        (node.tool_args ?? {}) as Record<string, unknown>,
      );
    }
  });

  client.on(EventType.HITL_REQUEST, (msg: GatewayMessage) => {
    const payload = msg.payload as HITLRequestPayload;
    hitl.onHitlRequest(payload);
    pendingToolArgs.set(payload.promise_id, payload.tool_args ?? {});
  });

  client.on(EventType.AGENT_RESPONSE, (msg: GatewayMessage) =>
    chat.onAgentResponse(msg.payload as AgentResponsePayload),
  );

  client.on(EventType.ABILITY_RESULT, (msg: GatewayMessage) => {
    const payload = msg.payload as AbilityResultPayload;
    const toolArgs = pendingToolArgs.get(payload.request_id);
    pendingToolArgs.delete(payload.request_id);
    changes.onAbilityResult(payload, toolArgs);
  });

  client.on(SystemType.COMMAND_RESULT, (msg: GatewayMessage) => {
    const payload = msg.payload as CommandResultPayload;
    if (!payload.success || !payload.data) return;
    const data = payload.data as Record<string, unknown>;
    if (Array.isArray(data.agents)) {
      agents.setAgentsFromList(data.agents as AgentListItem[]);
    }
  });

  client.on(EventType.AGENT_ERROR, (_msg: GatewayMessage) => {
    // Agent error: 后续可扩展 ErrorStore
  });

  client.on(EventType.MANIFEST_ABILITY_CREATED, (msg: GatewayMessage) =>
    manifests.onManifestAbilityCreated(msg.payload as ManifestAbilityEventPayload),
  );
  client.on(EventType.MANIFEST_ABILITY_UPDATED, (msg: GatewayMessage) =>
    manifests.onManifestAbilityInvalidated(msg.payload as ManifestAbilityEventPayload),
  );
  client.on(EventType.MANIFEST_ABILITY_DELETED, (msg: GatewayMessage) =>
    manifests.onManifestAbilityDeleted(msg.payload as ManifestAbilityEventPayload),
  );
  client.on(EventType.MANIFEST_AGENT_CREATED, (msg: GatewayMessage) =>
    manifests.onManifestAgentCreated(msg.payload as ManifestAgentEventPayload),
  );
  client.on(EventType.MANIFEST_AGENT_UPDATED, (msg: GatewayMessage) =>
    manifests.onManifestAgentInvalidated(msg.payload as ManifestAgentEventPayload),
  );
  client.on(EventType.MANIFEST_AGENT_DELETED, (msg: GatewayMessage) =>
    manifests.onManifestAgentDeleted(msg.payload as ManifestAgentEventPayload),
  );

  const eventTypes = [
    EventType.AGENT_SPAWNED,
    EventType.AGENT_TERMINATED,
    EventType.ACTION_CHAIN_UPDATED,
    EventType.HITL_REQUEST,
    EventType.AGENT_RESPONSE,
    EventType.ABILITY_RESULT,
    EventType.AGENT_ERROR,
    EventType.MANIFEST_ABILITY_CREATED,
    EventType.MANIFEST_ABILITY_UPDATED,
    EventType.MANIFEST_ABILITY_DELETED,
    EventType.MANIFEST_AGENT_CREATED,
    EventType.MANIFEST_AGENT_UPDATED,
    EventType.MANIFEST_AGENT_DELETED,
  ] as const;

  return () => {
    for (const et of eventTypes) client.off(et);
    client.off(SystemType.COMMAND_RESULT);
    client.clearLifecycleCallbacks();
    pendingToolArgs.clear();
  };
}
