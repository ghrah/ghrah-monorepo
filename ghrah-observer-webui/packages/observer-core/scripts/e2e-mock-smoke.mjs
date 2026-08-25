#!/usr/bin/env node
/**
 * 端到端 Mock 冒烟（计划任务 8.2）：真实 ObserverClient + connectStores 连接
 * @ghrah/mock-server（demo 场景，4 agent + 4 room），走完整 WS 协议断言全链路。
 *
 * 用法：
 *   pnpm --filter @ghrah/protocol build && pnpm --filter @ghrah/observer-core build \
 *     && pnpm --filter @ghrah/mock-server build
 *   node packages/observer-core/scripts/e2e-mock-smoke.mjs
 */
import { setTimeout as delay } from "node:timers/promises";
import { createPinia, setActivePinia } from "pinia";

import {
  MockServer,
  MockState,
  demoScenario,
  runScenario,
} from "../../mock-server/dist/index.js";
import {
  ObserverClient,
  connectStores,
  useActionChainsStore,
  useAgentsStore,
  useChatStore,
  useHitlStore,
  useProjectsStore,
  useRoomsStore,
} from "../dist/index.js";

let failures = 0;
function check(label, cond) {
  if (cond) {
    console.log(`  PASS ${label}`);
  } else {
    failures += 1;
    console.error(`  FAIL ${label}`);
  }
}

async function waitFor(label, cond, timeoutMs = 20_000, intervalMs = 100) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (cond()) return true;
    await delay(intervalMs);
  }
  console.error(`  TIMEOUT waiting: ${label}`);
  return false;
}

