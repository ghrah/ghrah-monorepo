<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";

const route = useRoute();
const { t } = useI18n();

const links = [
  { to: "/config/general", labelKey: "config.nav.general" },
  { to: "/config/agents", labelKey: "config.nav.agents" },
  { to: "/config/abilities", labelKey: "config.nav.abilities" },
] as const;
</script>

<template>
  <nav class="flex flex-col py-2">
    <RouterLink
      v-for="link in links"
      :key="link.to"
      :to="link.to"
      :class="[
        'px-4 py-2 text-sm transition-colors',
        route.path === link.to
          ? 'bg-blue-50 dark:bg-blue-900 text-blue-700 dark:text-blue-200 font-medium border-r-2 border-blue-600'
          : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800',
      ]"
    >
      {{ t(link.labelKey) }}
    </RouterLink>
  </nav>
</template>
