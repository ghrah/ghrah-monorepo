<script setup lang="ts">
import type { AbilityDefinitionPayload } from "@ghrah/protocol";
import { ref } from "vue";
import { useObserver } from "@/composables/useObserver";
import { DEFAULT_ABILITIES } from "@/constants/abilities";

const emit = defineEmits<{ close: [] }>();

const { spawnAgent, error } = useObserver();

const name = ref("");
const systemPrompt = ref("");
const maxIterations = ref(10);
const loading = ref(false);
const errorMsg = ref<string | null>(null);

async function handleSubmit() {
  if (!name.value.trim()) return;
  loading.value = true;
  errorMsg.value = null;

  const config = {
    name: name.value.trim(),
    description: "",
    system_prompt: systemPrompt.value,
    max_iterations: maxIterations.value,
  };

  const abilities: AbilityDefinitionPayload[] = [...DEFAULT_ABILITIES];

  const result = await spawnAgent(config, abilities);
  loading.value = false;

  if (result && !result.success) {
    errorMsg.value = result.error ?? "Failed to spawn agent";
  } else if (result) {
    emit("close");
  } else {
    // result is null: client not connected or request threw
    errorMsg.value = error.value ?? "Not connected to gateway";
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="emit('close')">
    <div class="bg-white dark:bg-gray-900 rounded-lg shadow-xl w-full max-w-md p-6">
      <h2 class="text-lg font-semibold mb-4">Spawn Agent</h2>

      <form class="space-y-4" @submit.prevent="handleSubmit">
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name *</label>
          <input
            v-model="name"
            type="text"
            required
            class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="e.g. designer"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">System Prompt</label>
          <textarea
            v-model="systemPrompt"
            rows="3"
            class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm dark:text-gray-100 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            placeholder="You are a helpful assistant..."
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Max Iterations</label>
          <input
            v-model.number="maxIterations"
            type="number"
            min="1"
            max="100"
            class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm dark:text-gray-100 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div v-if="errorMsg" class="text-red-600 dark:text-red-400 text-sm">{{ errorMsg }}</div>

        <div class="flex justify-end gap-2">
          <button type="button" class="btn-secondary" :disabled="loading" @click="emit('close')">Cancel</button>
          <button type="submit" class="btn-primary" :disabled="loading || !name.trim()">
            {{ loading ? "Spawning..." : "Spawn" }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>