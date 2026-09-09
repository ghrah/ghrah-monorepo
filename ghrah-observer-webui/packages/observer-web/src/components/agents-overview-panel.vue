<script setup lang="ts">
import {
  type ChainTarget,
  useAgentsStore,
  useBranchesStore,
  useProjectsStore,
  useRoomsStore,
  useSessionsStore,
} from "@ghrah/observer-core";
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const props = defineProps<{ projectId: string }>();
const emit = defineEmits<{ openAgent: [target: ChainTarget] }>();
const projects = useProjectsStore();
const agents = useAgentsStore();
const sessions = useSessionsStore();
const branches = useBranchesStore();
const rooms = useRoomsStore();
const { t } = useI18n();

const project = computed(() => projects.projects.get(props.projectId) ?? null);
const rows = computed(() =>
  (project.value?.agents ?? []).map((spec) => {
    const agentId = spec.agent_id ?? "";
    const target = { projectId: props.projectId, agentId, agentName: spec.name };
    const runtime = agentId ? agents.getAgent(target) : undefined;
    const sessionId = agentId ? sessions.activeSessionId(target) : null;
    const session = sessionId ? { ...target, sessionId } : null;
    const branchId = session ? branches.activeBranchId(session) : null;
    const chainTarget =
      session && branchId ? ({ ...session, branchId } satisfies ChainTarget) : null;
    const roomNames = rooms
      .roomsForProject(props.projectId)
      .filter((room) =>
        room.members.some(
          (member) =>
            member.subject_type === "agent" &&
            (member.subject === agentId ||
              member.subject === spec.name ||
              member.subject_name === spec.name),
        ),
      )
      .map((room) => room.name);
    return {
      agentId,
      name: runtime?.agentName ?? spec.name,
      clusterId: runtime?.clusterId ?? spec.cluster_id ?? "",
      status: runtime?.runtimeStatus ?? spec.runtime_status ?? "stopped",
      runtimeError: runtime?.runtimeError ?? spec.runtime_error ?? "",
      roomNames,
      chainTarget,
    };
  }),
);

function openAgent(row: (typeof rows.value)[number]) {
  if (!row.chainTarget) return;
  const target = row.chainTarget;
  const agent = {
    projectId: target.projectId,
    agentId: target.agentId,
    agentName: target.agentName,
  };
  agents.selectAgent(agent);
  sessions.setActiveSession(agent, target.sessionId);
  branches.setActiveBranch(target, target.branchId);
  emit("openAgent", target);
}
</script>

<template>
  <div class="project-panel agents-overview-panel">
    <header class="project-panel-header">
      <div>
        <span class="section-eyebrow">{{ t("agentsOverview.eyebrow") }}</span>
        <h2>{{ t("agentsOverview.title", { project: project?.name ?? projectId }) }}</h2>
      </div>
      <span class="project-panel-count">{{ rows.length }}</span>
    </header>
    <div v-if="rows.length === 0" class="project-panel-empty">{{ t("agentsOverview.empty") }}</div>
    <ul v-else class="agents-overview-list">
      <li v-for="row in rows" :key="row.agentId || row.name">
        <button type="button" :disabled="!row.chainTarget" @click="openAgent(row)">
          <span :class="['agents-overview-avatar', `status-${row.status}`]">{{ row.name.slice(0, 1).toUpperCase() }}</span>
          <span class="agents-overview-main"><strong>{{ row.name }}</strong><span>{{ row.agentId || t("agentsOverview.missingId") }}</span></span>
          <span class="agents-overview-rooms"><span v-for="roomName in row.roomNames" :key="roomName"># {{ roomName }}</span></span>
          <span class="agents-overview-runtime"><strong>{{ t(`agentsOverview.status.${row.status}`) }}</strong><span>{{ row.clusterId }}</span></span>
        </button>
        <p v-if="!row.chainTarget" class="agents-overview-chain-hint">{{ t("agentsOverview.noActiveChain") }}</p>
        <p v-if="row.runtimeError" class="agents-overview-error">{{ row.runtimeError }}</p>
      </li>
    </ul>
  </div>
</template>
