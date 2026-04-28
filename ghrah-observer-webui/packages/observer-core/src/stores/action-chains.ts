import type { ActionChainUpdatedPayload } from "@ghrah/protocol";
import { defineStore } from "pinia";
import { ref } from "vue";

export interface ActionNode {
  ability_name: string;
  tool_args: Record<string, unknown>;
  success?: boolean;
  error?: string;
  timestamp?: number;
}

export const useActionChainsStore = defineStore("ghrah-action-chains", () => {
  const chains = ref<Map<string, ActionNode[]>>(new Map());

  function onActionChainUpdated(payload: ActionChainUpdatedPayload) {
    const agentName = payload.agent_name;
    const existing = chains.value.get(agentName) ?? [];
    chains.value.set(agentName, [...existing, payload.node as unknown as ActionNode]);
  }

  function getChain(agentName: string): ActionNode[] {
    return chains.value.get(agentName) ?? [];
  }

  function clearChain(agentName: string) {
    chains.value.delete(agentName);
  }

  function clearAll() {
    chains.value.clear();
  }

  return {
    chains,
    onActionChainUpdated,
    getChain,
    clearChain,
    clearAll,
  };
});
