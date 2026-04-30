<script setup lang="ts">
import { useRoute } from "vue-router";

const route = useRoute();
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
      Agent 配置
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
      Ability 配置
    </RouterLink>
  </nav>
</template>