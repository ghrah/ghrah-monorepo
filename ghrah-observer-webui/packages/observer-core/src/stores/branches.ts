import type {
  BranchEventPayload,
  BranchInfoPayload,
  BranchLifecyclePayload,
} from "@ghrah/protocol";
import { defineStore } from "pinia";
import { ref } from "vue";
import {
  type AgentTarget,
  branchKey,
  type ChainTarget,
  type SessionTarget,
  sessionKey,
} from "../scope.js";

export interface BranchProjection {
  target: ChainTarget;
  info: BranchInfoPayload;
}

interface ActiveBranchSelection {
  target: SessionTarget;
  branchId: string;
}

/** list 请求发出前捕获的实体/运行态 revision 基线。 */
export interface BranchSyncBaseline {
  entities: Map<string, number>;
  active: number;
}

function targetFromEvent(payload: BranchEventPayload): ChainTarget | null {
  if (
    !payload.project_id ||
    !payload.agent_id ||
    !payload.agent_name ||
    !payload.branch.session_id ||
    !payload.branch.branch_id
  ) {
    return null;
  }
  return {
    projectId: payload.project_id,
    agentId: payload.agent_id,
    agentName: payload.agent_name,
    sessionId: payload.branch.session_id,
    branchId: payload.branch.branch_id,
  };
}

