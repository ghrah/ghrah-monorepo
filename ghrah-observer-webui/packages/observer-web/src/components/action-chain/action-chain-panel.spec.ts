// @vitest-environment happy-dom

import { useActionChainsStore, useAgentsStore } from "@ghrah/observer-core";
import { ActionNodeSchema, type ActionNode } from "@ghrah/protocol";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import ActionChainPanel from "./action-chain-panel.vue";

function node(overrides: Partial<ActionNode> = {}): ActionNode {
  return ActionNodeSchema.parse(overrides);
}

function setChains(
  store: ReturnType<typeof useActionChainsStore>,
  map: Record<string, ActionNode[]>,
) {
  (store as unknown as { chains: Map<string, ActionNode[]> }).chains = new Map(Object.entries(map));
}

function treeHeaders(wrapper: ReturnType<typeof mount>) {
  // 树容器内含 agent 头部 .border-b，统计头部数量即树数量
  return wrapper.findAll(".border-b").filter((el) => el.text().startsWith("@"));
}

describe("ActionChainPanel", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("renders multiple agent trees side by side", async () => {
    const chains = useActionChainsStore();
    const agents = useAgentsStore();
    setChains(chains, {
      alpha: [node({ id: "a1", parent_id: null, timestamp: "t1" })],
      beta: [node({ id: "b1", parent_id: null, timestamp: "t1" })],
    });
    void agents;
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    expect(treeHeaders(wrapper)).toHaveLength(2);
    expect(wrapper.text()).toContain("@alpha");
    expect(wrapper.text()).toContain("@beta");
  });

  it("renders parent_id tree with indent guides", async () => {
    const chains = useActionChainsStore();
    setChains(chains, {
      alpha: [
        node({ id: "root", parent_id: null, timestamp: "t0" }),
        node({ id: "c1", parent_id: "root", timestamp: "t1" }),
        node({ id: "c2", parent_id: "root", timestamp: "t2" }),
        node({ id: "c1a", parent_id: "c1", timestamp: "t1a" }),
      ],
    });
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    // 摘要行 4 条
    const summaries = wrapper.findAll(".tree-row");
    expect(summaries).toHaveLength(4);
    // 缩进引导线 span（每个 row 至少有 └/├ + 可选 │）
    const pipes = wrapper.findAll("span.text-gray-300, span.text-gray-700");
    expect(pipes.length).toBeGreaterThan(0);
    // 应同时存在 └ 和 ├ 字符
    const allText = wrapper.text();
    expect(allText).toContain("└");
    expect(allText).toContain("├");
  });

  it("suppresses conversation text and send_message tool_call blocks", async () => {
    const chains = useActionChainsStore();
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
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    // 节点可展开（hasDetails 应为 true：reasoning 仍可见）
    const expandBtn = wrapper.find("button.text-gray-400, button.text-gray-600");
    expect(expandBtn.exists()).toBe(true);
    await expandBtn.trigger("click");
    await wrapper.vm.$nextTick();
    // 展开内容应含 reasoning，不应含 "hello reply" 或 "send_message"
    const expandedText = wrapper.text();
    expect(expandedText).toContain("think");
    expect(expandedText).not.toContain("hello reply");
    expect(expandedText).not.toContain("send_message");
  });

  it("filter by agent narrows to one tree", async () => {
    const chains = useActionChainsStore();
    const agents = useAgentsStore();
    agents.onAgentSpawned({
      type: "agent_spawned",
      name: "alpha",
      config: { name: "alpha" },
    } as never);
    agents.onAgentSpawned({
      type: "agent_spawned",
      name: "beta",
      config: { name: "beta" },
    } as never);
    setChains(chains, {
      alpha: [node({ id: "a1", parent_id: null, timestamp: "t1" })],
      beta: [node({ id: "b1", parent_id: null, timestamp: "t1" })],
    });
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    expect(treeHeaders(wrapper)).toHaveLength(2);
    const select = wrapper.find("select");
    await select.setValue("alpha");
    await wrapper.vm.$nextTick();
    expect(treeHeaders(wrapper)).toHaveLength(1);
    expect(wrapper.text()).toContain("@alpha");
    expect(wrapper.text()).not.toContain("@beta");
  });

  it("shows empty state when no chains", async () => {
    const chains = useActionChainsStore();
    void chains;
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("No actions yet");
  });
});
