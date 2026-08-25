import type { RoomLogEntryPayload } from "@ghrah/protocol";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { DEFAULT_HUMAN_AUTHOR, useChatStore } from "./chat.js";

function makeRoomEntry(overrides: Partial<RoomLogEntryPayload> = {}): RoomLogEntryPayload {
  return {
    id: "e1",
    room_id: "r1",
    seq: 1,
    author: DEFAULT_HUMAN_AUTHOR,
    author_type: "human",
    timestamp: 1750000000,
    data: { message: "hi" },
    ...overrides,
  };
}

describe("useChatStore (active room pending 乐观层)", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("starts with empty entries", () => {
    const store = useChatStore();
    expect(store.allEntries).toHaveLength(0);
  });

  it("addPendingEntry sets pending=true with roomId", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "r1", content: "hello", agentName: "", roomId: "r1" });
    expect(store.allEntries).toHaveLength(1);
    expect(store.allEntries[0]).toMatchObject({
      from: DEFAULT_HUMAN_AUTHOR,
      to: "r1",
      content: "hello",
      kind: "human_input",
      roomId: "r1",
      pending: true,
    });
  });

  it("echo 确认：room_log_appended (human + 当前 author) FIFO 移除匹配 pending", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "r1", content: "hello", agentName: "", roomId: "r1" });
    store.onRoomLogAppended(makeRoomEntry({ data: { message: "hello" } }));
    expect(store.allEntries).toHaveLength(0);
  });

  it("echo 确认：roomId 不匹配时不确认", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "r1", content: "hello", agentName: "", roomId: "r1" });
    store.onRoomLogAppended(makeRoomEntry({ room_id: "r2", data: { message: "hello" } }));
    expect(store.allEntries).toHaveLength(1);
    expect(store.allEntries[0].pending).toBe(true);
  });

  it("echo 确认：agent 条目或其他 author 不确认 human pending", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "r1", content: "hello", agentName: "", roomId: "r1" });
    store.onRoomLogAppended(
      makeRoomEntry({ author: "agent-1", author_type: "agent", data: { message: "hello" } }),
    );
    store.onRoomLogAppended(
      makeRoomEntry({ author: "other-user", author_type: "human", data: { message: "hello" } }),
    );
    expect(store.allEntries).toHaveLength(1);
    expect(store.allEntries[0].pending).toBe(true);
  });

  it("echo 确认：content 取 data.message，缺失时回退 JSON.stringify(data)", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "r1", content: "hello", agentName: "", roomId: "r1" });
    // 无 message 字段 → content 不匹配，不确认
    store.onRoomLogAppended(makeRoomEntry({ data: { other: 1 } }));
    expect(store.allEntries).toHaveLength(1);
    store.onRoomLogAppended(makeRoomEntry({ data: { message: "hello" } }));
    expect(store.allEntries).toHaveLength(0);
  });

  it("连续相同内容的 echo 逐条确认（FIFO 不误删）", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "r1", content: "dup", agentName: "", roomId: "r1" });
    store.addPendingEntry({ to: "r1", content: "dup", agentName: "", roomId: "r1" });
    store.onRoomLogAppended(makeRoomEntry({ id: "e1", seq: 1, data: { message: "dup" } }));
    expect(store.allEntries).toHaveLength(1);
    store.onRoomLogAppended(makeRoomEntry({ id: "e2", seq: 2, data: { message: "dup" } }));
    expect(store.allEntries).toHaveLength(0);
  });

  it("多 room pending 互不干扰", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "r1", content: "hi", agentName: "", roomId: "r1" });
    store.addPendingEntry({ to: "r2", content: "hi", agentName: "", roomId: "r2" });
    store.onRoomLogAppended(makeRoomEntry({ room_id: "r2", data: { message: "hi" } }));
    expect(store.allEntries).toHaveLength(1);
    expect(store.allEntries[0].roomId).toBe("r1");
  });

  it("无 roomId 的旧式 pending 以 to 兜底匹配 room_id", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "r1", content: "hello", agentName: "r1" });
    store.onRoomLogAppended(makeRoomEntry({ data: { message: "hello" } }));
    expect(store.allEntries).toHaveLength(0);
  });

  it("markPendingError marks matching pending as error, leaves it in stream", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "r1", content: "hi", agentName: "", roomId: "r1" });
    store.markPendingError("r1", "hi", "发送失败：未连接", "r1");
    const e = store.allEntries;
    expect(e).toHaveLength(1);
    expect(e[0].pending).toBe(false);
    expect(e[0].error).toBe("发送失败：未连接");
  });

  it("markPendingError no-op when no matching pending", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "r1", content: "hi", agentName: "", roomId: "r1" });
    store.markPendingError("r1", "no-such-content", "err", "r1");
    expect(store.allEntries[0].pending).toBe(true);
    expect(store.allEntries[0].error).toBeUndefined();
  });

  it("setCurrentAuthor 改变 echo 匹配的 author", () => {
    const store = useChatStore();
    store.setCurrentAuthor("alice");
    store.addPendingEntry({ to: "r1", content: "hi", agentName: "", roomId: "r1" });
    expect(store.allEntries[0].from).toBe("alice");
    store.onRoomLogAppended(
      makeRoomEntry({ author: DEFAULT_HUMAN_AUTHOR, data: { message: "hi" } }),
    );
    expect(store.allEntries).toHaveLength(1);
    store.onRoomLogAppended(makeRoomEntry({ author: "alice", data: { message: "hi" } }));
    expect(store.allEntries).toHaveLength(0);
  });

  it("clearAll resets pending entries", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "r1", content: "hi", agentName: "", roomId: "r1" });
    store.clearAll();
    expect(store.allEntries).toHaveLength(0);
  });
});
