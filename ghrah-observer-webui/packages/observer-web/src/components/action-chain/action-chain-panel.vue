<script setup lang="ts">
import {
  type AgentTarget,
  type ChainTarget,
  chainKey,
  getVisibleNodes,
  useActionChainsStore,
  useAgentsStore,
  useBranchesStore,
  useSessionsStore,
} from "@ghrah/observer-core";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useObserver } from "@/composables/useObserver";
import { useTabScrollRestore } from "@/composables/useTabScrollRestore";
import ActionNodeRow from "./action-node.vue";

const { t } = useI18n();

import { createTreeCache, type TreeRow } from "./build-tree.js";

const props = defineProps<{
  agent: AgentTarget;
}>();

const chains = useActionChainsStore();
const agents = useAgentsStore();
const sessions = useSessionsStore();
const branches = useBranchesStore();
const { activateSession, activateBranch, createSession, createBranch } = useObserver();

// store 中的 AgentInfo 含 clusterId/config 等额外字段，对外（RPC/store 键）只投影纯 AgentTarget
const agentTarget = computed<AgentTarget>(() => {
  const resolved = agents.getAgent(props.agent);
  return resolved
    ? { projectId: resolved.projectId, agentId: resolved.agentId, agentName: resolved.agentName }
    : props.agent;
});
const selectedAgentName = computed(() => agentTarget.value.agentName);

type SwitchKind = "session" | "branch" | "new-session" | "new-branch";
const switching = ref<SwitchKind | null>(null);
const actionError = ref<string | null>(null);

// ── 运行态（runtimeActive*）：只由后端事件/同步结果推进 ──
const runtimeSessionId = computed(() =>
  agentTarget.value ? sessions.activeSessionId(agentTarget.value) : null,
);
const runtimeSessionTarget = computed(() => {
  const agent = agentTarget.value;
  const sessionId = agent ? sessions.activeSessionId(agent) : null;
  return agent && sessionId ? { ...agent, sessionId } : null;
});
const runtimeBranchId = computed(() =>
  runtimeSessionTarget.value ? branches.activeBranchId(runtimeSessionTarget.value) : null,
);

// ── 展示态（viewed*）：面板本地选择，不发运行时命令 ──
const viewedSessionId = computed(() =>
  agentTarget.value ? sessions.viewedSessionId(agentTarget.value) : null,
);
const viewedSessionTarget = computed(() => {
  const agent = agentTarget.value;
  const sessionId = agent ? sessions.viewedSessionId(agent) : null;
  return agent && sessionId ? { ...agent, sessionId } : null;
});
/** undefined = 尚未选择（回退运行态 Branch）；null = 查看全部 Branch。 */
const viewedBranchSelection = computed(() =>
  viewedSessionTarget.value ? branches.viewedBranchId(viewedSessionTarget.value) : undefined,
);

const sessionOptions = computed(() =>
  agentTarget.value ? sessions.sessionsForAgent(agentTarget.value) : [],
);
const branchOptions = computed(() =>
  viewedSessionTarget.value ? branches.branchesForSession(viewedSessionTarget.value) : [],
);

function failureOf(
  result:
    | { error?: string | null; error_detail?: string | null; success: boolean }
    | null
    | undefined,
): string {
  return result?.error_detail ?? result?.error ?? t("actionChain.switchFailed");
}

// ── 查看动作（普通切换，无运行时副作用） ──
function viewSession(sessionId: string) {
  const agent = agentTarget.value;
  if (!agent || !sessionId) return;
  sessions.viewSession(agent, sessionId);
  const target = { ...agent, sessionId };
  // 切换 Session 后展示态 Branch 回到"未选择"（回退该 Session 运行 Branch）
  branches.viewBranch(target, undefined);
}

function viewBranch(branchValue: string) {
  const session = viewedSessionTarget.value;
  if (!session) return;
  if (branchValue === "__all__") branches.viewBranch(session, null);
  else branches.viewBranch(session, branchValue);
}

// ── 显式激活动作（菜单按钮 + 确认，产生运行时副作用） ──
async function confirmActivateSession() {
  const agent = agentTarget.value;
  const sessionId = viewedSessionId.value;
  if (!agent || !sessionId || sessionId === runtimeSessionId.value) return;
  if (!window.confirm(t("actionChain.activateSessionConfirm"))) return;
  switching.value = "session";
  actionError.value = null;
  try {
    const result = await activateSession({ ...agent, sessionId });
    if (!result?.success) actionError.value = failureOf(result);
  } finally {
    switching.value = null;
  }
}

async function confirmActivateBranch() {
  const session = viewedSessionTarget.value;
  const branchId = viewedBranchSelection.value;
  if (!session || !branchId) return;
  if (branchId === runtimeBranchId.value) return;
  if (!window.confirm(t("actionChain.activateBranchConfirm"))) return;
  switching.value = "branch";
  actionError.value = null;
  try {
    const target: ChainTarget = { ...session, branchId };
    const result = await activateBranch(target);
    if (!result?.success) actionError.value = failureOf(result);
  } finally {
    switching.value = null;
  }
}

async function startSession() {
  const agent = agentTarget.value;
  if (!agent) return;
  switching.value = "new-session";
  actionError.value = null;
  try {
    const result = await createSession(agent);
    if (!result?.success) {
      actionError.value = failureOf(result);
      return;
    }
    const data = result.data as { session_id?: string } | null;
    // 新建 Session 只把展示切过去，不隐式激活运行态（D6 裁决）。
    if (data?.session_id) sessions.viewSession(agent, data.session_id);
  } finally {
    switching.value = null;
  }
}

