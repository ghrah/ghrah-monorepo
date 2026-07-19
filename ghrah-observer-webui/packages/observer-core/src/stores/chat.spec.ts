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
    expect(store.allEntries).toHaveLength(0);
  });

  it("onActionChainNode projects human_input into global stream", () => {
    const store = useChatStore();
    store.onActionChainNode(
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("hello")], "human:user")],
      }),
    );
    const e = store.allEntries;
    expect(e).toHaveLength(1);
    expect(e[0]).toMatchObject({
      from: "user",
      to: "agent-1",
      content: "hello",
      kind: "human_input",
      nodeId: "n1",
    });
  });

  it("flat global stream: entries from multiple agents in one timeline", () => {
    const store = useChatStore();
    store.onActionChainNode(
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("hi")], "human:user")],
      }),
    );
    store.onActionChainNode(
      makeNode({
        id: "n2",
        agent_name: "agent-2",
        messages_delta: [userMsg([textBlock("hi")], "human:user")],
      }),
    );
    const e = store.allEntries;
    expect(e).toHaveLength(2);
    expect(e[0].to).toBe("agent-1");
    expect(e[1].to).toBe("agent-2");
  });

  it("dedup: same node replay does not duplicate", () => {
    const store = useChatStore();
    const node = makeNode({
      id: "n1",
      ability_names: ["conversation"],
      messages_delta: [aiMsg([textBlock("reply")])],
    });
    store.onActionChainNode(node);
    store.onActionChainNode(node);
    expect(store.allEntries).toHaveLength(1);
  });

  it("same-content consecutive sends are NOT deduped (different nodeId)", () => {
    const store = useChatStore();
    store.onActionChainNode(
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("same")], "human:user")],
      }),
    );
    store.onActionChainNode(
      makeNode({
        id: "n2",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("same")], "human:user")],
      }),
    );
    expect(store.allEntries).toHaveLength(2);
  });

  it("conversation entry carries blocks", () => {
    const store = useChatStore();
    store.onActionChainNode(
      makeNode({
        id: "n1",
        ability_names: ["conversation"],
        messages_delta: [aiMsg([textBlock("rich reply")])],
      }),
    );
    const e = store.allEntries[0];
    expect(e.kind).toBe("conversation");
    expect(e.blocks).toBeDefined();
    expect(e.blocks?.[0]).toMatchObject({ type: "text" });
  });

  it("addPendingEntry sets pending=true; R1 echo confirms FIFO by content+to", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "agent-1", content: "hello", agentName: "agent-1" });
    expect(store.allEntries).toHaveLength(1);
    expect(store.allEntries[0].pending).toBe(true);

    store.onActionChainNode(
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("hello")], "human:user")],
      }),
    );
    const e = store.allEntries;
    expect(e).toHaveLength(1);
    expect(e[0].pending).toBe(false);
    expect(e[0].nodeId).toBe("n1");
  });

  it("markPendingError marks matching pending as error, leaves it in stream", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "agent-B", content: "hi", agentName: "agent-B" });
    expect(store.allEntries[0].pending).toBe(true);
    store.markPendingError("agent-B", "hi", "发送失败：未连接");
    const e = store.allEntries;
    expect(e).toHaveLength(1);
    expect(e[0].pending).toBe(false);
    expect(e[0].error).toBe("发送失败：未连接");
  });

  it("markPendingError no-op when no matching pending", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "agent-B", content: "hi", agentName: "agent-B" });
    store.markPendingError("agent-B", "no-such-content", "err");
    expect(store.allEntries[0].pending).toBe(true);
    expect(store.allEntries[0].error).toBeUndefined();
  });

  it("consecutive identical echoes confirm each pending (no cross-misdelete)", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "agent-1", content: "dup", agentName: "agent-1" });
    store.addPendingEntry({ to: "agent-1", content: "dup", agentName: "agent-1" });
    store.onActionChainNode(
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("dup")], "human:user")],
      }),
    );
    store.onActionChainNode(
      makeNode({
        id: "n2",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("dup")], "human:user")],
      }),
    );
    const e = store.allEntries;
    expect(e).toHaveLength(2);
    expect(e.every((x) => x.pending === false)).toBe(true);
    expect(e[0].nodeId).toBe("n1");
    expect(e[1].nodeId).toBe("n2");
  });

  it("multicast: N pending (distinct to, same content) each confirmed by matching R1", () => {
    const store = useChatStore();
    store.addPendingEntry({ to: "agent-B", content: "hi", agentName: "agent-B" });
    store.addPendingEntry({ to: "agent-C", content: "hi", agentName: "agent-C" });
    store.addPendingEntry({ to: "agent-D", content: "hi", agentName: "agent-D" });
    expect(store.allEntries).toHaveLength(3);

    store.onActionChainNode(
      makeNode({
        id: "nB",
        agent_name: "agent-B",
        messages_delta: [userMsg([textBlock("hi")], "human:user")],
      }),
    );
    store.onActionChainNode(
      makeNode({
        id: "nC",
        agent_name: "agent-C",
        messages_delta: [userMsg([textBlock("hi")], "human:user")],
      }),
    );
    store.onActionChainNode(
      makeNode({
        id: "nD",
        agent_name: "agent-D",
        messages_delta: [userMsg([textBlock("hi")], "human:user")],
      }),
    );
    const e = store.allEntries;
    expect(e).toHaveLength(3);
    const confirmed = e.filter((x) => x.pending === false);
    expect(confirmed).toHaveLength(3);
    const targets = confirmed.map((x) => x.to).sort();
    expect(targets).toEqual(["agent-B", "agent-C", "agent-D"]);
    const nodeIds = confirmed.map((x) => x.nodeId).sort();
    expect(nodeIds).toEqual(["nB", "nC", "nD"]);
  });

  it("clearAll resets the global stream", () => {
    const store = useChatStore();
    store.onActionChainNode(
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        messages_delta: [userMsg([textBlock("hi")], "human:user")],
      }),
    );
    store.clearAll();
    expect(store.allEntries).toHaveLength(0);
  });

  it("end_task entry derived from action_results", () => {
    const store = useChatStore();
    store.onActionChainNode(
      makeNode({
        id: "n1",
        agent_name: "agent-1",
        ability_names: ["end_task"],
        action_results: ar([
          { ability_name: "end_task", outcome: "success", data: { response: "all done" } },
        ]),
      }),
    );
    const e = store.allEntries;
    expect(e).toHaveLength(1);
    expect(e[0]).toMatchObject({ kind: "end_task", content: "all done" });
  });
});
