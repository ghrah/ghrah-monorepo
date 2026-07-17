import type { ActionNode } from "@ghrah/protocol";
import { ActionNodeSchema } from "@ghrah/protocol";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useChangesStore } from "./changes.js";

function makeNode(overrides: Partial<ActionNode> = {}): ActionNode {
  return ActionNodeSchema.parse(overrides);
}

function ar(
  items: {
    ability_name: string;
    outcome?: "success" | "failure" | "needs_input" | "delegate";
    data?: Record<string, unknown>;
  }[],
) {
  return items.map((it) => ({
    ability_name: it.ability_name,
    action_result: { outcome: it.outcome, data: it.data ?? {} },
  }));
}

describe("useChangesStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("starts with empty changes", () => {
    const store = useChangesStore();
    expect(store.changes).toHaveLength(0);
  });

  it("onActionChainNode adds change for write_file", () => {
    const store = useChangesStore();
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        timestamp: "2026-07-17T00:00:00Z",
        action_results: ar([
          { ability_name: "write_file", outcome: "success", data: { file_path: "/tmp/test.txt" } },
        ]),
      }),
    );
    expect(store.changes).toHaveLength(1);
    expect(store.changes[0].agentName).toBe("agent-1");
    expect(store.changes[0].abilityName).toBe("write_file");
    expect(store.changes[0].filePath).toBe("/tmp/test.txt");
    expect(store.changes[0].success).toBe(true);
    expect(store.changes[0].nodeId).toBe("n1");
  });

  it("onActionChainNode adds change for edit_file", () => {
    const store = useChangesStore();
    store.onActionChainNode(
      "agent-2",
      makeNode({
        id: "n1",
        action_results: ar([
          { ability_name: "edit_file", outcome: "success", data: { file_path: "/tmp/test.ts" } },
        ]),
      }),
    );
    expect(store.changes).toHaveLength(1);
    expect(store.changes[0].abilityName).toBe("edit_file");
  });

  it("onActionChainNode adds change for delete_file", () => {
    const store = useChangesStore();
    store.onActionChainNode(
      "agent-3",
      makeNode({
        id: "n1",
        action_results: ar([
          { ability_name: "delete_file", outcome: "success", data: { file_path: "/tmp/test" } },
        ]),
      }),
    );
    expect(store.changes).toHaveLength(1);
    expect(store.changes[0].abilityName).toBe("delete_file");
  });

  it("ignores non-file-change abilities", () => {
    const store = useChangesStore();
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        action_results: ar([{ ability_name: "read_file", outcome: "success", data: {} }]),
      }),
    );
    expect(store.changes).toHaveLength(0);
  });

  it("records failure with error and outcome", () => {
    const store = useChangesStore();
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        action_results: ar([
          { ability_name: "write_file", outcome: "failure", data: { error: "Permission denied" } },
        ]),
      }),
    );
    expect(store.changes).toHaveLength(1);
    expect(store.changes[0].success).toBe(false);
    expect(store.changes[0].error).toBe("Permission denied");
    expect(store.changes[0].outcome).toBe("failure");
  });

  it("filePath is undefined when data missing file_path (degraded)", () => {
    const store = useChangesStore();
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        action_results: ar([{ ability_name: "write_file", outcome: "success", data: {} }]),
      }),
    );
    expect(store.changes).toHaveLength(1);
    expect(store.changes[0].filePath).toBeUndefined();
  });

  it("multiple action_results preserve order", () => {
    const store = useChangesStore();
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        action_results: ar([
          { ability_name: "write_file", outcome: "success", data: { file_path: "/a" } },
          { ability_name: "edit_file", outcome: "success", data: { file_path: "/b" } },
        ]),
      }),
    );
    expect(store.changes.map((c) => c.abilityName)).toEqual(["write_file", "edit_file"]);
  });

  it("dedup: same nodeId+ability+filePath replay does not duplicate", () => {
    const store = useChangesStore();
    const node = makeNode({
      id: "n1",
      action_results: ar([
        { ability_name: "write_file", outcome: "success", data: { file_path: "/x" } },
      ]),
    });
    store.onActionChainNode("agent-1", node);
    store.onActionChainNode("agent-1", node);
    expect(store.changes).toHaveLength(1);
  });

  it("clearAll removes all changes", () => {
    const store = useChangesStore();
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        action_results: ar([
          { ability_name: "write_file", outcome: "success", data: { file_path: "/a" } },
        ]),
      }),
    );
    store.onActionChainNode(
      "agent-2",
      makeNode({
        id: "n2",
        action_results: ar([
          { ability_name: "edit_file", outcome: "success", data: { file_path: "/b" } },
        ]),
      }),
    );
    store.clearAll();
    expect(store.changes).toHaveLength(0);
  });
});
