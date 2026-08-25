// @vitest-environment happy-dom

import { useChatStore, useConnectionStore, useRoomsStore } from "@ghrah/observer-core";
import type { RoomInfoPayload, RoomLogEntryPayload } from "@ghrah/protocol";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

const roomSendMock = vi.fn();
vi.mock("@/composables/useObserver", () => ({
  useObserver: () => ({ roomSend: roomSendMock }),
}));

import ChatPanel from "./chat-panel.vue";

function room(id: string, name: string): RoomInfoPayload {
  return {
    room_id: id,
    project_id: "p1",
    name,
    status: "active",
    members: [],
    seq_watermark: 0,
    version: 1,
    created_at: "",
    updated_at: "",
  };
}

function logEntry(
  roomId: string,
  seq: number,
  author: string,
  authorType: "agent" | "human",
  message: string,
): RoomLogEntryPayload {
  return {
    id: `${roomId}-${seq}`,
    room_id: roomId,
    seq,
    author,
    author_type: authorType,
    timestamp: 1767225600,
    data: { message },
  };
}

function setup() {
  const rooms = useRoomsStore();
  rooms.setRoomsFromList([room("r1", "arch"), room("r2", "frontend")]);
  const chat = useChatStore();
  const connection = useConnectionStore();
  connection.setConnected();
  return { rooms, chat, connection };
}

describe("ChatPanel", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    roomSendMock.mockReset();
  });

  it("shows empty state when no active room", () => {
    setup();
    const wrapper = mount(ChatPanel);
    expect(wrapper.text()).toContain("Select a room to start chatting");
  });

  it("shows active room name in header", async () => {
    const { rooms } = setup();
    rooms.setActiveRoom("r1");
    const wrapper = mount(ChatPanel);
    await wrapper.vm.$nextTick();
    expect(wrapper.find("h3").text()).toContain("arch");
  });

  it("projects room log entries (agent → conversation, human → human_input)", async () => {
    const { rooms } = setup();
    rooms.setActiveRoom("r1");
    rooms.setRoomLog("r1", [
      logEntry("r1", 1, "architect", "agent", "hello from agent"),
      logEntry("r1", 2, "user", "human", "hello from human"),
    ]);
    const wrapper = mount(ChatPanel);
    await wrapper.vm.$nextTick();
    const entries = wrapper.findAll(".chat-entry");
    expect(entries).toHaveLength(2);
    expect(entries[0].classes()).toContain("entry-conversation");
    expect(entries[0].text()).toContain("hello from agent");
    expect(entries[1].classes()).toContain("entry-human");
    expect(entries[1].text()).toContain("hello from human");
  });

  it("merges pending entries of the active room only", async () => {
    const { rooms, chat } = setup();
    rooms.setActiveRoom("r1");
    rooms.setRoomLog("r1", [logEntry("r1", 1, "architect", "agent", "history")]);
    chat.addPendingEntry({ to: "r1", content: "pending-r1", agentName: "", roomId: "r1" });
    chat.addPendingEntry({ to: "r2", content: "pending-r2", agentName: "", roomId: "r2" });
    const wrapper = mount(ChatPanel);
    await wrapper.vm.$nextTick();
    const entries = wrapper.findAll(".chat-entry");
    expect(entries).toHaveLength(2);
    expect(wrapper.text()).toContain("history");
    expect(wrapper.text()).toContain("pending-r1");
    expect(wrapper.text()).not.toContain("pending-r2");
    expect(entries[1].classes()).toContain("entry-pending");
  });

  it("handleSend calls roomSend and adds pending entry", async () => {
    const { rooms, chat } = setup();
    rooms.setActiveRoom("r1");
    roomSendMock.mockResolvedValueOnce({ success: true });
    const wrapper = mount(ChatPanel);
    await wrapper.vm.$nextTick();
    await wrapper.find('input[type="text"]').setValue("hello room");
    await wrapper.find("form").trigger("submit");
    expect(roomSendMock).toHaveBeenCalledWith("r1", "hello room");
    const pending = chat.allEntries.find((e) => e.content === "hello room");
    expect(pending?.roomId).toBe("r1");
    expect(pending?.pending).toBe(true);
  });

  it("pending entry is removed when echo arrives and history shows instead", async () => {
    const { rooms, chat } = setup();
    rooms.setActiveRoom("r1");
    roomSendMock.mockResolvedValueOnce({ success: true });
    const wrapper = mount(ChatPanel);
    await wrapper.vm.$nextTick();
    await wrapper.find('input[type="text"]').setValue("echo me");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.text()).toContain("echo me");
    // 模拟 bind 的 ROOM_LOG_APPENDED 分发：rooms 追加 + chat echo 确认
    const echo = logEntry("r1", 1, "user", "human", "echo me");
    rooms.onRoomLogAppended({ entry: echo });
    chat.onRoomLogAppended(echo);
    await wrapper.vm.$nextTick();
    expect(chat.allEntries.find((e) => e.content === "echo me")).toBeUndefined();
    const entries = wrapper.findAll(".chat-entry");
    expect(entries).toHaveLength(1);
    expect(entries[0].classes()).toContain("entry-human");
    expect(entries[0].classes()).not.toContain("entry-pending");
  });

  it("marks pending error when roomSend returns null", async () => {
    const { rooms, chat } = setup();
    rooms.setActiveRoom("r1");
    roomSendMock.mockResolvedValueOnce(null);
    const wrapper = mount(ChatPanel);
    await wrapper.vm.$nextTick();
    await wrapper.find('input[type="text"]').setValue("boom");
    await wrapper.find("form").trigger("submit");
    await vi.waitFor(() => {
      expect(chat.allEntries.some((e) => e.error)).toBe(true);
    });
    const e = chat.allEntries.find((x) => x.error);
    expect(e?.error).toContain("发送失败");
    expect(e?.roomId).toBe("r1");
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".chat-entry").classes()).toContain("entry-error");
  });

  it("does not send when input is empty", async () => {
    const { rooms } = setup();
    rooms.setActiveRoom("r1");
    const wrapper = mount(ChatPanel);
    await wrapper.vm.$nextTick();
    await wrapper.find("form").trigger("submit");
    expect(roomSendMock).not.toHaveBeenCalled();
  });
});
