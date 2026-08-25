<script setup lang="ts">
import { useProjectsStore, useRoomsStore } from "@ghrah/observer-core";
import type { RoomInfoPayload } from "@ghrah/protocol";
import { computed } from "vue";
import { useObserver } from "@/composables/useObserver";

const rooms = useRoomsStore();
const projects = useProjectsStore();
const { switchRoom } = useObserver();

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
</script>

<template>
  <div class="p-3 border-b border-gray-200 dark:border-gray-700">
    <h3 class="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">Rooms</h3>

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
        @click="switchRoom(room.room_id)"
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
              'room-member inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-semibold',
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

    <p v-else class="text-gray-400 dark:text-gray-600 text-xs italic">No rooms</p>
  </div>
</template>
