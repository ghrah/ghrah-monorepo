import type { HITLRequestPayload } from "@ghrah/protocol";
import { defineStore } from "pinia";
import { computed, ref } from "vue";

export interface HitlRequest {
  promiseId: string;
  agentName: string;
  abilityName: string;
  toolArgs: Record<string, unknown>;
  context: Record<string, unknown>;
}

export const useHitlStore = defineStore("ghrah-hitl", () => {
  const requests = ref<HitlRequest[]>([]);

  const pendingRequests = computed(() => requests.value);

  function onHitlRequest(payload: HITLRequestPayload) {
    requests.value.push({
      promiseId: payload.promise_id,
      agentName: payload.agent_name,
      abilityName: payload.ability_name,
      toolArgs: payload.tool_args,
      context: payload.context,
    });
  }

  function removeRequest(promiseId: string) {
    requests.value = requests.value.filter((r) => r.promiseId !== promiseId);
  }

  function clearAll() {
    requests.value = [];
  }

  return {
    requests,
    pendingRequests,
    onHitlRequest,
    removeRequest,
    clearAll,
  };
});
