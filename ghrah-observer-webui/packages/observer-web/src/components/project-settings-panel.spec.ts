// @vitest-environment happy-dom

import { useProjectsStore, useRoomsStore } from "@ghrah/observer-core";
import type { ProjectInfoPayload, RoomInfoPayload } from "@ghrah/protocol";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import ProjectSettingsPanel from "./project-settings-panel.vue";

function project(id: string, name: string): ProjectInfoPayload {
  return {
    project_id: id,
    name,
    status: "active",
    version: 4,
    archived_at: null,
    project_root_locator: `file:///projects/${id}`,
    workspaces: [{ locator: `file:///workspaces/${id}`, name: `${name} workspace` }],
    agents: [{ name: `${name} Agent`, agent_id: `${id}-agent` }],
  } as never;
}

function room(id: string, projectId: string): RoomInfoPayload {
  return {
    room_id: id,
    project_id: projectId,
    name: id,
    status: "active",
    members: [],
    seq_watermark: 0,
    version: 1,
    created_at: "",
    updated_at: "",
    archived_at: null,
  };
}

describe("ProjectSettingsPanel", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("renders an unavailable state when the scoped Project no longer exists", () => {
    const wrapper = mount(ProjectSettingsPanel, { props: { projectId: "missing" } });

    expect(wrapper.text()).toContain("This project is no longer available");
  });

  it("shows only the requested Project ownership boundary and Room count", () => {
    useProjectsStore().setProjectsFromList([
      project("p1", "Project One"),
      project("p2", "Project Two"),
    ]);
    useRoomsStore().replaceProjectRooms("p1", [room("r1", "p1"), room("r2", "p1")], "active");
    useRoomsStore().replaceProjectRooms("p2", [room("foreign", "p2")], "active");

    const wrapper = mount(ProjectSettingsPanel, { props: { projectId: "p1" } });

    expect(wrapper.text()).toContain("Project One");
    expect(wrapper.text()).toContain("file:///projects/p1");
    expect(wrapper.text()).not.toContain("Project Two");
    const values = wrapper.findAll("dd").map((node) => node.text());
    expect(values).toEqual(["file:///projects/p1", "1", "1", "2"]);
  });
});
