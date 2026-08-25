import type {
  RoomDeletedEventPayload,
  RoomEventPayload,
  RoomInfoPayload,
  RoomLogEntryPayload,
  RoomLogEventPayload,
  RoomMemberEventPayload,
} from "@ghrah/protocol";
import { defineStore } from "pinia";
import { computed, ref } from "vue";

/** room log 缓存上限：最多保留最近访问的 N 个 room（LRU）。 */
export const MAX_CACHED_ROOM_LOGS = 10;

export const useRoomsStore = defineStore("ghrah-rooms", () => {
  const rooms = ref<Map<string, RoomInfoPayload>>(new Map());
  /** logs 的 Map 插入序即 LRU 序（最近访问的在尾部）。 */
  const logs = ref<Map<string, RoomLogEntryPayload[]>>(new Map());
  const activeRoomId = ref<string | null>(null);

  const roomList = computed(() => [...rooms.value.values()]);

  const activeRoom = computed(() => {
    if (!activeRoomId.value) return null;
    return rooms.value.get(activeRoomId.value) ?? null;
  });

  const activeRoomLog = computed<RoomLogEntryPayload[]>(() => {
    if (!activeRoomId.value) return [];
    const list = logs.value.get(activeRoomId.value);
    if (!list) return [];
    return [...list].sort((a, b) => a.seq - b.seq);
  });

  function upsertRoom(room: RoomInfoPayload) {
    const next = new Map(rooms.value);
    next.set(room.room_id, room);
    rooms.value = next;
  }

  /** LRU touch：把 roomId 移到 Map 尾部；超限淘汰最久未访问的（不淘汰 active room）。 */
  function touchLog(roomId: string) {
    const map = logs.value;
    const list = map.get(roomId);
    if (list !== undefined) {
      map.delete(roomId);
      map.set(roomId, list);
    }
    while (map.size > MAX_CACHED_ROOM_LOGS) {
      let evicted = false;
      for (const key of map.keys()) {
        if (key === activeRoomId.value) continue;
        map.delete(key);
        evicted = true;
        break;
      }
      if (!evicted) break;
    }
  }

  function onRoomCreated(payload: RoomEventPayload) {
    upsertRoom(payload.room);
  }

  function onRoomUpdated(payload: RoomEventPayload) {
    upsertRoom(payload.room);
  }

  function onRoomDeleted(payload: RoomDeletedEventPayload) {
    const next = new Map(rooms.value);
    next.delete(payload.room_id);
    rooms.value = next;
    logs.value.delete(payload.room_id);
    if (activeRoomId.value === payload.room_id) {
      activeRoomId.value = null;
    }
  }

  function onRoomMemberJoined(payload: RoomMemberEventPayload) {
    upsertRoom(payload.room);
  }

  function onRoomMemberLeft(payload: RoomMemberEventPayload) {
    upsertRoom(payload.room);
  }

  function onRoomLogAppended(payload: RoomLogEventPayload) {
    const entry = payload.entry;
    if (!entry) return;
    const map = logs.value;
    let list = map.get(entry.room_id);
    if (!list) {
      list = [];
      map.set(entry.room_id, list);
    }
    // dedup by entry.id（重连 replay）
    if (list.some((e) => e.id === entry.id)) return;
    // 按 seq 有序插入：正常路径 append 到尾部，乱序/补漏插到对应位置
    let idx = list.length;
    while (idx > 0 && list[idx - 1].seq > entry.seq) idx -= 1;
    list.splice(idx, 0, entry);
    touchLog(entry.room_id);
  }

  function setRoomsFromList(list: RoomInfoPayload[]) {
    rooms.value = new Map(list.map((r) => [r.room_id, r]));
  }

  /** 替换式灌入（供 room_get_log 结果用）。 */
  function setRoomLog(roomId: string, entries: RoomLogEntryPayload[]) {
    logs.value.set(roomId, [...entries].sort((a, b) => a.seq - b.seq));
    touchLog(roomId);
  }

  function setActiveRoom(roomId: string | null) {
    activeRoomId.value = roomId;
    if (roomId !== null && logs.value.has(roomId)) {
      touchLog(roomId);
    }
  }

  function clearAll() {
    rooms.value = new Map();
    logs.value = new Map();
    activeRoomId.value = null;
  }

  return {
    rooms,
    logs,
    activeRoomId,
    roomList,
    activeRoom,
    activeRoomLog,
    onRoomCreated,
    onRoomUpdated,
    onRoomDeleted,
    onRoomMemberJoined,
    onRoomMemberLeft,
    onRoomLogAppended,
    setRoomsFromList,
    setRoomLog,
    setActiveRoom,
    clearAll,
  };
});
