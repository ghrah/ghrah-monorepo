<script setup lang="ts">
import { useActionChainsStore, useAgentsStore } from "@ghrah/observer-core";
import { computed } from "vue";
import ActionNode from "./action-node.vue";

const chains = useActionChainsStore();
const agents = useAgentsStore();

const selectedChain = computed(() => {
  if (!agents.selectedAgentName) return [];
  return chains.getChain(agents.selectedAgentName);
});
</script>

<template>
  <div class="p-3 h-full flex flex-col">
    <h3 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">Action Chain</h3>

    <div v-if="!agents.selectedAgentName" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-600 text-sm italic">
      Select an agent
    </div>

    <div v-else-if="selectedChain.length === 0" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-600 text-sm italic">
      No actions yet
    </div>

    <div v-else class="flex-1 overflow-y-auto space-y-1">
      <ActionNode v-for="(node, i) in selectedChain" :key="i" :node="node" />
    </div>
  </div>
</template>