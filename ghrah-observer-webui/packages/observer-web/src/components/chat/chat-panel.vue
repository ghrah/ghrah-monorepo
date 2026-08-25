<script setup lang="ts">
import type { ChatEntry } from "@ghrah/observer-core";
import {
  roomLogToChatEntries,
  useChatStore,
  useConnectionStore,
  useRoomsStore,
} from "@ghrah/observer-core";
import type { ContentBlock } from "@ghrah/protocol";
import { computed, nextTick, ref, watch } from "vue";
import { useMarkdown } from "@/composables/useMarkdown";
import { useObserver } from "@/composables/useObserver";
import MessageInput from "./message-input.vue";

const chat = useChatStore();
const rooms = useRoomsStore();
const connection = useConnectionStore();
const { roomSend } = useObserver();
const { render: renderMarkdown } = useMarkdown();

const messageContainer = ref<HTMLElement | null>(null);

/** active room 历史（room log 投影） + 本 room 的 pending/error 乐观层，按序合并。 */
const roomEntries = computed<ChatEntry[]>(() => {
  const roomId = rooms.activeRoomId;
  if (!roomId) return [];
  const history = rooms.activeRoomLog.map(roomLogToChatEntries);
  const pending = chat.allEntries.filter(
    (e) => (e.pending === true || e.error !== undefined) && e.roomId === roomId,
  );
  return [...history, ...pending];
});

const canChat = computed(() => rooms.activeRoomId !== null && connection.state === "connected");

async function handleSend(targets: string[], content: string) {
  const roomId = rooms.activeRoomId;
  if (!roomId || !content) return;
  chat.addPendingEntry({ to: roomId, content, agentName: "", roomId, targets });
  roomSend(roomId, content, targets)
    .then((r) => {
      if (r === null) chat.markPendingError(roomId, content, "发送失败：未连接", roomId);
    })
    .catch((e) => chat.markPendingError(roomId, content, `发送失败：${String(e ?? "")}`, roomId));
  await nextTick(() => scrollToBottom());
}

function scrollToBottom() {
  if (messageContainer.value) {
    messageContainer.value.scrollTop = messageContainer.value.scrollHeight;
  }
}

watch(roomEntries, () => {
  nextTick(() => scrollToBottom());
});

function entryClass(entry: ChatEntry): string {
  if (entry.error) return "entry-error";
  switch (entry.kind) {
    case "human_input":
      return "entry-human";
    case "conversation":
      return "entry-conversation";
    case "send_message":
      return "entry-send";
    case "broadcast":
      return "entry-broadcast";
    case "end_task":
      return "entry-endtask";
    default:
      return "entry-conversation";
  }
}

function entryHeader(entry: ChatEntry): string {
  const targetSuffix =
    entry.targets && entry.targets.length > 0
      ? ` → ${entry.targets.map((t) => `@${t}`).join(" ")}`
      : "";
  switch (entry.kind) {
    case "human_input":
      return `you${targetSuffix}`;
    case "conversation":
      return `@${entry.from}${targetSuffix}`;
    case "send_message":
      return `@${entry.from} → @${entry.to}`;
    case "broadcast":
      return `@${entry.from} → @all`;
    case "end_task":
      return `✓ @${entry.from}`;
    default:
      return `@${entry.from}`;
  }
}

function imgSrc(block: Extract<ContentBlock, { type: "image" }>): string {
  if (block.url) return block.url;
  if (block.base64) return `data:${block.mime_type ?? "image/png"};base64,${block.base64}`;
  return "";
}

function audioSrc(block: Extract<ContentBlock, { type: "audio" }>): string {
  return `data:${block.mime_type};base64,${block.data}`;
}

function fileHref(block: Extract<ContentBlock, { type: "file" }>): string {
  if (block.url) return block.url;
  if (block.base64)
    return `data:${block.mime_type ?? "application/octet-stream"};base64,${block.base64}`;
  return "";
}

function fileLabel(block: Extract<ContentBlock, { type: "file" }>): string {
  return block.filename ?? "file";
}

