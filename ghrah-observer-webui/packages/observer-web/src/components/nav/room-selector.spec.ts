// @vitest-environment happy-dom

import { useProjectsStore, useRoomsStore } from "@ghrah/observer-core";
import type { RoomInfoPayload } from "@ghrah/protocol";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

const switchRoomMock = vi.fn();
vi.mock("@/composables/useObserver", () => ({
  useObserver: () => ({ switchRoom: switchRoomMock }),
}));

import RoomSelector from "./room-selector.vue";

function room(id: string, projectId: string, name: string, members: string[] = []): RoomInfoPayload {
  return {
    room_id: id,
    project_id: projectId,
    name,
    status: "active",
    members: members.map((s) => ({ subject: s, subject_type: "agent" as const, joined_at: "" })),
    seq_watermark: 0,
    version: 1,
    created_at: "",
    updated_at: "",
  };
}

describe("RoomSelector", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    switchRoomMock.mockReset();
  });

  it("shows empty state when no rooms", () => {
    const wrapper = mount(RoomSelector);
    expect(wrapper.text()).toContain("No rooms");
  });

  it("lists rooms with member counts and emits switchRoom on click", async () => {
    const rooms = useRoomsStore();
    rooms.setRoomsFromList([
      room("r1", "p1", "arch", ["architect", "frontend"]),
      room("r2", "p1", "frontend", ["frontend"]),
    ]);
    const wrapper = mount(RoomSelector);
    await wrapper.vm.$nextTick();
    const items = wrapper.findAll("li");
    expect(items).toHaveLength(2);
    expect(items[0].text()).toContain("arch");
    expect(items[0].text()).toContain("2");
    expect(items[1].text()).toContain("1");
    await items[0].trigger("click");
    expect(switchRoomMock).toHaveBeenCalledWith("r1");
  });

  it("filters rooms by active project", async () => {
    const rooms = useRoomsStore();
    const projects = useProjectsStore();
    rooms.setRoomsFromList([room("r1", "p1", "arch"), room("r2", "p2", "other")]);
    projects.setActiveProject("p2");
    const wrapper = mount(RoomSelector);
    await wrapper.vm.$nextTick();
    const items = wrapper.findAll("li");
    expect(items).toHaveLength(1);
    expect(items[0].text()).toContain("other");
  });

  it("lists all rooms when no active project", async () => {
    const rooms = useRoomsStore();
    rooms.setRoomsFromList([room("r1", "p1", "arch"), room("r2", "p2", "other")]);
    const wrapper = mount(RoomSelector);
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll("li")).toHaveLength(2);
  });

  it("badges members that belong to multiple rooms", async () => {
    const rooms = useRoomsStore();
    // architect 同时在 3 个 room；frontend 只在 2 个；tester 只在 1 个
    rooms.setRoomsFromList([
      room("r1", "p1", "arch", ["architect", "frontend"]),
      room("r2", "p1", "frontend", ["architect", "frontend"]),
      room("r3", "p1", "backend", ["architect", "tester"]),
    ]);
    const wrapper = mount(RoomSelector);
    await wrapper.vm.$nextTick();
    // r3 中：architect（3 room）高亮，tester（1 room）普通
    const r3 = wrapper.findAll("li")[2];
    const badges = r3.findAll(".room-member");
    expect(badges).toHaveLength(2);
    expect(badges[0].attributes("title")).toBe("architect");
    expect(badges[0].classes().join(" ")).toContain("bg-amber-200");
    expect(badges[1].attributes("title")).toBe("tester");
    expect(badges[1].classes().join(" ")).toContain("bg-gray-200");
    // 每个 room 的 architect badge 都高亮（跨 3 room）
    for (const li of wrapper.findAll("li")) {
      const architectBadge = li
        .findAll(".room-member")
        .find((b) => b.attributes("title") === "architect");
      expect(architectBadge?.classes().join(" ")).toContain("bg-amber-200");
    }
  });

  it("highlights the active room", async () => {
    const rooms = useRoomsStore();
    rooms.setRoomsFromList([room("r1", "p1", "arch"), room("r2", "p1", "frontend")]);
    rooms.setActiveRoom("r2");
    const wrapper = mount(RoomSelector);
    await wrapper.vm.$nextTick();
    const items = wrapper.findAll("li");
    expect(items[0].classes().join(" ")).not.toContain("bg-blue-100");
    expect(items[1].classes().join(" ")).toContain("bg-blue-100");
  });
});
