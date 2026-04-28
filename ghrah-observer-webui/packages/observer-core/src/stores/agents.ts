import type {
  AgentConfigPayload,
  AgentSpawnedPayload,
  AgentTerminatedPayload,
} from "@ghrah/protocol";
import { defineStore } from "pinia";
import { computed, ref } from "vue";

export interface AgentInfo {
  name: string;
  config: AgentConfigPayload;
  status: "active" | "terminated";
}

export const useAgentsStore = defineStore("ghrah-agents", () => {
  const agents = ref<Map<string, AgentInfo>>(new Map());

  const activeAgents = computed(() =>
    Array.from(agents.value.values()).filter((a) => a.status === "active"),
  );

  function onAgentSpawned(payload: AgentSpawnedPayload) {
    agents.value.set(payload.name, {
      name: payload.name,
      config: payload.config,
      status: "active",
    });
  }

  function onAgentTerminated(payload: AgentTerminatedPayload) {
    const existing = agents.value.get(payload.name);
    if (existing) {
      existing.status = "terminated";
    }
  }

  function setAgentsFromList(list: Array<{ name: string; config: AgentConfigPayload }>) {
    agents.value.clear();
    for (const item of list) {
      agents.value.set(item.name, {
        name: item.name,
        config: item.config,
        status: "active",
      });
    }
  }

  function removeAgent(name: string) {
    agents.value.delete(name);
  }

  return {
    agents,
    activeAgents,
    onAgentSpawned,
    onAgentTerminated,
    setAgentsFromList,
    removeAgent,
  };
});
