<script setup lang="ts">
import { useProjectsStore } from "@ghrah/observer-core";
import { nextTick, ref } from "vue";
import { useObserver } from "@/composables/useObserver";

const projects = useProjectsStore();
const { switchProject, createProject, error } = useObserver();

const creating = ref(false);
const newName = ref("");
const busy = ref(false);
const nameInput = ref<HTMLInputElement | null>(null);

function startCreate() {
  creating.value = true;
  newName.value = "";
  void nextTick(() => nameInput.value?.focus());
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
      const created = (result.data as { project?: { project_id: string } } | undefined)?.project;
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
  <div class="project-selector sidebar-section">
    <div class="project-heading">
      <h3>Projects</h3>
    </div>

    <ul v-if="projects.projectList.length > 0" class="project-list">
      <li
        v-for="project in projects.projectList"
        :key="project.project_id"
        :title="project.name"
        :aria-label="project.name"
        :aria-current="projects.activeProjectId === project.project_id ? 'true' : undefined"
        role="button"
        tabindex="0"
        :class="[
          'project-item cursor-pointer text-sm truncate transition-colors',
          projects.activeProjectId === project.project_id
            ? 'active bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100 font-medium'
            : 'hover:bg-gray-100 dark:hover:bg-gray-800',
        ]"
        @click="switchProject(project.project_id)"
        @keydown.enter="switchProject(project.project_id)"
        @keydown.space.prevent="switchProject(project.project_id)"
      >
        <span class="project-avatar">{{ project.name.slice(0, 2).toUpperCase() }}</span>
        <span class="project-name-visually-hidden">{{ project.name }}</span>
      </li>
    </ul>

    <p v-else class="project-empty">No projects</p>

    <div class="project-add-area">
      <span class="project-divider" />
      <button
        v-if="!creating"
        class="project-add"
        type="button"
        aria-label="New project"
        title="New project"
        @click="startCreate"
      >
        <span aria-hidden="true">+</span>
      </button>

      <form v-else class="project-create-popover" @submit.prevent="submitCreate">
        <label for="new-project-name">Create project</label>
        <div class="project-create-row">
          <input
            id="new-project-name"
            ref="nameInput"
            v-model="newName"
            type="text"
            placeholder="Project name"
            class="project-create-input"
            @keydown.esc="cancelCreate"
          />
          <button type="submit" class="btn-primary" :disabled="busy || !newName.trim()">
            {{ busy ? "…" : "Create" }}
          </button>
          <button
            type="button"
            class="project-create-cancel"
            aria-label="Cancel"
            @click="cancelCreate"
          >
            ×
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
