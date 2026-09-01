import type { ActionChainUpdatedPayload, ActionNode } from "@ghrah/protocol";
import { ActionNodeSchema } from "@ghrah/protocol";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useActionChainsStore } from "./action-chains.js";

function makeNode(overrides: Partial<ActionNode> = {}): ActionNode {
  return ActionNodeSchema.parse(overrides);
}

function makePayload(agent_name: string, node: ActionNode): ActionChainUpdatedPayload {
  return { agent_id: "", project_id: "", cluster_id: "", agent_name, node };
}

describe("useActionChainsStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("starts with empty chains", () => {
    const store = useActionChainsStore();
    expect(store.chains.size).toBe(0);
  });

  it("onActionChainUpdated adds typed node to agent chain", () => {
    const store = useActionChainsStore();
    const payload = makePayload(
      "agent-1",
      makeNode({
        id: "node-1",
        ability_names: ["read_file"],
        action_results: [
          {
            ability_name: "read_file",
            action_result: { outcome: "success", data: { file_path: "/tmp/a.txt" } },
          },
        ],
      }),
    );
    store.onActionChainUpdated(payload);
    const chain = store.getChain("agent-1");
    expect(chain).toHaveLength(1);
    expect(chain[0].id).toBe("node-1");
    expect(chain[0].ability_names).toEqual(["read_file"]);
  });

  it("onActionChainUpdated appends nodes to existing chain", () => {
    const store = useActionChainsStore();
    store.onActionChainUpdated(
      makePayload("agent-1", makeNode({ id: "n1", ability_names: ["read_file"] })),
    );
    store.onActionChainUpdated(
      makePayload("agent-1", makeNode({ id: "n2", ability_names: ["write_file"] })),
    );
    const chain = store.getChain("agent-1");
    expect(chain).toHaveLength(2);
    expect(chain[0].id).toBe("n1");
    expect(chain[1].id).toBe("n2");
  });

  it("chains are separated by agent_name", () => {
    const store = useActionChainsStore();
    store.onActionChainUpdated(
      makePayload("agent-1", makeNode({ id: "n1", ability_names: ["read_file"] })),
    );
    store.onActionChainUpdated(
      makePayload("agent-2", makeNode({ id: "n2", ability_names: ["execute_command"] })),
    );
    expect(store.getChain("agent-1")).toHaveLength(1);
    expect(store.getChain("agent-2")).toHaveLength(1);
    expect(store.getChain("agent-3")).toHaveLength(0);
  });

  it("id dedup: same node.id replay does not duplicate", () => {
    const store = useActionChainsStore();
    const payload = makePayload("agent-1", makeNode({ id: "n1", ability_names: ["read_file"] }));
    store.onActionChainUpdated(payload);
    store.onActionChainUpdated(payload);
    expect(store.getChain("agent-1")).toHaveLength(1);
  });

  it("clearChain removes agent chain", () => {
    const store = useActionChainsStore();
    store.onActionChainUpdated(
      makePayload("agent-1", makeNode({ id: "n1", ability_names: ["read_file"] })),
    );
    store.clearChain("agent-1");
    expect(store.getChain("agent-1")).toHaveLength(0);
  });

  it("clearAll removes all chains", () => {
    const store = useActionChainsStore();
    store.onActionChainUpdated(
      makePayload("agent-1", makeNode({ id: "n1", ability_names: ["read_file"] })),
    );
    store.onActionChainUpdated(
      makePayload("agent-2", makeNode({ id: "n2", ability_names: ["write_file"] })),
    );
    store.clearAll();
    expect(store.getChain("agent-1")).toHaveLength(0);
    expect(store.getChain("agent-2")).toHaveLength(0);
  });

  it("setChain replaces agent chain with read-back nodes (F2 initial sync)", () => {
    const store = useActionChainsStore();
    store.setChain("agent-1", [
      makeNode({ id: "r1", ability_names: ["conversation"] }),
      makeNode({ id: "r2", ability_names: ["send"] }),
    ]);
    const chain = store.getChain("agent-1");
    expect(chain.map((n) => n.id)).toEqual(["r1", "r2"]);
  });

  it("setChain merges idempotently with concurrent increments (node id dedup)", () => {
    const store = useActionChainsStore();
    // 刷新瞬间：增量事件已先到 n1
    store.onActionChainUpdated(
      makePayload("agent-1", makeNode({ id: "n1", ability_names: ["conversation"] })),
    );
    // 读回的完整链含 n1（重复）+ n2（新）
    store.setChain("agent-1", [
      makeNode({ id: "n1", ability_names: ["conversation"] }),
      makeNode({ id: "n2", ability_names: ["send"] }),
    ]);
    const chain = store.getChain("agent-1");
    expect(chain.map((n) => n.id)).toEqual(["n1", "n2"]);
  });
});
