<script setup lang="ts">
import MessageInput from "./message-input.vue";

function handleSend(_content: string) {
  // TODO: send message via ObserverClient.sendMessage() when client is injected
}
</script>

<template>
  <div class="chat-panel">
    <div class="chat-messages">
      <p class="placeholder">Select an agent to start chatting.</p>
    </div>
    <MessageInput @send="handleSend" />
  </div>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem;
}

.placeholder {
  color: #999;
  font-size: 0.875rem;
}
</style>
