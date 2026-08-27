<script setup lang="ts">
import { useChangesStore } from "@ghrah/observer-core";
import { ref } from "vue";
import { useI18n } from "vue-i18n";

const { t, locale } = useI18n();

const changes = useChangesStore();
const expandedKey = ref<string | null>(null);

function toggle(key: string) {
  expandedKey.value = expandedKey.value === key ? null : key;
}

function changeKey(c: { nodeId: string; abilityName: string; filePath?: string }): string {
  return `${c.nodeId}#${c.abilityName}#${c.filePath ?? ""}`;
}

function timeStr(ts: string): string {
  if (!ts) return "";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString(locale.value);
}
</script>

<template>
  <div class="changes-page p-3 h-full flex flex-col">
    <h2 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">{{ t("changes.title") }}</h2>

    <div v-if="changes.changes.length === 0" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-600 text-sm italic">
      {{ t("changes.empty") }}
    </div>

    <div v-else class="flex-1 overflow-y-auto space-y-1">
      <div
        v-for="c in changes.changes"
        :key="changeKey(c)"
        class="border border-gray-200 dark:border-gray-700 rounded"
      >
        <button
          type="button"
          :class="['flex items-center gap-2 w-full px-2 py-1.5 text-left text-xs', c.success ? '' : 'bg-red-50 dark:bg-red-950/40']"
          @click="toggle(changeKey(c))"
        >
          <span class="flex-shrink-0">{{ c.success ? "\u2705" : "\u274c" }}</span>
          <span class="font-mono flex-1 truncate text-gray-700 dark:text-gray-300">{{ c.filePath ?? t("changes.unknownPath") }}</span>
          <span class="text-gray-500 dark:text-gray-400">@{{ c.agentName }}</span>
          <span class="text-gray-400 dark:text-gray-600">{{ c.abilityName }}</span>
          <span class="text-gray-400 dark:text-gray-600 flex-shrink-0">{{ timeStr(c.timestamp) }}</span>
        </button>
        <pre v-if="expandedKey === changeKey(c)" class="px-3 py-2 text-xs bg-gray-50 dark:bg-gray-900 whitespace-pre-wrap overflow-x-auto">{{ JSON.stringify(c.result ?? { error: c.error, outcome: c.outcome }, null, 2) }}</pre>
      </div>
    </div>
  </div>
</template>
