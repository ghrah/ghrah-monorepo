import type { AgentResponsePayload, ContentBlock } from "@ghrah/protocol";
import { defineStore } from "pinia";
import { ref } from "vue";

export interface ChatMessage {
  sender: string;
  recipient: string;
  content: string;
  contentBlocks?: ContentBlock[];
  messageType: string;
  metadata: Record<string, unknown>;
  timestamp?: number;
}

export const useChatStore = defineStore("ghrah-chat", () => {
  const messages = ref<Map<string, ChatMessage[]>>(new Map());

  function onAgentResponse(payload: AgentResponsePayload) {
    const agentName = payload.sender;
    const existing = messages.value.get(agentName) ?? [];
    const updated = new Map(messages.value);
    updated.set(agentName, [
      ...existing,
      {
        sender: payload.sender,
        recipient: payload.recipient,
        content: payload.content,
        contentBlocks: payload.content_blocks ?? undefined,
        messageType: payload.message_type,
        metadata: payload.metadata,
      },
    ]);
    messages.value = updated;
  }

  function addMessage(agentName: string, message: ChatMessage) {
    const existing = messages.value.get(agentName) ?? [];
    const updated = new Map(messages.value);
    updated.set(agentName, [...existing, message]);
    messages.value = updated;
  }

  function getMessages(agentName: string): ChatMessage[] {
    return messages.value.get(agentName) ?? [];
  }

  function clearMessages(agentName: string) {
    messages.value.delete(agentName);
  }

  return {
    messages,
    onAgentResponse,
    addMessage,
    getMessages,
    clearMessages,
  };
});
