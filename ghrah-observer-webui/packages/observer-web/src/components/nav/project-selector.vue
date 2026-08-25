<script setup lang="ts">
import { useProjectsStore } from "@ghrah/observer-core";
import { useObserver } from "@/composables/useObserver";

const projects = useProjectsStore();
const { switchProject } = useObserver();
</script>

<template>
  <div class="p-3 border-b border-gray-200 dark:border-gray-700">
    <h3 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">Projects</h3>

    <ul v-if="projects.projectList.length > 0" class="space-y-1">
      <li
        v-for="project in projects.projectList"
        :key="project.project_id"
        :class="[
          'px-2 py-1.5 rounded cursor-pointer text-sm truncate transition-colors',
          projects.activeProjectId === project.project_id
            ? 'bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100 font-medium'
            : 'hover:bg-gray-100 dark:hover:bg-gray-800',
        ]"
        @click="switchProject(project.project_id)"
      >
        {{ project.name }}
      </li>
    </ul>

    <p v-else class="text-gray-400 dark:text-gray-600 text-sm italic">No projects</p>
  </div>
</template>
