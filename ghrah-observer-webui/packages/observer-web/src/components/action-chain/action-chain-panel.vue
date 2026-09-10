<script setup lang="ts">
import {
  type AgentTarget,
  type ChainTarget,
  chainKey,
  useActionChainsStore,
  useAgentsStore,
  useBranchesStore,
  useSessionsStore,
} from "@ghrah/observer-core";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useObserver } from "@/composables/useObserver";
import ActionNodeRow from "./action-node.vue";

const { t } = useI18n();

import { createTreeCache, type TreeRow } from "./build-tree.js";

const chains = useActionChainsStore();
const agents = useAgentsStore();
const sessions = useSessionsStore();
const branches = useBranchesStore();
const { activateSession, activateBranch, createSession, createBranch } = useObserver();

const selectedAgentName = computed(() => agents.selectedAgentName);
const agentTarget = computed<AgentTarget | null>(() => agents.selectedAgentTarget);

type SwitchKind = "session" | "branch" | "new-session" | "new-branch";
const switching = ref<SwitchKind | null>(null);
const actionError = ref<string | null>(null);

const activeSessionTarget = computed(() => {
  const agent = agentTarget.value;
  const sessionId = agent ? sessions.activeSessionId(agent) : null;
  return agent && sessionId ? { ...agent, sessionId } : null;
});

const sessionOptions = computed(() =>
  agentTarget.value ? sessions.sessionsForAgent(agentTarget.value) : [],
);
const currentSessionId = computed(() =>
  agentTarget.value ? sessions.activeSessionId(agentTarget.value) : null,
);
const branchOptions = computed(() =>
  activeSessionTarget.value ? branches.branchesForSession(activeSessionTarget.value) : [],
);
const currentBranchId = computed(() =>
  activeSessionTarget.value ? branches.activeBranchId(activeSessionTarget.value) : null,
);

function failureOf(
  result: {
    success: boolean;
    error?: string | null;
    error_detail?: string | null;
  } | null,
): string {
  return result?.error_detail ?? result?.error ?? t("actionChain.switchFailed");
}

async function switchSession(sessionId: string) {
  const agent = agentTarget.value;
  if (!agent || sessionId === currentSessionId.value) return;
  switching.value = "session";
  actionError.value = null;
  try {
    const result = await activateSession({ ...agent, sessionId });
    if (!result?.success) actionError.value = failureOf(result);
  } finally {
    switching.value = null;
  }
}

async function switchBranch(branchId: string) {
  const session = activeSessionTarget.value;
  if (!session || branchId === currentBranchId.value) return;
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
    if (data?.session_id && data.session_id !== currentSessionId.value) {
      const activated = await activateSession({ ...agent, sessionId: data.session_id });
      if (!activated?.success) actionError.value = failureOf(activated);
    }
  } finally {
    switching.value = null;
  }
}

async function startBranch() {
  const session = activeSessionTarget.value;
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
    if (data?.branch_id && data.branch_id !== currentBranchId.value) {
      const activated = await activateBranch({ ...session, branchId: data.branch_id });
      if (!activated?.success) actionError.value = failureOf(activated);
    }
  } finally {
    switching.value = null;
  }
}

// per-chain 树缓存（性能红线 2）：append-only 增长走增量补建，切换作用域不清缓存
const treeCache = createTreeCache();

const activeChainTarget = computed<ChainTarget | null>(() => {
  const session = activeSessionTarget.value;
  if (!session) return null;
  const branchId = branches.activeBranchId(session);
  return branchId ? { ...session, branchId } : null;
});

const rows = computed<TreeRow[]>(() => {
  const target = activeChainTarget.value;
  if (!target) return [];
  return treeCache.rowsFor(chainKey(target), chains.getChain(target));
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
          :value="currentSessionId ?? ''"
          :disabled="switching !== null"
          @change="switchSession(($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>{{ t("actionChain.selectSession") }}</option>
          <option v-for="option in sessionOptions" :key="option.target.sessionId" :value="option.target.sessionId">
            {{ option.target.sessionId }}
          </option>
        </select>
      </label>
      <label class="text-xs text-gray-500 dark:text-gray-400">
        {{ t("actionChain.branch") }}
        <select
          class="chain-branch-select text-xs rounded-sm border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200"
          :value="currentBranchId ?? ''"
          :disabled="switching !== null || !activeSessionTarget"
          @change="switchBranch(($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>{{ t("actionChain.selectBranch") }}</option>
          <option v-for="option in branchOptions" :key="option.target.branchId" :value="option.target.branchId">
            {{ option.info.name || option.target.branchId }}
          </option>
        </select>
      </label>
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
        :disabled="switching !== null || !activeSessionTarget"
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

    <div v-else class="flex-1 overflow-y-auto">
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
