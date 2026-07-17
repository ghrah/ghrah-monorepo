import type { ActionChainUpdatedPayload, ActionNode } from "@ghrah/protocol";
import { ActionNodeSchema } from "@ghrah/protocol";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useActionChainsStore } from "./action-chains.js";

function makeNode(overrides: Partial<ActionNode> = {}): ActionNode {
  return ActionNodeSchema.parse(overrides);
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
    const payload: ActionChainUpdatedPayload = {
      agent_name: "agent-1",
      node: makeNode({
        id: "node-1",
        ability_names: ["read_file"],
        action_results: [
          {
            ability_name: "read_file",
            action_result: { outcome: "success", data: { file_path: "/tmp/a.txt" } },
          },
        ],
      }),
    };
    store.onActionChainUpdated(payload);
    const chain = store.getChain("agent-1");
    expect(chain).toHaveLength(1);
    expect(chain[0].id).toBe("node-1");
    expect(chain[0].ability_names).toEqual(["read_file"]);
  });

  it("onActionChainUpdated appends nodes to existing chain", () => {
    const store = useActionChainsStore();
    store.onActionChainUpdated({
      agent_name: "agent-1",
      node: makeNode({ id: "n1", ability_names: ["read_file"] }),
    });
    store.onActionChainUpdated({
      agent_name: "agent-1",
      node: makeNode({ id: "n2", ability_names: ["write_file"] }),
    });
    const chain = store.getChain("agent-1");
    expect(chain).toHaveLength(2);
    expect(chain[0].id).toBe("n1");
    expect(chain[1].id).toBe("n2");
  });

  it("chains are separated by agent_name", () => {
    const store = useActionChainsStore();
    store.onActionChainUpdated({
      agent_name: "agent-1",
      node: makeNode({ id: "n1", ability_names: ["read_file"] }),
    });
    store.onActionChainUpdated({
      agent_name: "agent-2",
      node: makeNode({ id: "n2", ability_names: ["execute_command"] }),
    });
    expect(store.getChain("agent-1")).toHaveLength(1);
    expect(store.getChain("agent-2")).toHaveLength(1);
    expect(store.getChain("agent-3")).toHaveLength(0);
  });

  it("id dedup: same node.id replay does not duplicate", () => {
    const store = useActionChainsStore();
    const payload = {
      agent_name: "agent-1",
      node: makeNode({ id: "n1", ability_names: ["read_file"] }),
    };
    store.onActionChainUpdated(payload);
    store.onActionChainUpdated(payload);
    expect(store.getChain("agent-1")).toHaveLength(1);
  });

  it("clearChain removes agent chain", () => {
    const store = useActionChainsStore();
    store.onActionChainUpdated({
      agent_name: "agent-1",
      node: makeNode({ id: "n1", ability_names: ["read_file"] }),
    });
    store.clearChain("agent-1");
    expect(store.getChain("agent-1")).toHaveLength(0);
  });

  it("clearAll removes all chains", () => {
    const store = useActionChainsStore();
    store.onActionChainUpdated({
      agent_name: "agent-1",
      node: makeNode({ id: "n1", ability_names: ["read_file"] }),
    });
    store.onActionChainUpdated({
      agent_name: "agent-2",
      node: makeNode({ id: "n2", ability_names: ["write_file"] }),
    });
    store.clearAll();
    expect(store.getChain("agent-1")).toHaveLength(0);
    expect(store.getChain("agent-2")).toHaveLength(0);
  });
});
