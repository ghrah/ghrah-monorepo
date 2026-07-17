import type { ActionNode } from "@ghrah/protocol";
import { defineStore } from "pinia";
import { ref } from "vue";
import { type ChatEntry, projectNodeToChatEntries } from "../projection.js";

export const useChatStore = defineStore("ghrah-chat", () => {
  const entries = ref<Map<string, ChatEntry[]>>(new Map());
  const dedupKeys = ref<Map<string, Set<string>>>(new Map());
  let pendingSeq = 0;

  function onActionChainNode(agentName: string, node: ActionNode) {
    const projected = projectNodeToChatEntries(node);
    if (projected.length === 0) return;
    const bucket = entries.value.get(agentName) ?? [];
    const keys = dedupKeys.value.get(agentName) ?? new Set<string>();
    const next = [...bucket];
    for (const e of projected) {
      const key = `${e.nodeId}#${e.kind}#${e.from}#${e.to}#${e.childSeq}`;
      if (e.kind === "human_input") {
        // echo 回环确认：FIFO 取首条 content+to 匹配的 pending 就地确认
        const idx = next.findIndex(
          (p) => p.pending === true && p.to === e.to && p.content === e.content,
        );
        if (idx >= 0) {
          next[idx] = { ...next[idx], nodeId: e.nodeId, pending: false, timestamp: e.timestamp };
          keys.add(key);
          continue;
        }
      }
      if (keys.has(key)) continue;
      next.push(e);
      keys.add(key);
    }
    entries.value = new Map(entries.value).set(agentName, next);
    dedupKeys.value = new Map(dedupKeys.value).set(agentName, keys);
  }

  function addPendingEntry(agentName: string, partial: { to: string; content: string }): ChatEntry {
    const seq = ++pendingSeq;
    const entry: ChatEntry = {
      from: "user",
      to: partial.to,
      content: partial.content,
      kind: "human_input",
      timestamp: new Date().toISOString(),
      nodeId: "",
      agentName,
      childSeq: -seq,
      pending: true,
    };
    const bucket = entries.value.get(agentName) ?? [];
    entries.value = new Map(entries.value).set(agentName, [...bucket, entry]);
    return entry;
  }

  function getEntries(agentName: string): ChatEntry[] {
    return entries.value.get(agentName) ?? [];
  }

  function clearEntries(agentName: string) {
    if (!entries.value.has(agentName) && !dedupKeys.value.has(agentName)) return;
    const nextEntries = new Map(entries.value);
    const nextKeys = new Map(dedupKeys.value);
    nextEntries.delete(agentName);
    nextKeys.delete(agentName);
    entries.value = nextEntries;
    dedupKeys.value = nextKeys;
  }

  function clearAll() {
    entries.value = new Map();
    dedupKeys.value = new Map();
    pendingSeq = 0;
  }

  return {
    entries,
    onActionChainNode,
    addPendingEntry,
    getEntries,
    clearEntries,
    clearAll,
  };
});