async function main() {
  // ── 1. 起 mock server（随机端口）+ demo 场景回放 ──
  const state = new MockState({ simulateChains: true, hitlTimeoutMs: 30_000 });
  const server = new MockServer({ port: 0, state, logger: () => {} });
  await server.start();
  const cancelScenario = runScenario(demoScenario, {
    state,
    apply: (type, payload) => state.handleCommand(type, payload),
  });
  console.log(`mock server on ws://localhost:${server.port}/ws (scenario: demo)`);

  // ── 2. 真实 ObserverClient + connectStores ──
  setActivePinia(createPinia());
  const projects = useProjectsStore();
  const rooms = useRoomsStore();
  const agents = useAgentsStore();
  const chains = useActionChainsStore();
  const hitl = useHitlStore();
  const chat = useChatStore();

  const client = new ObserverClient(`ws://localhost:${server.port}/ws`);
  const unbind = connectStores(client);
  await client.connect();
  check("client connected", client.connected);

  // ── 3. 初始同步：projects/rooms/agents ──
  const synced =
    (await waitFor("project synced", () => projects.projectList.length >= 1)) &&
    (await waitFor("4 rooms synced", () => rooms.roomList.length >= 4)) &&
    (await waitFor("4 agents spawned", () => agents.agents.size >= 4));
  check("initial sync (project + 4 rooms + 4 agents)", synced);

  const roomByName = (name) => rooms.roomList.find((r) => r.name === name);
  check(
    "4 demo rooms by name",
    ["architecture", "frontend", "backend", "testing"].every((n) => roomByName(n)),
  );

  // ── 4. 成员多 room：architect 在 3 个 room（join 在场景 2.2s 处，等事件落地）──
  const architectRooms = () =>
    rooms.roomList.filter((r) =>
      (r.members ?? []).some((m) => m.subject === "architect" && m.subject_type === "agent"),
    );
  const joinedOk = await waitFor("architect joins 3 rooms", () => architectRooms().length === 3);
  check("architect member of 3 rooms", joinedOk);

  // ── 5. room chat：历史拉取 + room_send → ROOM_LOG_APPENDED 闭环 + pending 确认 ──
  const arch = roomByName("architecture");
  rooms.setActiveRoom(arch.room_id);
  await waitFor("scenario kickoff broadcast into architecture log", () =>
    (rooms.logs.get(arch.room_id) ?? []).some((e) => e.author_type === "human"),
  );
  await client.getRoomLog(arch.room_id);
  const historyOk = await waitFor(
    "getRoomLog hydrates store",
    () => (rooms.logs.get(arch.room_id) ?? []).length >= 1,
  );
  check("room history via get_room_log", historyOk);

  chat.addPendingEntry({ to: arch.room_id, content: "smoke hello", agentName: "", roomId: arch.room_id });
  const sendRes = await client.roomSend(arch.room_id, { message: "smoke hello" });
  check("room_send COMMAND_RESULT success + entry echoed", sendRes.success && !!sendRes.data?.entry);
  const echoOk = await waitFor(
    "ROOM_LOG_APPENDED confirms pending entry",
    () =>
      !(chat.entries ?? []).some((e) => e.content === "smoke hello" && e.pending) &&
      (rooms.logs.get(arch.room_id) ?? []).some((e) => e.data?.message === "smoke hello"),
  );
  check("pending echo confirmed & entry in room log", echoOk);

  // ── 6. seq 单调 ──
  const seqs = (rooms.logs.get(arch.room_id) ?? []).map((e) => e.seq);
  check("room log seq strictly increasing", seqs.every((s, i) => i === 0 || s > seqs[i - 1]));

  // ── 6.5 定向发信（data.targets 约定）──
  const targetedRes = await client.roomSend(arch.room_id, {
    message: "targeted smoke",
    targets: ["architect"],
  });
  check(
    "targeted room_send success + data.targets echoed",
    targetedRes.success &&
      JSON.stringify(targetedRes.data?.entry?.data?.targets) === '["architect"]',
  );
  const badTarget = await client.roomSend(arch.room_id, {
    message: "to nobody",
    targets: ["ghost"],
  });
  check("invalid target rejected", !badTarget.success && /target not in room/.test(badTarget.error ?? ""));
  const scenarioTargeted = await waitFor(
    "scenario targeted message in frontend room",
    () =>
      (rooms.logs.get(roomByName("frontend")?.room_id) ?? []).some(
        (e) => Array.isArray(e.data?.targets) && e.data.targets.includes("frontend"),
      ),
  );
  check("scenario targeted entry visible in room log", scenarioTargeted);

  // ── 7. per-agent ActionChain ──
  const chainOk = await waitFor(
    "action_chain_updated for architect",
    () => chains.getChain("architect").length > 0,
    25_000,
  );
  check("per-agent chain received", chainOk);

  // ── 8. HITL 单路径：scenario 12.6s 处 backend 触发 deploy 审批 ──
  const hitlOk = await waitFor("hitl_request received", () => hitl.pendingRequests.length > 0, 25_000);
  check("HITL_REQUEST received", hitlOk);
  if (hitlOk) {
    const req = hitl.pendingRequests[0];
    await client.sendHitlResponse(req.promiseId, true);
    const resolved = await waitFor(
      "mock state hitl approved",
      () => state.pendingHitl.get(req.promiseId)?.status === "approved",
      5_000,
    );
    check("hitl_response approved by mock", resolved);
  }

  // ── 9. 重连 seq resume：断开后同 client 重连，回放不重复 ──
  const idsBefore = new Map();
  for (const [rid, list] of rooms.logs) idsBefore.set(rid, new Set(list.map((e) => e.id)));
  const seqIdBefore = client.lastSeqId;
  await client.disconnect();
  await client.connect();
  const resumed = await waitFor("reconnected", () => client.connected, 10_000);
  check("reconnect succeeded", resumed && client.lastSeqId >= seqIdBefore);
  let dupes = 0;
  let allIncreasing = true;
  for (const [rid, list] of rooms.logs) {
    const before = idsBefore.get(rid) ?? new Set();
    const seen = new Set();
    let prev = 0;
    for (const e of list) {
      if (seen.has(e.id)) dupes += 1;
      seen.add(e.id);
      if (e.seq <= prev) allIncreasing = false;
      prev = e.seq;
      before.delete(e.id);
    }
  }
  check("no duplicate room log entries after resume", dupes === 0);
  check("seq still strictly increasing after resume", allIncreasing);
  await waitFor("post-reconnect sync", () => rooms.roomList.length >= 4, 10_000);

  // ── teardown ──
  unbind();
  await client.disconnect();
  cancelScenario();
  await server.close();

  console.log(failures === 0 ? "\nSMOKE PASS" : `\nSMOKE FAIL (${failures} failures)`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
