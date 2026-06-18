<script setup lang="ts">
import type { ContentBlock } from "@ghrah/protocol";
import { useAgentsStore, useChatStore, useConnectionStore } from "@ghrah/observer-core";
import { computed, nextTick, ref, watch } from "vue";
import { useObserver } from "@/composables/useObserver";
import MessageInput from "./message-input.vue";

const chat = useChatStore();
const agents = useAgentsStore();
const connection = useConnectionStore();
const { sendMessage } = useObserver();

const messageContainer = ref<HTMLElement | null>(null);

const selectedMessages = computed(() => {
  if (!agents.selectedAgentName) return [];
  return chat.getMessages(agents.selectedAgentName);
});

async function handleSend(content: string) {
  await sendMessage(content);
  await nextTick(() => scrollToBottom());
}

function scrollToBottom() {
  if (messageContainer.value) {
    messageContainer.value.scrollTop = messageContainer.value.scrollHeight;
  }
}

watch(selectedMessages, () => {
  nextTick(() => scrollToBottom());
});

function messageClass(msg: { messageType: string; sender: string }): string {
  if (msg.messageType === "error") return "msg-error";
  if (msg.messageType === "thinking") return "msg-thinking";
  if (msg.sender === "user") return "msg-user";
  return "msg-agent";
}

function blockClass(block: ContentBlock): string {
  if (block.type === "reasoning") return "block-reasoning";
  return "";
}

function blockText(block: ContentBlock): string {
  switch (block.type) {
    case "text":
      return block.text;
    case "reasoning":
      return block.reasoning;
    case "error":
      return block.message;
    default:
      return "";
  }
}

function hasStructuredBlocks(msg: { contentBlocks?: ContentBlock[] }): boolean {
  return !!(msg.contentBlocks && msg.contentBlocks.length > 0);
}
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="px-3 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
      <h3 class="text-sm font-semibold truncate">
        {{ agents.selectedAgentName ? `Chat: ${agents.selectedAgentName}` : "Chat" }}
      </h3>
    </div>

    <div v-if="!agents.selectedAgentName" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-600 text-sm">
      Select an agent to start chatting
    </div>

    <div v-else-if="selectedMessages.length === 0" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-600 text-sm">
      No messages yet
    </div>

    <div
      v-else
      ref="messageContainer"
      class="flex-1 overflow-y-auto p-3 space-y-2"
    >
      <div
        v-for="(msg, i) in selectedMessages"
        :key="i"
        :class="['message-bubble', messageClass(msg)]"
      >
        <span class="font-semibold text-xs mr-2">{{ msg.sender }}</span>
        <template v-if="hasStructuredBlocks(msg)">
          <div
            v-for="(block, j) in msg.contentBlocks"
            :key="j"
            :class="['text-sm', blockClass(block)]"
          >{{ blockText(block) }}</div>
        </template>
        <span v-else :class="['text-sm', msg.messageType === 'thinking' ? 'italic text-gray-500 dark:text-gray-400' : '']">{{ msg.content }}</span>
      </div>
    </div>

    <MessageInput
      v-if="agents.selectedAgentName"
      :disabled="connection.state !== 'connected'"
      @send="handleSend"
    />
  </div>
</template>

<style scoped>
.message-bubble {
  padding: 0.375rem 0.75rem;
  border-radius: 0.5rem;
  max-width: 85%;
  word-break: break-word;
}

.msg-agent {
  background: #e8f0fe;
  color: #1a3a5c;
  align-self: flex-start;
}

:root.dark .msg-agent {
  background: #1e3a5f;
  color: #b8d4f0;
}

.msg-user {
  background: #d1fae5;
  color: #065f46;
  align-self: flex-end;
  margin-left: auto;
}

:root.dark .msg-user {
  background: #064e3b;
  color: #a7f3d0;
}

.msg-error {
  background: #fee2e2;
  color: #991b1b;
}

:root.dark .msg-error {
  background: #7f1d1d;
  color: #fecaca;
}

.msg-thinking {
  background: #f3f4f6;
  color: #6b7280;
  font-style: italic;
}

:root.dark .msg-thinking {
  background: #1f2937;
  color: #9ca3af;
}

.block-reasoning {
  font-style: italic;
  color: #6b7280;
  padding: 0.125rem 0;
}

:root.dark .block-reasoning {
  color: #9ca3af;
}
</style>