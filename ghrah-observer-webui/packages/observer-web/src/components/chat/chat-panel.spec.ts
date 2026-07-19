// @vitest-environment happy-dom

import type { ChatEntry } from "@ghrah/observer-core";
import { useAgentsStore, useChatStore, useConnectionStore } from "@ghrah/observer-core";
import type { AgentSpawnedPayload } from "@ghrah/protocol";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sendMessageMock = vi.fn();
vi.mock("@/composables/useObserver", () => ({
  useObserver: () => ({ sendMessage: sendMessageMock }),
}));

import ChatPanel from "./chat-panel.vue";

function spawn(name: string) {
  return { type: "agent_spawned", name, config: { name } } as unknown as AgentSpawnedPayload;
}

function entry(overrides: Partial<ChatEntry> = {}): ChatEntry {
  return {
    from: "agent-1",
    to: "user",
    content: "hi",
    kind: "conversation",
    timestamp: "2026-01-01T00:00:00Z",
    nodeId: "n1",
    agentName: "agent-1",
    childSeq: 0,
    ...overrides,
  };
}

function setup() {
  setActivePinia(createPinia());
  const agents = useAgentsStore();
  agents.onAgentSpawned(spawn("B"));
  agents.onAgentSpawned(spawn("C"));
  const chat = useChatStore();
  const connection = useConnectionStore();
  connection.setConnected();
  return { agents, chat, connection };
}

function setEntries(chat: ReturnType<typeof useChatStore>, list: ChatEntry[]) {
  (chat as unknown as { entries: ChatEntry[] }).entries = list;
}

describe("ChatPanel", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    sendMessageMock.mockReset();
  });

  it("renders entry kind → CSS class mapping", async () => {
    const { chat } = setup();
    setEntries(chat, [
      entry({ kind: "human_input", to: "B", agentName: "B" }),
      entry({ kind: "conversation" }),
      entry({ kind: "send_message", from: "B", to: "C" }),
      entry({ kind: "broadcast", from: "B", to: "all" }),
      entry({ kind: "end_task" }),
    ]);
    const wrapper = mount(ChatPanel);
    await wrapper.vm.$nextTick();
    const entries = wrapper.findAll(".chat-entry");
    expect(entries).toHaveLength(5);
    expect(entries[0].classes()).toContain("entry-human");
    expect(entries[1].classes()).toContain("entry-conversation");
    expect(entries[2].classes()).toContain("entry-send");
    expect(entries[3].classes()).toContain("entry-broadcast");
    expect(entries[4].classes()).toContain("entry-endtask");
  });

  it("renders multimodal blocks", async () => {
    const { chat } = setup();
    setEntries(chat, [
      entry({
        kind: "conversation",
        blocks: [
          { type: "image", url: "https://x/y.png" },
          { type: "audio", data: "BASE64", mime_type: "audio/wav" },
          { type: "file", filename: "doc.txt", url: "https://x/doc.txt" },
          { type: "reasoning", reasoning: "thinking...", incomplete: false },
          { type: "tool_call", id: "t1", name: "search", arguments: { q: "x" } },
          { type: "tool_result", tool_call_id: "t1", name: "search", content: "ok", success: true },
          { type: "error", error_type: "X", message: "boom" },
        ],
      }),
    ]);
    const wrapper = mount(ChatPanel);
    await wrapper.vm.$nextTick();
    expect(wrapper.find('img[alt="image"]').exists()).toBe(true);
    expect(wrapper.find("audio").exists()).toBe(true);
    expect(wrapper.find("a[download]").exists()).toBe(true);
    // reasoning / tool_call / tool_result / error 各一个 <details> 或 div
    expect(wrapper.findAll("details").length).toBeGreaterThanOrEqual(3);
  });

  it("renders markdown text block (safe links)", async () => {
    const { chat } = setup();
    setEntries(chat, [
      entry({
        kind: "conversation",
        blocks: [{ type: "text", text: "[good](https://example.com) [bad](javascript:alert(1))" }],
      }),
    ]);
    const wrapper = mount(ChatPanel);
    await wrapper.vm.$nextTick();
    const links = wrapper.findAll(".markdown-body a");
    // javascript: 链接应被 validateLink 拒绝，渲染为纯文本，仅 good 产生 <a>
    expect(links).toHaveLength(1);
    expect(links[0].attributes("href")).toBe("https://example.com");
  });

  it("filter by agent narrows entries", async () => {
    const { chat } = setup();
    setEntries(chat, [
      entry({ kind: "conversation", agentName: "B", from: "B" }),
      entry({ kind: "conversation", agentName: "C", from: "C" }),
    ]);
    const wrapper = mount(ChatPanel);
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".chat-entry")).toHaveLength(2);
    const select = wrapper.find("select");
    await select.setValue("B");
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".chat-entry")).toHaveLength(1);
  });

  it("shows error block on entry.error", async () => {
    const { chat } = setup();
    setEntries(chat, [
      entry({ kind: "human_input", to: "B", agentName: "B", error: "发送失败：未连接" }),
    ]);
    const wrapper = mount(ChatPanel);
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".chat-entry").classes()).toContain("entry-error");
    expect(wrapper.find(".block-error").text()).toContain("发送失败：未连接");
  });

  it("handleSend marks pending error when sendMessage returns null", async () => {
    const { chat } = setup();
    sendMessageMock.mockResolvedValueOnce(null);
    const wrapper = mount(ChatPanel);
    await wrapper.vm.$nextTick();
    const input = wrapper.find('input[type="text"]');
    await input.setValue("@B hello");
    await wrapper.find("form").trigger("submit");
    await vi.waitFor(() => {
      expect(chat.allEntries.some((e) => e.error)).toBe(true);
    });
    const e = chat.allEntries.find((x) => x.error);
    expect(e?.error).toContain("发送失败");
  });
});
