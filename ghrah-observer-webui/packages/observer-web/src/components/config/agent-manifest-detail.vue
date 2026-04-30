<script setup lang="ts">
import type { AgentManifestInfo } from "@ghrah/observer-core";

defineProps<{
  manifest: AgentManifestInfo | null;
}>();

defineEmits<{
  spawn: [];
  edit: [];
  delete: [];
}>();

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}...` : text;
}
</script>

<template>
  <div v-if="!manifest" class="text-gray-400 dark:text-gray-600 text-sm italic py-8 text-center">
    Select an Agent Manifest to view details
  </div>
  <div v-else class="border border-gray-200 dark:border-gray-700 rounded p-4 bg-white dark:bg-gray-900 space-y-3">
    <div class="flex items-center justify-between">
      <h3 class="font-semibold">{{ manifest.title || manifest.name }}</h3>
      <span class="badge bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 text-xs">{{ manifest.namespace }}</span>
    </div>

    <div v-if="manifest.description" class="text-sm text-gray-600 dark:text-gray-400">
      {{ manifest.description }}
    </div>

    <div class="grid grid-cols-2 gap-2 text-sm">
      <div>
        <span class="text-gray-500 dark:text-gray-400">Name:</span>
        <span class="ml-1 font-mono">{{ manifest.name }}</span>
      </div>
      <div>
        <span class="text-gray-500 dark:text-gray-400">Config:</span>
        <span class="ml-1 font-mono">{{ manifest.agent_config_name || "—" }}</span>
      </div>
      <div>
        <span class="text-gray-500 dark:text-gray-400">Temperature:</span>
        <span class="ml-1">—</span>
      </div>
      <div>
        <span class="text-gray-500 dark:text-gray-400">Max Iterations:</span>
        <span class="ml-1">{{ manifest.max_iterations }}</span>
      </div>
    </div>

    <div v-if="manifest.tags.length > 0" class="flex flex-wrap gap-1">
      <span v-for="tag in manifest.tags" :key="tag" class="badge bg-gray-100 dark:bg-gray-700 text-xs">{{ tag }}</span>
    </div>

    <div v-if="manifest.system_prompt" class="space-y-1">
      <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">System Prompt</div>
      <pre class="text-xs bg-gray-50 dark:bg-gray-800 p-2 rounded overflow-x-auto whitespace-pre-wrap max-h-32 overflow-y-auto">{{ truncate(manifest.system_prompt, 500) }}</pre>
    </div>

    <div v-if="manifest.ability_refs.length > 0" class="space-y-1">
      <div class="text-xs text-gray-500 dark:text-gray-400 font-medium">Abilities ({{ manifest.ability_refs.length }})</div>
      <ul class="text-xs space-y-0.5">
        <li v-for="ref in manifest.ability_refs" :key="ref" class="font-mono text-gray-700 dark:text-gray-300">
          {{ ref }}
        </li>
      </ul>
    </div>

    <div class="flex gap-2 pt-2 border-t border-gray-100 dark:border-gray-800">
      <button class="btn-primary text-xs" @click="$emit('spawn')">Spawn Agent</button>
      <button class="btn-secondary text-xs" @click="$emit('edit')">Edit YAML</button>
      <button class="btn-danger text-xs" @click="$emit('delete')">Delete</button>
    </div>
  </div>
</template>