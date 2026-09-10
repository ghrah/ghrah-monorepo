// @vitest-environment happy-dom

import {
  type AgentTarget,
  type ChainTarget,
  type SessionTarget,
  useActionChainsStore,
  useAgentsStore,
  useBranchesStore,
  useSessionsStore,
} from "@ghrah/observer-core";
import {
  type ActionNode,
  ActionNodeSchema,
  type AgentSpawnedPayload,
  BranchInfoPayloadSchema,
  SessionInfoPayloadSchema,
} from "@ghrah/protocol";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

const activateSession = vi.fn();
const activateBranch = vi.fn();
const createSession = vi.fn();
const createBranch = vi.fn();

vi.mock("@/composables/useObserver", () => ({
  useObserver: () => ({ activateSession, activateBranch, createSession, createBranch }),
}));

import ActionChainPanel from "./action-chain-panel.vue";

function node(overrides: Partial<ActionNode> = {}): ActionNode {
  return ActionNodeSchema.parse(overrides);
}

function target(name: string): AgentTarget {
  return { projectId: "p1", agentId: `${name}-id`, agentName: name };
}

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

function chainTarget(name: string): ChainTarget {
  return { ...target(name), sessionId: `${name}-session`, branchId: `${name}-branch` };
}

function setActiveChain(name: string, nodes: ActionNode[]) {
  const agent = target(name);
  const sessionId = `${name}-session`;
  useSessionsStore().setActiveSession(agent, sessionId);
  useBranchesStore().setActiveBranch({ ...agent, sessionId }, `${name}-branch`);
  useActionChainsStore().setChain(chainTarget(name), nodes);
}

