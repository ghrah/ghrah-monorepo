import type { HITLRequestPayload } from "@ghrah/protocol";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useHitlStore } from "./hitl.js";

const makeRequest = (
  promise_id: string,
  agent_name: string,
  ability_name: string,
  tool_args: Record<string, unknown> = {},
): HITLRequestPayload => ({
  promise_id,
  agent_id: "",
  project_id: "",
  cluster_id: "",
  agent_name,
  ability_name,
  tool_args,
  context: {},
});

describe("useHitlStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("starts with empty requests", () => {
    const store = useHitlStore();
    expect(store.requests).toHaveLength(0);
    expect(store.pendingRequests).toHaveLength(0);
  });

  it("onHitlRequest adds request to the list", () => {
    const store = useHitlStore();
    store.onHitlRequest(makeRequest("p1", "agent-1", "write_file", { file_path: "/tmp/test.ts" }));
    expect(store.requests).toHaveLength(1);
    expect(store.requests[0].promiseId).toBe("p1");
    expect(store.requests[0].agentName).toBe("agent-1");
    expect(store.requests[0].abilityName).toBe("write_file");
  });

  it("removeRequest removes by promiseId", () => {
    const store = useHitlStore();
    store.onHitlRequest(makeRequest("p1", "agent-1", "write_file"));
    store.onHitlRequest(makeRequest("p2", "agent-1", "execute_command"));
    expect(store.requests).toHaveLength(2);

    store.removeRequest("p1");
    expect(store.requests).toHaveLength(1);
    expect(store.requests[0].promiseId).toBe("p2");
  });

  it("clearAll removes all requests", () => {
    const store = useHitlStore();
    store.onHitlRequest(makeRequest("p1", "agent-1", "write_file"));
    store.onHitlRequest(makeRequest("p2", "agent-2", "execute_command"));
    store.clearAll();
    expect(store.requests).toHaveLength(0);
  });
});
