import { z } from "zod";

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
  agent_id: z.string().nullable().optional(),
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
  agent_id: z.string().nullable().optional(),
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
  agent_id: z.string().nullable().optional(),
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
  agent_id: z.string().optional().default(""),
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
  agent_id: z.string().nullable().optional(),
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
  agent_id: z.string().nullable().optional(),
  agent_name: z.string().nullable().optional(),
});

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
