<script setup lang="ts">
import type { AgentManifestInfo } from "@ghrah/observer-core";
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import AgentManifestCard from "@/components/config/agent-manifest-card.vue";
import AgentManifestDetail from "@/components/config/agent-manifest-detail.vue";
import NewAgentManifestDialog from "@/components/config/new-agent-manifest-dialog.vue";
import SpawnFromManifestDialog from "@/components/config/spawn-from-manifest-dialog.vue";
import { useObserver } from "@/composables/useObserver";

const { manifests, listManifestAgents, deleteAgent } = useObserver();
const { t } = useI18n();

const selected = ref<AgentManifestInfo | null>(null);
const showSpawnDialog = ref(false);
const showNewDialog = ref(false);
const loading = ref(false);
const error = ref<string | null>(null);

onMounted(async () => {
  if (manifests.agentList.length === 0) {
    await listManifestAgents();
  }
});

function handleSelect(manifest: AgentManifestInfo) {
  selected.value = selected.value?.full_name === manifest.full_name ? null : manifest;
}

function handleSpawn(manifest: AgentManifestInfo) {
  selected.value = manifest;
  showSpawnDialog.value = true;
}

function handleEdit(manifest: AgentManifestInfo) {
  window.postMessage?.({ type: "openFile", fullName: manifest.full_name, kind: "agent" });
}

async function handleDelete(fullName: string) {
  if (!confirm(t("config.agent.deleteConfirm"))) return;
  loading.value = true;
  error.value = null;
  const result = await deleteAgent(fullName);
  loading.value = false;
  if (result && !result.success) {
    error.value = result.error ?? t("config.agent.deleteFailed");
  } else if (result === null) {
    error.value = t("config.agent.notConnected");
  }
  if (selected.value?.full_name === fullName) {
    selected.value = null;
  }
}
</script>

<template>
  <div class="flex flex-col h-full gap-4">
    <div class="flex items-center justify-between">
      <h2 class="text-lg font-semibold">{{ t("config.agent.title") }}</h2>
      <button class="btn-primary text-xs" @click="showNewDialog = true">{{ t("config.agent.newManifest") }}</button>
    </div>

    <div v-if="error" class="text-red-600 dark:text-red-400 text-sm">{{ error }}</div>

    <div v-if="manifests.agentsLoading" class="text-gray-400 text-sm py-4 text-center">{{ t("common.loading") }}</div>

    <div v-else-if="manifests.agentList.length === 0" class="text-gray-400 text-sm py-4 text-center italic">
      {{ t("config.agent.empty") }}
    </div>

    <div v-else class="grid grid-cols-2 gap-2">
      <AgentManifestCard
        v-for="m in manifests.agentList"
        :key="m.full_name"
        :manifest="m"
        :selected="selected?.full_name === m.full_name"
        @select="handleSelect(m)"
        @spawn="handleSpawn(m)"
        @edit="handleEdit(m)"
        @delete="handleDelete(m.full_name)"
      />
    </div>

    <AgentManifestDetail :manifest="selected" @spawn="handleSpawn(selected!)" @edit="handleEdit(selected!)" @delete="handleDelete(selected!.full_name)" />

    <SpawnFromManifestDialog
      v-if="showSpawnDialog && selected"
      :manifest="selected"
      @close="showSpawnDialog = false"
    />

    <NewAgentManifestDialog v-if="showNewDialog" @close="showNewDialog = false" />
  </div>
</template>