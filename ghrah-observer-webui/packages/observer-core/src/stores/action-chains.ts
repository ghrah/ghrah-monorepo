import type { ActionChainUpdatedPayload, ActionNode as WireActionNode } from "@ghrah/protocol";
import { defineStore } from "pinia";
import { ref } from "vue";

// 视图模型（lagging wire 契约）。protocol 的 WireActionNode 是 serialize_node 的真实
// wire 形态；本 stub 保留 ActionChain 视图（Phase E 重构前）消费的 legacy 字段形状。
// projectWireNodeToEntry 做 wire→视图的受控映射（不再用 as unknown as 双重强转）。
// Phase C/E 投影层落地后应删除本类型与映射。
export interface ActionChainEntry {
  ability_name: string;
  tool_args: Record<string, unknown>;
  success?: boolean;
  error?: string;
  timestamp?: number;
}

function projectWireNodeToEntry(node: WireActionNode): ActionChainEntry {
  // 取首个 action_result 派生视图字段（legacy 视图假设单 ability/节点）。
  const firstResult = node.action_results?.[0]?.action_result;
  const firstAbility = node.ability_names?.[0] ?? "";
  // 文件能力的 file_path 回填在 action_result.data；tool_args 无 wire 对应物，
  // 以 action_result.data 降级填充（供 action-node.vue 读 args.file_path）。
  const data = (firstResult?.data ?? {}) as Record<string, unknown>;
  return {
    ability_name: firstAbility,
    tool_args: data,
    success: firstResult?.outcome === undefined ? undefined : firstResult.outcome === "success",
    error: typeof data.error === "string" ? data.error : undefined,
    timestamp: node.timestamp ? Date.parse(node.timestamp) / 1000 : undefined,
  };
}

export const useActionChainsStore = defineStore("ghrah-action-chains", () => {
  const chains = ref<Map<string, ActionChainEntry[]>>(new Map());

  function onActionChainUpdated(payload: ActionChainUpdatedPayload) {
    const agentName = payload.agent_name;
    const existing = chains.value.get(agentName) ?? [];
    chains.value.set(agentName, [...existing, projectWireNodeToEntry(payload.node)]);
  }

  function getChain(agentName: string): ActionChainEntry[] {
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
