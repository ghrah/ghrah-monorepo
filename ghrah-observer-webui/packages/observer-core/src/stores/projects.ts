import type {
  ProjectAgentEventPayload,
  ProjectEventPayload,
  ProjectInfoPayload,
} from "@ghrah/protocol";
import { defineStore } from "pinia";
import { computed, ref } from "vue";

export const useProjectsStore = defineStore("ghrah-projects", () => {
  const projects = ref<Map<string, ProjectInfoPayload>>(new Map());
  const activeProjectId = ref<string | null>(null);

  const projectList = computed(() => [...projects.value.values()]);

  const activeProject = computed(() => {
    if (!activeProjectId.value) return null;
    return projects.value.get(activeProjectId.value) ?? null;
  });

  function upsertProject(project: ProjectInfoPayload) {
    const next = new Map(projects.value);
    next.set(project.project_id, project);
    projects.value = next;
  }

  function removeProject(projectId: string) {
    const next = new Map(projects.value);
    next.delete(projectId);
    projects.value = next;
    if (activeProjectId.value === projectId) {
      activeProjectId.value = null;
    }
  }

  // Project 事件信封均为 { project } 或 { project, agent_name }，
  // created/updated/paused/resumed/stopped/recovery_set/agent_added/agent_removed 统一 upsert
  function onProjectEvent(payload: ProjectEventPayload | ProjectAgentEventPayload) {
    upsertProject(payload.project);
  }

  function onProjectDeleted(payload: ProjectEventPayload) {
    removeProject(payload.project.project_id);
  }

  function setProjectsFromList(list: ProjectInfoPayload[]) {
    projects.value = new Map(list.map((p) => [p.project_id, p]));
  }

  function setActiveProject(projectId: string | null) {
    activeProjectId.value = projectId;
  }

  function clearAll() {
    projects.value = new Map();
    activeProjectId.value = null;
  }

  return {
    projects,
    activeProjectId,
    projectList,
    activeProject,
    onProjectEvent,
    onProjectDeleted,
    setProjectsFromList,
    setActiveProject,
    clearAll,
  };
});
