<script setup lang="ts">
import { useAgentsStore, useProjectsStore, useRoomsStore } from "@ghrah/observer-core";
import type { RoomInfoPayload } from "@ghrah/protocol";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useObserver } from "@/composables/useObserver";

const { t } = useI18n();

const rooms = useRoomsStore();
const projects = useProjectsStore();
const agents = useAgentsStore();
const { switchRoom, createRoom, joinRoom, leaveRoom, error } = useObserver();
const emit = defineEmits<{
  openRoom: [room: { room_id: string; name: string }];
}>();

const visibleRooms = computed<RoomInfoPayload[]>(() => {
  const list = rooms.roomList;
  if (!projects.activeProjectId) return list;
  return list.filter((r) => r.project_id === projects.activeProjectId);
});

/** subject → 所属 room 数（跨全部 room 统计，用于标识多 room 成员）。 */
const membershipCount = computed<Map<string, number>>(() => {
  const count = new Map<string, number>();
  for (const room of rooms.roomList) {
    for (const member of room.members) {
      count.set(member.subject, (count.get(member.subject) ?? 0) + 1);
    }
  }
  return count;
});

function isMultiRoom(subject: string): boolean {
  return (membershipCount.value.get(subject) ?? 0) > 1;
}

function initial(subject: string): string {
  return subject.slice(0, 1).toUpperCase();
}

async function selectRoom(room: RoomInfoPayload) {
  await switchRoom(room.room_id);
  emit("openRoom", { room_id: room.room_id, name: room.name });
}

// ── 创建 room（active project 域内） ──

const creating = ref(false);
const newName = ref("");
const busy = ref(false);

function startCreate() {
  creating.value = true;
  newName.value = "";
}

function cancelCreate() {
  creating.value = false;
  newName.value = "";
}

async function submitCreate() {
  const name = newName.value.trim();
  const projectId = projects.activeProjectId;
  if (!name || busy.value) return;
  if (!projectId) {
    error.value = t("nav.room.selectProjectFirst");
    return;
  }
  busy.value = true;
  try {
    const result = await createRoom(projectId, name);
    if (result?.success) {
      const created = (result.data as { room?: { room_id: string } } | undefined)?.room;
      if (created?.room_id) {
        await switchRoom(created.room_id);
        emit("openRoom", { room_id: created.room_id, name });
      }
      cancelCreate();
    } else if (result && !result.success) {
      error.value = result.error ?? t("nav.room.createFailed");
    }
  } finally {
    busy.value = false;
  }
}

// ── 成员管理（active room） ──

const activeRoom = computed(() => rooms.activeRoom);
const showMembers = ref(false);
const addOpen = ref(false);
const memberBusy = ref(false);

/** 候选成员 = 当前 active agents 中尚未入室者。 */
const candidateAgents = computed<string[]>(() => {
  const room = activeRoom.value;
  if (!room) return [];
  const inRoom = new Set(room.members.map((m) => m.subject));
  return agents.activeAgents.map((a) => a.name).filter((n) => !inRoom.has(n));
});

async function addMember(subject: string) {
  const room = activeRoom.value;
  if (!room || memberBusy.value) return;
  memberBusy.value = true;
  try {
    const result = await joinRoom(room.room_id, subject, "agent");
    if (result && !result.success) {
      error.value = result.error ?? t("nav.room.joinFailed");
    }
  } finally {
    memberBusy.value = false;
    addOpen.value = false;
  }
}

async function removeMember(subject: string) {
  const room = activeRoom.value;
  if (!room || memberBusy.value) return;
  memberBusy.value = true;
  try {
    const result = await leaveRoom(room.room_id, subject);
    if (result && !result.success) {
      error.value = result.error ?? t("nav.room.removeFailed");
    }
  } finally {
    memberBusy.value = false;
  }
}
</script>

