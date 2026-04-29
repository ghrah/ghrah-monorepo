<script setup lang="ts">
import { ref } from "vue";

defineProps<{ disabled?: boolean }>();

const emit = defineEmits<{ send: [content: string] }>();

const input = ref("");

function handleSubmit() {
  const value = input.value.trim();
  if (!value) return;
  emit("send", value);
  input.value = "";
}
</script>

<template>
  <form class="flex gap-2 p-2 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900" @submit.prevent="handleSubmit">
    <input
      v-model="input"
      type="text"
      :disabled="disabled"
      class="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm dark:text-gray-100 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
      placeholder="Type a message..."
      @keydown.ctrl.enter="handleSubmit"
    />
    <button
      type="submit"
      :disabled="disabled || !input.trim()"
      class="btn-primary text-sm"
    >
      Send
    </button>
  </form>
</template>