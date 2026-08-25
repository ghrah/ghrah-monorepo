import type { RoomLogEntryPayload } from "@ghrah/protocol";
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type { ChatEntry } from "../projection.js";

/** 当前人类用户的默认 author 标识（与 ObserverClient.roomSend 默认 author 对齐）。 */
export const DEFAULT_HUMAN_AUTHOR = "user";

/**
 * chat store = active room 的 pending 乐观层。
 * 历史条目不再由本 store 持有——由 rooms store 的 logs 经 roomLogToChatEntries 投影
 * （component 层组合）；这里只保留 pending / error 条目。
 */
export const useChatStore = defineStore("ghrah-chat", () => {
  /** 仅 pending / error 条目（确认后从列表移除，由 room log 投影接管显示）。 */
  const entries = ref<ChatEntry[]>([]);
  const currentAuthor = ref<string>(DEFAULT_HUMAN_AUTHOR);
  let pendingSeq = 0;

  function addPendingEntry(partial: {
    to: string;
    content: string;
    agentName: string;
    roomId?: string;
  }): ChatEntry {
    const seq = ++pendingSeq;
    const entry: ChatEntry = {
      from: currentAuthor.value,
      to: partial.to,
      content: partial.content,
      kind: "human_input",
      timestamp: new Date().toISOString(),
      nodeId: "",
      agentName: partial.agentName,
      childSeq: -seq,
      roomId: partial.roomId,
      pending: true,
    };
    entries.value = [...entries.value, entry];
    return entry;
  }

  function _entryContent(entry: RoomLogEntryPayload): string {
    const data = entry.data ?? {};
    const message = data.message;
    return typeof message === "string" ? message : JSON.stringify(data);
  }

  /**
   * echo 回环确认：room_log_appended 中 author_type=human 且 author 匹配当前用户时，
   * FIFO 取首条 roomId+to+content 匹配的 pending 移除（历史由 room log 投影展示）。
   */
  function onRoomLogAppended(entry: RoomLogEntryPayload) {
    if (entry.author_type !== "human" || entry.author !== currentAuthor.value) return;
    const content = _entryContent(entry);
    const idx = entries.value.findIndex(
      (p) =>
        p.pending === true &&
        p.content === content &&
        (p.roomId != null ? p.roomId === entry.room_id : p.to === entry.room_id),
    );
    if (idx < 0) return;
    const next = [...entries.value];
    next.splice(idx, 1);
    entries.value = next;
  }

  // 发送失败回退：FIFO 找首条 roomId+to+content 匹配的 pending，标记 error 留流
  function markPendingError(to: string, content: string, error: string, roomId?: string) {
    const idx = entries.value.findIndex(
      (p) =>
        p.pending === true &&
        p.to === to &&
        p.content === content &&
        (roomId === undefined || p.roomId === roomId),
    );
    if (idx < 0) return;
    const next = [...entries.value];
    next[idx] = { ...next[idx], pending: false, error };
    entries.value = next;
  }

  const allEntries = computed<ChatEntry[]>(() => entries.value);

  function setCurrentAuthor(author: string) {
    currentAuthor.value = author;
  }

  function clearAll() {
    entries.value = [];
    pendingSeq = 0;
  }

  return {
    entries,
    allEntries,
    currentAuthor,
    setCurrentAuthor,
    addPendingEntry,
    onRoomLogAppended,
    markPendingError,
    clearAll,
  };
});
