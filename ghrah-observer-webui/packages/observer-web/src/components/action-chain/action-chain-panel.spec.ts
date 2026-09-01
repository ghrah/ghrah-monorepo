// @vitest-environment happy-dom

import { useActionChainsStore, useAgentsStore } from "@ghrah/observer-core";
import { type ActionNode, ActionNodeSchema, type AgentSpawnedPayload } from "@ghrah/protocol";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import ActionChainPanel from "./action-chain-panel.vue";

function node(overrides: Partial<ActionNode> = {}): ActionNode {
  return ActionNodeSchema.parse(overrides);
}

function spawn(name: string): AgentSpawnedPayload {
  return { type: "agent_spawned", name, config: { name } } as unknown as AgentSpawnedPayload;
}

function setChains(
  store: ReturnType<typeof useActionChainsStore>,
  map: Record<string, ActionNode[]>,
) {
  (store as unknown as { chains: Map<string, ActionNode[]> }).chains = new Map(Object.entries(map));
}

describe("ActionChainPanel", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("prompts to select an agent when none selected", () => {
    const wrapper = mount(ActionChainPanel);
    expect(wrapper.text()).toContain("Select an agent");
  });

  it("shows empty state when selected agent has no chain", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    agents.selectAgent("alpha");
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("No actions yet");
  });

  it("renders only the selected agent's chain", async () => {
    const chains = useActionChainsStore();
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    agents.onAgentSpawned(spawn("beta"));
    setChains(chains, {
      alpha: [node({ id: "a1", parent_id: null, timestamp: "t1" })],
      beta: [node({ id: "b1", parent_id: null, timestamp: "t1" })],
    });
    agents.selectAgent("alpha");
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("@alpha");
    expect(wrapper.text()).not.toContain("@beta");
    expect(wrapper.findAll(".tree-row")).toHaveLength(1);
  });

  it("switches tree when global selectedAgentName changes", async () => {
    const chains = useActionChainsStore();
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    agents.onAgentSpawned(spawn("beta"));
    setChains(chains, {
      alpha: [node({ id: "a1", parent_id: null, timestamp: "t1" })],
      beta: [
        node({ id: "b1", parent_id: null, timestamp: "t1" }),
        node({ id: "b2", parent_id: "b1", timestamp: "t2" }),
      ],
    });
    agents.selectAgent("alpha");
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".tree-row")).toHaveLength(1);
    agents.selectAgent("beta");
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("@beta");
    expect(wrapper.text()).not.toContain("@alpha");
    expect(wrapper.findAll(".tree-row")).toHaveLength(2);
  });

  it("renders parent_id tree with indent guides", async () => {
    const chains = useActionChainsStore();
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    setChains(chains, {
      alpha: [
        node({ id: "root", parent_id: null, timestamp: "t0" }),
        node({ id: "c1", parent_id: "root", timestamp: "t1" }),
        node({ id: "c2", parent_id: "root", timestamp: "t2" }),
        node({ id: "c1a", parent_id: "c1", timestamp: "t1a" }),
      ],
    });
    agents.selectAgent("alpha");
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".tree-row")).toHaveLength(4);
    const allText = wrapper.text();
    expect(allText).toContain("└");
    expect(allText).toContain("├");
  });

  it("suppresses conversation text and send_message tool_call blocks", async () => {
    const chains = useActionChainsStore();
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    setChains(chains, {
      alpha: [
        node({
          id: "n1",
          parent_id: null,
          timestamp: "t1",
          ability_names: ["conversation"],
          messages_delta: [
            {
              role: "ai",
              content_blocks: [
                { type: "text", text: "hello reply" },
                { type: "tool_call", id: "x", name: "send_message", arguments: {} },
                { type: "reasoning", reasoning: "think", incomplete: false },
              ],
              metadata: {},
            },
          ],
        }),
      ],
    });
    agents.selectAgent("alpha");
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    const expandBtn = wrapper.find("button.text-gray-400, button.text-gray-600");
    expect(expandBtn.exists()).toBe(true);
    await expandBtn.trigger("click");
    await wrapper.vm.$nextTick();
    const expandedText = wrapper.text();
    expect(expandedText).toContain("think");
    expect(expandedText).not.toContain("hello reply");
    expect(expandedText).not.toContain("send_message");
  });
});
