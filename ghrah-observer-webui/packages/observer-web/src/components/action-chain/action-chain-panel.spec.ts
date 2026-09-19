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
const archiveSession = vi.fn();
const deleteSession = vi.fn();
const archiveBranch = vi.fn();
const deleteBranch = vi.fn();

vi.mock("@/composables/useObserver", () => ({
  useObserver: () => ({
    activateSession,
    activateBranch,
    createSession,
    createBranch,
    archiveSession,
    deleteSession,
    archiveBranch,
    deleteBranch,
  }),
}));

import ActionChainPanel from "./action-chain-panel.vue";

/** 从画布节点 DOM 提取 meta 行文本（节点去重断言用）。 */
function textOfMeta(
  nodeWrapper: ReturnType<import("@vue/test-utils").VueWrapper["findAll"]>[number],
): string {
  const meta = nodeWrapper.find(".ac-node-meta");
  return meta.exists() ? meta.text() : nodeWrapper.text();
}

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
    for (const mock of [
      activateSession,
      activateBranch,
      createSession,
      createBranch,
      archiveSession,
      deleteSession,
      archiveBranch,
      deleteBranch,
    ]) {
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
    expect(wrapper.findAll(".ac-node")).toHaveLength(1);
  });

  it("switches canvas when the agent prop changes", async () => {
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
    expect(wrapper.findAll(".ac-node")).toHaveLength(1);
    await wrapper.setProps({ agent: target("beta") });
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("@beta");
    expect(wrapper.text()).not.toContain("@alpha");
    expect(wrapper.findAll(".ac-node")).toHaveLength(2);
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
    expect(wrapper.findAll(".ac-node")).toHaveLength(4);
    // 单 Session 泳道布局：main(3 节点) 泳道 0 + retry(1 节点) 泳道 1 → 1 条泳道分隔线
    expect(wrapper.findAll(".ac-lane-guide")).toHaveLength(1);
  });

  it("classifies conversation nodes as converse on the canvas", async () => {
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
    expect(wrapper.findAll(".ac-node--converse")).toHaveLength(1);
    // 详情区（尽力渲染）后置阶段 3：卡片摘要不含消息内容
    expect(wrapper.text()).not.toContain("hello reply");
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
    expect(wrapper.findAll(".ac-node")).toHaveLength(5);
    // 合并布局去重：共享祖先 root 只渲染一次
    const summaryTexts = wrapper.findAll(".ac-node").map((n) => textOfMeta(n));
    const unique = new Set(summaryTexts);
    expect(unique.size).toBe(summaryTexts.length);
  });

  it("selects and clears a node via canvas interactions", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    setActiveChain("alpha", [
      { id: "a1", parent_id: null, timestamp: "t1" },
      { id: "a2", parent_id: "a1", timestamp: "t2" },
    ]);
    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    // 横向滚动出口条件：画布视口为唯一滚动容器，AgentName 头与图例在滚动区之外
    const viewport = wrapper.find(".ac-canvas-viewport");
    expect(viewport.exists()).toBe(true);
    const header = wrapper.find(".chain-header, .chain-canvas-scroll");
    expect(header.exists()).toBe(false);
    // AgentName 头部不得在滚动视口内
    const headerText = wrapper.findAll("div").filter((d) => d.text() === "@alpha");
    expect(headerText.length).toBeGreaterThan(0);
    expect(headerText[0].element.parentElement?.closest(".ac-canvas-viewport")).toBeNull();
    const nodes = wrapper.findAll(".ac-node");
    await nodes[1].trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".ac-node.selected")).toHaveLength(1);
    await wrapper.find(".ac-canvas-viewport").trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".ac-node.selected")).toHaveLength(0);
  });

  // ── 详情区组合（阶段 3 S2 增补） ──

  it("shows node detail when a canvas node is selected", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    setActiveChain("alpha", [
      {
        id: "a1",
        parent_id: null,
        timestamp: "t1",
        ability_names: ["write_file"],
        action_results: [
          {
            ability_name: "write_file",
            action_result: { outcome: "success", data: { file_path: "src/foo.py" } },
          },
        ],
      },
      { id: "a2", parent_id: "a1", timestamp: "t2" },
    ]);
    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    // 未选中时占位提示
    expect(wrapper.find(".ac-detail--empty").exists()).toBe(true);

    await wrapper.findAll(".ac-node")[0].trigger("click");
    await wrapper.vm.$nextTick();
    const detail = wrapper.find(".ac-detail");
    expect(detail.exists()).toBe(true);
    expect(wrapper.find(".ac-detail--empty").exists()).toBe(false);
    // write_file 节点渲染出 file_path 表格
    expect(detail.text()).toContain("src/foo.py");
    expect(wrapper.findAll(".ac-node.selected")).toHaveLength(1);

    // 再次点击背景清空选中与详情
    await wrapper.find(".ac-canvas-viewport").trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".ac-detail--empty").exists()).toBe(true);
  });

  it("clears detail when the viewed session switches", async () => {
    const agents = useAgentsStore();
    const sessions = useSessionsStore();
    agents.onAgentSpawned(spawn("alpha"));
    const agent = target("alpha");
    // setActiveChain 会重置 agent 的 session 列表，先建第一条链再补第二个 Session
    setActiveChain("alpha", [{ id: "a1", parent_id: null, timestamp: "t1" }]);
    sessions.replaceAgentSessions(agent, [
      SessionInfoPayloadSchema.parse({
        session_id: "alpha-session",
        agent_name: "alpha",
        root_node_id: "a1",
        active_branch_id: "alpha-branch",
      }),
      SessionInfoPayloadSchema.parse({
        session_id: "alpha-session-2",
        agent_name: "alpha",
        root_node_id: "z1",
        active_branch_id: "alpha-branch",
      }),
    ]);
    sessions.setActiveSession(agent, "alpha-session");
    chains_setup2();
    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    await wrapper.findAll(".ac-node")[0].trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".ac-detail").exists()).toBe(true);
    expect(wrapper.find(".ac-detail--empty").exists()).toBe(false);

    // 切换 viewed Session：详情随选中更新（选中节点不在新链中 → 占位）
    await wrapper.get<HTMLSelectElement>(".chain-session-select").setValue("alpha-session-2");
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".ac-detail--empty").exists()).toBe(true);
  });

  /** 第二个 Session（alpha-session-2）的单节点链与 branch 夹具。 */
  function chains_setup2(): void {
    const session: SessionTarget = { ...target("alpha"), sessionId: "alpha-session-2" };
    useBranchesStore().replaceSessionBranches(
      session,
      [
        BranchInfoPayloadSchema.parse({
          branch_id: "alpha-branch",
          session_id: "alpha-session-2",
          name: "main",
          head_node_id: "z1",
        }),
      ],
      { explicitActiveBranchId: "alpha-branch" },
    );
    useActionChainsStore().setChain({ ...session, branchId: "alpha-branch" }, [
      node({
        id: "z1",
        parent_id: null,
        timestamp: "t9",
        session_id: "alpha-session-2",
        created_on_branch_id: "alpha-branch",
      }),
    ]);
  }

  // ── S3：管理操作（归档/删除）与从此节点重试 ──

  it("archives the viewed session with confirmation and correct scope", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("alpha"));
    setActiveChain("alpha", [{ id: "a1", parent_id: null, timestamp: "t1" }]);
    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();

    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    await wrapper.get("button.chain-archive-session").trigger("click");
    expect(confirm).toHaveBeenCalledOnce();
    expect(archiveSession).toHaveBeenCalledWith({
      ...target("alpha"),
      sessionId: "alpha-session",
    });

    // 拒绝确认不发命令
    confirm.mockReturnValue(false);
    await wrapper.get("button.chain-archive-session").trigger("click");
    expect(archiveSession).toHaveBeenCalledTimes(1);
  });

  it("archives and deletes the viewed branch with correct scope", async () => {
    const agents = useAgentsStore();
    const branches = useBranchesStore();
    agents.onAgentSpawned(spawn("alpha"));
    const agent = target("alpha");
    const session: SessionTarget = { ...agent, sessionId: "alpha-session" };
    sessions_setupTwoBranches();
    const wrapper = mount(ActionChainPanel, { props: { agent } });
    await wrapper.vm.$nextTick();

    // viewed Branch 初始回退 runtime（alpha-branch），切到第二个 Branch 后操作
    await wrapper.get<HTMLSelectElement>(".chain-branch-select").setValue("alpha-branch-2");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await wrapper.get("button.chain-archive-branch").trigger("click");
    expect(archiveBranch).toHaveBeenCalledWith({ ...session, branchId: "alpha-branch-2" });

    await wrapper.get("button.chain-delete-branch").trigger("click");
    expect(deleteBranch).toHaveBeenCalledWith({ ...session, branchId: "alpha-branch-2" });

    // 运行 Branch（runtime = alpha-branch）删除禁用
    await wrapper.get<HTMLSelectElement>(".chain-branch-select").setValue("alpha-branch");
    const deleteBtn = wrapper.get<HTMLButtonElement>("button.chain-delete-branch");
    expect(deleteBtn.attributes("disabled")).toBeDefined();
    expect(branches.activeBranchId(session)).toBe("alpha-branch");
  });

  it("disables deleting the running session", async () => {
    const agents = useAgentsStore();
    const sessions = useSessionsStore();
    agents.onAgentSpawned(spawn("alpha"));
    setActiveChain("alpha", [{ id: "a1", parent_id: null, timestamp: "t1" }]);
    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    // 单 Session：viewed = runtime → 删除禁用
    expect(sessions.activeSessionId(target("alpha"))).toBe("alpha-session");
    const btn = wrapper.get<HTMLButtonElement>("button.chain-delete-session");
    expect(btn.attributes("disabled")).toBeDefined();
  });

  it("deletes a non-running session with confirmation", async () => {
    const agents = useAgentsStore();
    const sessions = useSessionsStore();
    agents.onAgentSpawned(spawn("alpha"));
    const agent = target("alpha");
    setActiveChain("alpha", [{ id: "a1", parent_id: null, timestamp: "t1" }]);
    sessions.replaceAgentSessions(agent, [
      SessionInfoPayloadSchema.parse({
        session_id: "alpha-session",
        agent_name: "alpha",
        root_node_id: "a1",
        active_branch_id: "alpha-branch",
      }),
      SessionInfoPayloadSchema.parse({
        session_id: "alpha-session-2",
        agent_name: "alpha",
        root_node_id: "z1",
        active_branch_id: "alpha-branch",
      }),
    ]);
    sessions.setActiveSession(agent, "alpha-session");
    chains_setup2();

    const wrapper = mount(ActionChainPanel, { props: { agent } });
    await wrapper.vm.$nextTick();
    await wrapper.get<HTMLSelectElement>(".chain-session-select").setValue("alpha-session-2");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await wrapper.get("button.chain-delete-session").trigger("click");
    expect(deleteSession).toHaveBeenCalledWith({ ...agent, sessionId: "alpha-session-2" });
    // 运行态不被触碰
    expect(sessions.activeSessionId(agent)).toBe("alpha-session");
  });

  it("retries from the selected node: createBranch(fromNodeId) only, no implicit activate", async () => {
    const agents = useAgentsStore();
    const branches = useBranchesStore();
    agents.onAgentSpawned(spawn("alpha"));
    setActiveChain("alpha", [
      { id: "a1", parent_id: null, timestamp: "t1" },
      { id: "a2", parent_id: "a1", timestamp: "t2" },
    ]);
    createBranch.mockResolvedValue({ success: true, data: { branch_id: "alpha-branch-2" } });

    const wrapper = mount(ActionChainPanel, { props: { agent: target("alpha") } });
    await wrapper.vm.$nextTick();
    // 未选中节点时无重试入口
    expect(wrapper.find("button.chain-retry-from-node").exists()).toBe(false);

    await wrapper.findAll(".ac-node")[1].trigger("click");
    await wrapper.vm.$nextTick();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await wrapper.get("button.chain-retry-from-node").trigger("click");

    // 重试 = createBranch(fromNodeId)，绝不 sessionCreate / activate*
    const session: SessionTarget = { ...target("alpha"), sessionId: "alpha-session" };
    expect(createBranch).toHaveBeenCalledWith(session, "retry-2", { fromNodeId: "a2" });
    expect(createSession).not.toHaveBeenCalled();
    expect(activateSession).not.toHaveBeenCalled();
    expect(activateBranch).not.toHaveBeenCalled();
    // 成功后仅 viewBranch 切展示（D6）
    expect(branches.viewedBranchId(session)).toBe("alpha-branch-2");
    // 运行 Branch 不动
    expect(branches.activeBranchId(session)).toBe("alpha-branch");
  });

  it("shows failure receipts for management actions without moving viewed/runtime pointers", async () => {
    const agents = useAgentsStore();
    const sessions = useSessionsStore();
    agents.onAgentSpawned(spawn("alpha"));
    setActiveChain("alpha", [
      { id: "a1", parent_id: null, timestamp: "t1" },
      { id: "a2", parent_id: "a1", timestamp: "t2" },
    ]);
    const agent = target("alpha");
    const session: SessionTarget = { ...agent, sessionId: "alpha-session" };

    // 归档失败：回执展示，列表不移除、viewed 不动
    archiveSession.mockResolvedValue({
      success: false,
      error: "session is active",
      error_detail: "cannot archive the active session",
    });
    const wrapper = mount(ActionChainPanel, { props: { agent } });
    await wrapper.vm.$nextTick();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await wrapper.get("button.chain-archive-session").trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.get('[role="alert"]').text()).toContain("cannot archive the active session");
    expect(sessions.sessionsForAgent(agent).map((s) => s.target.sessionId)).toContain(
      "alpha-session",
    );

    // 重试失败：回执展示，不切 viewed Branch
    createBranch.mockResolvedValue({
      success: false,
      error: "fork node not found",
      error_detail: "fork node is not readable",
    });
    await wrapper.findAll(".ac-node")[0].trigger("click");
    await wrapper.vm.$nextTick();
    await wrapper.get("button.chain-retry-from-node").trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.get('[role="alert"]').text()).toContain("fork node is not readable");
    expect(useBranchesStore().viewedBranchId(session)).not.toBe("alpha-branch-2");
  });

  /** 双 Branch 夹具：alpha-branch（runtime，head=root）+ alpha-branch-2。 */
  function sessions_setupTwoBranches(): void {
    const agent = target("alpha");
    const session: SessionTarget = { ...agent, sessionId: "alpha-session" };
    useSessionsStore().replaceAgentSessions(agent, [
      SessionInfoPayloadSchema.parse({
        session_id: "alpha-session",
        agent_name: "alpha",
        root_node_id: "root",
        active_branch_id: "alpha-branch",
      }),
    ]);
    useSessionsStore().setActiveSession(agent, "alpha-session");
    useBranchesStore().replaceSessionBranches(
      session,
      [
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
      ],
      { explicitActiveBranchId: "alpha-branch" },
    );
  }
});
