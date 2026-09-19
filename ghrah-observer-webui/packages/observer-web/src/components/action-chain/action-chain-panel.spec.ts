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

function chainNodes(name: string, overrides: Partial<ActionNode>[]): ActionNode[] {
  return overrides.map((item) =>
    node({ ...item, session_id: `${name}-session`, created_on_branch_id: `${name}-branch` }),
  );
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

function setActiveChain(name: string, overrides: Partial<ActionNode>[]) {
  const nodes = chainNodes(name, overrides);
  const agent = target(name);
  const sessionId = `${name}-session`;
  const session: SessionTarget = { ...agent, sessionId };
  // head = 不作为任何节点 parent 的节点中的最后一个（测试夹具为单链/单 Head）
  const parentIds = new Set(nodes.map((item) => item.parent_id).filter(Boolean));
  const heads = nodes.filter((item) => item.id && !parentIds.has(item.id));
  const head = heads.at(-1)?.id ?? nodes.at(-1)?.id ?? "root";
  useSessionsStore().replaceAgentSessions(agent, [
    SessionInfoPayloadSchema.parse({
      session_id: sessionId,
      agent_name: name,
      root_node_id: nodes[0]?.id ?? "root",
      active_branch_id: `${name}-branch`,
    }),
  ]);
  useSessionsStore().setActiveSession(agent, sessionId);
  useBranchesStore().replaceSessionBranches(
    session,
    [
      BranchInfoPayloadSchema.parse({
        branch_id: `${name}-branch`,
        session_id: sessionId,
        name: "main",
        head_node_id: head,
      }),
    ],
    { explicitActiveBranchId: `${name}-branch` },
  );
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

  it("shows empty state when the target agent has no chain", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("No actions yet");
  });

  it("renders only the target agent's chain", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    agents.onAgentSpawned(spawn("beta"));
    setActiveChain("alpha", [{ id: "a1", parent_id: null, timestamp: "t1" }]);
    setActiveChain("beta", [{ id: "b1", parent_id: null, timestamp: "t1" }]);
    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("@alpha");
    expect(wrapper.text()).not.toContain("@beta");
    expect(wrapper.findAll(".tree-row")).toHaveLength(1);
  });

  it("switches tree when the agent prop changes", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    agents.onAgentSpawned(spawn("beta"));
    setActiveChain("alpha", [{ id: "a1", parent_id: null, timestamp: "t1" }]);
    setActiveChain("beta", [
      { id: "b1", parent_id: null, timestamp: "t1" },
      { id: "b2", parent_id: "b1", timestamp: "t2" },
    ]);
    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".tree-row")).toHaveLength(1);
    await wrapper.setProps({ agent: target("beta") });
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("@beta");
    expect(wrapper.text()).not.toContain("@alpha");
    expect(wrapper.findAll(".tree-row")).toHaveLength(2);
  });

  it("renders parent_id tree with indent guides", async () => {
    const agents = useAgentsStore();
    const sessions = useSessionsStore();
    const branches = useBranchesStore();
    const chainsStore = useActionChainsStore();
    agents.onAgentSpawned(spawn("alpha"));
    const agent = target("alpha");
    const session: SessionTarget = { ...agent, sessionId: "alpha-session" };
    sessions.replaceAgentSessions(agent, [
      SessionInfoPayloadSchema.parse({
        session_id: "alpha-session",
        agent_name: "alpha",
        root_node_id: "root",
        active_branch_id: "main",
      }),
    ]);
    sessions.setActiveSession(agent, "alpha-session");
    branches.replaceSessionBranches(
      session,
      [
        BranchInfoPayloadSchema.parse({
          branch_id: "main",
          session_id: "alpha-session",
          name: "main",
          head_node_id: "c1a",
        }),
        BranchInfoPayloadSchema.parse({
          branch_id: "retry",
          session_id: "alpha-session",
          name: "retry",
          head_node_id: "c2",
        }),
      ],
      { explicitActiveBranchId: "main" },
    );
    chainsStore.setChain({ ...session, branchId: "main" }, [
      node({
        id: "root",
        parent_id: null,
        timestamp: "t0",
        session_id: "alpha-session",
        created_on_branch_id: "main",
      }),
      node({
        id: "c1",
        parent_id: "root",
        timestamp: "t1",
        session_id: "alpha-session",
        created_on_branch_id: "main",
      }),
      node({
        id: "c1a",
        parent_id: "c1",
        timestamp: "t1a",
        session_id: "alpha-session",
        created_on_branch_id: "main",
      }),
    ]);
    chainsStore.setChain({ ...session, branchId: "retry" }, [
      node({
        id: "c2",
        parent_id: "root",
        timestamp: "t2",
        session_id: "alpha-session",
        created_on_branch_id: "retry",
      }),
    ]);

    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    const branchSelect = wrapper.get<HTMLSelectElement>(".chain-branch-select");
    await branchSelect.setValue("__all__");
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
      {
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
      },
    ]);
    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
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

  it("plain select only views; explicit buttons activate runtime", async () => {
    const agents = useAgentsStore();
    const sessions = useSessionsStore();
    const branches = useBranchesStore();
    agents.onAgentSpawned(spawn("alpha"));

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

    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    const sessionSelect = wrapper.get<HTMLSelectElement>(".chain-session-select");
    // viewed 初始回退 runtime active Session
    expect(sessionSelect.element.value).toBe("alpha-session-2");

    // 普通切换 Session = 纯查看，不发 activate 命令
    await sessionSelect.setValue("alpha-session");
    await wrapper.vm.$nextTick();
    expect(activateSession).not.toHaveBeenCalled();
    expect(sessions.viewedSessionId(agent)).toBe("alpha-session");
    // runtime active 不被查看选择抢占
    expect(sessions.activeSessionId(agent)).toBe("alpha-session-2");

    // 显式激活按钮出现并发命令
    const activateBtn = wrapper.get("button.chain-activate-session");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await activateBtn.trigger("click");
    expect(activateSession).toHaveBeenCalledWith({ ...agent, sessionId: "alpha-session" });

    // Branch select 同理：普通切换只查看
    const branchSelect = wrapper.get<HTMLSelectElement>(".chain-branch-select");
    await branchSelect.setValue("alpha-branch-2");
    expect(activateBranch).not.toHaveBeenCalled();
  });

  it("activates branch explicitly from viewed branch", async () => {
    const agents = useAgentsStore();
    const sessions = useSessionsStore();
    const branches = useBranchesStore();
    agents.onAgentSpawned(spawn("alpha"));
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
      BranchInfoPayloadSchema.parse({
        branch_id: "alpha-branch-2",
        session_id: "alpha-session",
        name: "Branch 2",
        head_node_id: "root",
      }),
    ]);

    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    const branchSelect = wrapper.get<HTMLSelectElement>(".chain-branch-select");
    await branchSelect.setValue("alpha-branch-2");
    expect(activateBranch).not.toHaveBeenCalled();

    vi.spyOn(window, "confirm").mockReturnValue(true);
    const btn = wrapper.get("button.chain-activate-branch");
    await btn.trigger("click");
    expect(activateBranch).toHaveBeenCalledWith({
      ...agent,
      sessionId: "alpha-session",
      branchId: "alpha-branch-2",
    });
  });

  it("creates a session; view follows the receipt without runtime activation", async () => {
    const agents = useAgentsStore();
    const sessions = useSessionsStore();
    agents.onAgentSpawned(spawn("alpha"));
    createSession.mockResolvedValue({
      success: true,
      data: { session_id: "alpha-session-2", agent_name: "alpha" },
    });
    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    await wrapper.get("button.chain-new-session").trigger("click");
    expect(createSession).toHaveBeenCalledWith(target("alpha"));
    // D6：新建只切展示，不隐式激活运行态
    expect(activateSession).not.toHaveBeenCalled();
    expect(sessions.viewedSessionId(target("alpha"))).toBe("alpha-session-2");
  });

  it("creates a branch; view follows the receipt, surfaces failures", async () => {
    const agents = useAgentsStore();
    const sessions = useSessionsStore();
    const branches = useBranchesStore();
    agents.onAgentSpawned(spawn("alpha"));
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
    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    await wrapper.get("button.chain-new-branch").trigger("click");
    expect(createBranch).toHaveBeenCalledWith(session, "Branch 2");
    // D6：新建 Branch 不隐式激活
    expect(activateBranch).not.toHaveBeenCalled();
    expect(branches.viewedBranchId(session)).toBe("alpha-branch-2");

    createBranch.mockResolvedValue({
      success: false,
      error: "fork node not found",
      error_detail: "fork node is not readable",
    });
    await wrapper.get("button.chain-new-branch").trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.get('[role="alert"]').text()).toContain("fork node is not readable");
  });

  it("renders all branches merged when viewing all-branches mode", async () => {
    const agents = useAgentsStore();
    const sessions = useSessionsStore();
    const branches = useBranchesStore();
    const chainsStore = useActionChainsStore();
    agents.onAgentSpawned(spawn("alpha"));
    const agent = target("alpha");
    const session: SessionTarget = { ...agent, sessionId: "alpha-session" };
    sessions.replaceAgentSessions(agent, [
      SessionInfoPayloadSchema.parse({
        session_id: "alpha-session",
        agent_name: "alpha",
        root_node_id: "root",
        active_branch_id: "main",
      }),
    ]);
    sessions.setActiveSession(agent, "alpha-session");
    branches.replaceSessionBranches(session, [
      BranchInfoPayloadSchema.parse({
        branch_id: "main",
        session_id: "alpha-session",
        name: "main",
        head_node_id: "n2",
      }),
      BranchInfoPayloadSchema.parse({
        branch_id: "retry",
        session_id: "alpha-session",
        name: "retry-1",
        head_node_id: "r2",
      }),
    ]);
    // 共享祖先 root；main: root→n1→n2；retry: root→r1→r2
    chainsStore.setChain({ ...session, branchId: "main" }, [
      node({
        id: "root",
        parent_id: null,
        timestamp: "t0",
        iteration: 0,
        session_id: "alpha-session",
        created_on_branch_id: "main",
      }),
      node({
        id: "n1",
        parent_id: "root",
        timestamp: "t1",
        iteration: 1,
        session_id: "alpha-session",
        created_on_branch_id: "main",
      }),
      node({
        id: "n2",
        parent_id: "n1",
        timestamp: "t2",
        iteration: 2,
        session_id: "alpha-session",
        created_on_branch_id: "main",
      }),
    ]);
    chainsStore.setChain({ ...session, branchId: "retry" }, [
      node({
        id: "r1",
        parent_id: "root",
        timestamp: "t3",
        iteration: 3,
        session_id: "alpha-session",
        created_on_branch_id: "retry",
      }),
      node({
        id: "r2",
        parent_id: "r1",
        timestamp: "t4",
        iteration: 4,
        session_id: "alpha-session",
        created_on_branch_id: "retry",
      }),
    ]);
    // root 在 main 桶；retry 桶缺 root，回溯到 root 停止（缺父保留已知部分）

    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    const branchSelect = wrapper.get<HTMLSelectElement>(".chain-branch-select");
    await branchSelect.setValue("__all__");
    await wrapper.vm.$nextTick();
    // 全部 Branch 模式：main(n2)+retry(r2) 两 Head 回溯合并去重（root/n1 共享）= 5
    expect(wrapper.findAll(".tree-row")).toHaveLength(5);
  });
});
