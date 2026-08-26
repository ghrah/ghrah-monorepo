<script setup lang="ts">
import { useProjectsStore } from "@ghrah/observer-core";
import { ref } from "vue";
import { useObserver } from "@/composables/useObserver";

const projects = useProjectsStore();
const { switchProject, createProject, error } = useObserver();

const creating = ref(false);
const newName = ref("");
const busy = ref(false);

function startCreate() {
  creating.value = true;
  newName.value = "";
}

function cancelCreate() {
  creating.value = false;
  newName.value = "";
}

async function submitCreate() {
  const name = newName.value.trim();
  if (!name || busy.value) return;
  busy.value = true;
  try {
    const result = await createProject(name);
    if (result?.success) {
      // PROJECT_CREATED 事件驱动 store 后选定新 project
      const created = (result.data as { project?: { project_id: string } } | undefined)
        ?.project;
      if (created?.project_id) switchProject(created.project_id);
      cancelCreate();
    } else if (result && !result.success) {
      error.value = result.error ?? "创建失败";
    }
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="p-3 border-b border-gray-200 dark:border-gray-700">
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Projects</h3>
      <button
        v-if="!creating"
        class="btn-primary text-xs px-2 py-0.5"
        title="New project"
        @click="startCreate"
      >
        + New
      </button>
    </div>

    <form v-if="creating" class="mb-2 flex gap-1" @submit.prevent="submitCreate">
      <input
        ref="nameInput"
        v-model="newName"
        type="text"
        placeholder="Project name"
        class="flex-1 min-w-0 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
        @keydown.esc="cancelCreate"
      />
      <button
        type="submit"
        class="btn-primary text-xs px-2 py-1"
        :disabled="busy || !newName.trim()"
      >
        {{ busy ? "…" : "Create" }}
      </button>
      <button
        type="button"
        class="btn-secondary text-xs px-2 py-1"
        @click="cancelCreate"
      >
        ✕
      </button>
    </form>

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
