<script setup lang="ts">
import { onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useObserver } from "@/composables/useObserver";

const { manifests, listManifestAbilities } = useObserver();
const { t } = useI18n();

onMounted(async () => {
  if (manifests.abilityList.length === 0) {
    await listManifestAbilities();
  }
});
</script>

<template>
  <div class="flex flex-col h-full">
    <h2 class="text-lg font-semibold mb-4">{{ t("config.ability.title") }}</h2>
    <p class="text-gray-500 dark:text-gray-400 text-sm mb-4">{{ t("config.ability.comingSoon") }}</p>
    <div class="text-sm text-gray-600 dark:text-gray-300">
      {{ t("config.ability.registered") }} <span class="font-medium">{{ manifests.abilityList.length }}</span>
    </div>
  </div>
</template>