export const useBranchesStore = defineStore("ghrah-branches", () => {
  const branches = ref<Map<string, BranchProjection>>(new Map());
  const activeBranches = ref<Map<string, ActiveBranchSelection>>(new Map());
  /** 实体事件 revision：晚到 list 不得覆盖 revision 更高的实体状态。 */
  const entityRevisions = ref<Map<string, number>>(new Map());
  /** Session 运行态 active_branch revision：晚到 list 不得回退事件后的指针。 */
  const activeRevisions = ref<Map<string, number>>(new Map());
  /** 纯前端展示态：null = 查看该 Session 的全部 Branch。 */
  const viewedBranches = ref<Map<string, string | null>>(new Map());

  function bumpEntity(key: string) {
    entityRevisions.value.set(key, (entityRevisions.value.get(key) ?? 0) + 1);
  }

  function bumpActive(target: SessionTarget) {
    const key = sessionKey(target);
    activeRevisions.value.set(key, (activeRevisions.value.get(key) ?? 0) + 1);
  }

  function captureBaseline(target: SessionTarget): BranchSyncBaseline {
    const entities = new Map<string, number>();
    for (const projection of branchesForSession(target)) {
      const key = branchKey(projection.target);
      entities.set(key, entityRevisions.value.get(key) ?? 0);
    }
    return { entities, active: activeRevisions.value.get(sessionKey(target)) ?? 0 };
  }

  function branchesForSession(target: SessionTarget): BranchProjection[] {
    return [...branches.value.values()].filter(
      (branch) =>
        branch.target.projectId === target.projectId &&
        branch.target.agentId === target.agentId &&
        branch.target.sessionId === target.sessionId,
    );
  }

  function getBranch(target: ChainTarget): BranchProjection | undefined {
    return branches.value.get(branchKey(target));
  }

  function activeBranchId(target: SessionTarget): string | null {
    return activeBranches.value.get(sessionKey(target))?.branchId ?? null;
  }

  function setActiveBranch(target: SessionTarget, branchId: string | null) {
    const next = new Map(activeBranches.value);
    if (branchId) next.set(sessionKey(target), { target, branchId });
    else next.delete(sessionKey(target));
    activeBranches.value = next;
  }

  /** 展示态读取：用户显式选择优先，null 显式表示"全部 Branch"。 */
  function viewedBranchId(target: SessionTarget): string | null | undefined {
    const key = sessionKey(target);
    return viewedBranches.value.has(key) ? (viewedBranches.value.get(key) ?? null) : undefined;
  }

  function viewBranch(target: SessionTarget, branchId: string | null | undefined) {
    const key = sessionKey(target);
    const next = new Map(viewedBranches.value);
    if (branchId === undefined) next.delete(key);
    else next.set(key, branchId);
    viewedBranches.value = next;
  }

  function upsert(target: ChainTarget, info: BranchInfoPayload) {
    branches.value.set(branchKey(target), {
      target,
      info: { ...info, session_id: target.sessionId, branch_id: target.branchId },
    });
  }

  function onBranchCreated(payload: BranchEventPayload) {
    const target = targetFromEvent(payload);
    if (!target) return;
    upsert(target, payload.branch);
    bumpEntity(branchKey(target));
  }

  function onBranchActivated(payload: BranchEventPayload) {
    const target = targetFromEvent(payload);
    if (!target) return;
    upsert(target, payload.branch);
    bumpEntity(branchKey(target));
    setActiveBranch(target, target.branchId);
    bumpActive(target);
  }

  /** commit 事件携带的权威 Branch 快照：只前移 Head，不回退。 */
  function advanceHead(target: ChainTarget, info: BranchInfoPayload) {
    const key = branchKey(target);
    const existing = branches.value.get(key);
    if (!existing) {
      upsert(target, info);
      bumpEntity(key);
      return;
    }
    if (existing.info.head_node_id === info.head_node_id) return;
    branches.value.set(key, {
      target,
      info: { ...existing.info, head_node_id: info.head_node_id, name: info.name },
    });
    bumpEntity(key);
  }

  function removeBranch(payload: BranchLifecyclePayload): ChainTarget | null {
    if (
      !payload.project_id ||
      !payload.agent_id ||
      !payload.agent_name ||
      !payload.session_id ||
      !payload.branch_id
    ) {
      return null;
    }
    const target: ChainTarget = {
      projectId: payload.project_id,
      agentId: payload.agent_id,
      agentName: payload.agent_name,
      sessionId: payload.session_id,
      branchId: payload.branch_id,
    };
    const key = branchKey(target);
    branches.value.delete(key);
    bumpEntity(key);
    if (activeBranchId(target) === target.branchId) setActiveBranch(target, null);
    if (viewedBranches.value.get(sessionKey(target)) === target.branchId) {
      viewBranch(target, null);
    }
    return target;
  }

  function replaceSessionBranches(
    target: SessionTarget,
    list: BranchInfoPayload[],
    options: {
      explicitActiveBranchId?: string | null;
      baseline?: BranchSyncBaseline;
    } = {},
  ) {
    const baseline = options.baseline;
    const next = new Map(
      [...branches.value.entries()].filter(
        ([, branch]) =>
          branch.target.projectId !== target.projectId ||
          branch.target.agentId !== target.agentId ||
          branch.target.sessionId !== target.sessionId,
      ),
    );
    // 事件已更新的实体（revision 高于请求基线）保留事件版本，list 只补缺失实体。
    if (baseline) {
      for (const [key, projection] of branches.value.entries()) {
        if (
          projection.target.projectId === target.projectId &&
          projection.target.agentId === target.agentId &&
          projection.target.sessionId === target.sessionId &&
          (entityRevisions.value.get(key) ?? 0) > (baseline.entities.get(key) ?? 0)
        ) {
          next.set(key, projection);
        }
      }
    }
    for (const info of list) {
      if (!info.branch_id || info.session_id !== target.sessionId) continue;
      const branchTarget = { ...target, branchId: info.branch_id };
      const key = branchKey(branchTarget);
      if (next.has(key)) continue;
      next.set(key, { target: branchTarget, info });
    }
    branches.value = next;
    const activeAdvancedByEvent =
      baseline !== undefined &&
      (activeRevisions.value.get(sessionKey(target)) ?? 0) > baseline.active;
    if (options.explicitActiveBranchId !== undefined && !activeAdvancedByEvent) {
      setActiveBranch(target, options.explicitActiveBranchId);
    }
    const active = activeBranchId(target);
    if (active && !next.has(branchKey({ ...target, branchId: active })))
      setActiveBranch(target, null);
  }

  function clearSession(target: SessionTarget) {
    branches.value = new Map(
      [...branches.value.entries()].filter(
        ([, branch]) =>
          branch.target.projectId !== target.projectId ||
          branch.target.agentId !== target.agentId ||
          branch.target.sessionId !== target.sessionId,
      ),
    );
    setActiveBranch(target, null);
    viewedBranches.value = new Map(
      [...viewedBranches.value.entries()].filter(([key]) => key !== sessionKey(target)),
    );
  }

  function clearAgent(target: AgentTarget) {
    branches.value = new Map(
      [...branches.value.entries()].filter(
        ([, branch]) =>
          branch.target.projectId !== target.projectId || branch.target.agentId !== target.agentId,
      ),
    );
    activeBranches.value = new Map(
      [...activeBranches.value.entries()].filter(
        ([, selection]) =>
          selection.target.projectId !== target.projectId ||
          selection.target.agentId !== target.agentId,
      ),
    );
    viewedBranches.value = new Map(
      [...viewedBranches.value.entries()].filter(([key]) => {
        try {
          const [projectId, agentId] = JSON.parse(key) as [string, string, string];
          return !(projectId === target.projectId && agentId === target.agentId);
        } catch {
          return true;
        }
      }),
    );
  }

  function clearProject(projectId: string) {
    branches.value = new Map(
      [...branches.value.entries()].filter(([, branch]) => branch.target.projectId !== projectId),
    );
    activeBranches.value = new Map(
      [...activeBranches.value.entries()].filter(
        ([, selection]) => selection.target.projectId !== projectId,
      ),
    );
    viewedBranches.value = new Map(
      [...viewedBranches.value.entries()].filter(([key]) => {
        try {
          const [parsedProject] = JSON.parse(key) as [string, string, string];
          return parsedProject !== projectId;
        } catch {
          return true;
        }
      }),
    );
  }

  function clearAll() {
    branches.value = new Map();
    activeBranches.value = new Map();
    viewedBranches.value = new Map();
  }

  return {
    branches,
    activeBranches,
    branchesForSession,
    getBranch,
    activeBranchId,
    setActiveBranch,
    viewedBranchId,
    viewBranch,
    captureBaseline,
    onBranchCreated,
    onBranchActivated,
    advanceHead,
    removeBranch,
    replaceSessionBranches,
    clearSession,
    clearAgent,
    clearProject,
    clearAll,
  };
});
