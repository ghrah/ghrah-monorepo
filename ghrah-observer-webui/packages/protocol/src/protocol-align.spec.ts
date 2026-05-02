import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { ServerMessageSchema, parseMessage, serializeMessage } from "./message.js";
import {
  AbilityDefinitionPayloadSchema,
  AbilityResultPayloadSchema,
  ActionChainUpdatedPayloadSchema,
  AgentConfigPayloadSchema,
  AgentErrorPayloadSchema,
  AgentResponsePayloadSchema,
  AgentSpawnedPayloadSchema,
  AgentTerminatedPayloadSchema,
  BroadcastMessagePayloadSchema,
  ClusterStatusPayloadSchema,
  CommandResultPayloadSchema,
  CreateWorkspacePayloadSchema,
  DelegatePayloadSchema,
  DestroyWorkspacePayloadSchema,
  ErrorPayloadSchema,
  ExecuteAbilityPayloadSchema,
  GetAgentInfoPayloadSchema,
  HealthCheckPayloadSchema,
  HealthStatusPayloadSchema,
  HITLRequestPayloadSchema,
  HITLResponsePayloadSchema,
  InitClusterPayloadSchema,
  ListAgentsPayloadSchema,
  PersistDeletePayloadSchema,
  PersistListPayloadSchema,
  PersistLoadPayloadSchema,
  PersistSavePayloadSchema,
  RegisterAbilityPayloadSchema,
  SendMessagePayloadSchema,
  ShutdownClusterPayloadSchema,
  SpawnAgentPayloadSchema,
  SubscribePayloadSchema,
  TerminateAgentPayloadSchema,
  UnregisterAbilityPayloadSchema,
  UnsubscribePayloadSchema,
  WorkspaceCreatedPayloadSchema,
  WorkspaceDestroyedPayloadSchema,
  WorkspaceDiffPayloadSchema,
  WorkspaceRollbackPayloadSchema,
  WorkspaceRolledBackPayloadSchema,
  WorkspaceSnapshotCreatedPayloadSchema,
  WorkspaceSnapshotPayloadSchema,
  WorkspaceStatusPayloadSchema,
} from "./payloads.js";

const SNAPSHOTS_DIR = path.join(import.meta.dirname, "__snapshots__");

function loadSnapshot(name: string): Record<string, unknown> {
  const filePath = path.join(SNAPSHOTS_DIR, `${name}.json`);
  return JSON.parse(fs.readFileSync(filePath, "utf-8")) as Record<string, unknown>;
}

const PAYLOAD_SCHEMA_MAP: Record<string, import("zod").ZodTypeAny> = {
  AgentConfigPayload: AgentConfigPayloadSchema,
  AgentConfigPayload_full: AgentConfigPayloadSchema,
  AbilityDefinitionPayload: AbilityDefinitionPayloadSchema,
  SpawnAgentPayload: SpawnAgentPayloadSchema,
  SpawnAgentPayload_minimal: SpawnAgentPayloadSchema,
  TerminateAgentPayload: TerminateAgentPayloadSchema,
  SendMessagePayload: SendMessagePayloadSchema,
  SendMessagePayload_default_sender: SendMessagePayloadSchema,
  BroadcastMessagePayload: BroadcastMessagePayloadSchema,
  RegisterAbilityPayload: RegisterAbilityPayloadSchema,
  UnregisterAbilityPayload: UnregisterAbilityPayloadSchema,
  ListAgentsPayload: ListAgentsPayloadSchema,
  HealthCheckPayload: HealthCheckPayloadSchema,
  DelegatePayload: DelegatePayloadSchema,
  GetAgentInfoPayload: GetAgentInfoPayloadSchema,
  SubscribePayload: SubscribePayloadSchema,
  SubscribePayload_all: SubscribePayloadSchema,
  UnsubscribePayload: UnsubscribePayloadSchema,
  ExecuteAbilityPayload: ExecuteAbilityPayloadSchema,
  ExecuteAbilityPayload_default_args: ExecuteAbilityPayloadSchema,
  HITLResponsePayload: HITLResponsePayloadSchema,
  HITLResponsePayload_with_reason: HITLResponsePayloadSchema,
  InitClusterPayload: InitClusterPayloadSchema,
  ShutdownClusterPayload: ShutdownClusterPayloadSchema,
  ClusterStatusPayload: ClusterStatusPayloadSchema,
  PersistSavePayload: PersistSavePayloadSchema,
  PersistSavePayload_default_ns: PersistSavePayloadSchema,
  PersistLoadPayload: PersistLoadPayloadSchema,
  PersistDeletePayload: PersistDeletePayloadSchema,
  PersistListPayload: PersistListPayloadSchema,
  PersistListPayload_defaults: PersistListPayloadSchema,
  CreateWorkspacePayload: CreateWorkspacePayloadSchema,
  DestroyWorkspacePayload: DestroyWorkspacePayloadSchema,
  WorkspaceSnapshotPayload: WorkspaceSnapshotPayloadSchema,
  WorkspaceSnapshotPayload_default_msg: WorkspaceSnapshotPayloadSchema,
  WorkspaceRollbackPayload: WorkspaceRollbackPayloadSchema,
  WorkspaceDiffPayload: WorkspaceDiffPayloadSchema,
  WorkspaceDiffPayload_null_snapshot: WorkspaceDiffPayloadSchema,
  WorkspaceStatusPayload: WorkspaceStatusPayloadSchema,
  AgentSpawnedPayload: AgentSpawnedPayloadSchema,
  AgentTerminatedPayload: AgentTerminatedPayloadSchema,
  AgentResponsePayload: AgentResponsePayloadSchema,
  AgentResponsePayload_defaults: AgentResponsePayloadSchema,
  ActionChainUpdatedPayload: ActionChainUpdatedPayloadSchema,
  AgentErrorPayload: AgentErrorPayloadSchema,
  HealthStatusPayload: HealthStatusPayloadSchema,
  AbilityResultPayload_success: AbilityResultPayloadSchema,
  AbilityResultPayload_failure: AbilityResultPayloadSchema,
  HITLRequestPayload: HITLRequestPayloadSchema,
  HITLRequestPayload_with_args: HITLRequestPayloadSchema,
  WorkspaceCreatedPayload: WorkspaceCreatedPayloadSchema,
  WorkspaceDestroyedPayload: WorkspaceDestroyedPayloadSchema,
  WorkspaceSnapshotCreatedPayload: WorkspaceSnapshotCreatedPayloadSchema,
  WorkspaceRolledBackPayload: WorkspaceRolledBackPayloadSchema,
  CommandResultPayload_success: CommandResultPayloadSchema,
  CommandResultPayload_failure: CommandResultPayloadSchema,
  ErrorPayload: ErrorPayloadSchema,
  ErrorPayload_with_details: ErrorPayloadSchema,
};

