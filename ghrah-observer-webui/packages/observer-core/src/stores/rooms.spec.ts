import type { RoomInfoPayload, RoomLogEntryPayload, RoomMember } from "@ghrah/protocol";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { MAX_CACHED_ROOM_LOGS, useRoomsStore } from "./rooms.js";

function makeRoom(overrides: Partial<RoomInfoPayload> = {}): RoomInfoPayload {
  return {
    room_id: "r1",
    project_id: "p1",
    name: "room-1",
    status: "active",
    members: [],
    seq_watermark: 0,
    version: 1,
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

function makeMember(subject: string, subject_type: RoomMember["subject_type"] = "agent"): RoomMember {
  return { subject, subject_type, joined_at: "" };
}

function makeEntry(overrides: Partial<RoomLogEntryPayload> = {}): RoomLogEntryPayload {
  return {
    id: "e1",
    room_id: "r1",
    seq: 1,
    author: "agent-1",
    author_type: "agent",
    timestamp: 1750000000,
    data: { message: "hi" },
    ...overrides,
  };
}

describe("useRoomsStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("starts empty", () => {
    const store = useRoomsStore();
    expect(store.rooms.size).toBe(0);
    expect(store.logs.size).toBe(0);
    expect(store.activeRoomId).toBeNull();
    expect(store.activeRoom).toBeNull();
    expect(store.activeRoomLog).toEqual([]);
  });

  it("onRoomCreated / onRoomUpdated upsert by room_id", () => {
    const store = useRoomsStore();
    store.onRoomCreated({ room: makeRoom() });
    expect(store.rooms.size).toBe(1);
    store.onRoomUpdated({ room: makeRoom({ name: "renamed", version: 2 }) });
    expect(store.rooms.size).toBe(1);
    expect(store.rooms.get("r1")?.name).toBe("renamed");
  });

  it("onRoomDeleted removes room + its log, resets activeRoomId", () => {
    const store = useRoomsStore();
    store.onRoomCreated({ room: makeRoom() });
    store.setRoomLog("r1", [makeEntry()]);
    store.setActiveRoom("r1");
    store.onRoomDeleted({ room_id: "r1", project_id: "p1" });
    expect(store.rooms.size).toBe(0);
    expect(store.logs.has("r1")).toBe(false);
    expect(store.activeRoomId).toBeNull();
  });

  it("onRoomMemberJoined / onRoomMemberLeft upsert envelope room", () => {
    const store = useRoomsStore();
    store.onRoomCreated({ room: makeRoom() });
    store.onRoomMemberJoined({
      room: makeRoom({ members: [makeMember("agent-1")] }),
      member: makeMember("agent-1"),
    });
    expect(store.rooms.get("r1")?.members).toHaveLength(1);
    store.onRoomMemberLeft({
      room: makeRoom({ members: [] }),
      subject: "agent-1",
    });
    expect(store.rooms.get("r1")?.members).toHaveLength(0);
  });

  it("onRoomLogAppended appends by room, dedup by entry.id", () => {
    const store = useRoomsStore();
    store.onRoomLogAppended({ entry: makeEntry() });
    store.onRoomLogAppended({ entry: makeEntry() });
    store.onRoomLogAppended({ entry: makeEntry({ id: "e2", seq: 2 }) });
    expect(store.logs.get("r1")).toHaveLength(2);
  });

  it("onRoomLogAppended keeps seq order on out-of-order delivery", () => {
    const store = useRoomsStore();
    store.onRoomLogAppended({ entry: makeEntry({ id: "e2", seq: 2 }) });
    store.onRoomLogAppended({ entry: makeEntry({ id: "e1", seq: 1 }) });
    store.onRoomLogAppended({ entry: makeEntry({ id: "e3", seq: 3 }) });
    expect(store.logs.get("r1")?.map((e) => e.seq)).toEqual([1, 2, 3]);
  });

  it("setRoomsFromList replaces rooms map", () => {
    const store = useRoomsStore();
    store.onRoomCreated({ room: makeRoom({ room_id: "old" }) });
    store.setRoomsFromList([makeRoom({ room_id: "r1" }), makeRoom({ room_id: "r2" })]);
    expect([...store.rooms.keys()].sort()).toEqual(["r1", "r2"]);
  });

  it("setRoomLog replaces entries sorted by seq", () => {
    const store = useRoomsStore();
    store.setRoomLog("r1", [makeEntry({ id: "e2", seq: 2 }), makeEntry({ id: "e1", seq: 1 })]);
    expect(store.activeRoomLog).toEqual([]);
    store.setActiveRoom("r1");
    expect(store.activeRoomLog.map((e) => e.seq)).toEqual([1, 2]);
  });

  it("activeRoom / activeRoomLog follow activeRoomId", () => {
    const store = useRoomsStore();
    store.setRoomsFromList([makeRoom({ room_id: "r1" }), makeRoom({ room_id: "r2", name: "two" })]);
    store.setRoomLog("r2", [makeEntry({ room_id: "r2" })]);
    store.setActiveRoom("r2");
    expect(store.activeRoom?.name).toBe("two");
    expect(store.activeRoomLog).toHaveLength(1);
  });

  it("LRU: keeps at most MAX_CACHED_ROOM_LOGS rooms, evicts least recently used", () => {
    const store = useRoomsStore();
    for (let i = 0; i < MAX_CACHED_ROOM_LOGS + 2; i++) {
      store.setRoomLog(`r${i}`, [makeEntry({ room_id: `r${i}` })]);
    }
    expect(store.logs.size).toBe(MAX_CACHED_ROOM_LOGS);
    // 最久未访问的 r0、r1 被淘汰
    expect(store.logs.has("r0")).toBe(false);
    expect(store.logs.has("r1")).toBe(false);
    expect(store.logs.has(`r${MAX_CACHED_ROOM_LOGS + 1}`)).toBe(true);
  });

  it("LRU: accessing a room (setActiveRoom) protects it from eviction; switching does not clear cache", () => {
    const store = useRoomsStore();
    for (let i = 0; i < MAX_CACHED_ROOM_LOGS; i++) {
      store.setRoomLog(`r${i}`, [makeEntry({ room_id: `r${i}` })]);
    }
    store.setActiveRoom("r0");
    // 再灌 2 个 room，触发淘汰；r0 是 active，不淘汰
    store.setRoomLog("rA", [makeEntry({ room_id: "rA" })]);
    store.setRoomLog("rB", [makeEntry({ room_id: "rB" })]);
    expect(store.logs.size).toBe(MAX_CACHED_ROOM_LOGS);
    expect(store.logs.has("r0")).toBe(true);
    expect(store.logs.has("r1")).toBe(false);
    // 切换 active 不清缓存
    store.setActiveRoom("rA");
    expect(store.logs.size).toBe(MAX_CACHED_ROOM_LOGS);
    expect(store.logs.has("r0")).toBe(true);
  });

  it("clearAll resets everything", () => {
    const store = useRoomsStore();
    store.onRoomCreated({ room: makeRoom() });
    store.setRoomLog("r1", [makeEntry()]);
    store.setActiveRoom("r1");
    store.clearAll();
    expect(store.rooms.size).toBe(0);
    expect(store.logs.size).toBe(0);
    expect(store.activeRoomId).toBeNull();
  });
});
