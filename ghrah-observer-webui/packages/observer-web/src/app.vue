<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import { useObserver } from "@/composables/useObserver";

const route = useRoute();
const { connection, error, autoConnect, disconnect } = useObserver();

onMounted(async () => {
  await autoConnect();
});

onUnmounted(() => {
  disconnect();
});

const statusClass: Record<string, string> = {
  connected: "bg-green-200 text-green-900",
  connecting: "bg-yellow-200 text-yellow-900",
  reconnecting: "bg-yellow-200 text-yellow-900",
  disconnected: "bg-red-200 text-red-900",
};

const statusDot: Record<string, string> = {
  connected: "bg-green-500",
  connecting: "bg-yellow-500 animate-pulse",
  reconnecting: "bg-yellow-500 animate-pulse",
  disconnected: "bg-red-500",
};

const statusText: Record<string, string> = {
  connected: "Connected",
  connecting: "Connecting...",
  reconnecting: "Reconnecting...",
  disconnected: "Disconnected",
};
</script>

<template>
  <div class="h-screen flex flex-col bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100">
    <header class="flex items-center justify-between px-4 py-2 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
      <div class="flex items-center gap-3">
        <h1 class="text-lg font-bold tracking-tight">Ghrah Observer</h1>
        <span :class="['badge', statusClass[connection.state]]">
          <span :class="['inline-block w-2 h-2 rounded-full mr-1', statusDot[connection.state]]" />
          {{ statusText[connection.state] }}
        </span>
      </div>
      <nav class="flex gap-1 text-sm">
        <RouterLink to="/" :class="['px-3 py-1 rounded transition-colors', route.path === '/' ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200 font-medium' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800']">Dashboard</RouterLink>
        <RouterLink to="/config" :class="['px-3 py-1 rounded transition-colors', route.path.startsWith('/config') ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200 font-medium' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800']">Config</RouterLink>
      </nav>
      <div class="flex items-center gap-2 text-sm">
        <span class="text-gray-500 dark:text-gray-400 font-mono text-xs">{{ connection.gatewayUrl }}</span>
        <button
          v-if="connection.state === 'connected'"
          class="btn-secondary text-xs"
          @click="disconnect"
        >
          Disconnect
        </button>
        <button
          v-else
          class="btn-primary text-xs"
          :disabled="connection.state === 'connecting' || connection.state === 'reconnecting'"
          @click="autoConnect()"
        >
          Connect
        </button>
      </div>
    </header>
    <div v-if="error" class="px-4 py-1 bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 text-xs">
      {{ error }}
    </div>
    <main class="flex-1 min-h-0">
      <RouterView />
    </main>
  </div>
</template>