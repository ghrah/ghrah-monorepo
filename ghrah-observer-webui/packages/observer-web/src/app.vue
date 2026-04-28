<script setup lang="ts">
import { useConnectionStore } from "@ghrah/observer-core";

const connection = useConnectionStore();
</script>

<template>
  <header class="app-header">
    <h1>Ghrah Observer</h1>
    <span :class="['connection-status', connection.state]">
      {{ connection.state }}
    </span>
  </header>
  <main>
    <RouterView />
  </main>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 1rem;
  border-bottom: 1px solid #ddd;
}

.connection-status {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.875rem;
}

.connection-status.connected {
  background: #d4edda;
  color: #155724;
}

.connection-status.disconnected,
.connection-status.reconnecting {
  background: #f8d7da;
  color: #721c24;
}

.connection-status.connecting {
  background: #fff3cd;
  color: #856404;
}
</style>
