// @vitest-environment happy-dom

import { type ActionNode, ActionNodeSchema } from "@ghrah/protocol";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ActionNodeRow from "./action-node.vue";

function node(overrides: Partial<ActionNode> = {}): ActionNode {
  return ActionNodeSchema.parse(overrides);
}

const compactNode = node({
  id: "n1",
  ability_names: ["compact"],
  metadata: {
    trigger_source: "manual",
    summarized_range: "n-001..n-004",
    kept_recent_nodes: 2,
    tokens_before: 6800,
    tokens_after: 2400,
    post_check: "ok",
  },
});

const plainNode = node({ id: "n2", ability_names: ["think"] });

function mountRow(n: ActionNode) {
  return mount(ActionNodeRow, {
    props: { node: n, depth: 0, isLastChild: true, ancestorPipes: [] },
  });
}

describe("ActionNodeRow compact badge", () => {
  it("renders compact badge with trigger source for compact nodes", () => {
    const wrapper = mountRow(compactNode);
    const badge = wrapper.find(".bg-indigo-100");
    expect(badge.exists()).toBe(true);
    expect(badge.text()).toContain("compact");
    expect(badge.text()).toContain("manual");
    const title = badge.attributes("title") ?? "";
    expect(title).toContain("n-001..n-004");
    expect(title).toContain("2");
    expect(title).toContain("6800");
    expect(title).toContain("2400");
    expect(title).toContain("ok");
  });

  it("renders no badge for plain nodes", () => {
    const wrapper = mountRow(plainNode);
    expect(wrapper.find(".bg-indigo-100").exists()).toBe(false);
  });

  it("falls back to placeholder when metadata keys are missing", () => {
    const sparse = node({ id: "n3", ability_names: ["compact"], metadata: {} });
    const wrapper = mountRow(sparse);
    const badge = wrapper.find(".bg-indigo-100");
    expect(badge.exists()).toBe(true);
    expect(badge.text()).toContain("—");
  });
});
