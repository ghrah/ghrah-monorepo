<script setup lang="ts">
import type { HitlRequest } from "@ghrah/observer-core";

defineProps<{
  request: HitlRequest;
}>();

const emit = defineEmits<{
  approve: [promiseId: string];
  reject: [promiseId: string];
}>();
</script>

<template>
  <li class="hitl-request-item">
    <span class="ability">{{ request.abilityName }}</span>
    <span class="agent">{{ request.agentName }}</span>
    <div class="actions">
      <button class="approve" @click="emit('approve', request.promiseId)">Approve</button>
      <button class="reject" @click="emit('reject', request.promiseId)">Reject</button>
    </div>
  </li>
</template>

<style scoped>
.hitl-request-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0;
  font-size: 0.875rem;
}

.ability {
  font-weight: 500;
}

.agent {
  color: #666;
}

.actions {
  margin-left: auto;
  display: flex;
  gap: 0.25rem;
}

.approve {
  padding: 0.25rem 0.5rem;
  border: none;
  border-radius: 4px;
  background: #28a745;
  color: white;
  cursor: pointer;
  font-size: 0.75rem;
}

.reject {
  padding: 0.25rem 0.5rem;
  border: none;
  border-radius: 4px;
  background: #dc3545;
  color: white;
  cursor: pointer;
  font-size: 0.75rem;
}
</style>
