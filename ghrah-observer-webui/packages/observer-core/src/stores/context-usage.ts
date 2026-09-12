import type { ContextUsageUpdatedPayload } from "@ghrah/protocol";
import { defineStore } from "pinia";
import { ref } from "vue";
import type { AgentKey, AgentTarget } from "../scope.js";
import { agentKey } from "../scope.js";

/** Single wire snapshot of context usage for one agent. */
export interface ContextUsageSnapshot {
  target: AgentTarget;
  phase: string;
  basis: string;
  occupiedTokens: number | null;
  budgetTokens: number;
  compactThreshold: number | null;
  realInputTokens: number | null;
  realOutputTokens: number | null;
  realCacheReadTokens: number | null;
  realCacheWriteTokens: number | null;
  budgetSource: string | null;
  compaction: Record<string, unknown> | null;
  iteration: number | null;
  updatedAt: number | null;
}

/** Per-agent usage state: latest snapshot, latest post_call slot, cumulative real input. */
export interface ContextUsageEntry {
  target: AgentTarget;
  latest: ContextUsageSnapshot;
  latestPostCall: ContextUsageSnapshot | null;
  cumulativeInputTokens: number;
  cumulativeOutputTokens: number;
  cumulativeCacheReadTokens: number;
}

/** Derived display projection for UI (ratio bar when budgeted, cumulative otherwise). */
export interface ContextUsageDisplay {
  mode: "ratio" | "cumulative";
  occupiedTokens: number | null;
  budgetTokens: number;
  budgetSource: string | null;
  percent: number | null;
  compactThreshold: number | null;
  /** Latest post_call real usage breakdown (normalized: input includes cache). */
  realInputTokens: number | null;
  realOutputTokens: number | null;
  realCacheReadTokens: number | null;
  realCacheWriteTokens: number | null;
  cumulativeInputTokens: number;
  cumulativeOutputTokens: number;
  cumulativeCacheReadTokens: number;
  basis: string;
  updatedAt: number | null;
}

export const useContextUsageStore = defineStore("ghrah-context-usage", () => {
  const entries = ref<Map<string, ContextUsageEntry>>(new Map());

  function toSnapshot(
    payload: ContextUsageUpdatedPayload,
    timestamp: number | null,
  ): ContextUsageSnapshot {
    return {
      target: {
        projectId: payload.project_id,
        agentId: payload.agent_id,
        agentName: payload.agent_name,
      },
      phase: payload.phase,
      basis: payload.basis,
      occupiedTokens: payload.occupied_tokens ?? null,
      budgetTokens: payload.budget_tokens ?? 0,
      compactThreshold: payload.compact_threshold ?? null,
      realInputTokens: payload.real_input_tokens ?? null,
      realOutputTokens: payload.real_output_tokens ?? null,
      realCacheReadTokens: payload.real_cache_read_tokens ?? null,
      realCacheWriteTokens: payload.real_cache_write_tokens ?? null,
      budgetSource: payload.budget_source ?? null,
      compaction: payload.compaction ?? null,
      iteration: payload.iteration ?? null,
      updatedAt: timestamp,
    };
  }

  function onContextUsageUpdated(
    payload: ContextUsageUpdatedPayload,
    timestamp: number | null = null,
  ): boolean {
    if (!payload.project_id || !payload.agent_id) return false;
    const snapshot = toSnapshot(payload, timestamp);
    const key = agentKey(snapshot.target);
    const existing = entries.value.get(key);
    const cumulativeInput =
      (existing?.cumulativeInputTokens ?? 0) + (snapshot.realInputTokens ?? 0);
    const cumulativeOutput =
      (existing?.cumulativeOutputTokens ?? 0) + (snapshot.realOutputTokens ?? 0);
    const cumulativeCacheRead =
      (existing?.cumulativeCacheReadTokens ?? 0) + (snapshot.realCacheReadTokens ?? 0);
    const next: ContextUsageEntry = {
      target: snapshot.target,
      latest: snapshot,
      latestPostCall:
        snapshot.phase === "post_call" ? snapshot : (existing?.latestPostCall ?? null),
      cumulativeInputTokens: cumulativeInput,
      cumulativeOutputTokens: cumulativeOutput,
      cumulativeCacheReadTokens: cumulativeCacheRead,
    };
    entries.value.set(key, next);
    return true;
  }

  function usageFor(target: AgentKey): ContextUsageDisplay | null {
    const entry = entries.value.get(agentKey(target));
    if (!entry) return null;
    const source = entry.latestPostCall ?? entry.latest;
    const budget = source.budgetTokens;
    if (budget > 0) {
      const percent =
        source.occupiedTokens != null
          ? Math.min(100, Math.round((source.occupiedTokens / budget) * 100))
          : null;
      return {
        mode: "ratio",
        occupiedTokens: source.occupiedTokens,
        budgetTokens: budget,
        budgetSource: source.budgetSource,
        percent,
        compactThreshold: source.compactThreshold,
        realInputTokens: source.realInputTokens,
        realOutputTokens: source.realOutputTokens,
        realCacheReadTokens: source.realCacheReadTokens,
        realCacheWriteTokens: source.realCacheWriteTokens,
        cumulativeInputTokens: entry.cumulativeInputTokens,
        cumulativeOutputTokens: entry.cumulativeOutputTokens,
        cumulativeCacheReadTokens: entry.cumulativeCacheReadTokens,
        basis: source.basis,
        updatedAt: source.updatedAt,
      };
    }
    return {
      mode: "cumulative",
      occupiedTokens: source.occupiedTokens,
      budgetTokens: 0,
      budgetSource: source.budgetSource,
      percent: null,
      compactThreshold: source.compactThreshold,
      realInputTokens: source.realInputTokens,
      realOutputTokens: source.realOutputTokens,
      realCacheReadTokens: source.realCacheReadTokens,
      realCacheWriteTokens: source.realCacheWriteTokens,
      cumulativeInputTokens: entry.cumulativeInputTokens,
      cumulativeOutputTokens: entry.cumulativeOutputTokens,
      cumulativeCacheReadTokens: entry.cumulativeCacheReadTokens,
      basis: source.basis,
      updatedAt: source.updatedAt,
    };
  }

  function clearAgent(target: AgentKey) {
    entries.value.delete(agentKey(target));
  }

  function clearProject(projectId: string) {
    entries.value = new Map(
      [...entries.value.entries()].filter(([, entry]) => entry.target.projectId !== projectId),
    );
  }

  function clearAll() {
    entries.value = new Map();
  }

  return {
    entries,
    onContextUsageUpdated,
    usageFor,
    clearAgent,
    clearProject,
    clearAll,
  };
});
