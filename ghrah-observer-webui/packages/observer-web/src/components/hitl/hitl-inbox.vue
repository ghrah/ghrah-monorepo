<script setup lang="ts">
import { useHitlStore } from "@ghrah/observer-core";
import { useI18n } from "vue-i18n";
import HitlRequestItem from "./hitl-request-item.vue";

const { t } = useI18n();

const hitl = useHitlStore();
</script>

<template>
  <div class="p-3">
    <h3 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">
      {{ t("hitl.inbox") }}
      <span v-if="hitl.pendingRequests.length > 0" class="bg-yellow-200 dark:bg-yellow-800 text-yellow-900 dark:text-yellow-100 px-1.5 py-0.5 rounded-full text-xs ml-2">
        {{ hitl.pendingRequests.length }}
      </span>
    </h3>

    <div v-if="hitl.pendingRequests.length === 0" class="text-gray-400 dark:text-gray-600 text-sm italic">
      {{ t("hitl.empty") }}
    </div>

    <ul v-else class="space-y-2">
      <HitlRequestItem
        v-for="req in hitl.pendingRequests"
        :key="req.promiseId"
        :request="req"
      />
    </ul>
  </div>
</template>
