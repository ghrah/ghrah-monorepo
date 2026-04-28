<script setup lang="ts">
import { ref } from "vue";

const emit = defineEmits<{
  send: [content: string];
}>();

const input = ref("");

function handleSubmit() {
  const value = input.value.trim();
  if (!value) return;
  emit("send", value);
  input.value = "";
}
</script>

<template>
  <form class="message-input" @submit.prevent="handleSubmit">
    <input v-model="input" type="text" placeholder="Type a message..." />
    <button type="submit" :disabled="!input.trim()">Send</button>
  </form>
</template>

<style scoped>
.message-input {
  display: flex;
  gap: 0.5rem;
  padding: 0.5rem;
  border-top: 1px solid #ddd;
}

.message-input input {
  flex: 1;
  padding: 0.375rem 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.message-input button {
  padding: 0.375rem 0.75rem;
  border: none;
  border-radius: 4px;
  background: #0066cc;
  color: white;
  cursor: pointer;
}

.message-input button:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
