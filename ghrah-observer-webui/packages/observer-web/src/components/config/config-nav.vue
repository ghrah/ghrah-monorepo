<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";

const route = useRoute();
const { t } = useI18n();
</script>

<template>
  <nav class="flex flex-col py-2">
    <RouterLink
      to="/config/agents"
      :class="[
        'px-4 py-2 text-sm transition-colors',
        route.path === '/config/agents'
          ? 'bg-blue-50 dark:bg-blue-900 text-blue-700 dark:text-blue-200 font-medium border-r-2 border-blue-600'
          : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800',
      ]"
    >
      {{ t("config.nav.agents") }}
    </RouterLink>
    <RouterLink
      to="/config/abilities"
      :class="[
        'px-4 py-2 text-sm transition-colors',
        route.path === '/config/abilities'
          ? 'bg-blue-50 dark:bg-blue-900 text-blue-700 dark:text-blue-200 font-medium border-r-2 border-blue-600'
          : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800',
      ]"
    >
      {{ t("config.nav.abilities") }}
    </RouterLink>
  </nav>
</template>