<template>
  <div class="room-selector sidebar-section">
    <div class="section-heading">
      <div>
        <span class="section-eyebrow">{{ t("nav.room.workspace") }}</span>
        <h3>{{ t("nav.room.rooms") }}</h3>
      </div>
      <div class="flex items-center gap-1">
        <button
          v-if="activeRoom"
          class="btn-secondary text-xs px-2 py-0.5"
          :title="showMembers ? t('nav.room.hideMembers') : t('nav.room.manageMembers')"
          @click="showMembers = !showMembers"
        >
          👥 {{ activeRoom.members.length }}
        </button>
        <button
          v-if="!creating"
          class="btn-primary text-xs px-2 py-0.5"
          :title="t('nav.room.new')"
          @click="startCreate"
        >
          + {{ t("common.create") }}
        </button>
      </div>
    </div>

    <form v-if="creating" class="mb-2 flex gap-1" @submit.prevent="submitCreate">
      <input
        v-model="newName"
        type="text"
        :placeholder="t('nav.room.namePlaceholder')"
        class="flex-1 min-w-0 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
        @keydown.esc="cancelCreate"
      />
      <button
        type="submit"
        class="btn-primary text-xs px-2 py-1"
        :disabled="busy || !newName.trim()"
      >
        {{ busy ? "…" : t("common.create") }}
      </button>
      <button
        type="button"
        class="btn-secondary text-xs px-2 py-1"
        @click="cancelCreate"
      >
        ✕
      </button>
    </form>

    <ul v-if="visibleRooms.length > 0" class="space-y-1">
      <li
        v-for="room in visibleRooms"
        :key="room.room_id"
        :class="[
          'px-2 py-1.5 rounded cursor-pointer text-sm transition-colors',
          rooms.activeRoomId === room.room_id
            ? 'bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100 font-medium'
            : 'hover:bg-gray-100 dark:hover:bg-gray-800',
        ]"
        @click="selectRoom(room)"
      >
        <div class="flex items-center justify-between">
          <span class="truncate">{{ room.name }}</span>
          <span class="text-xs text-gray-400 dark:text-gray-500 flex-shrink-0">{{ room.members.length }}</span>
        </div>
        <div v-if="room.members.length > 0" class="flex flex-wrap gap-1 mt-1">
          <span
            v-for="member in room.members"
            :key="member.subject"
            :title="member.subject"
            :class="[
              'room-member inline-flex items-center justify-center w-5 h-5 rounded-full text-xs font-semibold',
              isMultiRoom(member.subject)
                ? 'bg-amber-200 dark:bg-amber-800 text-amber-900 dark:text-amber-100 ring-1 ring-amber-500'
                : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300',
            ]"
          >
            {{ initial(member.subject) }}
          </span>
        </div>
      </li>
    </ul>

    <p v-else class="text-gray-400 dark:text-gray-600 text-sm italic">{{ t("nav.room.empty") }}</p>

    <!-- 成员管理（active room） -->
    <div
      v-if="activeRoom && showMembers"
      class="mt-2 p-2 border border-gray-200 dark:border-gray-700 rounded bg-gray-50 dark:bg-gray-800 text-xs"
    >
      <div class="font-semibold text-gray-600 dark:text-gray-300 mb-1">
        {{ t("nav.room.membersTitle", { name: activeRoom.name }) }}
      </div>
      <ul class="space-y-0.5 mb-2">
        <li
          v-for="member in activeRoom.members"
          :key="member.subject"
          class="flex items-center justify-between gap-1"
        >
          <span class="truncate" :title="member.subject">
            {{ member.subject_type === "human" ? "👤" : "🤖" }} {{ member.subject }}
          </span>
          <button
            class="text-red-500 hover:text-red-700 dark:hover:text-red-400 px-1"
            :title="t('nav.room.removeTitle')"
            :disabled="memberBusy"
            @click="removeMember(member.subject)"
          >
            ✕
          </button>
        </li>
        <li v-if="activeRoom.members.length === 0" class="text-gray-400 dark:text-gray-600 italic">
          {{ t("nav.room.noMembers") }}
        </li>
      </ul>

      <div class="relative">
        <button
          class="btn-secondary text-xs px-2 py-0.5 w-full"
          :disabled="memberBusy || candidateAgents.length === 0"
          @click="addOpen = !addOpen"
        >
          {{ t("nav.room.addMember") }}
        </button>
        <ul
          v-if="addOpen && candidateAgents.length > 0"
          class="absolute z-10 left-0 right-0 mt-1 max-h-40 overflow-y-auto bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded shadow-lg"
        >
          <li
            v-for="name in candidateAgents"
            :key="name"
            class="px-2 py-1 cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900 text-gray-700 dark:text-gray-200"
            @click="addMember(name)"
          >
            🤖 {{ name }}
          </li>
        </ul>
        <p v-if="addOpen && candidateAgents.length === 0" class="text-gray-400 dark:text-gray-600 mt-1 italic">
          {{ t("nav.room.allAgentsInRoom") }}
        </p>
      </div>
    </div>
  </div>
</template>