function isText(block: ContentBlock): block is Extract<ContentBlock, { type: "text" }> {
  return block.type === "text";
}
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="px-3 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 flex items-center justify-between">
      <h3 class="text-sm font-semibold truncate">
        Chat<span v-if="rooms.activeRoom" class="text-gray-500 dark:text-gray-400 font-normal"> · {{ rooms.activeRoom.name }}</span>
      </h3>
    </div>

    <div v-if="!rooms.activeRoomId" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-600 text-sm">
      Select a room to start chatting
    </div>

    <div v-else-if="roomEntries.length === 0" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-600 text-sm">
      No messages yet
    </div>

    <div
      v-else
      ref="messageContainer"
      class="flex-1 overflow-y-auto p-3 space-y-2"
    >
      <div
        v-for="entry in roomEntries"
        :key="`${entry.nodeId}-${entry.childSeq}`"
        :class="['chat-entry', entryClass(entry), { 'entry-pending': entry.pending }]"
      >
        <div class="entry-header">{{ entryHeader(entry) }}</div>

        <div v-if="entry.error" class="block-error">
          <span class="text-sm text-red-600 dark:text-red-400">{{ entry.error }}</span>
        </div>

        <!-- 富块渲染 -->
        <template v-else-if="entry.blocks && entry.blocks.length > 0">
          <div
            v-for="(block, j) in entry.blocks"
            :key="j"
            :class="['entry-block', `block-${block.type}`]"
          >
            <div v-if="isText(block)" class="markdown-body" v-html="renderMarkdown(block.text)" />
            <details v-else-if="block.type === 'reasoning'" class="block-reasoning">
              <summary class="text-xs italic text-gray-500 dark:text-gray-400">reasoning{{ block.incomplete ? "…" : "" }}</summary>
              <pre class="text-xs whitespace-pre-wrap">{{ block.reasoning }}</pre>
            </details>
            <img v-else-if="block.type === 'image'" :src="imgSrc(block)" alt="image" class="max-w-full rounded" />
            <audio v-else-if="block.type === 'audio'" :src="audioSrc(block)" controls class="w-full" />
            <a v-else-if="block.type === 'file'" :href="fileHref(block)" :download="fileLabel(block)" class="text-xs text-blue-600 dark:text-blue-400 underline">
              📎 {{ fileLabel(block) }}
            </a>
            <details v-else-if="block.type === 'tool_call'" class="block-tool">
              <summary class="text-xs">🔧 {{ block.name }}</summary>
              <pre class="text-xs whitespace-pre-wrap">{{ block.arguments }}</pre>
            </details>
            <details v-else-if="block.type === 'tool_result'" class="block-tool">
              <summary :class="['text-xs', block.success ? 'text-green-600' : 'text-red-600']">↳ {{ block.name ?? block.tool_call_id }}{{ block.success ? "" : " (failed)" }}</summary>
              <pre class="text-xs whitespace-pre-wrap">{{ block.content }}</pre>
              <pre v-if="block.error" class="text-xs text-red-500 whitespace-pre-wrap">{{ block.error }}</pre>
            </details>
            <div v-else-if="block.type === 'error'" class="block-error">
              <span class="text-xs text-red-600 dark:text-red-400">{{ block.error_type }}: {{ block.message }}</span>
            </div>
          </div>
        </template>

        <!-- 无块：纯 content -->
        <span v-else class="text-base">{{ entry.content }}</span>
      </div>
    </div>

    <MessageInput
      v-if="rooms.activeRoomId"
      :disabled="!canChat"
      @send="handleSend"
    />
  </div>
</template>

<style scoped>
.chat-entry {
  padding: 0.375rem 0.75rem;
  border-radius: 0.5rem;
  max-width: 85%;
  word-break: break-word;
}

.entry-human {
  background: #d1fae5;
  color: #065f46;
  align-self: flex-end;
  margin-left: auto;
}
:root.dark .entry-human {
  background: #064e3b;
  color: #a7f3d0;
}

.entry-conversation {
  background: #e8f0fe;
  color: #1a3a5c;
  align-self: flex-start;
}
:root.dark .entry-conversation {
  background: #1e3a5f;
  color: #b8d4f0;
}

.entry-send {
  background: #f3f4f6;
  color: #4b5563;
  align-self: flex-start;
  margin-left: 2rem;
  border-left: 2px solid #9ca3af;
}
:root.dark .entry-send {
  background: #1f2937;
  color: #9ca3af;
}

.entry-broadcast {
  background: #fef3c7;
  color: #92400e;
  align-self: center;
  margin: 0 auto;
  border: 1px dashed #d97706;
}
:root.dark .entry-broadcast {
  background: #422006;
  color: #fde68a;
}

.entry-endtask {
  background: transparent;
  color: #6b7280;
  font-style: italic;
  align-self: flex-start;
}
:root.dark .entry-endtask {
  color: #9ca3af;
}

.entry-pending {
  opacity: 0.55;
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.55; }
  50% { opacity: 0.85; }
}

.entry-error {
  background: #fee2e2;
  color: #991b1b;
  align-self: flex-end;
  margin-left: auto;
}
:root.dark .entry-error {
  background: #7f1d1d;
  color: #fecaca;
}

.block-error {
  margin-top: 0.125rem;
}

.entry-header {
  font-size: 0.7rem;
  font-weight: 600;
  margin-bottom: 0.125rem;
  opacity: 0.8;
}

.entry-block {
  margin-top: 0.125rem;
}

.block-reasoning,
.block-tool {
  margin: 0.125rem 0;
}

.markdown-body :deep(p) {
  margin: 0.125rem 0;
}
.markdown-body :deep(pre) {
  background: rgba(0, 0, 0, 0.05);
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  overflow-x: auto;
}
:root.dark .markdown-body :deep(pre) {
  background: rgba(0, 0, 0, 0.3);
}
</style>
