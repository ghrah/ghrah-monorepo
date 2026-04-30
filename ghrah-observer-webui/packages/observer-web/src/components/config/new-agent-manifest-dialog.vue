<script setup lang="ts">
import { reactive, ref, computed } from "vue";
import { useObserver } from "@/composables/useObserver";

const emit = defineEmits<{ close: [] }>();

const { putAgent, listManifestAgents } = useObserver();

const loading = ref(false);
const error = ref<string | null>(null);

// ── Form state ──

interface AbilityEntry {
  mode: "type" | "ref";
  value: string;
}

const form = reactive({
  // metadata
  namespace: "",
  name: "",
  title: "",
  description: "",
  tags: "",
  // model
  agent_config_name: "",
  temperature: "" as string,
  max_tokens: "" as string,
  // prompt
  system_prompt: "You are a helpful assistant.",
  // abilities
  abilities: [{ mode: "type" as const, value: "end_task" }] as AbilityEntry[],
  // settings
  max_iterations: 10,
});

// ── Computed ──

const canSubmit = computed(() => {
  return (
    form.namespace.trim() !== "" &&
    form.name.trim() !== "" &&
    form.agent_config_name.trim() !== "" &&
    form.system_prompt.trim() !== "" &&
    form.abilities.length > 0 &&
    form.abilities.every((a) => a.value.trim() !== "")
  );
});

// ── Abilities ──

function addAbility() {
  form.abilities.push({ mode: "type", value: "" });
}

function removeAbility(index: number) {
  if (form.abilities.length > 1) {
    form.abilities.splice(index, 1);
  }
}

// ── YAML builder ──

function buildYaml(): string {
  const ns = form.namespace.trim();
  const nm = form.name.trim();
  const lines: string[] = [];

  lines.push("manifest: agent");
  lines.push('version: "1"');

  // metadata
  lines.push("metadata:");
  lines.push(`  namespace: ${ns}`);
  lines.push(`  name: ${nm}`);
  lines.push(`  title: ${quote(form.title)}`);
  lines.push(`  description: ${quote(form.description)}`);
  const tagsList = form.tags
    .split(",")
    .map((t) => t.trim())
    .filter((t) => t);
  lines.push(`  tags: [${tagsList.map((t) => quote(t)).join(", ")}]`);

  // model
  lines.push("model:");
  lines.push(`  agent_config_name: ${quote(form.agent_config_name.trim())}`);
  if (form.temperature !== "") {
    lines.push(`  temperature: ${form.temperature}`);
  }
  if (form.max_tokens !== "") {
    lines.push(`  max_tokens: ${form.max_tokens}`);
  }

  // system_prompt (multiline safe)
  lines.push(`system_prompt: ${quoteBlock(form.system_prompt)}`);

  // abilities
  lines.push("abilities:");
  for (const ab of form.abilities) {
    if (ab.mode === "type") {
      lines.push(`  - type: ${ab.value.trim()}`);
    } else {
      lines.push(`  - ref: ${ab.value.trim()}`);
    }
  }

  // settings
  lines.push(`max_iterations: ${form.max_iterations}`);

  return lines.join("\n") + "\n";
}

