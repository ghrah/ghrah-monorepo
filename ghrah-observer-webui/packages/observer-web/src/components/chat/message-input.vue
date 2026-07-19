<script setup lang="ts">
import { useAgentsStore } from "@ghrah/observer-core";
import { computed, ref } from "vue";

defineProps<{ disabled?: boolean }>();
const emit = defineEmits<{ send: [targets: string[], content: string] }>();

const agents = useAgentsStore();

const input = ref("");
const selectedTargets = ref<Set<string>>(new Set());

const activeAgentNames = computed(() => agents.activeAgents.map((a) => a.name));

// @-补全：输入以 @ 开头时弹出过滤列表
const mentionQuery = computed(() => {
  const v = input.value;
  if (!v.startsWith("@")) return null;
  const rest = v.slice(1);
  // 仅当尚未空格分隔（仍在输入 name 阶段）时弹补全
  if (rest.includes(" ")) return null;
  return rest.toLowerCase();
});

const mentionCandidates = computed(() => {
  const q = mentionQuery.value;
  if (q === null) return [];
  return activeAgentNames.value.filter((n) => n.toLowerCase().includes(q));
});

function toggleTarget(name: string) {
  const next = new Set(selectedTargets.value);
  if (next.has(name)) next.delete(name);
  else next.add(name);
  selectedTargets.value = next;
}

function pickMention(name: string) {
  toggleTarget(name);
  input.value = "";
}

// 解析前导 @<name> token（一个或多个，可连写如 @B@C 或以空格/结尾分隔），追加进 targets 并从 content 剥离。
// 语义：前导 @ 与 chip 选择合并去重；无前导 @ 时 content=raw；有前导 @ 时 content=剥离后剩余。
function parseLeadingMentions(text: string): { targets: string[]; content: string } {
  const targets = new Set<string>();
  let rest = text;
  // @name 后可跟：空白、下一个 @、或字符串结尾
  const re = /^@([^\s@]+)(?:\s+|(?=@)|$)/;
  let m = rest.match(re);
  while (m) {
    const name = m[1];
    if (activeAgentNames.value.includes(name)) {
      targets.add(name);
      // 剥离整个匹配（含分隔符）；若分隔符是 \s+，content 去掉该空白
      rest = rest.slice(m[0].length);
      m = rest.match(re);
    } else {
      break;
    }
  }
  return { targets: [...targets], content: rest.trim() };
}

function handleSubmit() {
  const raw = input.value.trim();
  if (!raw) return;
  const parsed = parseLeadingMentions(raw);
  const targets = new Set(selectedTargets.value);
  for (const t of parsed.targets) targets.add(t);
  // 有前导 @ 被解析时 content 取剥离后剩余；否则 content 取原文
  const content = parsed.targets.length > 0 ? parsed.content : raw;
  if (targets.size === 0 || !content) return;
  emit("send", [...targets], content);
  input.value = "";
  selectedTargets.value = new Set();
}
</script>

<template>
  <form
    class="flex flex-col gap-2 p-2 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900"
    @submit.prevent="handleSubmit"
  >
    <!-- 多选 target 表单 -->
    <div v-if="activeAgentNames.length > 0" class="flex flex-wrap gap-2">
      <button
        v-for="name in activeAgentNames"
        :key="name"
        type="button"
        :class="[
          'px-2 py-0.5 rounded-full text-xs border transition-colors',
          selectedTargets.has(name)
            ? 'bg-blue-100 dark:bg-blue-900 border-blue-400 text-blue-900 dark:text-blue-100'
            : 'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-blue-400',
        ]"
        @click="toggleTarget(name)"
      >
        @{{ name }}
      </button>
    </div>

    <div class="relative flex gap-2">
      <input
        v-model="input"
        type="text"
        :disabled="disabled || activeAgentNames.length === 0"
        class="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm dark:text-gray-100 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        placeholder="Type @name or select targets above..."
        @keydown.ctrl.enter="handleSubmit"
      />
      <!-- @-补全下拉 -->
      <ul
        v-if="mentionCandidates.length > 0"
        class="absolute bottom-full mb-1 left-0 right-0 max-h-40 overflow-y-auto bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded shadow-lg z-10"
      >
        <li
          v-for="name in mentionCandidates"
          :key="name"
          class="px-3 py-1.5 text-sm cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900 text-gray-700 dark:text-gray-200"
          @mousedown.prevent="pickMention(name)"
        >
          @{{ name }}
        </li>
      </ul>
      <button
        type="submit"
        :disabled="disabled || activeAgentNames.length === 0 || !input.trim()"
        class="btn-primary text-sm"
      >
        Send
      </button>
    </div>
  </form>
</template>