async function startBranch() {
  const session = viewedSessionTarget.value;
  if (!session) return;
  switching.value = "new-branch";
  actionError.value = null;
  try {
    const name = t("actionChain.newBranchName", {
      index: branches.branchesForSession(session).length + 1,
    });
    const result = await createBranch(session, name);
    if (!result?.success) {
      actionError.value = failureOf(result);
      return;
    }
    const data = result.data as { branch_id?: string } | null;
    // 新建 Branch 只把展示切过去，不隐式激活运行态（D6 裁决）。
    if (data?.branch_id) branches.viewBranch(session, data.branch_id);
  } finally {
    switching.value = null;
  }
}

// ── 可视节点（getVisibleNodes：viewed Session + viewed/runtime Branch 回溯） ──
const visibleNodes = computed(() => {
  const agent = agentTarget.value;
  if (!agent) return [];
  return getVisibleNodes(sessions, branches, chains, agent);
});

// per-chain 树缓存（性能红线 2）：append-only 增长走增量补建，切换作用域不清缓存
const treeCache = createTreeCache();

const viewCacheKey = computed(() => {
  const session = viewedSessionTarget.value;
  if (!session) return "none";
  const branch = viewedBranchSelection.value;
  return chainKey({ ...session, branchId: branch ?? "__all__" });
});

const rows = computed<TreeRow[]>(() => treeCache.rowsFor(viewCacheKey.value, visibleNodes.value));

const chainContainer = ref<HTMLElement | null>(null);
const { onScroll: onChainScroll } = useTabScrollRestore(chainContainer, {
  contentKey: computed(() => rows.value.length),
});

const selectBranchValue = computed(() => {
  const selection = viewedBranchSelection.value;
  if (selection === undefined) return runtimeBranchId.value ?? "";
  return selection ?? "__all__";
});
</script>

<template>
  <div class="p-3 h-full flex flex-col">
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">{{ t("actionChain.title") }}</h3>
      <span v-if="selectedAgentName" class="text-xs text-gray-500 dark:text-gray-400">@{{ selectedAgentName }}</span>
    </div>

    <div v-if="agentTarget" class="flex items-center gap-2 flex-wrap mb-2">
      <label class="text-xs text-gray-500 dark:text-gray-400">
        {{ t("actionChain.session") }}
        <select
          class="chain-session-select text-xs rounded-sm border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200"
          :value="viewedSessionId ?? ''"
          :disabled="switching !== null"
          @change="viewSession(($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>{{ t("actionChain.selectSession") }}</option>
          <option v-for="option in sessionOptions" :key="option.target.sessionId" :value="option.target.sessionId">
            {{ option.info.name || option.target.sessionId }}
            <template v-if="option.target.sessionId === runtimeSessionId">●</template>
          </option>
        </select>
      </label>
      <button
        v-if="viewedSessionId && viewedSessionId !== runtimeSessionId"
        type="button"
        class="chain-activate-session text-xs underline text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
        :disabled="switching !== null"
        @click="confirmActivateSession"
      >
        {{ t("actionChain.activateSession") }}
      </button>
      <label v-if="viewedSessionTarget" class="text-xs text-gray-500 dark:text-gray-400">
        {{ t("actionChain.branch") }}
        <select
          class="chain-branch-select text-xs rounded-sm border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200"
          :value="selectBranchValue"
          :disabled="switching !== null || !viewedSessionTarget"
          @change="viewBranch(($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>{{ t("actionChain.selectBranch") }}</option>
          <option value="__all__">{{ t("actionChain.allBranches") }}</option>
          <option v-for="option in branchOptions" :key="option.target.branchId" :value="option.target.branchId">
            {{ option.info.name || option.target.branchId }}
            <template v-if="option.target.branchId === runtimeBranchId">●</template>
          </option>
        </select>
      </label>
      <button
        v-if="viewedBranchSelection && viewedBranchSelection !== runtimeBranchId"
        type="button"
        class="chain-activate-branch text-xs underline text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
        :disabled="switching !== null || !viewedSessionTarget"
        @click="confirmActivateBranch"
      >
        {{ t("actionChain.activateBranch") }}
      </button>
      <button
        type="button"
        class="chain-new-session text-xs underline text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
        :disabled="switching !== null"
        @click="startSession"
      >
        {{ t("actionChain.newSession") }}
      </button>
      <button
        type="button"
        class="chain-new-branch text-xs underline text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
        :disabled="switching !== null || !viewedSessionTarget"
        @click="startBranch"
      >
        {{ t("actionChain.newBranch") }}
      </button>
    </div>

    <div v-if="actionError" class="mb-2 text-xs text-red-600 dark:text-red-400" role="alert">
      {{ actionError }}
    </div>

    <div v-if="!selectedAgentName" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-600 text-sm italic">
      {{ t("actionChain.selectAgent") }}
    </div>

    <div v-else-if="rows.length === 0" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-600 text-sm italic">
      {{ t("actionChain.empty") }}
    </div>

    <div v-else ref="chainContainer" class="flex-1 overflow-y-auto" @scroll.passive="onChainScroll">
      <div class="border border-gray-200 dark:border-gray-700 rounded">
        <div class="px-2 py-1 bg-gray-50 dark:bg-gray-800 text-xs font-semibold text-gray-600 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
          @{{ selectedAgentName }}
        </div>
        <div class="px-1 py-1">
          <ActionNodeRow
            v-for="(row, i) in rows"
            :key="`${selectedAgentName}-${row.node.id}-${i}`"
            :node="row.node"
            :depth="row.depth"
            :is-last-child="row.isLastChild"
            :ancestor-pipes="row.ancestorPipes"
          />
        </div>
      </div>
    </div>
  </div>
</template>
