<script setup lang="ts">
import {
  type ChainTarget,
  chainKey,
  useActionChainsStore,
  useAgentsStore,
  useBranchesStore,
  useSessionsStore,
} from "@ghrah/observer-core";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import ActionNodeRow from "./action-node.vue";

const { t } = useI18n();

import { createTreeCache, type TreeRow } from "./build-tree.js";

const chains = useActionChainsStore();
const agents = useAgentsStore();
const sessions = useSessionsStore();
const branches = useBranchesStore();

const selectedAgentName = computed(() => agents.selectedAgentName);
const activeChainTarget = computed<ChainTarget | null>(() => {
  const agent = agents.selectedAgentTarget;
  if (!agent) return null;
  const sessionId = sessions.activeSessionId(agent);
  if (!sessionId) return null;
  const session = { ...agent, sessionId };
  const branchId = branches.activeBranchId(session);
  return branchId ? { ...session, branchId } : null;
});

// per-chain 树缓存（性能红线 2）：append-only 增长走增量补建，切换作用域不清缓存
const treeCache = createTreeCache();

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
