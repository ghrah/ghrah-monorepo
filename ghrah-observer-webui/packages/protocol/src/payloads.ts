import { z } from "zod";

export const AgentConfigPayloadSchema = z.object({
  name: z.string(),
  agent_config_name: z.string().nullable().optional(),
  description: z.string().optional().default(""),
  system_prompt: z.string().optional().default(""),
  max_iterations: z.number().int().optional().default(10),
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
  cluster_id: z.string(),
  config: z.record(z.unknown()).optional().default({}),
});

export const ShutdownClusterPayloadSchema = z.object({
  cluster_id: z.string(),
  config: z.record(z.unknown()).optional().default({}),
});

export const ClusterStatusPayloadSchema = z.object({
  cluster_id: z.string(),
});

export const ListClustersPayloadSchema = z.object({});

export const ClusterInfoPayloadSchema = z.object({
  cluster_id: z.string(),
  active_agents: z.number(),
  status: z.string(),
  bound: z.boolean(),
});

export const ListClustersResultPayloadSchema = z.object({
  clusters: z.array(ClusterInfoPayloadSchema),
});

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

export const WorkspaceRegisterPayloadSchema = z.object({
  locator: z.string(),
  name: z.string().optional().default(""),
  provider_type: z.string().nullable().optional(),
});

export const WorkspaceGetPayloadSchema = z.object({
  workspace_id: z.string(),
});

export const WorkspaceListPayloadSchema = z.object({
  provider_type: z.string().nullable().optional(),
});

export const AgentSpawnedPayloadSchema = z.object({
  name: z.string(),
  config: AgentConfigPayloadSchema,
});

export const AgentTerminatedPayloadSchema = z.object({
  name: z.string(),
});

export const ContentBlockSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("text"),
    text: z.string(),
  }),
  z.object({
    type: z.literal("reasoning"),
    reasoning: z.string(),
    incomplete: z.boolean().optional().default(false),
  }),
  z.object({
    type: z.literal("image"),
    url: z.string().nullable().optional(),
    base64: z.string().nullable().optional(),
    mime_type: z.string().nullable().optional(),
  }),
  z.object({
    type: z.literal("audio"),
    data: z.string(),
    mime_type: z.string(),
  }),
  z.object({
    type: z.literal("file"),
    url: z.string().nullable().optional(),
    base64: z.string().nullable().optional(),
    mime_type: z.string().nullable().optional(),
    filename: z.string().nullable().optional(),
  }),
  z.object({
    type: z.literal("tool_call"),
    id: z.string(),
    name: z.string(),
    arguments: z.record(z.unknown()),
  }),
  z.object({
    type: z.literal("tool_result"),
    tool_call_id: z.string(),
    name: z.string().nullable().optional(),
    content: z.string(),
    success: z.boolean().optional().default(true),
    error: z.string().nullable().optional(),
  }),
  z.object({
    type: z.literal("error"),
    error_type: z.string(),
    message: z.string(),
    details: z.record(z.unknown()).nullable().optional(),
  }),
]);

export type ContentBlock = z.infer<typeof ContentBlockSchema>;

export const ChatMessageWireSchema = z.object({
  role: z.enum(["system", "user", "ai", "tool"]).default("user"),
  content_blocks: z.array(ContentBlockSchema).optional().default([]),
  source: z.string().nullable().optional(),
  metadata: z.record(z.unknown()).optional().default({}),
});
export type ChatMessageWire = z.infer<typeof ChatMessageWireSchema>;

export const ActionResultItemSchema = z.object({
  ability_name: z.string(),
  action_result: z
    .object({
      outcome: z.enum(["success", "failure", "needs_input", "delegate"]).optional(),
      data: z.record(z.unknown()).optional().default({}),
      next_action_hint: z.string().nullable().optional(),
    })
    .nullable()
    .optional(),
});
export type ActionResultItem = z.infer<typeof ActionResultItemSchema>;

export const ActionNodeSchema = z.object({
  id: z.string().optional().default(""),
  parent_id: z.string().nullable().optional(),
  agent_name: z.string().optional().default(""),
  timestamp: z.string().optional(),
  iteration: z.number().int().optional().default(0),
  ability_names: z.array(z.string()).optional().default([]),
  agent_state: z.record(z.unknown()).optional().default({}),
  messages_delta: z.array(ChatMessageWireSchema).optional().default([]),
  messages_snapshot: z.array(ChatMessageWireSchema).nullable().optional(),
  is_snapshot: z.boolean().optional().default(false),
  action_results: z.array(ActionResultItemSchema).optional().default([]),
  metadata: z.record(z.unknown()).optional().default({}),
  branch_name: z.string().optional().default("main"),
  session_id: z.string().optional().default(""),
});
export type ActionNode = z.infer<typeof ActionNodeSchema>;

export const AgentResponsePayloadSchema = z.object({
  sender: z.string(),
  recipient: z.string(),
  content: z.string(),
  content_blocks: z.array(ContentBlockSchema).nullable().optional(),
  message_type: z.string().optional().default("result"),
  metadata: z.record(z.unknown()).optional().default({}),
});

export const ActionChainUpdatedPayloadSchema = z.object({
  agent_name: z.string(),
  node: ActionNodeSchema.optional().default({}),
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
export type ListClustersPayload = z.infer<typeof ListClustersPayloadSchema>;
export type ClusterInfoPayload = z.infer<typeof ClusterInfoPayloadSchema>;
export type ListClustersResultPayload = z.infer<typeof ListClustersResultPayloadSchema>;
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
export type WorkspaceRegisterPayload = z.infer<typeof WorkspaceRegisterPayloadSchema>;
export type WorkspaceGetPayload = z.infer<typeof WorkspaceGetPayloadSchema>;
export type WorkspaceListPayload = z.infer<typeof WorkspaceListPayloadSchema>;
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
