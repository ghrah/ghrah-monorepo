<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useObserver } from "@/composables/useObserver";
import AgentManifestCard from "@/components/config/agent-manifest-card.vue";
import AgentManifestDetail from "@/components/config/agent-manifest-detail.vue";
import SpawnFromManifestDialog from "@/components/config/spawn-from-manifest-dialog.vue";
import NewAgentManifestDialog from "@/components/config/new-agent-manifest-dialog.vue";
import type { AgentManifestInfo } from "@ghrah/observer-core";

const { manifests, listManifestAgents, deleteAgent } = useObserver();

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
  if (!confirm("确定要删除此 Agent Manifest 吗？")) return;
  loading.value = true;
  error.value = null;
  const result = await deleteAgent(fullName);
  loading.value = false;
  if (result && !result.success) {
    error.value = result.error ?? "删除失败";
  } else if (result === null) {
    error.value = "未连接到 Gateway";
  }
  if (selected.value?.full_name === fullName) {
    selected.value = null;
  }
}
</script>

<template>
  <div class="flex flex-col h-full gap-4">
    <div class="flex items-center justify-between">
      <h2 class="text-lg font-semibold">Agent 配置</h2>
      <button class="btn-primary text-xs" @click="showNewDialog = true">+ New Agent Manifest</button>
    </div>

    <div v-if="error" class="text-red-600 dark:text-red-400 text-sm">{{ error }}</div>

    <div v-if="manifests.agentsLoading" class="text-gray-400 text-sm py-4 text-center">Loading...</div>

    <div v-else-if="manifests.agentList.length === 0" class="text-gray-400 text-sm py-4 text-center italic">
      No agent manifests found
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