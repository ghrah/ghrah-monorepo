<script setup lang="ts">
import { useAgentsStore } from "@ghrah/observer-core";
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import MonacoDiff from "@/components/monaco-diff.vue";
import { useObserver } from "@/composables/useObserver";

const agents = useAgentsStore();
const { t } = useI18n();
const {
  terminateAgent,
  createWorkspace,
  workspaceSnapshot,
  workspaceDiff,
  error: observerError,
} = useObserver();

const showMenu = ref(false);
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const showDiff = ref(false);
const diffPatch = ref<string>("");

async function handleTerminate() {
  if (!agents.selectedAgentName) return;
  loading.value = true;
  errorMsg.value = null;
  const result = await terminateAgent(agents.selectedAgentName);
  loading.value = false;
  if (result === null) {
    errorMsg.value = observerError.value ?? t("agents.notConnected");
  } else if (result && !result.success) {
    errorMsg.value = result.error ?? t("agents.terminateFailed");
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
    errorMsg.value = result.error ?? t("agents.workspaceFailed");
  } else if (result === null) {
    errorMsg.value = observerError.value ?? t("agents.notConnected");
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
    errorMsg.value = observerError.value ?? t("agents.notConnected");
  } else if (result && !result.success) {
    errorMsg.value = result.error ?? t("agents.snapshotFailed");
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
  if (result === null) {
    errorMsg.value = observerError.value ?? t("agents.notConnected");
    return;
  }
  if (result && !result.success) {
    errorMsg.value = result.error ?? t("agents.diffFailed");
    return;
  }
  const data = (result?.data ?? {}) as Record<string, unknown>;
  const patch = typeof data.diff === "string" ? data.diff : "";
  diffPatch.value = patch;
  showDiff.value = true;
  showMenu.value = false;
}

function closeDiff() {
  showDiff.value = false;
  diffPatch.value = "";
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
      :title="t('agents.actions')"
      @click="showMenu = !showMenu"
    >
      &#8943;
    </button>

    <div v-if="showMenu" class="absolute right-0 top-full mt-1 w-52 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded shadow-lg z-40">
      <div class="px-3 py-2 text-xs text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-800">
        {{ agents.selectedAgentName }}
      </div>

      <div v-if="errorMsg" class="px-3 py-1 text-xs text-red-600 dark:text-red-400">
        {{ errorMsg }}
      </div>

      <button class="w-full text-left px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50" :disabled="loading" @click="handleCreateWorkspace">
        {{ t("agents.createWorkspace") }}
      </button>
      <button class="w-full text-left px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50" :disabled="loading" @click="handleSnapshot">
        {{ t("agents.workspaceSnapshot") }}
      </button>
      <button class="w-full text-left px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50" :disabled="loading" @click="handleDiff">
        {{ t("agents.workspaceDiff") }}
      </button>
      <div class="border-t border-gray-100 dark:border-gray-800" />
      <button class="w-full text-left px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 disabled:opacity-50" :disabled="loading" @click="handleTerminate">
        {{ t("agents.terminateAgent") }}
      </button>
      <div class="border-t border-gray-100 dark:border-gray-800" />
      <button class="w-full text-left px-3 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800" @click="close">
        {{ t("common.close") }}
      </button>
    </div>

    <div v-if="showMenu" class="fixed inset-0 z-30" @click="close" />

    <div v-if="showDiff" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="closeDiff">
      <div class="bg-white dark:bg-gray-900 rounded shadow-lg w-[90vw] h-[80vh] flex flex-col">
        <div class="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-700">
          <span class="text-sm font-semibold">{{ t("agents.diffTitle", { name: agents.selectedAgentName }) }}</span>
          <button type="button" class="btn-secondary" @click="closeDiff">{{ t("common.close") }}</button>
        </div>
        <div class="flex-1 min-h-0">
          <MonacoDiff :patch="diffPatch" />
        </div>
      </div>
    </div>
  </div>
</template>