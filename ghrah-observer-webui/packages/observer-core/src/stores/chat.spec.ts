import type { ActionNode, ContentBlock } from "@ghrah/protocol";
import { ActionNodeSchema } from "@ghrah/protocol";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useChatStore } from "./chat.js";

function makeNode(overrides: Partial<ActionNode> = {}): ActionNode {
  return ActionNodeSchema.parse(overrides);
}

function textBlock(t: string): { type: "text"; text: string } {
  return { type: "text", text: t };
}

function userMsg(blocks: ReturnType<typeof textBlock>[], source: string) {
  return { role: "user" as const, content_blocks: blocks, source, metadata: {} };
}

function aiMsg(blocks: ContentBlock[]) {
  return { role: "ai" as const, content_blocks: blocks, metadata: {} };
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

describe("useChatStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("starts with empty entries", () => {
    const store = useChatStore();
    expect(store.getEntries("agent-1")).toHaveLength(0);
  });

  it("onActionChainNode projects human_input for agent", () => {
    const store = useChatStore();
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("hello")], "human:user")],
      }),
    );
    const e = store.getEntries("agent-1");
    expect(e).toHaveLength(1);
    expect(e[0]).toMatchObject({
      from: "user",
      to: "agent-1",
      content: "hello",
      kind: "human_input",
      nodeId: "n1",
    });
  });

  it("entries separated by agent_name", () => {
    const store = useChatStore();
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("hi")], "human:user")],
      }),
    );
    store.onActionChainNode(
      "agent-2",
      makeNode({
        id: "n2",
        agent_name: "agent-2",
        messages_delta: [userMsg([textBlock("hi")], "human:user")],
      }),
    );
    expect(store.getEntries("agent-1")).toHaveLength(1);
    expect(store.getEntries("agent-2")).toHaveLength(1);
    expect(store.getEntries("agent-3")).toHaveLength(0);
  });

  it("dedup: same node replay does not duplicate", () => {
    const store = useChatStore();
    const node = makeNode({
      id: "n1",
      ability_names: ["conversation"],
      messages_delta: [aiMsg([textBlock("reply")])],
    });
    store.onActionChainNode("agent-1", node);
    store.onActionChainNode("agent-1", node);
    expect(store.getEntries("agent-1")).toHaveLength(1);
  });

  it("same-content consecutive sends are NOT deduped (dedup key excludes content)", () => {
    const store = useChatStore();
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("same")], "human:user")],
      }),
    );
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n2",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("same")], "human:user")],
      }),
    );
    expect(store.getEntries("agent-1")).toHaveLength(2);
  });

  it("conversation entry carries blocks", () => {
    const store = useChatStore();
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        ability_names: ["conversation"],
        messages_delta: [aiMsg([textBlock("rich reply")])],
      }),
    );
    const e = store.getEntries("agent-1")[0];
    expect(e.kind).toBe("conversation");
    expect(e.blocks).toBeDefined();
    expect(e.blocks?.[0]).toMatchObject({ type: "text" });
  });

  it("addPendingEntry sets pending=true; R1 echo confirms FIFO by content+to", () => {
    const store = useChatStore();
    store.addPendingEntry("agent-1", { to: "agent-1", content: "hello" });
    expect(store.getEntries("agent-1")).toHaveLength(1);
    expect(store.getEntries("agent-1")[0].pending).toBe(true);

    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("hello")], "human:user")],
      }),
    );
    const e = store.getEntries("agent-1");
    expect(e).toHaveLength(1);
    expect(e[0].pending).toBe(false);
    expect(e[0].nodeId).toBe("n1");
  });

  it("consecutive identical echoes confirm each pending (no cross-misdelete)", () => {
    const store = useChatStore();
    store.addPendingEntry("agent-1", { to: "agent-1", content: "dup" });
    store.addPendingEntry("agent-1", { to: "agent-1", content: "dup" });
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("dup")], "human:user")],
      }),
    );
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n2",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("dup")], "human:user")],
      }),
    );
    const e = store.getEntries("agent-1");
    expect(e).toHaveLength(2);
    expect(e.every((x) => x.pending === false)).toBe(true);
    expect(e[0].nodeId).toBe("n1");
    expect(e[1].nodeId).toBe("n2");
  });

  it("clearEntries removes entries for an agent", () => {
    const store = useChatStore();
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("hi")], "human:user")],
      }),
    );
    store.clearEntries("agent-1");
    expect(store.getEntries("agent-1")).toHaveLength(0);
  });

  it("end_task entry derived from action_results", () => {
    const store = useChatStore();
    store.onActionChainNode(
      "agent-1",
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        ability_names: ["end_task"],
        action_results: ar([
          { ability_name: "end_task", outcome: "success", data: { response: "all done" } },
        ]),
      }),
    );
    const e = store.getEntries("agent-1");
    expect(e).toHaveLength(1);
    expect(e[0]).toMatchObject({ kind: "end_task", content: "all done" });
  });
});
