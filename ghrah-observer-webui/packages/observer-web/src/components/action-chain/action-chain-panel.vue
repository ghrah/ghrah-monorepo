<script setup lang="ts">
import { useActionChainsStore, useAgentsStore } from "@ghrah/observer-core";
import { computed } from "vue";
import ActionNodeRow from "./action-node.vue";
import { buildTree, type TreeRow } from "./build-tree.js";

const chains = useActionChainsStore();
const agents = useAgentsStore();

const selectedAgentName = computed(() => agents.selectedAgentName);

const rows = computed<TreeRow[]>(() => {
  const name = selectedAgentName.value;
  if (!name) return [];
  return buildTree(chains.getChain(name));
});
</script>

<template>
  <div class="p-3 h-full flex flex-col">
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Action Chain</h3>
      <span v-if="selectedAgentName" class="text-xs text-gray-500 dark:text-gray-400">@{{ selectedAgentName }}</span>
    </div>

    <div v-if="!selectedAgentName" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-600 text-sm italic">
      Select an agent to view its action chain
    </div>

    <div v-else-if="rows.length === 0" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-600 text-sm italic">
      No actions yet
    </div>

    <div v-else class="flex-1 overflow-y-auto">
      <div class="border border-gray-200 dark:border-gray-700 rounded">
        <div class="px-2 py-1 bg-gray-50 dark:bg-gray-800 text-xs font-semibold text-gray-600 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
          @{{ selectedAgentName }}
        </div>
        <div class="px-1 py-1">
          <ActionNodeRow
            v-for="(row, i) in rows"
            :key="`${selectedAgentName}-${row.node.id}-${i}`"
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
