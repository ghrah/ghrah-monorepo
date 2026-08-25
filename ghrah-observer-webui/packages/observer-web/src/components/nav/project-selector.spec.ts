// @vitest-environment happy-dom

import { useProjectsStore } from "@ghrah/observer-core";
import type { ProjectInfoPayload } from "@ghrah/protocol";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

const switchProjectMock = vi.fn();
vi.mock("@/composables/useObserver", () => ({
  useObserver: () => ({ switchProject: switchProjectMock }),
}));

import ProjectSelector from "./project-selector.vue";

function project(id: string, name: string): ProjectInfoPayload {
  return { project_id: id, name } as ProjectInfoPayload;
}

describe("ProjectSelector", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    switchProjectMock.mockReset();
  });

  it("shows empty state when no projects", () => {
    const wrapper = mount(ProjectSelector);
    expect(wrapper.text()).toContain("No projects");
  });

  it("lists projects and emits switchProject on click", async () => {
    const projects = useProjectsStore();
    projects.setProjectsFromList([project("p1", "alpha"), project("p2", "beta")]);
    const wrapper = mount(ProjectSelector);
    await wrapper.vm.$nextTick();
    const items = wrapper.findAll("li");
    expect(items).toHaveLength(2);
    expect(wrapper.text()).toContain("alpha");
    expect(wrapper.text()).toContain("beta");
    await items[1].trigger("click");
    expect(switchProjectMock).toHaveBeenCalledWith("p2");
  });

  it("highlights the active project", async () => {
    const projects = useProjectsStore();
    projects.setProjectsFromList([project("p1", "alpha"), project("p2", "beta")]);
    projects.setActiveProject("p1");
    const wrapper = mount(ProjectSelector);
    await wrapper.vm.$nextTick();
    const items = wrapper.findAll("li");
    expect(items[0].classes().join(" ")).toContain("bg-blue-100");
    expect(items[1].classes().join(" ")).not.toContain("bg-blue-100");
  });
});