describe("ActionChainPanel", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    for (const mock of [activateSession, activateBranch, createSession, createBranch]) {
      mock.mockReset();
      mock.mockResolvedValue({ success: true });
    }
  });

  it("prompts to select an agent when none selected", () => {
    const wrapper = mount(ActionChainPanel);
    expect(wrapper.text()).toContain("Select an agent");
  });

  it("shows empty state when selected agent has no chain", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    agents.selectAgent(target("alpha"));
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("No actions yet");
  });

  it("renders only the selected agent's chain", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    agents.onAgentSpawned(spawn("beta"));
    setActiveChain("alpha", [node({ id: "a1", parent_id: null, timestamp: "t1" })]);
    setActiveChain("beta", [node({ id: "b1", parent_id: null, timestamp: "t1" })]);
    agents.selectAgent(target("alpha"));
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("@alpha");
    expect(wrapper.text()).not.toContain("@beta");
    expect(wrapper.findAll(".tree-row")).toHaveLength(1);
  });

  it("switches tree when global selectedAgentName changes", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    agents.onAgentSpawned(spawn("beta"));
    setActiveChain("alpha", [node({ id: "a1", parent_id: null, timestamp: "t1" })]);
    setActiveChain("beta", [
      node({ id: "b1", parent_id: null, timestamp: "t1" }),
      node({ id: "b2", parent_id: "b1", timestamp: "t2" }),
    ]);
    agents.selectAgent(target("alpha"));
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".tree-row")).toHaveLength(1);
    agents.selectAgent(target("beta"));
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("@beta");
    expect(wrapper.text()).not.toContain("@alpha");
    expect(wrapper.findAll(".tree-row")).toHaveLength(2);
  });

  it("renders parent_id tree with indent guides", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    setActiveChain("alpha", [
      node({ id: "root", parent_id: null, timestamp: "t0" }),
      node({ id: "c1", parent_id: "root", timestamp: "t1" }),
      node({ id: "c2", parent_id: "root", timestamp: "t2" }),
      node({ id: "c1a", parent_id: "c1", timestamp: "t1a" }),
    ]);
    agents.selectAgent(target("alpha"));
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".tree-row")).toHaveLength(4);
    const allText = wrapper.text();
    expect(allText).toContain("└");
    expect(allText).toContain("├");
  });

  it("suppresses conversation text and send_message tool_call blocks", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    setActiveChain("alpha", [
      node({
        id: "n1",
        parent_id: null,
        timestamp: "t1",
        ability_names: ["conversation"],
        messages_delta: [
          {
            role: "ai",
            content_blocks: [
              { type: "text", text: "hello reply" },
              { type: "tool_call", id: "x", name: "send_message", arguments: {} },
              { type: "reasoning", reasoning: "think", incomplete: false },
            ],
            metadata: {},
          },
        ],
      }),
    ]);
    agents.selectAgent(target("alpha"));
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    const expandBtn = wrapper.find("button.text-gray-400, button.text-gray-600");
    expect(expandBtn.exists()).toBe(true);
    await expandBtn.trigger("click");
    await wrapper.vm.$nextTick();
    const expandedText = wrapper.text();
    expect(expandedText).toContain("think");
    expect(expandedText).not.toContain("hello reply");
    expect(expandedText).not.toContain("send_message");
  });

  it("exposes session and branch switchers driven by server activation", async () => {
    const agents = useAgentsStore();
    const sessions = useSessionsStore();
    const branches = useBranchesStore();
    agents.onAgentSpawned(spawn("alpha"));
    agents.selectAgent(target("alpha"));

    const agent = target("alpha");
    const active: SessionTarget = { ...agent, sessionId: "alpha-session-2" };
    sessions.replaceAgentSessions(agent, [
      SessionInfoPayloadSchema.parse({
        session_id: "alpha-session",
        agent_name: "alpha",
        root_node_id: "root",
        active_branch_id: "alpha-branch",
      }),
      SessionInfoPayloadSchema.parse({
        session_id: "alpha-session-2",
        agent_name: "alpha",
        root_node_id: "root-2",
        active_branch_id: "alpha-branch-2",
      }),
    ]);
    sessions.setActiveSession(agent, "alpha-session-2");
    branches.replaceSessionBranches(active, [
      BranchInfoPayloadSchema.parse({
        branch_id: "alpha-branch-2",
        session_id: "alpha-session-2",
        name: "Branch 2",
        head_node_id: "root-2",
      }),
    ]);

    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    const sessionSelect = wrapper.get<HTMLSelectElement>(".chain-session-select");
    expect(sessionSelect.findAll("option").length).toBe(3);
    expect(sessionSelect.element.value).toBe("alpha-session-2");
    const branchSelect = wrapper.get<HTMLSelectElement>(".chain-branch-select");
    expect(branchSelect.find("option:not([disabled])").text()).toBe("Branch 2");

    await sessionSelect.setValue("alpha-session");
    expect(activateSession).toHaveBeenCalledWith({ ...agent, sessionId: "alpha-session" });

    await branchSelect.setValue("alpha-branch-2");
    expect(activateBranch).toHaveBeenCalledWith({
      ...agent,
      sessionId: "alpha-session-2",
      branchId: "alpha-branch-2",
    });
  });

  it("creates a session and activates it from the receipt", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    agents.selectAgent(target("alpha"));
    createSession.mockResolvedValue({
      success: true,
      data: { session_id: "alpha-session-2", agent_name: "alpha" },
    });
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    await wrapper.get("button.chain-new-session").trigger("click");
    expect(createSession).toHaveBeenCalledWith(target("alpha"));
    expect(activateSession).toHaveBeenCalledWith({
      ...target("alpha"),
      sessionId: "alpha-session-2",
    });
  });

  it("creates a branch, activates it from the receipt, and surfaces failures", async () => {
    const agents = useAgentsStore();
    const sessions = useSessionsStore();
    const branches = useBranchesStore();
    agents.onAgentSpawned(spawn("alpha"));
    agents.selectAgent(target("alpha"));
    const agent = target("alpha");
    const session: SessionTarget = { ...agent, sessionId: "alpha-session" };
    sessions.replaceAgentSessions(agent, [
      SessionInfoPayloadSchema.parse({
        session_id: "alpha-session",
        agent_name: "alpha",
        root_node_id: "root",
        active_branch_id: "alpha-branch",
      }),
    ]);
    sessions.setActiveSession(agent, "alpha-session");
    branches.replaceSessionBranches(session, [
      BranchInfoPayloadSchema.parse({
        branch_id: "alpha-branch",
        session_id: "alpha-session",
        name: "Branch 1",
        head_node_id: "root",
      }),
    ]);

    createBranch.mockResolvedValue({ success: true, data: { branch_id: "alpha-branch-2" } });
    const wrapper = mount(ActionChainPanel);
    await wrapper.vm.$nextTick();
    await wrapper.get("button.chain-new-branch").trigger("click");
    expect(createBranch).toHaveBeenCalledWith(session, "Branch 2");
    expect(activateBranch).toHaveBeenCalledWith({
      ...agent,
      sessionId: "alpha-session",
      branchId: "alpha-branch-2",
    });

    createBranch.mockResolvedValue({
      success: false,
      error: "fork node not found",
      error_detail: "fork node is not readable",
    });
    await wrapper.get("button.chain-new-branch").trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.get('[role="alert"]').text()).toContain("fork node is not readable");
  });
});
