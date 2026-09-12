// @vitest-environment happy-dom

import { useAgentsStore } from "@ghrah/observer-core";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AgentActionMenu from "./agent-action-menu.vue";

const agentCompactContext = vi.fn();
const terminateAgent = vi.fn();
const createWorkspace = vi.fn();
const workspaceSnapshot = vi.fn();
const workspaceDiff = vi.fn();

vi.mock("@/composables/useObserver", () => ({
  useObserver: () => ({
    agentCompactContext,
    terminateAgent,
    createWorkspace,
    workspaceSnapshot,
    workspaceDiff,
    error: { value: null },
  }),
}));

// 隔离 MonacoDiff（其 monaco-editor 依赖链在测试环境不可解析）
vi.mock("@/components/monaco-diff.vue", () => ({
  default: { template: "<div />" },
}));

function mountMenu() {
  return mount(AgentActionMenu);
}

async function openMenu(wrapper: ReturnType<typeof mount>) {
  await wrapper.get("button").trigger("click");
}

describe("AgentActionMenu compact context", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    agentCompactContext.mockReset();
    agentCompactContext.mockResolvedValue({ success: true, data: { executed: true } });
    terminateAgent.mockReset();
    createWorkspace.mockReset();
    workspaceSnapshot.mockReset();
    workspaceDiff.mockReset();
    const agents = useAgentsStore();
    agents.selectAgent({ projectId: "p1", agentId: "a1", agentName: "coder" });
  });

  it("sends agent_compact_context with the selected agent target", async () => {
    const wrapper = mountMenu();
    await openMenu(wrapper);
    const compactButton = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Compact Context"));
    expect(compactButton).toBeDefined();
    await compactButton!.trigger("click");
    expect(agentCompactContext).toHaveBeenCalledWith({
      projectId: "p1",
      agentId: "a1",
      agentName: "coder",
    });
  });

  it("shows server error when the command fails", async () => {
    agentCompactContext.mockResolvedValue({ success: false, error: "agent context not found" });
    const wrapper = mountMenu();
    await openMenu(wrapper);
    const compactButton = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Compact Context"));
    await compactButton!.trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("agent context not found");
  });

  it("shows fallback error when not connected", async () => {
    agentCompactContext.mockResolvedValue(null);
    const wrapper = mountMenu();
    await openMenu(wrapper);
    const compactButton = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Compact Context"));
    await compactButton!.trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("Not connected to server");
  });
});
