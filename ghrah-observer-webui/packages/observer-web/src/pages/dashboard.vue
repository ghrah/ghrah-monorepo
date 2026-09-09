<script setup lang="ts">
import {
  type AgentTarget,
  agentKey,
  sameAgent,
  useAgentsStore,
  useRoomsStore,
} from "@ghrah/observer-core";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import ActionChainPanel from "@/components/action-chain/action-chain-panel.vue";
import AgentList from "@/components/agent-list.vue";
import ChatPanel from "@/components/chat/chat-panel.vue";
import HitlInbox from "@/components/hitl/hitl-inbox.vue";
import InstanceProfileControl from "@/components/instance-profile-control.vue";
import ProjectSelector from "@/components/nav/project-selector.vue";
import RoomSelector from "@/components/nav/room-selector.vue";
import { useObserver } from "@/composables/useObserver";

type RoomWorkspaceTab = {
  id: string;
  kind: "room";
  target: string;
  label: string;
};

type AgentWorkspaceTab = {
  id: string;
  kind: "agent";
  target: AgentTarget;
  label: string;
};

type WorkspaceTab = RoomWorkspaceTab | AgentWorkspaceTab;
const emit = defineEmits<{
  openSettings: [section: "general" | "agents" | "abilities"];
}>();

const rooms = useRoomsStore();
const agents = useAgentsStore();
const { t } = useI18n();
const { switchRoom } = useObserver();
const tabs = ref<WorkspaceTab[]>([]);
const activeTabId = ref<string | null>(null);

const activeTab = computed(() => tabs.value.find((tab) => tab.id === activeTabId.value) ?? null);
const activePanel = computed(() => {
  if (activeTab.value?.kind === "room") return ChatPanel;
  if (activeTab.value?.kind === "agent") return ActionChainPanel;
  return null;
});

function openRoom(room: { room_id: string; name: string }) {
  const id = `room:${room.room_id}`;
  if (!tabs.value.some((tab) => tab.id === id)) {
    tabs.value.push({ id, kind: "room", target: room.room_id, label: room.name });
  }
  activeTabId.value = id;
}

function openAgent(target: AgentTarget) {
  const id = `agent:${agentKey(target)}`;
  if (!tabs.value.some((tab) => tab.id === id)) {
    tabs.value.push({ id, kind: "agent", target, label: target.agentName });
  }
  activeTabId.value = id;
}

async function activateTab(tab: WorkspaceTab) {
  activeTabId.value = tab.id;
  if (tab.kind === "room" && rooms.activeRoomId !== tab.target) {
    await switchRoom(tab.target);
  }
  if (tab.kind === "agent" && !sameAgent(agents.selectedAgentTarget, tab.target)) {
    agents.selectAgent(tab.target);
  }
}

function closeTab(tab: WorkspaceTab) {
  const index = tabs.value.findIndex((item) => item.id === tab.id);
  if (index < 0) return;
  const wasActive = activeTabId.value === tab.id;
  tabs.value.splice(index, 1);
  if (wasActive) {
    const next = tabs.value[Math.min(index, tabs.value.length - 1)];
    activeTabId.value = next?.id ?? null;
    if (next) void activateTab(next);
  }
}
</script>

<template>
  <div class="workspace-shell">
    <aside class="project-rail workspace-column" :aria-label="t('dashboard.projects')">
      <ProjectSelector />
    </aside>

    <aside class="room-sidebar workspace-column" :aria-label="t('dashboard.rooms')">
      <div class="room-sidebar-scroll">
        <RoomSelector @open-room="openRoom" />
      </div>
      <InstanceProfileControl @open-settings="emit('openSettings', 'general')" />
    </aside>

    <section class="workspace-main" :aria-label="t('dashboard.workspaceTabs')">
      <div class="workspace-tabs" role="tablist" :aria-label="t('dashboard.openViews')">
        <div class="tabs-scroll">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            type="button"
            :class="['workspace-tab', { active: activeTabId === tab.id }]"
            role="tab"
            :aria-selected="activeTabId === tab.id"
            @click="activateTab(tab)"
          >
            <span :class="['tab-kind', tab.kind]">{{ tab.kind === "room" ? "#" : "◎" }}</span>
            <span class="tab-label">{{ tab.label }}</span>
            <span
              class="tab-close"
              role="button"
              tabindex="0"
              :aria-label="t('dashboard.closeTab', { label: tab.label })"
              @click.stop="closeTab(tab)"
              @keydown.enter.stop="closeTab(tab)"
            >×</span>
          </button>
        </div>
        <span class="tab-count">{{ t("dashboard.openCount", { count: tabs.length }) }}</span>
      </div>

      <div class="workspace-content">
        <!-- KeepAlive 保留 ActionChain 增量缓存，同时让隐藏面板停止渲染更新。
             key 必须绑定 tab id：KeepAlive 以 vnode.key 为缓存键，若 key 恒为 0，
             ChatPanel 与 ActionChainPanel 会互相覆盖缓存条目，切回时 type 与
             component 不匹配，activate 分支 unmount 旧组件时
             parentComponent.ctx.deactivate 不存在 → TypeError，界面卡死。 -->
        <KeepAlive>
          <component :is="activePanel" v-if="activePanel" :key="activeTab?.id" />
        </KeepAlive>
        <div v-if="!activeTab" class="workspace-empty">
          <div class="empty-mark">⌘</div>
          <h2>{{ t("dashboard.readyTitle") }}</h2>
          <p>{{ t("dashboard.readyBody") }}</p>
          <div class="empty-shortcuts">
            <span class="shortcut-pill"><kbd>#</kbd> {{ t("dashboard.roomConversation") }}</span>
            <span class="shortcut-pill"><kbd>◎</kbd> {{ t("dashboard.agentActionChain") }}</span>
          </div>
        </div>
      </div>

      <footer class="hitl-dock">
        <HitlInbox />
      </footer>
    </section>

    <aside class="agent-sidebar workspace-column" :aria-label="t('dashboard.agents')">
      <AgentList @open-agent="openAgent" @open-settings="emit('openSettings', $event)" />
    </aside>
  </div>
</template>
