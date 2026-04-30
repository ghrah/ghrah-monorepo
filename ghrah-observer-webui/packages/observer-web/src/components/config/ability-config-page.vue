<script setup lang="ts">
import { onMounted } from "vue";
import { useObserver } from "@/composables/useObserver";

const { manifests, listManifestAbilities } = useObserver();

onMounted(async () => {
  if (manifests.abilityList.length === 0) {
    await listManifestAbilities();
  }
});
</script>

<template>
  <div class="flex flex-col h-full">
    <h2 class="text-lg font-semibold mb-4">Ability 配置</h2>
    <p class="text-gray-500 dark:text-gray-400 text-sm mb-4">Ability 配置功能即将推出。</p>
    <div class="text-sm text-gray-600 dark:text-gray-300">
      当前已注册 Ability: <span class="font-medium">{{ manifests.abilityList.length }}</span>
    </div>
  </div>
</template>