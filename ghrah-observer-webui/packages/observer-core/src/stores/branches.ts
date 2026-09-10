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

  function branchesForSession(target: SessionTarget): BranchProjection[] {
    return [...branches.value.values()].filter(
      (branch) =>
        branch.target.projectId === target.projectId &&
        branch.target.agentId === target.agentId &&
        branch.target.sessionId === target.sessionId,
    );
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

  function upsert(target: ChainTarget, info: BranchInfoPayload) {
    branches.value.set(branchKey(target), {
      target,
      info: { ...info, session_id: target.sessionId, branch_id: target.branchId },
    });
  }

  function onBranchCreated(payload: BranchEventPayload) {
    const target = targetFromEvent(payload);
    if (target) upsert(target, payload.branch);
  }

  function onBranchActivated(payload: BranchEventPayload) {
    const target = targetFromEvent(payload);
    if (!target) return;
    upsert(target, payload.branch);
    setActiveBranch(target, target.branchId);
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
    branches.value.delete(branchKey(target));
    if (activeBranchId(target) === target.branchId) setActiveBranch(target, null);
    return target;
  }

  function replaceSessionBranches(
    target: SessionTarget,
    list: BranchInfoPayload[],
    explicitActiveBranchId?: string | null,
  ) {
    const next = new Map(
      [...branches.value.entries()].filter(
        ([, branch]) =>
          branch.target.projectId !== target.projectId ||
          branch.target.agentId !== target.agentId ||
          branch.target.sessionId !== target.sessionId,
      ),
    );
    for (const info of list) {
      if (!info.branch_id || info.session_id !== target.sessionId) continue;
      const branchTarget = { ...target, branchId: info.branch_id };
      next.set(branchKey(branchTarget), { target: branchTarget, info });
    }
    branches.value = next;
    if (explicitActiveBranchId !== undefined) setActiveBranch(target, explicitActiveBranchId);
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
  }

  function clearAll() {
    branches.value = new Map();
    activeBranches.value = new Map();
  }

  return {
    branches,
    activeBranches,
    branchesForSession,
    activeBranchId,
    setActiveBranch,
    onBranchCreated,
    onBranchActivated,
    removeBranch,
    replaceSessionBranches,
    clearSession,
    clearAgent,
    clearProject,
    clearAll,
  };
});
