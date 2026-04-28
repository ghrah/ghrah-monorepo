<script setup lang="ts">
defineProps<{
  abilityName: string;
  success?: boolean;
  timestamp?: number;
}>();
</script>

<template>
  <div class="action-node">
    <span class="icon">{{ success === true ? "✅" : success === false ? "❌" : "⏳" }}</span>
    <span class="name">{{ abilityName }}</span>
    <span v-if="timestamp" class="time">{{ new Date(timestamp * 1000).toLocaleTimeString() }}</span>
  </div>
</template>

<style scoped>
.action-node {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
  font-size: 0.875rem;
}

.icon {
  flex-shrink: 0;
}

.name {
  flex: 1;
}

.time {
  color: #999;
  font-size: 0.75rem;
}
</style>
