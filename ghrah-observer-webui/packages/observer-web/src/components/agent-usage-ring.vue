<script setup lang="ts">
import type { ContextUsageDisplay } from "@ghrah/observer-core";
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const props = defineProps<{ usage: ContextUsageDisplay }>();
const { t } = useI18n();

const RADIUS = 5;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

const dashOffset = computed(() => {
  if (props.usage.mode !== "ratio" || props.usage.percent == null) return CIRCUMFERENCE;
  return CIRCUMFERENCE * (1 - props.usage.percent / 100);
});

const title = computed(() => {
  if (props.usage.mode === "ratio" && props.usage.percent != null) {
    return t("agentsOverview.usageTitle", {
      occupied: props.usage.occupiedTokens ?? 0,
      budget: props.usage.budgetTokens,
      percent: props.usage.percent,
    });
  }
  return t("agentsOverview.usageCumulative", {
    tokens: props.usage.cumulativeInputTokens,
  });
});
</script>

<template>
  <span :title="title" class="inline-flex items-center justify-center w-5 h-5 flex-shrink-0">
    <svg viewBox="0 0 14 14" class="w-4 h-4" aria-hidden="true">
      <circle
        cx="7"
        cy="7"
        :r="RADIUS"
        fill="none"
        stroke-width="2.5"
        class="stroke-gray-300 dark:stroke-gray-600"
      />
      <circle
        cx="7"
        cy="7"
        :r="RADIUS"
        fill="none"
        stroke-width="2.5"
        stroke-linecap="round"
        class="stroke-gray-700 dark:stroke-gray-200"
        :stroke-dasharray="CIRCUMFERENCE"
        :stroke-dashoffset="dashOffset"
        transform="rotate(-90 7 7)"
      />
    </svg>
  </span>
</template>
