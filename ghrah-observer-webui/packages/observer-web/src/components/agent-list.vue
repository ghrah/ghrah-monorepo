<script setup lang="ts">
import { useAgentsStore, useRoomsStore } from "@ghrah/observer-core";
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import AgentActionMenu from "@/components/agent-action-menu.vue";

const { t } = useI18n();

const agents = useAgentsStore();
const rooms = useRoomsStore();
const emit = defineEmits<{ openAgent: [agentName: string] }>();

/** agent 名 → 所属 room 列表（RoomMember.subject_type === "agent"）。 */
const agentRooms = computed<Map<string, string[]>>(() => {
  const map = new Map<string, string[]>();
  for (const room of rooms.roomList) {
    for (const member of room.members) {
      if (member.subject_type !== "agent") continue;
      const list = map.get(member.subject) ?? [];
      list.push(room.name);
      map.set(member.subject, list);
    }
  }
  return map;
});

function roomsOf(agentName: string): string[] {
  return agentRooms.value.get(agentName) ?? [];
}

function selectAgent(agentName: string) {
  agents.selectAgent(agentName);
  emit("openAgent", agentName);
}
</script>

<template>
  <div class="agent-list sidebar-section h-full flex flex-col">
    <div class="section-heading">
      <div>
        <span class="section-eyebrow">{{ t("agents.runtime") }}</span>
        <h3>{{ t("agents.title") }}</h3>
      </div>
      <RouterLink to="/config/agents" class="btn-primary">{{ t("agents.spawn") }}</RouterLink>
    </div>

    <ul v-if="agents.activeAgents.length > 0" class="flex-1 overflow-y-auto space-y-1">
      <li
        v-for="agent in agents.activeAgents"
        :key="agent.name"
        :class="[
          'flex items-center justify-between px-2 py-1.5 rounded cursor-pointer text-sm transition-colors',
          agents.selectedAgentName === agent.name
            ? 'bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100 font-medium'
            : 'hover:bg-gray-100 dark:hover:bg-gray-800',
        ]"
        @click="selectAgent(agent.name)"
      >
        <span class="truncate">{{ agent.name }}</span>
        <div class="flex items-center gap-1">
          <span
            v-for="roomName in roomsOf(agent.name)"
            :key="roomName"
            :title="roomName"
            class="agent-room-badge inline-flex items-center justify-center min-w-5 h-5 px-1 rounded text-xs font-semibold bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
          >{{ roomName.slice(0, 1).toUpperCase() }}</span>
          <AgentActionMenu v-if="agents.selectedAgentName === agent.name" />
          <span class="w-2 h-2 rounded-full bg-green-500 flex-shrink-0" />
        </div>
      </li>
    </ul>

    <p v-else class="text-gray-400 dark:text-gray-600 text-sm italic">{{ t("agents.empty") }}</p>
  </div>
</template>
