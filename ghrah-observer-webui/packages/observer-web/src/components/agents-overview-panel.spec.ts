// @vitest-environment happy-dom

import {
  useAgentsStore,
  useBranchesStore,
  useProjectsStore,
  useRoomsStore,
  useSessionsStore,
} from "@ghrah/observer-core";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import AgentsOverviewPanel from "./agents-overview-panel.vue";

describe("AgentsOverviewPanel", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    useProjectsStore().setProjectsFromList([
      {
        project_id: "p1",
        name: "Project One",
        status: "active",
        archived_at: null,
        agents: [
          { name: "Coder", agent_id: "a1", cluster_id: "c1", runtime_status: "running" },
          { name: "Reviewer", agent_id: "a2", cluster_id: "c2", runtime_status: "stopped" },
        ],
      } as never,
      {
        project_id: "p2",
        name: "Project Two",
        status: "active",
        archived_at: null,
        agents: [{ name: "Foreign", agent_id: "a9" }],
      } as never,
    ]);
    useAgentsStore().replaceProjectAgents(
      "p1",
      [
        { project_id: "p1", agent_id: "a1", name: "Coder", runtime_state: "running" },
        { project_id: "p1", agent_id: "a2", name: "Reviewer", runtime_state: "stopped" },
      ],
      { status: "active", archived_at: null },
    );
    useRoomsStore().replaceProjectRooms(
      "p1",
      [
        {
          room_id: "r1",
          project_id: "p1",
          name: "Architecture",
          status: "active",
          members: [
            {
              subject: "a1",
              subject_type: "agent",
              subject_name: "Coder",
              joined_at: "",
            },
          ],
          seq_watermark: 0,
          version: 1,
          created_at: "",
          updated_at: "",
          archived_at: null,
        },
      ],
      "active",
    );
    const agent = { projectId: "p1", agentId: "a1", agentName: "Coder" };
    useSessionsStore().replaceAgentSessions(
      agent,
      [{ session_id: "s1", agent_name: "Coder", state: "active" } as never],
      "s1",
    );
    useBranchesStore().replaceSessionBranches(
      { ...agent, sessionId: "s1" },
      [{ branch_id: "b1", session_id: "s1", name: "main" } as never],
      "b1",
    );
  });

  it("renders only project agents with room and runtime context", () => {
    const wrapper = mount(AgentsOverviewPanel, { props: { projectId: "p1" } });

    expect(wrapper.text()).toContain("Coder");
    expect(wrapper.text()).toContain("Reviewer");
    expect(wrapper.text()).toContain("Architecture");
    expect(wrapper.text()).not.toContain("Foreign");
    expect(wrapper.findAll("li")[1].find("button").attributes("disabled")).toBeDefined();
  });

  it("selects Session and Branch explicitly before opening ActionChain", async () => {
    const wrapper = mount(AgentsOverviewPanel, { props: { projectId: "p1" } });
    await wrapper.findAll("li")[0].find("button").trigger("click");

    const target = {
      projectId: "p1",
      agentId: "a1",
      agentName: "Coder",
      sessionId: "s1",
      branchId: "b1",
    };
    expect(wrapper.emitted("openAgent")?.[0]).toEqual([target]);
    expect(useAgentsStore().selectedAgentTarget).toEqual({
      projectId: "p1",
      agentId: "a1",
      agentName: "Coder",
    });
    expect(useSessionsStore().activeSessionId(target)).toBe("s1");
    expect(useBranchesStore().activeBranchId(target)).toBe("b1");
  });
});
