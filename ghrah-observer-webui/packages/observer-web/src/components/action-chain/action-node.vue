<script setup lang="ts">
import type { ActionChainEntry } from "@ghrah/observer-core";
import { computed } from "vue";

const props = defineProps<{ node: ActionChainEntry }>();

const statusIcon = computed(() => {
  if (props.node.success === true) return "\u2705";
  if (props.node.success === false) return "\u274c";
  return "\u23f3";
});

const summary = computed(() => {
  const args = props.node.tool_args;
  if (!args) return props.node.ability_name;
  if (args.file_path) return `${props.node.ability_name}: ${args.file_path}`;
  if (args.command) return `${props.node.ability_name}: ${args.command}`;
  if (args.path) return `${props.node.ability_name}: ${args.path}`;
  return props.node.ability_name;
});

const timeStr = computed(() => {
  if (!props.node.timestamp) return "";
  return new Date(props.node.timestamp * 1000).toLocaleTimeString();
});
</script>

<template>
  <div :class="['flex items-center gap-2 px-2 py-1 rounded text-sm', node.success === false ? 'bg-red-50 dark:bg-red-950' : 'hover:bg-gray-50 dark:hover:bg-gray-800']">
    <span class="flex-shrink-0">{{ statusIcon }}</span>
    <span class="flex-1 truncate font-mono text-xs">{{ summary }}</span>
    <span v-if="node.error" class="text-red-600 dark:text-red-400 text-xs truncate max-w-40">{{ node.error }}</span>
    <span v-if="timeStr" class="text-gray-400 dark:text-gray-600 text-xs flex-shrink-0">{{ timeStr }}</span>
  </div>
</template>