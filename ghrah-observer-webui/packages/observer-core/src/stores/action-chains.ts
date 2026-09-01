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

  /**
   * 初始同步（F2 刷新恢复）：用后端读回的完整链替换该 agent 的桶。
   * 与增量 onActionChainUpdated 幂等——以 node id 去重保序合并，
   * 避免刷新瞬间事件增量与读回并发产生重复节点。
   */
  function setChain(agentName: string, nodes: ActionNode[]) {
    const bucket = chains.value.get(agentName) ?? [];
    const seen = new Set(bucket.map((n) => n.id).filter((id): id is string => id != null));
    const merged = [...bucket];
    for (const node of nodes) {
      if (node.id && seen.has(node.id)) continue;
      if (node.id) seen.add(node.id);
      merged.push(node);
    }
    chains.value.set(agentName, merged);
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
    setChain,
    getChain,
    clearChain,
    clearAll,
  };
});
