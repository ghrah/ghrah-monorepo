<script setup lang="ts">
import { useActionChainsStore, useAgentsStore } from "@ghrah/observer-core";
import { computed, ref } from "vue";
import ActionNodeRow from "./action-node.vue";
import { buildTree, type TreeRow } from "./build-tree.js";

const chains = useActionChainsStore();
const agents = useAgentsStore();

const filterAgent = ref<string | null>(null);

interface AgentTree {
  agentName: string;
  rows: TreeRow[];
}

const trees = computed<AgentTree[]>(() => {
  const out: AgentTree[] = [];
  for (const [agentName, nodes] of chains.chains) {
    if (filterAgent.value !== null && agentName !== filterAgent.value) continue;
    out.push({ agentName, rows: buildTree(nodes) });
  }
  out.sort((a, b) => a.agentName.localeCompare(b.agentName));
  return out;
});

const hasAny = computed(() => chains.chains.size > 0);
</script>

<template>
  <div class="p-3 h-full flex flex-col">
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Action Chain</h3>
      <select
        v-model="filterAgent"
        class="text-xs bg-transparent border border-gray-300 dark:border-gray-600 rounded px-1 py-0.5"
        aria-label="Filter by agent"
      >
        <option :value="null">all</option>
        <option v-for="a in agents.activeAgents" :key="a.name" :value="a.name">{{ a.name }}</option>
      </select>
    </div>

    <div v-if="!hasAny" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-600 text-sm italic">
      No actions yet
    </div>

    <div v-else class="flex-1 overflow-y-auto space-y-3">
      <div v-for="tree in trees" :key="tree.agentName" class="border border-gray-200 dark:border-gray-700 rounded">
        <div class="px-2 py-1 bg-gray-50 dark:bg-gray-800 text-xs font-semibold text-gray-600 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
          @{{ tree.agentName }}
        </div>
        <div class="px-1 py-1">
          <ActionNodeRow
            v-for="(row, i) in tree.rows"
            :key="`${tree.agentName}-${row.node.id}-${i}`"
            :node="row.node"
            :depth="row.depth"
            :is-last-child="row.isLastChild"
            :ancestor-pipes="row.ancestorPipes"
          />
        </div>
      </div>
    </div>
  </div>
</template>
