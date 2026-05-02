import { z } from "zod";

export const AgentConfigPayloadSchema = z.object({
  name: z.string(),
  agent_config_name: z.string().nullable().optional(),
  description: z.string().optional().default(""),
  system_prompt: z.string().optional().default(""),
  max_iterations: z.number().int().optional().default(10),
  gateway_url: z.string().nullable().optional(),
  // gateway_url: Subject ObserverServer URL (e.g. ws://localhost:4112/ws).
  // Kept as "gateway_url" for wire protocol compatibility with Python side.
});

export const AbilityDefinitionPayloadSchema = z.object({
  ability_type: z.string(),
  params: z.record(z.unknown()).optional().default({}),
});

export const SpawnAgentPayloadSchema = z.object({
  config: AgentConfigPayloadSchema,
  abilities: z.array(AbilityDefinitionPayloadSchema).nullable().optional(),
  manifest_ref: z.string().nullable().optional(),
});

export const TerminateAgentPayloadSchema = z.object({
  name: z.string(),
});

export const SendMessagePayloadSchema = z.object({
  target: z.string(),
  content: z.string(),
  sender: z.string().optional().default("user"),
});

export const BroadcastMessagePayloadSchema = z.object({
  content: z.string(),
  sender: z.string().optional().default("user"),
});

export const RegisterAbilityPayloadSchema = z.object({
  agent_name: z.string(),
  ability: AbilityDefinitionPayloadSchema,
});

export const UnregisterAbilityPayloadSchema = z.object({
  agent_name: z.string(),
  ability_name: z.string(),
});

export const ListAgentsPayloadSchema = z.object({});

export const HealthCheckPayloadSchema = z.object({});

export const DelegatePayloadSchema = z.object({
  from_agent: z.string(),
  to_agent: z.string(),
  content: z.string(),
});

export const GetAgentInfoPayloadSchema = z.object({
  name: z.string(),
});

export const SubscribePayloadSchema = z.object({
  agent_names: z.array(z.string()).nullable().optional(),
  event_types: z.array(z.string()).nullable().optional(),
});

export const UnsubscribePayloadSchema = z.object({
  agent_names: z.array(z.string()).nullable().optional(),
  event_types: z.array(z.string()).nullable().optional(),
});

export const ExecuteAbilityPayloadSchema = z.object({
  request_id: z.string(),
  agent_name: z.string(),
  ability_name: z.string(),
  tool_args: z.record(z.unknown()).optional().default({}),
});

export const HITLResponsePayloadSchema = z.object({
  promise_id: z.string(),
  approved: z.boolean(),
  reason: z.string().nullable().optional(),
});

export const InitClusterPayloadSchema = z.object({
  config: z.record(z.unknown()).optional().default({}),
});

export const ShutdownClusterPayloadSchema = z.object({
  config: z.record(z.unknown()).optional().default({}),
});

export const ClusterStatusPayloadSchema = z.object({});

export const PersistSavePayloadSchema = z.object({
  key: z.string(),
  data: z.record(z.unknown()),
  namespace: z.string().optional().default("default"),
});

export const PersistLoadPayloadSchema = z.object({
  key: z.string(),
  namespace: z.string().optional().default("default"),
});

export const PersistDeletePayloadSchema = z.object({
  key: z.string(),
  namespace: z.string().optional().default("default"),
});

export const PersistListPayloadSchema = z.object({
  namespace: z.string().optional().default("default"),
  prefix: z.string().nullable().optional(),
});

export const CreateWorkspacePayloadSchema = z.object({
  agent_name: z.string(),
});

export const DestroyWorkspacePayloadSchema = z.object({
  agent_name: z.string(),
});

export const WorkspaceSnapshotPayloadSchema = z.object({
  agent_name: z.string(),
  message: z.string().optional().default(""),
});

export const WorkspaceRollbackPayloadSchema = z.object({
  agent_name: z.string(),
  snapshot_id: z.string(),
});

export const WorkspaceDiffPayloadSchema = z.object({
  agent_name: z.string(),
  snapshot_id: z.string().nullable().optional(),
});

export const WorkspaceStatusPayloadSchema = z.object({
  agent_name: z.string(),
});

