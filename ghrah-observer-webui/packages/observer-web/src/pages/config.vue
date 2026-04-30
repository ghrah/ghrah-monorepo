<script setup lang="ts">
import ConfigNav from "@/components/config/config-nav.vue";
</script>

<template>
  <div class="flex h-full">
    <aside class="w-44 shrink-0 border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-y-auto">
      <ConfigNav />
    </aside>
    <main class="flex-1 min-w-0 overflow-y-auto p-4">
      <RouterView />
    </main>
  </div>
</template>
