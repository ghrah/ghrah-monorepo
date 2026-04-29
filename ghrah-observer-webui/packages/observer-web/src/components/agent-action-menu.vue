<script setup lang="ts">
import { useAgentsStore } from "@ghrah/observer-core";
import { ref } from "vue";
import { useObserver } from "@/composables/useObserver";

const agents = useAgentsStore();
const { terminateAgent, createWorkspace, workspaceSnapshot, workspaceDiff, error: observerError } = useObserver();

const showMenu = ref(false);
const loading = ref(false);
const errorMsg = ref<string | null>(null);

async function handleTerminate() {
  if (!agents.selectedAgentName) return;
  loading.value = true;
  errorMsg.value = null;
  const result = await terminateAgent(agents.selectedAgentName);
  loading.value = false;
  if (result === null) {
    errorMsg.value = observerError.value ?? "Not connected to gateway";
  } else if (result && !result.success) {
    errorMsg.value = result.error ?? "Failed to terminate agent";
  } else {
    showMenu.value = false;
  }
}

async function handleCreateWorkspace() {
  if (!agents.selectedAgentName) return;
  loading.value = true;
  errorMsg.value = null;
  const result = await createWorkspace(agents.selectedAgentName);
  loading.value = false;
  if (result && !result.success) {
    errorMsg.value = result.error ?? "Failed to create workspace";
  } else if (result === null) {
    errorMsg.value = observerError.value ?? "Not connected to gateway";
  } else {
    showMenu.value = false;
  }
}

async function handleSnapshot() {
  if (!agents.selectedAgentName) return;
  loading.value = true;
  errorMsg.value = null;
  const result = await workspaceSnapshot(agents.selectedAgentName);
  loading.value = false;
  if (result === null) {
    errorMsg.value = observerError.value ?? "Not connected to gateway";
  } else if (result && !result.success) {
    errorMsg.value = result.error ?? "Failed to create snapshot";
  } else {
    showMenu.value = false;
  }
}

async function handleDiff() {
  if (!agents.selectedAgentName) return;
  loading.value = true;
  errorMsg.value = null;
  const result = await workspaceDiff(agents.selectedAgentName);
  loading.value = false;
  if (result && !result.success) {
    errorMsg.value = result.error ?? "Failed to get workspace diff";
  } else if (result === null) {
    errorMsg.value = observerError.value ?? "Not connected to gateway";
  }
  showMenu.value = false;
}

function close() {
  showMenu.value = false;
  errorMsg.value = null;
}
</script>

<template>
  <div v-if="agents.selectedAgentName" class="relative">
    <button
      class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-lg px-1"
      title="Agent actions"
      @click="showMenu = !showMenu"
    >
      &#8943;
    </button>

    <div v-if="showMenu" class="absolute left-0 top-full mt-1 w-52 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded shadow-lg z-40">
      <div class="px-3 py-2 text-xs text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-800">
        {{ agents.selectedAgentName }}
      </div>

      <div v-if="errorMsg" class="px-3 py-1 text-xs text-red-600 dark:text-red-400">
        {{ errorMsg }}
      </div>

      <button class="w-full text-left px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50" :disabled="loading" @click="handleCreateWorkspace">
        Create Workspace
      </button>
      <button class="w-full text-left px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50" :disabled="loading" @click="handleSnapshot">
        Workspace Snapshot
      </button>
      <button class="w-full text-left px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50" :disabled="loading" @click="handleDiff">
        Workspace Diff
      </button>
      <div class="border-t border-gray-100 dark:border-gray-800" />
      <button class="w-full text-left px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 disabled:opacity-50" :disabled="loading" @click="handleTerminate">
        Terminate Agent
      </button>
      <div class="border-t border-gray-100 dark:border-gray-800" />
      <button class="w-full text-left px-3 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800" @click="close">
        Close
      </button>
    </div>

    <div v-if="showMenu" class="fixed inset-0 z-30" @click="close" />
  </div>
</template>