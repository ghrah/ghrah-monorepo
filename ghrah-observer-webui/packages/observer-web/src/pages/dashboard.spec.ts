// @vitest-environment happy-dom

import {
  useAgentsStore,
  useBranchesStore,
  useProjectsStore,
  useRoomsStore,
  useSessionsStore,
} from "@ghrah/observer-core";
import type { ProjectInfoPayload, RoomInfoPayload } from "@ghrah/protocol";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

const switchProjectMock = vi.fn();
const switchRoomMock = vi.fn();
const selectAgentMock = vi.fn();
vi.mock("@/composables/useObserver", () => ({
  useObserver: () => ({
    switchProject: switchProjectMock,
    switchRoom: switchRoomMock,
    selectAgent: selectAgentMock,
  }),
}));
vi.mock("@/components/action-chain/action-chain-panel.vue", () => ({
  default: { template: "<div>chain panel</div>" },
}));
vi.mock("@/components/agent-action-menu.vue", () => ({
  default: { template: "<div />" },
}));
vi.mock("@/components/chat/chat-panel.vue", () => ({
  default: { template: "<div>chat panel</div>" },
}));
vi.mock("@/components/hitl/hitl-inbox.vue", () => ({
  default: { template: "<div />" },
}));
vi.mock("@/components/instance-profile-control.vue", () => ({
  default: { emits: ["openSettings"], template: "<div />" },
}));
vi.mock("@/components/nav/project-selector.vue", () => ({
  default: { template: "<div />" },
}));
vi.mock("@/components/room-admin-panel.vue", () => ({
  default: { emits: ["roomInvalidated"], template: "<div />" },
}));
vi.mock("@/components/project-changes-panel.vue", () => ({
  default: { template: "<div>changes panel</div>" },
}));
vi.mock("@/components/project-settings-panel.vue", () => ({
  default: { template: "<div>settings panel</div>" },
}));
vi.mock("@/components/agents-overview-panel.vue", () => ({
  default: { emits: ["openAgent"], template: "<div>agents panel</div>" },
}));

import Dashboard from "./dashboard.vue";

const RoomSelectorStub = {
  emits: ["openRoom"],
  template: `<div>
    <button id="open-p1-room" @click="$emit('openRoom', { room_id: 'r1', project_id: 'p1', name: 'Room One' })">p1 room</button>
    <button id="open-p2-room" @click="$emit('openRoom', { room_id: 'r2', project_id: 'p2', name: 'Room Two' })">p2 room</button>
  </div>`,
};
const ProjectFixedNavStub = {
  emits: ["openProjectView"],
  template: `<div>
    <button id="open-changes" @click="$emit('openProjectView', { kind: 'changes', projectId: 'p1' })">changes</button>
  </div>`,
};
const AgentListStub = {
  emits: ["openAgent", "openSettings"],
  template: `<button id="open-chain" @click="$emit('openAgent', {
    projectId: 'p2', agentId: 'a2', agentName: 'Coder', sessionId: 's2', branchId: 'b2'
  })">agent</button>`,
};

function project(id: string, name: string): ProjectInfoPayload {
  return {
    project_id: id,
    name,
    status: "active",
    archived_at: null,
    agents: [],
  } as never;
}

function room(id: string, projectId: string, name: string): RoomInfoPayload {
  return {
    room_id: id,
    project_id: projectId,
    name,
    status: "active",
    members: [],
    seq_watermark: 0,
    version: 1,
    created_at: "",
    updated_at: "",
    archived_at: null,
  };
}

function mountDashboard() {
  return mount(Dashboard, {
    global: {
      stubs: {
        ProjectSelector: true,
        RoomSelector: RoomSelectorStub,
        ProjectFixedNav: ProjectFixedNavStub,
        InstanceProfileControl: true,
        HitlInbox: true,
        RoomAdminPanel: true,
        AgentList: AgentListStub,
        ChatPanel: { template: "<div>chat panel</div>" },
        ActionChainPanel: { template: "<div>chain panel</div>" },
        ProjectChangesPanel: { template: "<div>changes panel</div>" },
        ProjectSettingsPanel: { template: "<div>settings panel</div>" },
        AgentsOverviewPanel: { template: "<div>agents panel</div>" },
      },
    },
  });
}

