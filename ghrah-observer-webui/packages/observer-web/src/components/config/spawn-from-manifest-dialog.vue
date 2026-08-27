<script setup lang="ts">
import type { AgentManifestInfo } from "@ghrah/observer-core";
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useObserver } from "@/composables/useObserver";

const props = defineProps<{
  manifest: AgentManifestInfo;
}>();

const emit = defineEmits<{ close: [] }>();

const { spawnAgent, error } = useObserver();
const { t } = useI18n();

const runtimeName = ref(props.manifest.name);
const loading = ref(false);
const errorMsg = ref<string | null>(null);

async function handleSubmit() {
  if (!runtimeName.value.trim()) return;
  loading.value = true;
  errorMsg.value = null;

  const result = await spawnAgent(
    { name: runtimeName.value.trim(), description: "", system_prompt: "", max_iterations: 10 },
    props.manifest.full_name,
  );
  loading.value = false;

  if (result && !result.success) {
    errorMsg.value = result.error ?? t("config.spawn.failed");
  } else if (result) {
    emit("close");
  } else {
    errorMsg.value = error.value ?? t("config.spawn.notConnected");
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="$emit('close')">
    <div class="bg-white dark:bg-gray-900 rounded-lg shadow-xl w-full max-w-sm p-6">
      <h2 class="text-lg font-semibold mb-1">{{ t("config.spawn.title") }}</h2>
      <p class="text-xs text-gray-500 dark:text-gray-400 mb-4">
        {{ t("config.spawn.fromManifest") }} <span class="font-mono">{{ manifest.full_name }}</span>
      </p>

      <form class="space-y-4" @submit.prevent="handleSubmit">
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t("config.spawn.runtimeName") }}</label>
          <input
            v-model="runtimeName"
            type="text"
            required
            class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            :placeholder="t('config.spawn.runtimeNamePlaceholder')"
          />
        </div>

        <div v-if="errorMsg" class="text-red-600 dark:text-red-400 text-sm">{{ errorMsg }}</div>

        <div class="flex justify-end gap-2">
          <button type="button" class="btn-secondary" :disabled="loading" @click="$emit('close')">{{ t("common.cancel") }}</button>
          <button type="submit" class="btn-primary" :disabled="loading || !runtimeName.trim()">
            {{ loading ? t("config.spawn.spawning") : t("config.spawn.spawn") }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>