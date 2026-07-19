<script setup lang="ts">
import type { ActionNode, ContentBlock } from "@ghrah/protocol";
import { computed, ref } from "vue";

const props = defineProps<{
  node: ActionNode;
  depth: number;
  isLastChild: boolean;
  ancestorPipes: boolean[];
}>();

const expanded = ref(false);

const SUPPRESSED_TOOL_NAMES = new Set(["send_message", "broadcast_message"]);

function isTextBlock(block: ContentBlock): boolean {
  return block.type === "text";
}
function shouldSuppress(block: ContentBlock): boolean {
  // conversation TextBlock + send_message/broadcast tool_call 抑制（已在 chat 视图显示），保留其余
  if (isTextBlock(block) && (props.node.ability_names ?? []).includes("conversation")) return true;
  if (block.type === "tool_call" && SUPPRESSED_TOOL_NAMES.has(block.name ?? "")) return true;
  return false;
}

const visibleBlocks = computed<ContentBlock[]>(() => {
  const blocks: ContentBlock[] = [];
  for (const m of props.node.messages_delta ?? []) {
    for (const b of m.content_blocks ?? []) {
      if (shouldSuppress(b)) continue;
      blocks.push(b);
    }
  }
  return blocks;
});

const abilitySummary = computed(() => (props.node.ability_names ?? []).join(",") || "—");
const stateKeys = computed(() => Object.keys(props.node.agent_state ?? {}));
const actionResults = computed(() => props.node.action_results ?? []);
const timeStr = computed(() => {
  const ts = props.node.timestamp;
  if (!ts) return "";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleTimeString();
});
const summary = computed(() => {
  const iter = props.node.iteration ?? 0;
  const branch =
    props.node.branch_name && props.node.branch_name !== "main"
      ? ` [${props.node.branch_name}]`
      : "";
  return `${timeStr.value} iter=${iter} | abilities=[${abilitySummary.value}] | state_keys=[${stateKeys.value.join(",")}]${branch}`;
});

const hasDetails = computed(() => visibleBlocks.value.length > 0 || actionResults.value.length > 0);
</script>

<template>
  <div class="tree-row">
    <div class="flex items-start gap-1 py-0.5">
      <!-- 缩进引导线 -->
      <span
        v-for="(pipe, idx) in ancestorPipes"
        :key="idx"
        class="inline-block w-4 text-center text-gray-300 dark:text-gray-700 select-none flex-shrink-0"
      >{{ pipe ? "│" : " " }}</span>
      <span class="inline-block w-4 text-center text-gray-400 dark:text-gray-600 select-none flex-shrink-0">{{ isLastChild ? "└" : "├" }}</span>
      <button
        v-if="hasDetails"
        type="button"
        class="text-xs text-gray-400 dark:text-gray-600 flex-shrink-0 w-4"
        @click="expanded = !expanded"
      >{{ expanded ? "▾" : "▸" }}</button>
      <span v-else class="inline-block w-4 flex-shrink-0" />
      <span class="flex-1 font-mono text-xs text-gray-700 dark:text-gray-300 truncate">{{ summary }}</span>
    </div>
    <div v-if="expanded && hasDetails" class="pl-10 py-1 space-y-1">
      <div
        v-for="(block, j) in visibleBlocks"
        :key="`b${j}`"
        class="text-xs"
      >
        <pre v-if="block.type === 'reasoning'" class="italic text-gray-500 dark:text-gray-400 whitespace-pre-wrap">{{ block.reasoning }}</pre>
        <pre v-else-if="block.type === 'error'" class="text-red-600 dark:text-red-400 whitespace-pre-wrap">{{ block.error_type }}: {{ block.message }}</pre>
        <details v-else-if="block.type === 'tool_call'" class="text-gray-600 dark:text-gray-400">
          <summary>🔧 {{ block.name }}</summary>
          <pre class="whitespace-pre-wrap">{{ block.arguments }}</pre>
        </details>
        <details v-else-if="block.type === 'tool_result'" :class="block.success ? 'text-green-600' : 'text-red-600'">
          <summary>↳ {{ block.name ?? block.tool_call_id }}</summary>
          <pre class="whitespace-pre-wrap">{{ block.content }}</pre>
        </details>
        <pre v-else class="whitespace-pre-wrap">{{ JSON.stringify(block, null, 2) }}</pre>
      </div>
      <details v-if="actionResults.length > 0" class="text-xs text-gray-600 dark:text-gray-400">
        <summary>action_results ({{ actionResults.length }})</summary>
        <pre class="whitespace-pre-wrap">{{ JSON.stringify(actionResults, null, 2) }}</pre>
      </details>
    </div>
  </div>
</template>
