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
  <div class="app-frame h-screen flex flex-col text-gray-900 dark:text-gray-100">
    <header class="app-header">
      <div class="brand-lockup">
        <span class="brand-mark">G</span>
        <div>
          <h1>Ghrah</h1>
          <span>Agent workspace</span>
        </div>
        <span :class="['badge', statusClass[connection.state]]">
          <span :class="['inline-block w-2 h-2 rounded-full mr-1', statusDot[connection.state]]" />
          {{ statusText[connection.state] }}
        </span>
      </div>
      <nav class="top-nav">
        <RouterLink to="/" :class="['px-3 py-1 rounded transition-colors', route.path === '/' ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200 font-medium' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800']">Dashboard</RouterLink>
        <RouterLink to="/changes" :class="['px-3 py-1 rounded transition-colors', route.path === '/changes' ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200 font-medium' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800']">Changes</RouterLink>
        <RouterLink to="/config" :class="['px-3 py-1 rounded transition-colors', route.path.startsWith('/config') ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200 font-medium' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800']">Config</RouterLink>
      </nav>
      <div class="connection-tools">
        <span class="server-address">{{ connection.serverUrl }}</span>
        <button
          v-if="connection.state === 'connected'"
          class="btn-secondary"
          @click="disconnect"
        >
          Disconnect
        </button>
        <button
          v-else
          class="btn-primary"
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
