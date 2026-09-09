import type { HITLRequestPayload } from "@ghrah/protocol";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useHitlStore } from "./hitl.js";

const payload = (overrides: Partial<HITLRequestPayload> = {}): HITLRequestPayload => ({
  project_id: "p1",
  agent_id: "a1",
  cluster_id: "c1",
  promise_id: "h1",
  agent_name: "coder",
  ability_name: "write_file",
  tool_args: {},
  context: {},
  ...overrides,
});

describe("useHitlStore", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("stores structured agent scope and deduplicates replay", () => {
    const store = useHitlStore();
    expect(store.onHitlRequest(payload())).toBe(true);
    expect(store.onHitlRequest(payload())).toBe(true);
    expect(store.requests).toEqual([
      expect.objectContaining({ projectId: "p1", agentId: "a1", agentName: "coder" }),
    ]);
  });

  it("rejects requests without project-scoped identity", () => {
    const store = useHitlStore();
    expect(store.onHitlRequest(payload({ project_id: "" }))).toBe(false);
    expect(store.requests).toEqual([]);
  });

  it("clears exact agent and project scopes", () => {
    const store = useHitlStore();
    store.onHitlRequest(payload());
    store.onHitlRequest(payload({ project_id: "p2", agent_id: "a2", promise_id: "h2" }));
    store.clearAgent({ projectId: "p1", agentId: "a1", agentName: "coder" });
    expect(store.requests.map((request) => request.promiseId)).toEqual(["h2"]);
    store.clearProject("p2");
    expect(store.requests).toEqual([]);
  });
});