export const AgentSpawnedPayloadSchema = z.object({
  name: z.string(),
  config: AgentConfigPayloadSchema,
});

export const AgentTerminatedPayloadSchema = z.object({
  name: z.string(),
});

export const AgentResponsePayloadSchema = z.object({
  sender: z.string(),
  recipient: z.string(),
  content: z.string(),
  message_type: z.string().optional().default("result"),
  metadata: z.record(z.unknown()).optional().default({}),
});

export const ActionChainUpdatedPayloadSchema = z.object({
  agent_name: z.string(),
  node: z.record(z.unknown()).optional().default({}),
});

export const AgentErrorPayloadSchema = z.object({
  agent_name: z.string(),
  error: z.string(),
});

export const HealthStatusPayloadSchema = z.object({
  status: z.record(z.boolean()),
});

export const AbilityResultPayloadSchema = z.object({
  request_id: z.string(),
  agent_name: z.string(),
  ability_name: z.string(),
  success: z.boolean(),
  result: z.unknown().nullable().optional(),
  error: z.string().nullable().optional(),
});

export const HITLRequestPayloadSchema = z.object({
  promise_id: z.string(),
  agent_name: z.string(),
  ability_name: z.string(),
  tool_args: z.record(z.unknown()).optional().default({}),
  context: z.record(z.unknown()).optional().default({}),
});

export const WorkspaceCreatedPayloadSchema = z.object({
  agent_name: z.string(),
  path: z.string(),
});

export const WorkspaceDestroyedPayloadSchema = z.object({
  agent_name: z.string(),
});

export const WorkspaceSnapshotCreatedPayloadSchema = z.object({
  agent_name: z.string(),
  snapshot_id: z.string(),
  message: z.string().optional().default(""),
});

export const WorkspaceRolledBackPayloadSchema = z.object({
  agent_name: z.string(),
  snapshot_id: z.string(),
});

// ─── Manifest CRUD Payloads ───

export const ManifestListPayloadSchema = z.object({
  namespace: z.string().nullable().optional(),
});

export const ManifestGetPayloadSchema = z.object({
  full_name: z.string(),
});

export const ManifestPutPayloadSchema = z.object({
  full_name: z.string(),
  content: z.string(),
  overwrite: z.boolean().optional().default(false),
});

export const ManifestDeletePayloadSchema = z.object({
  full_name: z.string(),
});

export const ManifestValidatePayloadSchema = z.object({
  content: z.string(),
  manifest_type: z.string(),
});

export const ManifestResolvePayloadSchema = z.object({
  agent_full_name: z.string(),
  runtime_name: z.string().nullable().optional(),
});

// ─── Manifest Event Payloads ───

export const ManifestAbilityEventPayloadSchema = z.object({
  full_name: z.string(),
  namespace: z.string(),
});

export const ManifestAgentEventPayloadSchema = z.object({
  full_name: z.string(),
  namespace: z.string(),
});

export const CommandResultPayloadSchema = z.object({
  request_id: z.string(),
  success: z.boolean(),
  data: z.unknown().nullable().optional(),
  error: z.string().nullable().optional(),
});

export const ErrorPayloadSchema = z.object({
  code: z.string(),
  message: z.string(),
  details: z.record(z.unknown()).nullable().optional(),
});

