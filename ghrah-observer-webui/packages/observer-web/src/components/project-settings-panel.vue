<script setup lang="ts">
import { useProjectsStore, useRoomsStore } from "@ghrah/observer-core";
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const props = defineProps<{ projectId: string }>();
const projects = useProjectsStore();
const rooms = useRoomsStore();
const { t } = useI18n();
const project = computed(() => projects.projects.get(props.projectId) ?? null);
const roomCount = computed(() => rooms.roomsForProject(props.projectId).length);
</script>

<template>
  <div class="project-panel project-settings-panel">
    <div v-if="!project" class="project-panel-empty">{{ t("projectSettings.unavailable") }}</div>
    <template v-else>
      <header class="project-panel-header">
        <div><span class="section-eyebrow">{{ t("projectSettings.eyebrow") }}</span><h2>{{ project.name }}</h2></div>
        <span class="project-status-chip">{{ project.status }} · v{{ project.version }}</span>
      </header>
      <section class="project-settings-section project-storage-summary">
        <h3>{{ t("projectSettings.storage") }}</h3>
        <dl>
          <div><dt>{{ t("projectSettings.root") }}</dt><dd><code>{{ project.project_root_locator || t("nav.project.legacyRoot") }}</code></dd></div>
          <div><dt>{{ t("projectSettings.workspaces") }}</dt><dd>{{ project.workspaces?.length ?? 0 }}</dd></div>
          <div><dt>{{ t("projectSettings.agents") }}</dt><dd>{{ project.agents?.length ?? 0 }}</dd></div>
          <div><dt>{{ t("projectSettings.rooms") }}</dt><dd>{{ roomCount }}</dd></div>
        </dl>
        <p>{{ t("projectSettings.workspaceBoundary") }}</p>
      </section>
    </template>
  </div>
</template>
