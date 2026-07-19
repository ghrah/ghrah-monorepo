import type { ActionNode } from "@ghrah/protocol";
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { type ChatEntry, projectNodeToChatEntries } from "../projection.js";

export const useChatStore = defineStore("ghrah-chat", () => {
  const entries = ref<ChatEntry[]>([]);
  const dedupKeys = ref<Set<string>>(new Set());
  let pendingSeq = 0;

  function onActionChainNode(node: ActionNode) {
    const projected = projectNodeToChatEntries(node);
    if (projected.length === 0) return;
    const next = [...entries.value];
    for (const e of projected) {
      const key = `${e.nodeId}#${e.kind}#${e.from}#${e.to}#${e.childSeq}`;
      if (e.kind === "human_input") {
        // echo 回环确认：FIFO 取首条 content+to 匹配的 pending 就地确认
        const idx = next.findIndex(
          (p) => p.pending === true && p.to === e.to && p.content === e.content,
        );
        if (idx >= 0) {
          next[idx] = { ...next[idx], nodeId: e.nodeId, pending: false, timestamp: e.timestamp };
          keysAdd(key);
          continue;
        }
      }
      if (dedupKeys.value.has(key)) continue;
      next.push(e);
      keysAdd(key);
    }
    entries.value = next;
  }

  function keysAdd(key: string) {
    const next = new Set(dedupKeys.value);
    next.add(key);
    dedupKeys.value = next;
  }

  function addPendingEntry(partial: { to: string; content: string; agentName: string }): ChatEntry {
    const seq = ++pendingSeq;
    const entry: ChatEntry = {
      from: "user",
      to: partial.to,
      content: partial.content,
      kind: "human_input",
      timestamp: new Date().toISOString(),
      nodeId: "",
      agentName: partial.agentName,
      childSeq: -seq,
      pending: true,
    };
    entries.value = [...entries.value, entry];
    return entry;
  }

  // 发送失败回退：FIFO 找首条 content+to 匹配的 pending，标记 error 留流
  function markPendingError(to: string, content: string, error: string) {
    const idx = entries.value.findIndex(
      (p) => p.pending === true && p.to === to && p.content === content,
    );
    if (idx < 0) return;
    const next = [...entries.value];
    next[idx] = { ...next[idx], pending: false, error };
    entries.value = next;
  }

  const allEntries = computed<ChatEntry[]>(() => entries.value);

  function clearAll() {
    entries.value = [];
    dedupKeys.value = new Set();
    pendingSeq = 0;
  }

  return {
    entries,
    allEntries,
    onActionChainNode,
    addPendingEntry,
    markPendingError,
    clearAll,
  };
});
