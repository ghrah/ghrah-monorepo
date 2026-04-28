import type { AbilityResultPayload } from "@ghrah/protocol";
import { defineStore } from "pinia";
import { ref } from "vue";

export interface FileChange {
  agentName: string;
  abilityName: string;
  filePath?: string;
  success: boolean;
  result?: unknown;
  error?: string;
  timestamp?: number;
}

const FILE_CHANGE_ABILITIES = new Set(["write_file", "edit_file", "delete_file"]);

export const useChangesStore = defineStore("ghrah-changes", () => {
  const changes = ref<FileChange[]>([]);

  function onAbilityResult(payload: AbilityResultPayload, toolArgs?: Record<string, unknown>) {
    if (!FILE_CHANGE_ABILITIES.has(payload.ability_name)) return;

    changes.value = [
      ...changes.value,
      {
        agentName: payload.agent_name,
        abilityName: payload.ability_name,
        filePath: toolArgs?.["file_path"] as string | undefined,
        success: payload.success,
        result: payload.result,
        error: payload.error ?? undefined,
        timestamp: Date.now(),
      },
    ];
  }

  function clearAll() {
    changes.value = [];
  }

  return {
    changes,
    onAbilityResult,
    clearAll,
  };
});
