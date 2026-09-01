import type { AgentConfigPayload } from "@ghrah/protocol";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useAgentsStore } from "./agents.js";

const makeConfig = (name: string): AgentConfigPayload => ({
  name,
  agent_config_name: null,
  description: "",
  system_prompt: "",
  max_iterations: 10,
});

describe("useAgentsStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("starts with empty agent list", () => {
    const store = useAgentsStore();
    expect(store.agents.size).toBe(0);
    expect(store.activeAgents).toHaveLength(0);
  });

  it("onAgentSpawned adds agent with active status", () => {
    const store = useAgentsStore();
    store.onAgentSpawned({
      name: "agent-1",
      agent_id: "stable-1",
      incarnation_id: "inc-1",
      recovery_mode: "restored",
      config: makeConfig("agent-1"),
    });
    expect(store.agents.get("agent-1")?.status).toBe("active");
    expect(store.agents.get("agent-1")?.name).toBe("agent-1");
    expect(store.agents.get("agent-1")?.agentId).toBe("stable-1");
    expect(store.agents.get("agent-1")?.incarnationId).toBe("inc-1");
    expect(store.agents.get("agent-1")?.recoveryMode).toBe("restored");
    expect(store.activeAgents).toHaveLength(1);
  });

  it("onAgentTerminated marks agent as terminated", () => {
    const store = useAgentsStore();
    store.onAgentSpawned({ name: "agent-1", config: makeConfig("agent-1") });
    store.onAgentTerminated({ name: "agent-1" });
    expect(store.agents.get("agent-1")?.status).toBe("terminated");
    expect(store.activeAgents).toHaveLength(0);
  });

  it("setAgentsFromList clears and replaces all agents", () => {
    const store = useAgentsStore();
    store.onAgentSpawned({ name: "old-1", config: makeConfig("old-1") });
    store.onAgentSpawned({ name: "old-2", config: makeConfig("old-2") });

    store.setAgentsFromList([
      { name: "new-1", config: makeConfig("new-1") },
      { name: "new-2", config: makeConfig("new-2") },
      { name: "new-3", config: makeConfig("new-3") },
    ]);

    expect(store.agents.size).toBe(3);
    expect(store.agents.has("old-1")).toBe(false);
    expect(store.agents.has("new-1")).toBe(true);
    expect(store.activeAgents).toHaveLength(3);
  });

  it("removeAgent deletes agent from map", () => {
    const store = useAgentsStore();
    store.onAgentSpawned({ name: "agent-1", config: makeConfig("agent-1") });
    expect(store.agents.has("agent-1")).toBe(true);

    store.removeAgent("agent-1");
    expect(store.agents.has("agent-1")).toBe(false);
  });

  it("activeAgents filters out terminated agents", () => {
    const store = useAgentsStore();
    store.onAgentSpawned({ name: "a1", config: makeConfig("a1") });
    store.onAgentSpawned({ name: "a2", config: makeConfig("a2") });
    store.onAgentSpawned({ name: "a3", config: makeConfig("a3") });
    store.onAgentTerminated({ name: "a2" });

    expect(store.activeAgents).toHaveLength(2);
    expect(store.activeAgents.map((a) => a.name)).toEqual(["a1", "a3"]);
  });
});
