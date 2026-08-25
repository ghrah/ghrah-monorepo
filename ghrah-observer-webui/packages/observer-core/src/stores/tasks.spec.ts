import type { TaskInfoPayload } from "@ghrah/protocol";
import { EventType } from "@ghrah/protocol";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useTasksStore } from "./tasks.js";

function makeTask(overrides: Partial<TaskInfoPayload> = {}): TaskInfoPayload {
  return {
    task_id: "t1",
    project_id: "p1",
    title: "task-1",
    description: "",
    status: "pending",
    priority: "normal",
    dependencies: [],
    created_at: "",
    updated_at: "",
    metadata: {},
    ...overrides,
  };
}

describe("useTasksStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("starts empty", () => {
    const store = useTasksStore();
    expect(store.tasks.size).toBe(0);
  });

  it("onTaskEvent upserts for non-delete events", () => {
    const store = useTasksStore();
    store.onTaskEvent(EventType.TASK_CREATED, { task: makeTask() });
    expect(store.tasks.size).toBe(1);
    store.onTaskEvent(EventType.TASK_UPDATED, {
      task: makeTask({ status: "in_progress" }),
      previous_status: "pending",
    });
    expect(store.tasks.size).toBe(1);
    expect(store.tasks.get("t1")?.status).toBe("in_progress");
  });

  it("onTaskEvent removes on TASK_DELETED", () => {
    const store = useTasksStore();
    store.onTaskEvent(EventType.TASK_CREATED, { task: makeTask() });
    store.onTaskEvent(EventType.TASK_DELETED, { task: makeTask(), reason: "cleanup" });
    expect(store.tasks.size).toBe(0);
  });

  it("tasksByProject filters by project_id", () => {
    const store = useTasksStore();
    store.setTasksFromList([
      makeTask({ task_id: "t1", project_id: "p1" }),
      makeTask({ task_id: "t2", project_id: "p2" }),
      makeTask({ task_id: "t3", project_id: "p1" }),
    ]);
    expect(
      store
        .tasksByProject("p1")
        .map((t) => t.task_id)
        .sort(),
    ).toEqual(["t1", "t3"]);
    expect(store.tasksByProject("p2")).toHaveLength(1);
    expect(store.tasksByProject("nope")).toEqual([]);
  });

  it("setTasksFromList replaces map", () => {
    const store = useTasksStore();
    store.onTaskEvent(EventType.TASK_CREATED, { task: makeTask({ task_id: "old" }) });
    store.setTasksFromList([makeTask({ task_id: "t1" })]);
    expect([...store.tasks.keys()]).toEqual(["t1"]);
  });

  it("clearAll resets", () => {
    const store = useTasksStore();
    store.setTasksFromList([makeTask()]);
    store.clearAll();
    expect(store.tasks.size).toBe(0);
  });
});
