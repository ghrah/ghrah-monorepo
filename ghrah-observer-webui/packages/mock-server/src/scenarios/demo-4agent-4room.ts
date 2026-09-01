import { CommandType } from "@ghrah/protocol";
import type { MockState } from "../state.js";
import type { Scenario } from "./types.js";

/**
 * MVP 演示场景：4 agent（architect/frontend/backend/tester）+ 1 project（demo-project）
 * + 4 room（architecture/frontend/backend/testing）；architect 在 3 个 room。
 * 时间线：spawn 4 agent → join rooms → 若干轮 room_send 对话 → 触发一次 hitl_request。
 *
 * 注：setup/timeline 均走 state.handleCommand 命令路径（与外部命令同一路径），
 * 需要 room_id 等生成值时从 state 读回。
 */

const PROJECT_NAME = "demo-project";
const ROOM_NAMES = ["architecture", "frontend", "backend", "testing"] as const;

function projectId(state: MockState): string {
  const project = [...state.projects.values()].find((p) => p.name === PROJECT_NAME);
  if (!project) throw new Error(`demo scenario: project not found: ${PROJECT_NAME}`);
  return project.project_id;
}

function roomId(state: MockState, name: string): string {
  const room = [...state.rooms.values()].find((r) => r.name === name);
  if (!room) throw new Error(`demo scenario: room not found: ${name}`);
  return room.room_id;
}

export const demoScenario: Scenario = {
  name: "demo",
  description: "MVP 演示：4 agent + 1 project + 4 room，architect 跨 3 room，含一次 HITL",

  setup(state) {
    const ctx = {
      state,
      apply: (t: CommandType, p: Record<string, unknown>) => state.handleCommand(t, p),
    };
    ctx.apply(CommandType.PROJECT_CREATE, { name: PROJECT_NAME });
    for (const name of ROOM_NAMES) {
      ctx.apply(CommandType.ROOM_CREATE, { project_id: projectId(state), name });
    }
  },

  timeline: [
    // ── spawn 4 agent ──
    [
      500,
      ({ apply }) =>
        apply(CommandType.SPAWN_AGENT, {
          config: {
            name: "architect",
            description: "架构师",
            system_prompt: "You are the architect.",
          },
        }),
    ],
    [
      900,
      ({ apply }) =>
        apply(CommandType.SPAWN_AGENT, { config: { name: "frontend", description: "前端工程师" } }),
    ],
    [
      1300,
      ({ apply }) =>
        apply(CommandType.SPAWN_AGENT, { config: { name: "backend", description: "后端工程师" } }),
    ],
    [
      1700,
      ({ apply }) =>
        apply(CommandType.SPAWN_AGENT, { config: { name: "tester", description: "测试工程师" } }),
    ],

    // ── join rooms（architect 在 architecture/frontend/backend 3 个 room） ──
    [
      2200,
      ({ state, apply }) => {
        const joins: Array<[string, string]> = [
          ["architecture", "architect"],
          ["frontend", "architect"],
          ["backend", "architect"],
          ["frontend", "frontend"],
          ["backend", "backend"],
          ["testing", "tester"],
        ];
        for (const [room, agent] of joins) {
          apply(CommandType.ROOM_JOIN, {
            room_id: roomId(state, room),
            subject: agent,
            subject_type: "agent",
          });
        }
      },
    ],

    // ── 对话轮次 ──
    [
      3000,
      ({ state, apply }) =>
        apply(CommandType.ROOM_SEND, {
          room_id: roomId(state, "architecture"),
          author: "human:user",
          author_type: "human",
          data: {
            message: "目标：实现一个支持多 room 协作的最小产品。请 architect 给出总体设计。",
          },
        }),
    ],
    [
      4200,
      ({ state, apply }) =>
        apply(CommandType.ROOM_SEND, {
          room_id: roomId(state, "architecture"),
          author: "architect",
          author_type: "agent",
          data: {
            message:
              "总体设计：前端 observer-web + 协议层 @ghrah/protocol + 后端 Subject。Room 为协作实体。",
          },
        }),
    ],
    [
      5400,
      ({ state, apply }) =>
        apply(CommandType.ROOM_SEND, {
          room_id: roomId(state, "frontend"),
          author: "architect",
          author_type: "agent",
          data: {
            message: "@frontend 前端按 Project → Room 三级导航拆分，chat 数据源走 RoomLog。",
            targets: ["frontend"],
          },
        }),
    ],
    [
      6600,
      ({ state, apply }) =>
        apply(CommandType.ROOM_SEND, {
          room_id: roomId(state, "frontend"),
          author: "frontend",
          author_type: "agent",
          data: { message: "收到。chat 按 activeRoom 增量投影，成员面板支持多 room 标记。" },
        }),
    ],
    [
      7800,
      ({ state, apply }) =>
        apply(CommandType.ROOM_SEND, {
          room_id: roomId(state, "backend"),
          author: "architect",
          author_type: "agent",
          data: { message: "@backend RoomUnit 独立 Unit，seq 单点分配，乐观锁 version。" },
        }),
    ],
    [
      9000,
      ({ state, apply }) =>
        apply(CommandType.ROOM_SEND, {
          room_id: roomId(state, "backend"),
          author: "backend",
          author_type: "agent",
          data: {
            message: "明白。room_send 收敛到 append_log，分配 seq 并广播 ROOM_LOG_APPENDED。",
          },
        }),
    ],
    [
      10200,
      ({ state, apply }) =>
        apply(CommandType.ROOM_SEND, {
          room_id: roomId(state, "testing"),
          author: "tester",
          author_type: "agent",
          data: { message: "测试计划：协议层闭环 + 乐观锁冲突 + 重连 seq resume 不重复。" },
        }),
    ],
    [
      11400,
      ({ state, apply }) =>
        apply(CommandType.ROOM_SEND, {
          room_id: roomId(state, "architecture"),
          author: "architect",
          author_type: "agent",
          data: { message: "各模块对齐完成，准备进入联调。" },
        }),
    ],

    // ── HITL 单路径：backend 请求部署审批（30s 超时自动拒绝） ──
    [
      12600,
      ({ state }) => {
        state.triggerHitl(
          "backend",
          "deploy",
          { target: "staging", ref: "main" },
          { room: "backend" },
        );
      },
    ],
  ],
};
