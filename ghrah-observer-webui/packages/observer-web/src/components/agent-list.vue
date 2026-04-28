<script setup lang="ts">
import { useAgentsStore } from "@ghrah/observer-core";

const agents = useAgentsStore();
</script>

<template>
  <div class="agent-list">
    <h3>Agents</h3>
    <ul>
      <li v-for="agent in agents.activeAgents" :key="agent.name" class="agent-item">
        <span class="agent-name">{{ agent.name }}</span>
        <span class="agent-status">{{ agent.status }}</span>
      </li>
    </ul>
    <p v-if="agents.activeAgents.length === 0" class="empty">No active agents</p>
  </div>
</template>

<style scoped>
.agent-list {
  padding: 0.5rem;
}

.agent-list h3 {
  margin: 0 0 0.5rem;
}

.agent-item {
  display: flex;
  justify-content: space-between;
  padding: 0.25rem 0;
}

.agent-name {
  font-weight: 500;
}

.agent-status {
  font-size: 0.75rem;
  color: #28a745;
}

.empty {
  color: #999;
  font-size: 0.875rem;
}
</style>
