import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import type { ChatMessage } from "./chat.js";
import { useChatStore } from "./chat.js";

describe("useChatStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("starts with empty messages", () => {
    const store = useChatStore();
    expect(store.getMessages("agent-1")).toHaveLength(0);
  });

  it("onAgentResponse adds message for agent", () => {
    const store = useChatStore();
    store.onAgentResponse({
      sender: "agent-1",
      recipient: "user",
      content: "Hello",
      message_type: "result",
      metadata: {},
    });
    const msgs = store.getMessages("agent-1");
    expect(msgs).toHaveLength(1);
    expect(msgs[0].content).toBe("Hello");
    expect(msgs[0].messageType).toBe("result");
  });

  it("onAgentResponse appends messages to existing agent", () => {
    const store = useChatStore();
    store.onAgentResponse({
      sender: "agent-1",
      recipient: "user",
      content: "First",
      message_type: "result",
      metadata: {},
    });
    store.onAgentResponse({
      sender: "agent-1",
      recipient: "user",
      content: "Second",
      message_type: "result",
      metadata: {},
    });
    const msgs = store.getMessages("agent-1");
    expect(msgs).toHaveLength(2);
    expect(msgs[0].content).toBe("First");
    expect(msgs[1].content).toBe("Second");
  });

  it("messages are separated by agent_name", () => {
    const store = useChatStore();
    store.onAgentResponse({
      sender: "agent-1",
      recipient: "user",
      content: "From 1",
      message_type: "result",
      metadata: {},
    });
    store.onAgentResponse({
      sender: "agent-2",
      recipient: "user",
      content: "From 2",
      message_type: "result",
      metadata: {},
    });
    expect(store.getMessages("agent-1")).toHaveLength(1);
    expect(store.getMessages("agent-2")).toHaveLength(1);
    expect(store.getMessages("agent-3")).toHaveLength(0);
  });

  it("addMessage manually adds a chat message", () => {
    const store = useChatStore();
    const msg: ChatMessage = {
      sender: "user",
      recipient: "agent-1",
      content: "Do something",
      messageType: "command",
      metadata: {},
    };
    store.addMessage("agent-1", msg);
    const msgs = store.getMessages("agent-1");
    expect(msgs).toHaveLength(1);
    expect(msgs[0].sender).toBe("user");
  });

  it("clearMessages removes all messages for agent", () => {
    const store = useChatStore();
    store.onAgentResponse({
      sender: "agent-1",
      recipient: "user",
      content: "Hello",
      message_type: "result",
      metadata: {},
    });
    store.clearMessages("agent-1");
    expect(store.getMessages("agent-1")).toHaveLength(0);
  });
});
