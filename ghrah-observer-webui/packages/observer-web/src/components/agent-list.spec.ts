// @vitest-environment happy-dom

import { useAgentsStore, useProjectsStore, useRoomsStore } from "@ghrah/observer-core";
import type { AgentSpawnedPayload, RoomInfoPayload } from "@ghrah/protocol";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

// 隔离 AgentActionMenu（其 monaco-diff 依赖链在测试环境不可解析）
vi.mock("@/components/agent-action-menu.vue", () => ({
  default: { template: "<div />" },
}));

import AgentList from "./agent-list.vue";

function spawn(name: string): AgentSpawnedPayload {
  return {
    type: "agent_spawned",
    project_id: "p1",
    agent_id: `${name}-id`,
    cluster_id: "cluster",
    incarnation_id: "incarnation",
    recovery_mode: "fresh",
    name,
    config: { name, agent_id: `${name}-id` },
  } as unknown as AgentSpawnedPayload;
}

function room(id: string, name: string, members: string[] = []): RoomInfoPayload {
  return {
    room_id: id,
    project_id: "p1",
    name,
    status: "active",
    members: members.map((s) => ({
      subject: s,
      subject_type: "agent" as const,
      subject_name: s,
      joined_at: "",
    })),
    seq_watermark: 0,
    version: 1,
    created_at: "",
    updated_at: "",
    archived_at: null,
  };
}

function agentItem(wrapper: ReturnType<typeof mount>, name: string) {
  return wrapper.findAll("li").find((li) => li.text().includes(name));
}

function mountAgentList() {
  return mount(AgentList, {
    global: { stubs: { AgentActionMenu: true } },
  });
}

describe("AgentList", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    useProjectsStore().setActiveProject("p1");
  });

  it("shows empty state when no agents", () => {
    const wrapper = mountAgentList();
    expect(wrapper.text()).toContain("No active agents");
  });

  it("opens Agent settings from Spawn", async () => {
    const wrapper = mountAgentList();
    await wrapper.get(".btn-primary").trigger("click");
    expect(wrapper.emitted("openSettings")?.[0]).toEqual(["agents"]);
  });

  it("click selects agent (drives per-agent ActionChain)", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("architect"));
    agents.onAgentSpawned(spawn("frontend"));
    const wrapper = mountAgentList();
    await wrapper.vm.$nextTick();
    await agentItem(wrapper, "frontend")!.trigger("click");
    expect(agents.selectedAgentName).toBe("frontend");
  });

  it("shows room membership badges per agent (multi-room → multiple badges)", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("architect"));
    agents.onAgentSpawned(spawn("tester"));
    const rooms = useRoomsStore();
    // architect 在 3 个 room；tester 不在任何 room
    rooms.replaceProjectRooms(
      "p1",
      [
        room("r1", "arch", ["architect"]),
        room("r2", "frontend", ["architect"]),
        room("r3", "backend", ["architect"]),
      ],
      "active",
    );
    const wrapper = mountAgentList();
    await wrapper.vm.$nextTick();
    const architectBadges = agentItem(wrapper, "architect")!.findAll(".agent-room-badge");
    expect(architectBadges).toHaveLength(3);
    expect(architectBadges.map((b) => b.attributes("title")).sort()).toEqual([
      "arch",
      "backend",
      "frontend",
    ]);
    expect(agentItem(wrapper, "tester")!.findAll(".agent-room-badge")).toHaveLength(0);
  });

  it("matches room badges by stable agent ID", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned({
      ...spawn("shuoxi"),
      agent_id: "stable-shuoxi",
    } as AgentSpawnedPayload);
    const rooms = useRoomsStore();
    const stableRoom = room("r1", "chat");
    stableRoom.members = [
      {
        subject: "stable-shuoxi",
        subject_type: "agent",
        subject_name: "shuoxi",
        joined_at: "",
      },
    ];
    rooms.replaceProjectRooms("p1", [stableRoom], "active");

    const wrapper = mountAgentList();
    await wrapper.vm.$nextTick();
    expect(agentItem(wrapper, "shuoxi")!.findAll(".agent-room-badge")).toHaveLength(1);
  });
});
