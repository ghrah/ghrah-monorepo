import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useHitlStore } from "./hitl.js";

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
    store.onHitlRequest({
      promise_id: "p1",
      agent_name: "agent-1",
      ability_name: "write_file",
      tool_args: { file_path: "/tmp/test.ts" },
      context: {},
    });
    expect(store.requests).toHaveLength(1);
    expect(store.requests[0].promiseId).toBe("p1");
    expect(store.requests[0].agentName).toBe("agent-1");
    expect(store.requests[0].abilityName).toBe("write_file");
  });

  it("removeRequest removes by promiseId", () => {
    const store = useHitlStore();
    store.onHitlRequest({
      promise_id: "p1",
      agent_name: "agent-1",
      ability_name: "write_file",
      tool_args: {},
      context: {},
    });
    store.onHitlRequest({
      promise_id: "p2",
      agent_name: "agent-1",
      ability_name: "execute_command",
      tool_args: {},
      context: {},
    });
    expect(store.requests).toHaveLength(2);

    store.removeRequest("p1");
    expect(store.requests).toHaveLength(1);
    expect(store.requests[0].promiseId).toBe("p2");
  });

  it("clearAll removes all requests", () => {
    const store = useHitlStore();
    store.onHitlRequest({
      promise_id: "p1",
      agent_name: "agent-1",
      ability_name: "write_file",
      tool_args: {},
      context: {},
    });
    store.onHitlRequest({
      promise_id: "p2",
      agent_name: "agent-2",
      ability_name: "execute_command",
      tool_args: {},
      context: {},
    });
    store.clearAll();
    expect(store.requests).toHaveLength(0);
  });
});
