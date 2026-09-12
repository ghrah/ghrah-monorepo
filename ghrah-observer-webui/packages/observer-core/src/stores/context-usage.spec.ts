import type { ContextUsageUpdatedPayload } from "@ghrah/protocol";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useContextUsageStore } from "./context-usage.js";

const payload = (
  overrides: Partial<ContextUsageUpdatedPayload> = {},
): ContextUsageUpdatedPayload => ({
  project_id: "p1",
  agent_id: "a1",
  cluster_id: "c1",
  agent_name: "coder",
  phase: "post_call",
  occupied_tokens: 4000,
  basis: "real",
  budget_tokens: 8192,
  compact_threshold: 0.8,
  real_input_tokens: 4000,
  real_output_tokens: 300,
  compaction: null,
  iteration: 2,
  ...overrides,
});

describe("useContextUsageStore", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("stores the latest snapshot keyed by agent", () => {
    const store = useContextUsageStore();
    expect(store.onContextUsageUpdated(payload(), 111)).toBe(true);
    expect(
      store.onContextUsageUpdated(payload({ phase: "pre_call", occupied_tokens: 4100 }), 222),
    ).toBe(true);
    const display = store.usageFor({ projectId: "p1", agentId: "a1" });
    // 展示优先 post_call 槽：latest 已是 pre_call，但占用取 4000
    expect(display).not.toBeNull();
    expect(display?.mode).toBe("ratio");
    expect(display?.occupiedTokens).toBe(4000);
    expect(display?.percent).toBe(49);
  });

  it("keeps latestPostCall slot separate from latest", () => {
    const store = useContextUsageStore();
    store.onContextUsageUpdated(payload(), 111);
    store.onContextUsageUpdated(payload({ phase: "pre_call", basis: "anchor" }), 222);
    const key = JSON.stringify(["p1", "a1"]);
    const entry = store.entries.get(key);
    expect(entry?.latest.phase).toBe("pre_call");
    expect(entry?.latestPostCall?.phase).toBe("post_call");
  });

  it("accumulates real input tokens across post_call events", () => {
    const store = useContextUsageStore();
    store.onContextUsageUpdated(payload({ real_input_tokens: 100 }), 1);
    store.onContextUsageUpdated(payload({ real_input_tokens: 250 }), 2);
    const display = store.usageFor({ projectId: "p1", agentId: "a1" });
    expect(display?.cumulativeInputTokens).toBe(350);
  });

  it("falls back to cumulative mode when budget is zero", () => {
    const store = useContextUsageStore();
    store.onContextUsageUpdated(payload({ budget_tokens: 0 }), 1);
    const display = store.usageFor({ projectId: "p1", agentId: "a1" });
    expect(display?.mode).toBe("cumulative");
    expect(display?.percent).toBeNull();
  });

  it("rejects payloads without project-scoped identity", () => {
    const store = useContextUsageStore();
    expect(store.onContextUsageUpdated(payload({ project_id: "" }))).toBe(false);
    expect(store.onContextUsageUpdated(payload({ agent_id: "" }))).toBe(false);
    expect(store.entries.size).toBe(0);
  });

  it("caps percent at 100 when occupied exceeds budget", () => {
    const store = useContextUsageStore();
    store.onContextUsageUpdated(payload({ occupied_tokens: 20000 }), 1);
    expect(store.usageFor({ projectId: "p1", agentId: "a1" })?.percent).toBe(100);
  });

  it("returns null for unknown agents", () => {
    const store = useContextUsageStore();
    store.onContextUsageUpdated(payload(), 1);
    expect(store.usageFor({ projectId: "p1", agentId: "nope" })).toBeNull();
  });

  it("clears exact agent and project scopes", () => {
    const store = useContextUsageStore();
    store.onContextUsageUpdated(payload(), 1);
    store.onContextUsageUpdated(payload({ project_id: "p2", agent_id: "a2" }), 2);
    store.clearAgent({ projectId: "p1", agentId: "a1" });
    expect(store.entries.size).toBe(1);
    store.clearProject("p2");
    expect(store.entries.size).toBe(0);
  });

  it("clearAll empties the store", () => {
    const store = useContextUsageStore();
    store.onContextUsageUpdated(payload(), 1);
    store.clearAll();
    expect(store.entries.size).toBe(0);
  });
});
