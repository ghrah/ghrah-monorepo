<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import { fontScale, setFontScale } from "@/composables/useFontScale";
import { useObserver } from "@/composables/useObserver";
import { type AppLocale, SUPPORTED_LOCALES, setLocale } from "@/i18n";

const route = useRoute();
const { t, locale } = useI18n();
const { connection, error, autoConnect, disconnect } = useObserver();

onMounted(async () => {
  await autoConnect();
});

onUnmounted(() => {
  disconnect();
});

const statusClass: Record<string, string> = {
  connected: "bg-green-200 text-green-900",
  connecting: "bg-yellow-200 text-yellow-900",
  reconnecting: "bg-yellow-200 text-yellow-900",
  disconnected: "bg-red-200 text-red-900",
};

const statusDot: Record<string, string> = {
  connected: "bg-green-500",
  connecting: "bg-yellow-500 animate-pulse",
  reconnecting: "bg-yellow-500 animate-pulse",
  disconnected: "bg-red-500",
};

const fontScales = ["0.9", "1", "1.1"] as const;
const localeOptions = SUPPORTED_LOCALES;

function statusLabel(state: string) {
  return t(`app.status.${state}`);
}

function onLocaleChange(event: Event) {
  setLocale((event.target as HTMLSelectElement).value as AppLocale);
}
</script>

<template>
  <div class="app-frame h-screen flex flex-col text-gray-900 dark:text-gray-100">
    <header class="app-header">
      <div class="brand-lockup">
        <span class="brand-mark">G</span>
        <div>
          <h1>{{ t("app.title") }}</h1>
          <span>{{ t("app.subtitle") }}</span>
        </div>
        <span :class="['badge', statusClass[connection.state]]">
          <span :class="['inline-block w-2 h-2 rounded-full mr-1', statusDot[connection.state]]" />
          {{ statusLabel(connection.state) }}
        </span>
      </div>
      <nav class="top-nav">
        <RouterLink to="/" :class="['px-3 py-1 rounded transition-colors', route.path === '/' ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200 font-medium' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800']">{{ t("app.nav.dashboard") }}</RouterLink>
        <RouterLink to="/changes" :class="['px-3 py-1 rounded transition-colors', route.path === '/changes' ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200 font-medium' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800']">{{ t("app.nav.changes") }}</RouterLink>
        <RouterLink to="/config" :class="['px-3 py-1 rounded transition-colors', route.path.startsWith('/config') ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200 font-medium' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800']">{{ t("app.nav.config") }}</RouterLink>
      </nav>
      <div class="connection-tools">
        <select
          class="px-2 py-0.5 rounded text-xs bg-transparent border border-gray-300 dark:border-gray-600"
          :aria-label="t('app.language')"
          :value="locale"
          @change="onLocaleChange"
        >
          <option v-for="option in localeOptions" :key="option" :value="option">
            {{ t(`app.languageNames.${option}`) }}
          </option>
        </select>
        <div class="flex items-center gap-1" :aria-label="t('app.interfaceScale')">
          <button
            v-for="scale in fontScales"
            :key="scale"
            type="button"
            :class="[
              'px-2 py-0.5 rounded text-xs transition-colors',
              fontScale === scale
                ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200 font-medium'
                : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800',
            ]"
            @click="setFontScale(scale)"
          >
            {{ Number(scale) * 100 }}%
          </button>
        </div>
        <span class="server-address">{{ connection.serverUrl }}</span>
        <button
          v-if="connection.state === 'connected'"
          class="btn-secondary"
          @click="disconnect"
        >
          {{ t("app.disconnect") }}
        </button>
        <button
          v-else
          class="btn-primary"
          :disabled="connection.state === 'connecting' || connection.state === 'reconnecting'"
          @click="autoConnect()"
        >
          {{ t("app.connect") }}
        </button>
      </div>
    </header>
    <div v-if="error" class="px-4 py-1 bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 text-xs">
      {{ error }}
    </div>
    <main class="flex-1 min-h-0">
      <RouterView />
    </main>
  </div>
</template>
