<script setup lang="ts">
import { useAgentsStore } from "@ghrah/observer-core";
import AgentActionMenu from "@/components/agent-action-menu.vue";

const agents = useAgentsStore();
</script>

<template>
  <div class="p-3 h-full flex flex-col">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Agents</h3>
      <RouterLink to="/config/agents" class="btn-primary text-xs">+ Spawn</RouterLink>
    </div>

    <ul v-if="agents.activeAgents.length > 0" class="flex-1 overflow-y-auto space-y-1">
      <li
        v-for="agent in agents.activeAgents"
        :key="agent.name"
        :class="[
          'flex items-center justify-between px-2 py-1.5 rounded cursor-pointer text-sm transition-colors',
          agents.selectedAgentName === agent.name
            ? 'bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100 font-medium'
            : 'hover:bg-gray-100 dark:hover:bg-gray-800',
        ]"
        @click="agents.selectAgent(agent.name)"
      >
        <span class="truncate">{{ agent.name }}</span>
        <div class="flex items-center gap-1">
          <AgentActionMenu v-if="agents.selectedAgentName === agent.name" />
          <span class="w-2 h-2 rounded-full bg-green-500 flex-shrink-0" />
        </div>
      </li>
    </ul>

    <p v-else class="text-gray-400 dark:text-gray-600 text-xs italic">No active agents</p>
  </div>
</template>