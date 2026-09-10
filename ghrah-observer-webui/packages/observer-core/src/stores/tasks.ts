import type { TaskEventPayload, TaskInfoPayload } from "@ghrah/protocol";
import { EventType } from "@ghrah/protocol";
import { defineStore } from "pinia";
import { ref } from "vue";

export const useTasksStore = defineStore("ghrah-tasks", () => {
  const tasks = ref<Map<string, TaskInfoPayload>>(new Map());

  function tasksByProject(projectId: string): TaskInfoPayload[] {
    return [...tasks.value.values()].filter((t) => t.project_id === projectId);
  }

  function upsertTask(task: TaskInfoPayload) {
    const next = new Map(tasks.value);
    next.set(task.task_id, task);
    tasks.value = next;
  }

  function removeTask(taskId: string) {
    const next = new Map(tasks.value);
    next.delete(taskId);
    tasks.value = next;
  }

  /**
   * TaskEventPayload 信封 = { task, previous_status?, reason? }，本身不含删除语义；
   * 由调用方（bind）传入事件类型，TASK_DELETED 移除，其余 upsert。
   */
  function onTaskEvent(eventType: EventType | string, payload: TaskEventPayload) {
    if (eventType === EventType.TASK_DELETED) {
      removeTask(payload.task.task_id);
    } else {
      upsertTask(payload.task);
    }
  }

  function setTasksFromList(list: TaskInfoPayload[]) {
    tasks.value = new Map(list.map((t) => [t.task_id, t]));
  }

  function clearProject(projectId: string) {
    tasks.value = new Map(
      [...tasks.value.entries()].filter(([, task]) => task.project_id !== projectId),
    );
  }

  function clearAll() {
    tasks.value = new Map();
  }

  return {
    tasks,
    tasksByProject,
    upsertTask,
    removeTask,
    onTaskEvent,
    setTasksFromList,
    clearProject,
    clearAll,
  };
});
