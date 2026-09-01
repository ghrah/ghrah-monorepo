import { demoScenario } from "./demo-4agent-4room.js";
import type { Scenario } from "./types.js";

const REGISTRY = new Map<string, Scenario>([[demoScenario.name, demoScenario]]);

export function getScenario(name: string): Scenario {
  const scenario = REGISTRY.get(name);
  if (!scenario) {
    throw new Error(`unknown scenario: ${name} (available: ${[...REGISTRY.keys()].join(", ")})`);
  }
  return scenario;
}

export function listScenarios(): Scenario[] {
  return [...REGISTRY.values()];
}

export { demoScenario } from "./demo-4agent-4room.js";
export type { Scenario, ScenarioContext, TimelineAction, TimelineEntry } from "./types.js";
export { runScenario } from "./types.js";
