import type {
  SessionActivatedPayload,
  SessionArchivedPayload,
  SessionCreatedPayload,
  SessionDeletedPayload,
  SessionInfoPayload,
} from "@ghrah/protocol";
import { defineStore } from "pinia";
import { ref } from "vue";
import { type AgentTarget, agentKey, type SessionTarget, sessionKey } from "../scope.js";

export interface SessionProjection {
  target: SessionTarget;
  info: SessionInfoPayload;
}

interface ActiveSessionSelection {
  target: AgentTarget;
  sessionId: string;
}

function targetFromPayload(
  payload: SessionCreatedPayload | SessionActivatedPayload,
): SessionTarget | null {
  const projectId = payload.project_id || payload.session.project_id;
  const agentId = payload.agent_id || payload.session.agent_id;
  const agentName = payload.agent_name || payload.session.agent_name;
  if (!projectId || !agentId || !agentName || !payload.session.session_id) return null;
  return { projectId, agentId, agentName, sessionId: payload.session.session_id };
}

export const useSessionsStore = defineStore("ghrah-sessions", () => {
  const sessions = ref<Map<string, SessionProjection>>(new Map());
  const activeSessions = ref<Map<string, ActiveSessionSelection>>(new Map());

  function sessionsForAgent(target: AgentTarget): SessionProjection[] {
    return [...sessions.value.values()].filter(
      (session) =>
        session.target.projectId === target.projectId && session.target.agentId === target.agentId,
    );
  }

  function getSession(target: SessionTarget): SessionProjection | undefined {
    return sessions.value.get(sessionKey(target));
  }

  function activeSessionId(target: AgentTarget): string | null {
    return activeSessions.value.get(agentKey(target))?.sessionId ?? null;
  }

  function setActiveSession(target: AgentTarget, sessionId: string | null) {
    const next = new Map(activeSessions.value);
    if (sessionId) next.set(agentKey(target), { target, sessionId });
    else next.delete(agentKey(target));
    activeSessions.value = next;
  }

  function upsert(target: SessionTarget, info: SessionInfoPayload) {
    sessions.value.set(sessionKey(target), {
      target,
      info: {
        ...info,
        project_id: target.projectId,
        agent_id: target.agentId,
        agent_name: target.agentName,
      },
    });
  }

  function onSessionCreated(payload: SessionCreatedPayload) {
    const target = targetFromPayload(payload);
    if (target) upsert(target, payload.session);
  }

  function onSessionActivated(payload: SessionActivatedPayload) {
    const target = targetFromPayload(payload);
    if (!target) return;
    upsert(target, payload.session);
    setActiveSession(target, target.sessionId);
  }

  function removeSession(
    payload: SessionArchivedPayload | SessionDeletedPayload,
  ): SessionTarget | null {
    if (!payload.project_id || !payload.agent_id || !payload.agent_name || !payload.session_id) {
      return null;
    }
    const target: SessionTarget = {
      projectId: payload.project_id,
      agentId: payload.agent_id,
      agentName: payload.agent_name,
      sessionId: payload.session_id,
    };
    sessions.value.delete(sessionKey(target));
    if (activeSessionId(target) === target.sessionId) setActiveSession(target, null);
    return target;
  }

  function replaceAgentSessions(
    target: AgentTarget,
    list: SessionInfoPayload[],
    explicitActiveSessionId?: string | null,
  ) {
    const next = new Map(
      [...sessions.value.entries()].filter(
        ([, session]) =>
          session.target.projectId !== target.projectId ||
          session.target.agentId !== target.agentId,
      ),
    );
    for (const info of list) {
      if (!info.session_id) continue;
      const sessionTarget = { ...target, sessionId: info.session_id };
      next.set(sessionKey(sessionTarget), {
        target: sessionTarget,
        info: {
          ...info,
          project_id: target.projectId,
          agent_id: target.agentId,
          agent_name: target.agentName,
        },
      });
    }
    sessions.value = next;
    if (explicitActiveSessionId !== undefined) setActiveSession(target, explicitActiveSessionId);
    const active = activeSessionId(target);
    if (active && !next.has(sessionKey({ ...target, sessionId: active })))
      setActiveSession(target, null);
  }

  function clearAgent(target: AgentTarget) {
    sessions.value = new Map(
      [...sessions.value.entries()].filter(
        ([, session]) =>
          session.target.projectId !== target.projectId ||
          session.target.agentId !== target.agentId,
      ),
    );
    setActiveSession(target, null);
  }

  function clearProject(projectId: string) {
    sessions.value = new Map(
      [...sessions.value.entries()].filter(([, session]) => session.target.projectId !== projectId),
    );
    activeSessions.value = new Map(
      [...activeSessions.value.entries()].filter(
        ([, selection]) => selection.target.projectId !== projectId,
      ),
    );
  }

  function clearAll() {
    sessions.value = new Map();
    activeSessions.value = new Map();
  }

  return {
    sessions,
    activeSessions,
    sessionsForAgent,
    getSession,
    activeSessionId,
    setActiveSession,
    onSessionCreated,
    onSessionActivated,
    removeSession,
    replaceAgentSessions,
    clearAgent,
    clearProject,
    clearAll,
  };
});
