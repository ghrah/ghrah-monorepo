import type { ActionNode } from "@ghrah/protocol";
import { defineStore } from "pinia";
import { ref } from "vue";
import { type FileChange, projectNodeToFileChanges } from "../projection.js";

export const useChangesStore = defineStore("ghrah-changes", () => {
  const changes = ref<FileChange[]>([]);
  const seenKeys = new Set<string>();

  function onActionChainNode(_agentName: string, node: ActionNode) {
    const fcs = projectNodeToFileChanges(node);
    if (fcs.length === 0) return;
    const next = [...changes.value];
    let appended = false;
    for (const fc of fcs) {
      const key = `${fc.nodeId}#${fc.abilityName}#${fc.filePath ?? ""}`;
      if (seenKeys.has(key)) continue;
      seenKeys.add(key);
      next.push(fc);
      appended = true;
    }
    if (appended) changes.value = next;
  }

  function clearAll() {
    changes.value = [];
    seenKeys.clear();
  }

  return {
    changes,
    onActionChainNode,
    clearAll,
  };
});
