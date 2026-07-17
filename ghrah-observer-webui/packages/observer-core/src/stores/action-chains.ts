import type { ActionChainUpdatedPayload, ActionNode } from "@ghrah/protocol";
import { defineStore } from "pinia";
import { ref } from "vue";

export const useActionChainsStore = defineStore("ghrah-action-chains", () => {
  const chains = ref<Map<string, ActionNode[]>>(new Map());

  function onActionChainUpdated(payload: ActionChainUpdatedPayload) {
    const agentName = payload.agent_name;
    const node = payload.node;
    if (!node) return;
    const bucket = chains.value.get(agentName) ?? [];
    if (node.id && bucket.some((n) => n.id === node.id)) return;
    chains.value.set(agentName, [...bucket, node]);
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
