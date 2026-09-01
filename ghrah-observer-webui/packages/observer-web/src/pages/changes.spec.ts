// @vitest-environment happy-dom

import type { FileChange } from "@ghrah/observer-core";
import { useChangesStore } from "@ghrah/observer-core";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import ChangesPage from "./changes.vue";

function change(overrides: Partial<FileChange> = {}): FileChange {
  return {
    projectId: "p1",
    agentId: "a1",
    agentName: "alpha",
    abilityName: "write_file",
    filePath: "src/a.ts",
    success: true,
    timestamp: "2026-01-01T00:00:00Z",
    nodeId: "n1",
    ...overrides,
  };
}

function setChanges(store: ReturnType<typeof useChangesStore>, list: FileChange[]) {
  (store as unknown as { changes: FileChange[] }).changes = list;
}

describe("ChangesPage", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("renders empty state when no changes", async () => {
    const store = useChangesStore();
    void store;
    const wrapper = mount(ChangesPage);
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("No file changes yet");
  });

  it("renders list of file changes", async () => {
    const store = useChangesStore();
    setChanges(store, [
      change({ nodeId: "n1", filePath: "src/a.ts" }),
      change({ nodeId: "n2", filePath: "src/b.ts" }),
    ]);
    const wrapper = mount(ChangesPage);
    await wrapper.vm.$nextTick();
    const buttons = wrapper.findAll("button[type=button]");
    expect(buttons).toHaveLength(2);
    expect(wrapper.text()).toContain("src/a.ts");
    expect(wrapper.text()).toContain("src/b.ts");
  });

  it("expands result on click", async () => {
    const store = useChangesStore();
    setChanges(store, [change({ nodeId: "n1", filePath: "src/a.ts", result: { lines: 10 } })]);
    const wrapper = mount(ChangesPage);
    await wrapper.vm.$nextTick();
    expect(wrapper.find("pre").exists()).toBe(false);
    await wrapper.find("button[type=button]").trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.find("pre").exists()).toBe(true);
    expect(wrapper.find("pre").text()).toContain('"lines"');
  });

  it("renders failure styling on success=false", async () => {
    const store = useChangesStore();
    setChanges(store, [change({ nodeId: "n1", success: false, error: "boom" })]);
    const wrapper = mount(ChangesPage);
    await wrapper.vm.$nextTick();
    const btn = wrapper.find("button[type=button]");
    expect(btn.classes()).toContain("bg-red-50");
    expect(wrapper.text()).toContain("❌");
  });
});