export type AgentConfigPayload = z.infer<typeof AgentConfigPayloadSchema>;
export type AbilityDefinitionPayload = z.infer<typeof AbilityDefinitionPayloadSchema>;
export type SpawnAgentPayload = z.infer<typeof SpawnAgentPayloadSchema>;
export type TerminateAgentPayload = z.infer<typeof TerminateAgentPayloadSchema>;
export type SendMessagePayload = z.infer<typeof SendMessagePayloadSchema>;
export type BroadcastMessagePayload = z.infer<typeof BroadcastMessagePayloadSchema>;
export type RegisterAbilityPayload = z.infer<typeof RegisterAbilityPayloadSchema>;
export type UnregisterAbilityPayload = z.infer<typeof UnregisterAbilityPayloadSchema>;
export type ListAgentsPayload = z.infer<typeof ListAgentsPayloadSchema>;
export type HealthCheckPayload = z.infer<typeof HealthCheckPayloadSchema>;
export type DelegatePayload = z.infer<typeof DelegatePayloadSchema>;
export type GetAgentInfoPayload = z.infer<typeof GetAgentInfoPayloadSchema>;
export type SubscribePayload = z.infer<typeof SubscribePayloadSchema>;
export type UnsubscribePayload = z.infer<typeof UnsubscribePayloadSchema>;
export type ExecuteAbilityPayload = z.infer<typeof ExecuteAbilityPayloadSchema>;
export type HITLResponsePayload = z.infer<typeof HITLResponsePayloadSchema>;
export type InitClusterPayload = z.infer<typeof InitClusterPayloadSchema>;
export type ShutdownClusterPayload = z.infer<typeof ShutdownClusterPayloadSchema>;
export type ClusterStatusPayload = z.infer<typeof ClusterStatusPayloadSchema>;
export type PersistSavePayload = z.infer<typeof PersistSavePayloadSchema>;
export type PersistLoadPayload = z.infer<typeof PersistLoadPayloadSchema>;
export type PersistDeletePayload = z.infer<typeof PersistDeletePayloadSchema>;
export type PersistListPayload = z.infer<typeof PersistListPayloadSchema>;
export type CreateWorkspacePayload = z.infer<typeof CreateWorkspacePayloadSchema>;
export type DestroyWorkspacePayload = z.infer<typeof DestroyWorkspacePayloadSchema>;
export type WorkspaceSnapshotPayload = z.infer<typeof WorkspaceSnapshotPayloadSchema>;
export type WorkspaceRollbackPayload = z.infer<typeof WorkspaceRollbackPayloadSchema>;
export type WorkspaceDiffPayload = z.infer<typeof WorkspaceDiffPayloadSchema>;
export type WorkspaceStatusPayload = z.infer<typeof WorkspaceStatusPayloadSchema>;
export type AgentSpawnedPayload = z.infer<typeof AgentSpawnedPayloadSchema>;
export type AgentTerminatedPayload = z.infer<typeof AgentTerminatedPayloadSchema>;
export type AgentResponsePayload = z.infer<typeof AgentResponsePayloadSchema>;
export type ActionChainUpdatedPayload = z.infer<typeof ActionChainUpdatedPayloadSchema>;
export type AgentErrorPayload = z.infer<typeof AgentErrorPayloadSchema>;
export type HealthStatusPayload = z.infer<typeof HealthStatusPayloadSchema>;
export type AbilityResultPayload = z.infer<typeof AbilityResultPayloadSchema>;
export type HITLRequestPayload = z.infer<typeof HITLRequestPayloadSchema>;
export type WorkspaceCreatedPayload = z.infer<typeof WorkspaceCreatedPayloadSchema>;
export type WorkspaceDestroyedPayload = z.infer<typeof WorkspaceDestroyedPayloadSchema>;
export type WorkspaceSnapshotCreatedPayload = z.infer<typeof WorkspaceSnapshotCreatedPayloadSchema>;
export type WorkspaceRolledBackPayload = z.infer<typeof WorkspaceRolledBackPayloadSchema>;
export type CommandResultPayload = z.infer<typeof CommandResultPayloadSchema>;
export type ErrorPayload = z.infer<typeof ErrorPayloadSchema>;
export type ManifestListPayload = z.infer<typeof ManifestListPayloadSchema>;
export type ManifestGetPayload = z.infer<typeof ManifestGetPayloadSchema>;
export type ManifestPutPayload = z.infer<typeof ManifestPutPayloadSchema>;
export type ManifestDeletePayload = z.infer<typeof ManifestDeletePayloadSchema>;
export type ManifestValidatePayload = z.infer<typeof ManifestValidatePayloadSchema>;
export type ManifestResolvePayload = z.infer<typeof ManifestResolvePayloadSchema>;
export type ManifestAbilityEventPayload = z.infer<typeof ManifestAbilityEventPayloadSchema>;
export type ManifestAgentEventPayload = z.infer<typeof ManifestAgentEventPayloadSchema>;
