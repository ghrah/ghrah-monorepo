import type { HITLRequestPayload } from "@ghrah/protocol";
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type { AgentTarget } from "../scope.js";

export interface HitlRequest {
  promiseId: string;
  projectId: string;
  agentId: string;
  agentName: string;
  abilityName: string;
  toolArgs: Record<string, unknown>;
  context: Record<string, unknown>;
}

export const useHitlStore = defineStore("ghrah-hitl", () => {
  const requests = ref<HitlRequest[]>([]);
  const pendingRequests = computed(() => requests.value);

  function onHitlRequest(payload: HITLRequestPayload): boolean {
    if (!payload.project_id || !payload.agent_id) return false;
    if (requests.value.some((request) => request.promiseId === payload.promise_id)) return true;
    requests.value.push({
      promiseId: payload.promise_id,
      projectId: payload.project_id,
      agentId: payload.agent_id,
      agentName: payload.agent_name,
      abilityName: payload.ability_name,
      toolArgs: payload.tool_args,
      context: payload.context,
    });
    return true;
  }

  function removeRequest(promiseId: string) {
    requests.value = requests.value.filter((request) => request.promiseId !== promiseId);
  }

  function clearAgent(target: AgentTarget) {
    requests.value = requests.value.filter(
      (request) => request.projectId !== target.projectId || request.agentId !== target.agentId,
    );
  }

  function clearProject(projectId: string) {
    requests.value = requests.value.filter((request) => request.projectId !== projectId);
  }

  function clearAll() {
    requests.value = [];
  }

  return {
    requests,
    pendingRequests,
    onHitlRequest,
    removeRequest,
    clearAgent,
    clearProject,
    clearAll,
  };
});