describe("Pydantic-Zod cross-validation", () => {
  const snapshotFiles = fs.readdirSync(SNAPSHOTS_DIR).filter((f) => f.endsWith(".json"));

  it("all payload schemas have corresponding snapshots", () => {
    const schemaNames = Object.keys(PAYLOAD_SCHEMA_MAP);
    const snapshotNames = snapshotFiles.map((f) => f.replace(".json", ""));
    for (const name of schemaNames) {
      expect(snapshotNames).toContain(name);
    }
  });

  for (const file of snapshotFiles) {
    const name = file.replace(".json", "");
    const schema = PAYLOAD_SCHEMA_MAP[name];

    if (!schema) continue;

    it(`Zod parses Python snapshot for ${name}`, () => {
      const pythonSnapshot = loadSnapshot(name);

      const parsed = schema.parse(pythonSnapshot);

      const pythonKeys = Object.keys(pythonSnapshot).sort();
      const tsKeys = Object.keys(parsed).sort();

      for (const key of pythonKeys) {
        expect(tsKeys).toContain(key);
      }
    });

    it(`TS parsed output keys match Python for ${name}`, () => {
      const pythonSnapshot = loadSnapshot(name);

      const parsed = schema.parse(pythonSnapshot);

      const pythonKeys = new Set(Object.keys(pythonSnapshot));
      const tsKeys = new Set(Object.keys(parsed));

      const missingFromTs = [...pythonKeys].filter((k) => !tsKeys.has(k));
      const extraInTs = [...tsKeys].filter((k) => !pythonKeys.has(k));

      if (missingFromTs.length > 0) {
        expect(
          missingFromTs.every((k) => pythonSnapshot[k] === null),
          `Keys missing from TS: ${missingFromTs.join(", ")} — acceptable only if Python value was null`,
        ).toBe(true);
      }

      if (extraInTs.length > 0) {
        expect(
          extraInTs.every((k) => parsed[k] === undefined || parsed[k] === null),
          `Extra keys in TS: ${extraInTs.join(", ")} — acceptable only if value is undefined/null`,
        ).toBe(true);
      }
    });
  }
});

describe("ServerMessage cross-validation", () => {
  it("Zod parses Python minimal ServerMessage snapshot", () => {
    const pythonSnapshot = loadSnapshot("GatewayMessage_minimal");
    const parsed = ServerMessageSchema.parse(pythonSnapshot);
    expect(parsed.type).toBe("ping");
    expect(parsed.payload).toEqual({});
  });

  it("Zod parses Python full ServerMessage snapshot", () => {
    const pythonSnapshot = loadSnapshot("GatewayMessage_full");
    const parsed = ServerMessageSchema.parse(pythonSnapshot);
    expect(parsed.type).toBe("spawn_agent");
    expect(parsed.request_id).toBe("abc123");
    expect(parsed.timestamp).toBe(12345.678);
  });

  it("serializeMessage round-trips Python ServerMessage snapshot", () => {
    const pythonSnapshot = loadSnapshot("GatewayMessage_full");
    const parsed = ServerMessageSchema.parse(pythonSnapshot);
    const serialized = serializeMessage(parsed);
    const reparsed = parseMessage(serialized);

    expect(reparsed.type).toBe(parsed.type);
    expect(reparsed.request_id).toBe(parsed.request_id);
  });
});