function quote(s: string): string {
  if (s === "" || /[:#{}[\],&*?|>!%@`]/.test(s) || s.includes("\n")) {
    return JSON.stringify(s);
  }
  return s;
}

function quoteBlock(s: string): string {
  if (!s.includes("\n")) {
    return quote(s);
  }
  // Use YAML literal block scalar for multiline
  return "|\n  " + s.split("\n").join("\n  ");
}

// ── Submit ──

async function handleSubmit() {
  const ns = form.namespace.trim();
  const nm = form.name.trim();
  if (!ns || !nm) return;
  loading.value = true;
  error.value = null;

  const fullName = `${ns}.${nm}`;
  const content = buildYaml();

  const result = await putAgent(fullName, content, false);
  loading.value = false;

  if (result && !result.success) {
    error.value = result.error ?? "创建失败";
  } else if (result === null) {
    error.value = "未连接到 Gateway";
  } else {
    await listManifestAgents();
    window.postMessage?.({ type: "openFile", fullName, kind: "agent" });
    emit("close");
  }
}


</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="$emit('close')">
    <div class="bg-white dark:bg-gray-900 rounded-lg shadow-xl w-full max-w-2xl max-h-[85vh] flex flex-col">
      <!-- Header -->
      <div class="px-6 pt-5 pb-3 border-b border-gray-200 dark:border-gray-700">
        <h2 class="text-lg font-semibold">New Agent Manifest</h2>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">
          创建一个完整的 Agent Manifest YAML 配置文件
        </p>
      </div>

      <!-- Scrollable form body -->
      <form class="flex-1 overflow-y-auto px-6 py-4 space-y-5" @submit.prevent="handleSubmit">
        <div v-if="error" class="text-red-600 dark:text-red-400 text-sm bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded">
          {{ error }}
        </div>

        <!-- Metadata Section -->
        <fieldset>
          <legend class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Metadata</legend>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                Namespace <span class="text-red-500">*</span>
              </label>
              <input
                v-model="form.namespace"
                type="text"
                required
                pattern="^[a-z][a-z0-9_.]*[a-z0-9]$"
                class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="e.g. ghrah.examples"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                Name <span class="text-red-500">*</span>
              </label>
              <input
                v-model="form.name"
                type="text"
                required
                pattern="^[a-z][a-z0-9_]*$"
                class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="e.g. designer"
              />
            </div>
          </div>
          <div class="mt-3">
            <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Title</label>
            <input
              v-model="form.title"
              type="text"
              class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g. Designer"
            />
          </div>
          <div class="mt-3">
            <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Description</label>
            <input
              v-model="form.description"
              type="text"
              class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Agent 功能描述"
            />
          </div>
          <div class="mt-3">
            <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Tags</label>
            <input
              v-model="form.tags"
              type="text"
              class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="逗号分隔，e.g. coding, design"
            />
          </div>
        </fieldset>

        <!-- Model Section -->
        <fieldset>
          <legend class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Model</legend>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                Agent Config Name <span class="text-red-500">*</span>
              </label>
              <input
                v-model="form.agent_config_name"
                type="text"
                required
                class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="e.g. gpt-4o-mini"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Max Iterations</label>
              <input
                v-model.number="form.max_iterations"
                type="number"
                min="1"
                class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3 mt-3">
            <div>
              <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Temperature</label>
              <input
                v-model="form.temperature"
                type="number"
                step="0.1"
                min="0"
                max="2"
                class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="可选，e.g. 0.7"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Max Tokens</label>
              <input
                v-model="form.max_tokens"
                type="number"
                min="1"
                class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="可选，e.g. 4096"
              />
            </div>
          </div>
        </fieldset>

        <!-- System Prompt Section -->
        <fieldset>
          <legend class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
            System Prompt <span class="text-red-500">*</span>
          </legend>
          <textarea
            v-model="form.system_prompt"
            required
            rows="4"
            class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
            placeholder="You are a helpful assistant."
          ></textarea>
        </fieldset>

        <!-- Abilities Section -->
        <fieldset>
          <legend class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
            Abilities <span class="text-red-500">*</span>
          </legend>
          <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">至少需要一个 Ability。type 为内置类型，ref 为完整引用名。</p>
          <div class="space-y-2">
            <div
              v-for="(ability, index) in form.abilities"
              :key="index"
              class="flex items-center gap-2"
            >
              <select
                v-model="ability.mode"
                class="px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="type">type (内置)</option>
                <option value="ref">ref (引用)</option>
              </select>
              <input
                v-model="ability.value"
                type="text"
                required
                class="flex-1 px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                :placeholder="ability.mode === 'type' ? 'e.g. end_task, conversation' : 'e.g. ghrah.fs.read_file'"
              />
              <button
                type="button"
                :disabled="form.abilities.length <= 1"
                class="px-2 py-1 text-xs text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 disabled:opacity-30 disabled:cursor-not-allowed"
                @click="removeAbility(index)"
              >
                ✕
              </button>
            </div>
          </div>
          <button
            type="button"
            class="mt-2 text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
            @click="addAbility()"
          >
            + Add Ability
          </button>
        </fieldset>

        <!-- Actions -->
        <div class="flex justify-end gap-2 pt-2 border-t border-gray-200 dark:border-gray-700">
          <button type="button" class="btn-secondary" :disabled="loading" @click="$emit('close')">Cancel</button>
          <button type="submit" class="btn-primary" :disabled="loading || !canSubmit">
            {{ loading ? "Creating..." : "Create Manifest" }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>