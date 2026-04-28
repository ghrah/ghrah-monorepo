import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useActionChainsStore } from "./action-chains.js";

describe("useActionChainsStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("starts with empty chains", () => {
    const store = useActionChainsStore();
    expect(store.chains.size).toBe(0);
  });

  it("onActionChainUpdated adds node to agent chain", () => {
    const store = useActionChainsStore();
    store.onActionChainUpdated({
      agent_name: "agent-1",
      node: {
        ability_name: "read_file",
        tool_args: { file_path: "/tmp/a.txt" },
      },
    });
    const chain = store.getChain("agent-1");
    expect(chain).toHaveLength(1);
    expect(chain[0].ability_name).toBe("read_file");
  });

  it("onActionChainUpdated appends nodes to existing chain", () => {
    const store = useActionChainsStore();
    store.onActionChainUpdated({
      agent_name: "agent-1",
      node: { ability_name: "read_file", tool_args: {} },
    });
    store.onActionChainUpdated({
      agent_name: "agent-1",
      node: { ability_name: "write_file", tool_args: {} },
    });
    const chain = store.getChain("agent-1");
    expect(chain).toHaveLength(2);
    expect(chain[0].ability_name).toBe("read_file");
    expect(chain[1].ability_name).toBe("write_file");
  });

  it("chains are separated by agent_name", () => {
    const store = useActionChainsStore();
    store.onActionChainUpdated({
      agent_name: "agent-1",
      node: { ability_name: "read_file", tool_args: {} },
    });
    store.onActionChainUpdated({
      agent_name: "agent-2",
      node: { ability_name: "execute_command", tool_args: {} },
    });
    expect(store.getChain("agent-1")).toHaveLength(1);
    expect(store.getChain("agent-2")).toHaveLength(1);
    expect(store.getChain("agent-3")).toHaveLength(0);
  });

  it("clearChain removes agent chain", () => {
    const store = useActionChainsStore();
    store.onActionChainUpdated({
      agent_name: "agent-1",
      node: { ability_name: "read_file", tool_args: {} },
    });
    store.clearChain("agent-1");
    expect(store.getChain("agent-1")).toHaveLength(0);
  });

  it("clearAll removes all chains", () => {
    const store = useActionChainsStore();
    store.onActionChainUpdated({
      agent_name: "agent-1",
      node: { ability_name: "read_file", tool_args: {} },
    });
    store.onActionChainUpdated({
      agent_name: "agent-2",
      node: { ability_name: "write_file", tool_args: {} },
    });
    store.clearAll();
    expect(store.getChain("agent-1")).toHaveLength(0);
    expect(store.getChain("agent-2")).toHaveLength(0);
  });
});
