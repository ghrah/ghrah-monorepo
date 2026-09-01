// @vitest-environment happy-dom

import { useAgentsStore, useProjectsStore, useRoomsStore } from "@ghrah/observer-core";
import type { RoomInfoPayload } from "@ghrah/protocol";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

const switchRoomMock = vi.fn();
const createRoomMock = vi.fn();
const joinRoomMock = vi.fn();
const leaveRoomMock = vi.fn();
const errorRef = ref<string | null>(null);
vi.mock("@/composables/useObserver", () => ({
  useObserver: () => ({
    switchRoom: switchRoomMock,
    createRoom: createRoomMock,
    joinRoom: joinRoomMock,
    leaveRoom: leaveRoomMock,
    error: errorRef,
  }),
}));

import RoomSelector from "./room-selector.vue";

function room(
  id: string,
  projectId: string,
  name: string,
  members: string[] = [],
): RoomInfoPayload {
  return {
    room_id: id,
    project_id: projectId,
    name,
    status: "active",
    members: members.map((s) => ({
      subject: s,
      subject_type: "agent" as const,
      subject_name: s,
      joined_at: "",
    })),
    seq_watermark: 0,
    version: 1,
    created_at: "",
    updated_at: "",
    archived_at: null,
  };
}

describe("RoomSelector", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    switchRoomMock.mockReset();
    createRoomMock.mockReset();
    joinRoomMock.mockReset();
    leaveRoomMock.mockReset();
    errorRef.value = null;
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

  // ── 创建 room ──

  it("creates a room in the active project and switches to it", async () => {
    const projects = useProjectsStore();
    projects.setProjectsFromList([{ project_id: "p1", name: "demo" } as never]);
    projects.setActiveProject("p1");

    const wrapper = mount(RoomSelector);
    await wrapper.find('button[title="New room"]').trigger("click");
    await wrapper.find('input[placeholder="Room name"]').setValue("architecture");
    createRoomMock.mockResolvedValue({
      success: true,
      data: { room: { room_id: "r9", name: "architecture" } },
    });
    await wrapper.find("form").trigger("submit.prevent");
    expect(createRoomMock).toHaveBeenCalledWith("p1", "architecture");
    expect(switchRoomMock).toHaveBeenCalledWith("r9");
    expect(wrapper.find('input[placeholder="Room name"]').exists()).toBe(false);
  });

  it("refuses room creation without an active project", async () => {
    const wrapper = mount(RoomSelector);
    await wrapper.find('button[title="New room"]').trigger("click");
    await wrapper.find('input[placeholder="Room name"]').setValue("orphan");
    await wrapper.find("form").trigger("submit.prevent");
    expect(createRoomMock).not.toHaveBeenCalled();
    expect(errorRef.value).toContain("project");
  });

  it("propagates creation failure", async () => {
    const projects = useProjectsStore();
    projects.setProjectsFromList([{ project_id: "p1", name: "d" } as never]);
    projects.setActiveProject("p1");

    const wrapper = mount(RoomSelector);
    await wrapper.find('button[title="New room"]').trigger("click");
    await wrapper.find('input[placeholder="Room name"]').setValue("dup");
    createRoomMock.mockResolvedValue({ success: false, error: "boom" });
    await wrapper.find("form").trigger("submit.prevent");
    expect(errorRef.value).toBe("boom");
    expect(wrapper.find('input[placeholder="Room name"]').exists()).toBe(true);
  });

  // ── 成员管理（active room） ──

  it("manages members of the active room: remove and add", async () => {
    const rooms = useRoomsStore();
    const agents = useAgentsStore();
    rooms.setRoomsFromList([room("r1", "p1", "arch", ["architect"])]);
    rooms.setActiveRoom("r1");
    // active agents：architect（已在室）+ tester（候选）
    agents.setAgentsFromList([
      { name: "architect", config: {} as never },
      { name: "tester", config: {} as never },
    ]);

    const wrapper = mount(RoomSelector);
    await wrapper.vm.$nextTick();

    // 默认不显示成员管理面板
    expect(wrapper.text()).not.toContain("members");

    // 打开面板
    await wrapper.find('button[title="Manage members"]').trigger("click");
    expect(wrapper.text()).toContain("arch members");
    expect(wrapper.text()).toContain("architect");

    // 移除成员
    leaveRoomMock.mockResolvedValue({ success: true, data: {} });
    const removeBtn = wrapper
      .findAll("button")
      .find((b) => b.attributes("title") === "Remove from room");
    expect(removeBtn).toBeDefined();
    await removeBtn!.trigger("click");
    expect(leaveRoomMock).toHaveBeenCalledWith("r1", "architect");

    // 添加成员：候选 = 不在室内的 active agents（tester）
    joinRoomMock.mockResolvedValue({ success: true, data: {} });
    const addBtn = wrapper.findAll("button").find((b) => b.text().includes("Add member"));
    expect(addBtn).toBeDefined();
    await addBtn!.trigger("click");
    await wrapper.vm.$nextTick();
    const candidate = wrapper
      .findAll("li")
      .find((li) => li.text().includes("tester") && li.text().includes("🤖"));
    expect(candidate).toBeDefined();
    await candidate!.trigger("click");
    expect(joinRoomMock).toHaveBeenCalledWith("r1", "tester", "agent");
  });

  it("member candidates exclude agents already in the room", async () => {
    const rooms = useRoomsStore();
    const agents = useAgentsStore();
    rooms.setRoomsFromList([room("r1", "p1", "arch", ["architect"])]);
    rooms.setActiveRoom("r1");
    agents.setAgentsFromList([{ name: "architect", config: {} as never }]);

    const wrapper = mount(RoomSelector);
    await wrapper.vm.$nextTick();
    await wrapper.find('button[title="Manage members"]').trigger("click");
    // 唯一 active agent 已在室 → 添加按钮禁用
    const addBtn = wrapper.findAll("button").find((b) => b.text().includes("Add member"));
    expect(addBtn).toBeDefined();
    expect(addBtn!.attributes("disabled")).toBeDefined();
  });

  it("uses stable member IDs on the wire but renders and matches the display name", async () => {
    const rooms = useRoomsStore();
    const agents = useAgentsStore();
    const stableRoom = room("r1", "p1", "stable-room");
    stableRoom.members = [
      {
        subject: "stable-shuoxi",
        subject_type: "agent",
        subject_name: "shuoxi",
        joined_at: "",
      },
    ];
    rooms.setRoomsFromList([stableRoom]);
    rooms.setActiveRoom("r1");
    agents.setAgentsFromList([
      { name: "shuoxi", agent_id: "stable-shuoxi", config: {} as never },
      { name: "tester", agent_id: "stable-tester", config: {} as never },
    ]);

    const wrapper = mount(RoomSelector);
    await wrapper.vm.$nextTick();
    await wrapper.find('button[title="Manage members"]').trigger("click");

    expect(wrapper.text()).toContain("shuoxi");
    expect(wrapper.text()).not.toContain("stable-shuoxi");

    joinRoomMock.mockResolvedValue({ success: true, data: {} });
    const addBtn = wrapper.findAll("button").find((b) => b.text().includes("Add member"));
    await addBtn!.trigger("click");
    const candidate = wrapper.findAll("li").find((li) => li.text().includes("tester"));
    await candidate!.trigger("click");
    expect(joinRoomMock).toHaveBeenCalledWith("r1", "stable-tester", "agent");
  });
});
