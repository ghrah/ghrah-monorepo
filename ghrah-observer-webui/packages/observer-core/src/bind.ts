import type {
  AbilityResultPayload,
  ActionChainUpdatedPayload,
  AgentConfigPayload,
  AgentResponsePayload,
  AgentSpawnedPayload,
  AgentTerminatedPayload,
  CommandResultPayload,
  ServerMessage,
  HITLRequestPayload,
  ManifestAbilityEventPayload,
  ManifestAgentEventPayload,
} from "@ghrah/protocol";
import { CommandType, EventType, SystemType } from "@ghrah/protocol";
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
    chains.onActionChainUpdated(payload);
    const node = payload.node as Record<string, unknown> | undefined;
    if (node?.request_id) {
      pendingToolArgs.set(
        node.request_id as string,
        (node.tool_args ?? {}) as Record<string, unknown>,
      );
    }
  });

  client.on(EventType.HITL_REQUEST, (msg: ServerMessage) => {
    const payload = msg.payload as HITLRequestPayload;
    hitl.onHitlRequest(payload);
    pendingToolArgs.set(payload.promise_id, payload.tool_args ?? {});
  });

  client.on(EventType.AGENT_RESPONSE, (msg: ServerMessage) =>
    chat.onAgentResponse(msg.payload as AgentResponsePayload),
  );

  client.on(EventType.ABILITY_RESULT, (msg: ServerMessage) => {
    const payload = msg.payload as AbilityResultPayload;
    const toolArgs = pendingToolArgs.get(payload.request_id);
    pendingToolArgs.delete(payload.request_id);
    changes.onAbilityResult(payload, toolArgs);
  });

  client.on(SystemType.COMMAND_RESULT, (msg: ServerMessage) => {
    const payload = msg.payload as CommandResultPayload;
    if (!payload.success || !payload.data) return;
    const data = payload.data as Record<string, unknown>;
    const originalCommand = (payload as Record<string, unknown>).original_command as
      | string
      | undefined;
    if (originalCommand === CommandType.LIST_AGENTS && Array.isArray(data.agents)) {
      agents.setAgentsFromList(data.agents as AgentListItem[]);
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
