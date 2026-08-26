<script setup lang="ts">
import { useProjectsStore } from "@ghrah/observer-core";
import { computed, nextTick, ref } from "vue";
import { useObserver } from "@/composables/useObserver";

const projects = useProjectsStore();
const { switchProject, createProject, error } = useObserver();

const creating = ref(false);
const newName = ref("");
const newDescription = ref("");
const newProjectRoot = ref("");
const newWorkspaces = ref<Array<{ locator: string; name: string }>>([]);
const busy = ref(false);
const nameInput = ref<HTMLInputElement | null>(null);
const activeProject = computed(() =>
  projects.activeProjectId ? projects.projects.get(projects.activeProjectId) : undefined,
);

function startCreate() {
  creating.value = true;
  newName.value = "";
  newDescription.value = "";
  newProjectRoot.value = "";
  newWorkspaces.value = [];
  void nextTick(() => nameInput.value?.focus());
}

function cancelCreate() {
  creating.value = false;
  newName.value = "";
  newDescription.value = "";
  newProjectRoot.value = "";
  newWorkspaces.value = [];
}

function addWorkspace() {
  newWorkspaces.value.push({
    locator: "",
    name: newWorkspaces.value.length ? "workspace" : "default",
  });
}

function removeWorkspace(index: number) {
  newWorkspaces.value.splice(index, 1);
}

async function submitCreate() {
  const name = newName.value.trim();
  if (!name || busy.value) return;
  if (newWorkspaces.value.some((workspace) => !workspace.locator.trim())) return;
  busy.value = true;
  try {
    const result = await createProject(name, {
      description: newDescription.value.trim(),
      projectRootLocator: newProjectRoot.value.trim() || undefined,
      writableWorkspaces: newWorkspaces.value.map((workspace, index) => ({
        locator: workspace.locator.trim(),
        name: workspace.name.trim() || `workspace-${index + 1}`,
        role: index === 0 ? "default" : "workspace",
        defaultForAgents: index === 0,
      })),
    });
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

    <div v-if="activeProject" class="project-summary">
      <strong>{{ activeProject.name }}</strong>
      <p v-if="activeProject.description">{{ activeProject.description }}</p>
      <span>Internal Project Root</span>
      <code :title="activeProject.project_root_locator">
        {{ activeProject.project_root_locator || "Legacy project — migration pending" }}
      </code>
      <small v-if="activeProject.project_root_locator" class="project-derived-paths">
        Internal stores: db/tasks.sqlite3 · db/rooms.sqlite3 · db/action-chains.sqlite3 ·
        manifests/agents
      </small>
      <small>{{ activeProject.workspaces?.length ?? 0 }} writable workspace(s)</small>
    </div>

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
        <div class="project-create-header">
          <strong>Create project</strong>
          <button
            type="button"
            class="project-create-cancel"
            aria-label="Cancel"
            @click="cancelCreate"
          >
            ×
          </button>
        </div>
        <div class="project-create-fields">
          <label for="new-project-name">Project name</label>
          <input
            id="new-project-name"
            ref="nameInput"
            v-model="newName"
            type="text"
            placeholder="Project name"
            class="project-create-input"
            @keydown.esc="cancelCreate"
          />
          <label for="new-project-description">Description</label>
          <textarea
            id="new-project-description"
            v-model="newDescription"
            rows="3"
            placeholder="What is this project for?"
            class="project-create-input project-create-textarea"
            @keydown.esc="cancelCreate"
          />
          <label for="new-project-root">Internal Project Root</label>
          <input
            id="new-project-root"
            v-model="newProjectRoot"
            type="text"
            placeholder="Auto-generated under ~/.ghrah/projects"
            class="project-create-input"
            @keydown.esc="cancelCreate"
          />
          <p class="project-create-hint">
            Private Subject data. Agents cannot access this folder as a workspace.
          </p>
          <div class="project-workspace-heading">
            <label>Writable workspaces</label>
            <button type="button" class="project-workspace-add" @click="addWorkspace">
              + Add
            </button>
          </div>
          <p v-if="newWorkspaces.length === 0" class="project-create-hint">
            None. Agents will start without a default writable folder.
          </p>
          <div
            v-for="(workspace, index) in newWorkspaces"
            :key="index"
            class="project-workspace-row"
          >
            <input
              v-model="workspace.name"
              type="text"
              :aria-label="`Workspace ${index + 1} name`"
              placeholder="Workspace name"
              class="project-create-input project-workspace-name"
            />
            <input
              v-model="workspace.locator"
              type="text"
              :aria-label="`Workspace ${index + 1} path`"
              placeholder="/absolute/path/to/workspace"
              class="project-create-input"
            />
            <button
              type="button"
              class="project-workspace-remove"
              :aria-label="`Remove workspace ${index + 1}`"
              @click="removeWorkspace(index)"
            >
              ×
            </button>
          </div>
          <p v-if="newWorkspaces.length > 0" class="project-create-hint">
            The first workspace is the default for agents. Workspaces cannot overlap Project Roots.
          </p>
        </div>
        <div class="project-create-actions">
          <button
            type="submit"
            class="btn-primary"
            :disabled="
              busy ||
              !newName.trim() ||
              newWorkspaces.some((workspace) => !workspace.locator.trim())
            "
          >
            {{ busy ? "…" : "Create" }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