describe("Dashboard workspace tabs", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    switchProjectMock.mockReset();
    switchRoomMock.mockReset();
    selectAgentMock.mockReset();

    const projects = useProjectsStore();
    projects.setProjectsFromList([project("p1", "Project One"), project("p2", "Project Two")]);
    projects.setActiveProject("p1");
    useRoomsStore().replaceProjectRooms("p1", [room("r1", "p1", "Room One")], "active");
    useRoomsStore().replaceProjectRooms("p2", [room("r2", "p2", "Room Two")], "active");

    const agent = { projectId: "p2", agentId: "a2", agentName: "Coder" };
    useAgentsStore().replaceProjectAgents(
      "p2",
      [{ project_id: "p2", agent_id: "a2", name: "Coder", runtime_state: "running" }],
      { status: "active", archived_at: null },
    );
    useSessionsStore().replaceAgentSessions(
      agent,
      [{ session_id: "s2", agent_name: "Coder", state: "active" } as never],
      "s2",
    );
    useBranchesStore().replaceSessionBranches(
      { ...agent, sessionId: "s2" },
      [{ branch_id: "b2", session_id: "s2", name: "main" } as never],
      "b2",
    );

    switchProjectMock.mockImplementation(async (projectId: string) => {
      useProjectsStore().setActiveProject(projectId);
      return { success: true };
    });
    switchRoomMock.mockImplementation(async (roomId: string | null) => {
      useRoomsStore().setActiveRoom(roomId);
      return { success: true };
    });
    selectAgentMock.mockImplementation((target: never) => useAgentsStore().selectAgent(target));
  });

  it("switches project before opening a room from another project", async () => {
    const order: string[] = [];
    switchProjectMock.mockImplementation(async (projectId: string) => {
      order.push(`project:${projectId}`);
      useProjectsStore().setActiveProject(projectId);
      return { success: true };
    });
    switchRoomMock.mockImplementation(async (roomId: string) => {
      order.push(`room:${roomId}`);
      useRoomsStore().setActiveRoom(roomId);
      return { success: true };
    });
    const wrapper = mountDashboard();

    await wrapper.find("#open-p2-room").trigger("click");
    await nextTick();

    expect(order).toEqual(["project:p2", "room:r2"]);
    expect(useProjectsStore().activeProjectId).toBe("p2");
    expect(useRoomsStore().activeRoomId).toBe("r2");
    expect(wrapper.find(".workspace-tab .tab-label").text()).toBe("Room Two");
  });

  it("derives room and project labels from stores instead of tab snapshots", async () => {
    const wrapper = mountDashboard();
    await wrapper.find("#open-p1-room").trigger("click");
    await wrapper.find("#open-changes").trigger("click");

    useRoomsStore().onRoomUpdated({ room: room("r1", "p1", "Renamed Room") });
    useProjectsStore().onProjectEvent({ project: project("p1", "Renamed Project") });
    await nextTick();

    const labels = wrapper.findAll(".tab-label").map((node) => node.text());
    expect(labels).toContain("Renamed Room");
    expect(labels).toContain("Renamed Project · Changes");
  });

  it("restores a complete chain target after switching projects", async () => {
    const order: string[] = [];
    switchProjectMock.mockImplementation(async (projectId: string) => {
      order.push(`project:${projectId}`);
      useProjectsStore().setActiveProject(projectId);
      return { success: true };
    });
    selectAgentMock.mockImplementation((target: never) => {
      order.push("agent:a2");
      useAgentsStore().selectAgent(target);
    });
    const wrapper = mountDashboard();

    await wrapper.find("#open-chain").trigger("click");
    await nextTick();

    expect(order).toEqual(["project:p2", "agent:a2"]);
    expect(useAgentsStore().selectedAgentTarget?.agentId).toBe("a2");
    expect(
      useSessionsStore().activeSessionId({
        projectId: "p2",
        agentId: "a2",
        agentName: "Coder",
      }),
    ).toBe("s2");
    expect(wrapper.find(".workspace-tab .tab-label").text()).toBe("Coder");
  });

  it("closes room and chain tabs when remote state invalidates their targets", async () => {
    const wrapper = mountDashboard();
    await wrapper.find("#open-p1-room").trigger("click");
    await wrapper.find("#open-chain").trigger("click");
    expect(wrapper.findAll(".workspace-tab")).toHaveLength(2);

    useRoomsStore().onRoomArchived({
      room: { ...room("r1", "p1", "Room One"), status: "archived" },
    });
    useSessionsStore().removeSession({
      project_id: "p2",
      agent_id: "a2",
      agent_name: "Coder",
      cluster_id: "c2",
      session_id: "s2",
    });
    await nextTick();
    await nextTick();

    expect(wrapper.findAll(".workspace-tab")).toHaveLength(0);
  });
});
