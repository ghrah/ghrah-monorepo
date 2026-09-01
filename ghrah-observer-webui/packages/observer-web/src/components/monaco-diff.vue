<script setup lang="ts">
import parseDiff from "parse-diff";
import { onBeforeUnmount, ref, watch } from "vue";
import { useMonaco } from "@/composables/useMonaco";

const props = defineProps<{ patch: string }>();

const container = ref<HTMLElement | null>(null);
const { createDiffEditor } = useMonaco();
let editor: Awaited<ReturnType<typeof createDiffEditor>> | null = null;

// 用 parse-diff 解析 unified patch：按 hunk 累积 original/modified，
// 多文件 patch 以文件分隔行展示（simplified multi-file view）。
function buildModelsFromPatch(patch: string): { original: string; modified: string } {
  if (!patch || !patch.trim()) return { original: "", modified: "" };
  let files: ReturnType<typeof parseDiff>;
  try {
    files = parseDiff(patch);
  } catch {
    return { original: "", modified: patch };
  }
  if (!files || files.length === 0) return { original: "", modified: patch };

  const origParts: string[] = [];
  const modParts: string[] = [];
  files.forEach((file, fi) => {
    const label = file.to ?? file.from ?? `file-${fi}`;
    if (fi > 0) {
      origParts.push("");
      modParts.push("");
    }
    const sep = `--- file: ${label} ---`;
    origParts.push(sep);
    modParts.push(sep);
    for (const chunk of file.chunks) {
      for (const change of chunk.changes) {
        if (change.type === "normal") {
          origParts.push(change.content);
          modParts.push(change.content);
        } else if (change.type === "del") {
          origParts.push(change.content);
        } else if (change.type === "add") {
          modParts.push(change.content);
        }
      }
    }
  });
  return { original: origParts.join("\n"), modified: modParts.join("\n") };
}

async function mount() {
  if (!container.value) return;
  if (editor) {
    editor.dispose();
    editor = null;
  }
  const { original, modified } = buildModelsFromPatch(props.patch ?? "");
  editor = await createDiffEditor(container.value, original, modified, "plaintext");
}

watch(
  () => props.patch,
  () => {
    void mount();
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  editor?.dispose();
  editor = null;
});
</script>

<template>
  <div ref="container" class="w-full h-full" />
</template>