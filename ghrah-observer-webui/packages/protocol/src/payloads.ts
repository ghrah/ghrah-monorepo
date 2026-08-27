import { z } from "zod";

export const AgentConfigPayloadSchema = z.object({
  name: z.string(),
  agent_id: z.string().optional(),
  agent_config_name: z.string().nullable().optional(),
  description: z.string().optional().default(""),
  system_prompt: z.string().optional().default(""),
  max_iterations: z.number().int().optional().default(10),
  communication_timeout: z.number().optional(),
  window: z.record(z.unknown()).nullable().optional(),
  context: z.record(z.unknown()).nullable().optional(),
  model_overrides: z.record(z.unknown()).nullable().optional(),
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
  agent_id: z.string().optional(),
  incarnation_id: z.string().optional(),
  recovery_mode: z.string().optional(),
  config: AgentConfigPayloadSchema,
});

export const AgentTerminatedPayloadSchema = z.object({
  name: z.string(),
  agent_id: z.string().optional(),
  incarnation_id: z.string().optional(),
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
  agent_id: z.string().optional(),
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

// ─── Task Payloads ───

export const TaskStatusSchema = z.enum([
  "pending",
  "in_progress",
  "blocked",
  "completed",
  "failed",
  "canceled",
]);

export const TaskPrioritySchema = z.enum(["low", "normal", "high", "urgent"]);

export const TaskInfoPayloadSchema = z.object({
  task_id: z.string(),
  project_id: z.string(),
  title: z.string(),
  description: z.string().optional().default(""),
  agent_name: z.string().nullable().optional(),
  status: TaskStatusSchema.optional().default("pending"),
  priority: TaskPrioritySchema.optional().default("normal"),
  parent_id: z.string().nullable().optional(),
  dependencies: z.array(z.string()).optional().default([]),
  result: z.unknown().nullable().optional(),
  error: z.string().nullable().optional(),
  created_at: z.string().optional().default(""),
  updated_at: z.string().optional().default(""),
  started_at: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  metadata: z.record(z.unknown()).optional().default({}),
});

export const TaskCreatePayloadSchema = z.object({
  title: z.string(),
  project_id: z.string(),
  description: z.string().optional().default(""),
  agent_name: z.string().nullable().optional(),
  priority: TaskPrioritySchema.optional().default("normal"),
  parent_id: z.string().nullable().optional(),
  dependencies: z.array(z.string()).optional().default([]),
  metadata: z.record(z.unknown()).optional().default({}),
});

export const TaskUpdatePayloadSchema = z.object({
  task_id: z.string(),
  title: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  agent_name: z.string().nullable().optional(),
  status: TaskStatusSchema.nullable().optional(),
  priority: TaskPrioritySchema.nullable().optional(),
  parent_id: z.string().nullable().optional(),
  dependencies: z.array(z.string()).nullable().optional(),
  result: z.unknown().nullable().optional(),
  error: z.string().nullable().optional(),
  metadata: z.record(z.unknown()).nullable().optional(),
  metadata_patch: z.record(z.unknown()).nullable().optional(),
  expected_version: z.number().int().nullable().optional(),
});

export const TaskIdPayloadSchema = z.object({
  task_id: z.string(),
});

export const TaskAssignPayloadSchema = z.object({
  task_id: z.string(),
  agent_name: z.string(),
});

export const TaskCompletePayloadSchema = z.object({
  task_id: z.string(),
  result: z.unknown().nullable().optional(),
});

export const TaskFailPayloadSchema = z.object({
  task_id: z.string(),
  error: z.string(),
});

export const TaskCancelPayloadSchema = z.object({
  task_id: z.string(),
  reason: z.string().nullable().optional(),
});

export const TaskBlockPayloadSchema = z.object({
  task_id: z.string(),
  reason: z.string().nullable().optional(),
});

export const TaskListPayloadSchema = z.object({
  agent_name: z.string().nullable().optional(),
  status: z
    .union([TaskStatusSchema, z.array(TaskStatusSchema)])
    .nullable()
    .optional(),
  parent_id: z.string().nullable().optional(),
  project_id: z.string().nullable().optional(),
  include_terminal: z.boolean().optional().default(true),
  limit: z.number().int().optional().default(100),
});

export const TaskDeletePayloadSchema = z.object({
  task_id: z.string(),
  force: z.boolean().optional().default(false),
});

export const TaskListResultPayloadSchema = z.object({
  tasks: z.array(TaskInfoPayloadSchema).optional().default([]),
  count: z.number().int().optional().default(0),
});

export const TaskEventPayloadSchema = z.object({
  task: TaskInfoPayloadSchema,
  previous_status: TaskStatusSchema.nullable().optional(),
  reason: z.string().nullable().optional(),
});

// ─── Project Payloads ───

export const ProjectStatusSchema = z.enum(["active", "paused", "stopped", "failed"]);

export const RecoveryActionSchema = z.enum(["resume", "pause", "drop"]);

export const PathGrantSchema = z.object({
  workspace_id: z.string(),
  subpath: z.string().optional().default("."),
});

export const WorkspaceMountSchema = z.object({
  workspace_id: z.string(),
  role: z.string().nullable().optional(),
  default_for_agents: z.boolean().optional().default(false),
});

export const WritableWorkspaceSpecSchema = z.object({
  locator: z.string(),
  name: z.string().optional().default(""),
  role: z.string().nullable().optional(),
  default_for_agents: z.boolean().optional().default(false),
});

export const AgentSpecSchema = z.object({
  agent_id: z.string().optional(),
  name: z.string(),
  cluster_id: z.string(),
  manifest_ref: z.string().optional().default(""),
  instance_manifest_path: z.string().optional().default(""),
  system_prompt: z.string().optional().default(""),
  abilities: z.array(z.string()).nullable().optional(),
  path_grants: z.array(PathGrantSchema).optional().default([]),
});

export const ProjectInfoPayloadSchema = z.object({
  project_id: z.string(),
  name: z.string(),
  description: z.string().optional().default(""),
  project_root_locator: z.string().optional().default(""),
  manifest_ref: z.string().optional().default(""),
  cluster_ids: z.array(z.string()).optional().default([]),
  workspaces: z.array(WorkspaceMountSchema).optional().default([]),
  agents: z.array(AgentSpecSchema).optional().default([]),
  task_ids: z.array(z.string()).optional().default([]),
  status: ProjectStatusSchema.optional().default("active"),
  recovery: RecoveryActionSchema.optional().default("resume"),
  version: z.number().int().optional().default(1),
  created_at: z.string().optional().default(""),
  updated_at: z.string().optional().default(""),
  deleted_at: z.string().nullable().optional(),
});

export const ProjectCreatePayloadSchema = z
  .object({
    name: z.string(),
    description: z.string().optional().default(""),
    project_root_locator: z.string().optional().default(""),
    writable_workspaces: z.array(WritableWorkspaceSpecSchema).optional().default([]),
    manifest_ref: z.string().optional().default(""),
    recovery: RecoveryActionSchema.optional().default("resume"),
  })
  .strict();

export const ProjectUpdatePayloadSchema = z
  .object({
    project_id: z.string(),
    name: z.string().nullable().optional(),
    description: z.string().nullable().optional(),
    manifest_ref: z.string().nullable().optional(),
    expected_version: z.number().int().nullable().optional(),
  })
  .strict();

export const ProjectIdPayloadSchema = z.object({
  project_id: z.string(),
});

export const ProjectDeletePayloadSchema = z.object({
  project_id: z.string(),
  force: z.boolean().optional().default(false),
  purge_storage: z.boolean().optional().default(false),
});

export const ProjectListPayloadSchema = z.object({
  status: ProjectStatusSchema.nullable().optional(),
  include_deleted: z.boolean().optional().default(false),
});

export const ProjectAddAgentPayloadSchema = z.object({
  project_id: z.string(),
  agent: AgentSpecSchema,
  expected_version: z.number().int().nullable().optional(),
});

export const ProjectRemoveAgentPayloadSchema = z.object({
  project_id: z.string(),
  agent_name: z.string(),
  expected_version: z.number().int().nullable().optional(),
});

export const ProjectLinkTaskPayloadSchema = z.object({
  project_id: z.string(),
  task_id: z.string(),
  expected_version: z.number().int().nullable().optional(),
});

export const ProjectUnlinkTaskPayloadSchema = z.object({
  project_id: z.string(),
  task_id: z.string(),
  expected_version: z.number().int().nullable().optional(),
});

export const ProjectSetRecoveryPayloadSchema = z.object({
  project_id: z.string(),
  recovery: RecoveryActionSchema.optional().default("resume"),
  expected_version: z.number().int().nullable().optional(),
});

export const ProjectListResultPayloadSchema = z.object({
  projects: z.array(ProjectInfoPayloadSchema).optional().default([]),
  count: z.number().int().optional().default(0),
});

// ─── Project Event Payloads ───

export const ProjectEventPayloadSchema = z.object({
  project: ProjectInfoPayloadSchema,
});

export const ProjectAgentEventPayloadSchema = z.object({
  project: ProjectInfoPayloadSchema,
  agent_name: z.string(),
});

// ─── Room Payloads ───

export const RoomSubjectTypeSchema = z.enum(["agent", "human"]);

export const RoomStatusSchema = z.enum(["active", "archived"]);

export const RoomMemberSchema = z.object({
  subject: z.string(),
  subject_type: RoomSubjectTypeSchema,
  /** 可读名称；subject 对 agent 成员保存 project-scoped 稳定 ID。 */
  subject_name: z.string().optional(),
  joined_at: z.string().optional().default(""),
});

export const RoomInfoPayloadSchema = z.object({
  room_id: z.string(),
  project_id: z.string(),
  name: z.string(),
  status: RoomStatusSchema.optional().default("active"),
  members: z.array(RoomMemberSchema).optional().default([]),
  seq_watermark: z.number().int().optional().default(0),
  version: z.number().int().optional().default(1),
  created_at: z.string().optional().default(""),
  updated_at: z.string().optional().default(""),
});

export const RoomLogEntryPayloadSchema = z.object({
  id: z.string(),
  room_id: z.string(),
  seq: z.number().int(),
  author: z.string(),
  author_type: RoomSubjectTypeSchema,
  timestamp: z.number(),
  data: z.record(z.unknown()).optional().default({}),
});

export const RoomCreatePayloadSchema = z.object({
  project_id: z.string(),
  name: z.string(),
});

export const RoomListPayloadSchema = z.object({
  project_id: z.string().nullable().optional(),
  status: RoomStatusSchema.nullable().optional(),
});

export const RoomIdPayloadSchema = z.object({
  room_id: z.string(),
});

export const RoomUpdatePayloadSchema = z.object({
  room_id: z.string(),
  name: z.string().nullable().optional(),
  expected_version: z.number().int().nullable().optional(),
});

export const RoomDeletePayloadSchema = z.object({
  room_id: z.string(),
  force: z.boolean().optional().default(false),
});

export const RoomJoinPayloadSchema = z.object({
  room_id: z.string(),
  subject: z.string(),
  subject_type: RoomSubjectTypeSchema,
  subject_name: z.string().optional(),
});

export const RoomLeavePayloadSchema = z.object({
  room_id: z.string(),
  subject: z.string(),
});

export const RoomGetLogPayloadSchema = z.object({
  room_id: z.string(),
  since_seq: z.number().int().nullable().optional(),
  limit: z.number().int().optional().default(100),
});

export const RoomSendPayloadSchema = z.object({
  room_id: z.string(),
  author: z.string(),
  author_type: RoomSubjectTypeSchema,
  data: z.record(z.unknown()).optional().default({}),
});

export const RoomListResultPayloadSchema = z.object({
  rooms: z.array(RoomInfoPayloadSchema).optional().default([]),
  count: z.number().int().optional().default(0),
});

export const RoomLogResultPayloadSchema = z.object({
  entries: z.array(RoomLogEntryPayloadSchema).optional().default([]),
  count: z.number().int().optional().default(0),
});

// ─── Room Event Payloads ───

export const RoomEventPayloadSchema = z.object({
  room: RoomInfoPayloadSchema,
});

export const RoomDeletedEventPayloadSchema = z.object({
  room_id: z.string(),
  project_id: z.string(),
});

export const RoomMemberEventPayloadSchema = z.object({
  room: RoomInfoPayloadSchema,
  member: RoomMemberSchema.nullable().optional(),
  subject: z.string().nullable().optional(),
});

export const RoomLogEventPayloadSchema = z.object({
  entry: RoomLogEntryPayloadSchema,
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
export type TaskStatus = z.infer<typeof TaskStatusSchema>;
export type TaskPriority = z.infer<typeof TaskPrioritySchema>;
export type TaskInfoPayload = z.infer<typeof TaskInfoPayloadSchema>;
export type TaskCreatePayload = z.infer<typeof TaskCreatePayloadSchema>;
export type TaskUpdatePayload = z.infer<typeof TaskUpdatePayloadSchema>;
export type TaskIdPayload = z.infer<typeof TaskIdPayloadSchema>;
export type TaskAssignPayload = z.infer<typeof TaskAssignPayloadSchema>;
export type TaskCompletePayload = z.infer<typeof TaskCompletePayloadSchema>;
export type TaskFailPayload = z.infer<typeof TaskFailPayloadSchema>;
export type TaskCancelPayload = z.infer<typeof TaskCancelPayloadSchema>;
export type TaskBlockPayload = z.infer<typeof TaskBlockPayloadSchema>;
export type TaskListPayload = z.infer<typeof TaskListPayloadSchema>;
export type TaskDeletePayload = z.infer<typeof TaskDeletePayloadSchema>;
export type TaskListResultPayload = z.infer<typeof TaskListResultPayloadSchema>;
export type TaskEventPayload = z.infer<typeof TaskEventPayloadSchema>;
export type ProjectStatus = z.infer<typeof ProjectStatusSchema>;
export type RecoveryAction = z.infer<typeof RecoveryActionSchema>;
export type PathGrant = z.infer<typeof PathGrantSchema>;
export type WorkspaceMount = z.infer<typeof WorkspaceMountSchema>;
export type WritableWorkspaceSpec = z.infer<typeof WritableWorkspaceSpecSchema>;
export type AgentSpec = z.infer<typeof AgentSpecSchema>;
export type ProjectInfoPayload = z.infer<typeof ProjectInfoPayloadSchema>;
export type ProjectCreatePayload = z.infer<typeof ProjectCreatePayloadSchema>;
export type ProjectUpdatePayload = z.infer<typeof ProjectUpdatePayloadSchema>;
export type ProjectIdPayload = z.infer<typeof ProjectIdPayloadSchema>;
export type ProjectDeletePayload = z.infer<typeof ProjectDeletePayloadSchema>;
export type ProjectListPayload = z.infer<typeof ProjectListPayloadSchema>;
export type ProjectAddAgentPayload = z.infer<typeof ProjectAddAgentPayloadSchema>;
export type ProjectRemoveAgentPayload = z.infer<typeof ProjectRemoveAgentPayloadSchema>;
export type ProjectLinkTaskPayload = z.infer<typeof ProjectLinkTaskPayloadSchema>;
export type ProjectUnlinkTaskPayload = z.infer<typeof ProjectUnlinkTaskPayloadSchema>;
export type ProjectSetRecoveryPayload = z.infer<typeof ProjectSetRecoveryPayloadSchema>;
export type ProjectListResultPayload = z.infer<typeof ProjectListResultPayloadSchema>;
export type ProjectEventPayload = z.infer<typeof ProjectEventPayloadSchema>;
export type ProjectAgentEventPayload = z.infer<typeof ProjectAgentEventPayloadSchema>;
export type RoomSubjectType = z.infer<typeof RoomSubjectTypeSchema>;
export type RoomStatus = z.infer<typeof RoomStatusSchema>;
export type RoomMember = z.infer<typeof RoomMemberSchema>;
export type RoomInfoPayload = z.infer<typeof RoomInfoPayloadSchema>;
export type RoomLogEntryPayload = z.infer<typeof RoomLogEntryPayloadSchema>;
export type RoomCreatePayload = z.infer<typeof RoomCreatePayloadSchema>;
export type RoomListPayload = z.infer<typeof RoomListPayloadSchema>;
export type RoomIdPayload = z.infer<typeof RoomIdPayloadSchema>;
export type RoomUpdatePayload = z.infer<typeof RoomUpdatePayloadSchema>;
export type RoomDeletePayload = z.infer<typeof RoomDeletePayloadSchema>;
export type RoomJoinPayload = z.infer<typeof RoomJoinPayloadSchema>;
export type RoomLeavePayload = z.infer<typeof RoomLeavePayloadSchema>;
export type RoomGetLogPayload = z.infer<typeof RoomGetLogPayloadSchema>;
export type RoomSendPayload = z.infer<typeof RoomSendPayloadSchema>;
export type RoomListResultPayload = z.infer<typeof RoomListResultPayloadSchema>;
export type RoomLogResultPayload = z.infer<typeof RoomLogResultPayloadSchema>;
export type RoomEventPayload = z.infer<typeof RoomEventPayloadSchema>;
export type RoomDeletedEventPayload = z.infer<typeof RoomDeletedEventPayloadSchema>;
export type RoomMemberEventPayload = z.infer<typeof RoomMemberEventPayloadSchema>;
export type RoomLogEventPayload = z.infer<typeof RoomLogEventPayloadSchema>;
