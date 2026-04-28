import { describe, expect, it } from "vitest";
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

describe("AgentConfigPayloadSchema", () => {
  it("parses with required name only", () => {
    const result = AgentConfigPayloadSchema.parse({ name: "test-agent" });
    expect(result.name).toBe("test-agent");
    expect(result.max_iterations).toBe(10);
    expect(result.description).toBe("");
    expect(result.system_prompt).toBe("");
    expect(result.agent_config_name).toBeUndefined();
    expect(result.gateway_url).toBeUndefined();
  });

  it("parses with all fields", () => {
    const result = AgentConfigPayloadSchema.parse({
      name: "agent-1",
      agent_config_name: "default",
      description: "desc",
      system_prompt: "prompt",
      max_iterations: 5,
      gateway_url: "ws://localhost:8080",
    });
    expect(result.max_iterations).toBe(5);
    expect(result.agent_config_name).toBe("default");
  });

  it("rejects missing name", () => {
    expect(() => AgentConfigPayloadSchema.parse({})).toThrow();
  });
});

describe("AbilityDefinitionPayloadSchema", () => {
  it("parses with required ability_type", () => {
    const result = AbilityDefinitionPayloadSchema.parse({ ability_type: "bash" });
    expect(result.ability_type).toBe("bash");
    expect(result.params).toEqual({});
  });

  it("parses with params", () => {
    const result = AbilityDefinitionPayloadSchema.parse({
      ability_type: "bash",
      params: { command: "ls" },
    });
    expect(result.params).toEqual({ command: "ls" });
  });
});

describe("SpawnAgentPayloadSchema", () => {
  it("parses with config only", () => {
    const result = SpawnAgentPayloadSchema.parse({
      config: { name: "agent-1" },
    });
    expect(result.config.name).toBe("agent-1");
    expect(result.abilities).toBeUndefined();
  });

  it("parses with abilities array", () => {
    const result = SpawnAgentPayloadSchema.parse({
      config: { name: "agent-1" },
      abilities: [{ ability_type: "bash" }],
    });
    expect(result.abilities).toHaveLength(1);
  });
});

describe("TerminateAgentPayloadSchema", () => {
  it("parses with name", () => {
    const result = TerminateAgentPayloadSchema.parse({ name: "agent-1" });
    expect(result.name).toBe("agent-1");
  });

  it("rejects missing name", () => {
    expect(() => TerminateAgentPayloadSchema.parse({})).toThrow();
  });
});

describe("SendMessagePayloadSchema", () => {
  it("parses with required fields and default sender", () => {
    const result = SendMessagePayloadSchema.parse({
      target: "agent-1",
      content: "hello",
    });
    expect(result.target).toBe("agent-1");
    expect(result.content).toBe("hello");
    expect(result.sender).toBe("user");
  });

  it("parses with custom sender", () => {
    const result = SendMessagePayloadSchema.parse({
      target: "agent-1",
      content: "hello",
      sender: "agent-2",
    });
    expect(result.sender).toBe("agent-2");
  });
});

describe("BroadcastMessagePayloadSchema", () => {
  it("parses with content and default sender", () => {
    const result = BroadcastMessagePayloadSchema.parse({ content: "hello all" });
    expect(result.content).toBe("hello all");
    expect(result.sender).toBe("user");
  });
});

describe("RegisterAbilityPayloadSchema", () => {
  it("parses with agent_name and ability", () => {
    const result = RegisterAbilityPayloadSchema.parse({
      agent_name: "agent-1",
      ability: { ability_type: "bash" },
    });
    expect(result.agent_name).toBe("agent-1");
    expect(result.ability.ability_type).toBe("bash");
  });
});

describe("UnregisterAbilityPayloadSchema", () => {
  it("parses with agent_name and ability_name", () => {
    const result = UnregisterAbilityPayloadSchema.parse({
      agent_name: "agent-1",
      ability_name: "bash",
    });
    expect(result.ability_name).toBe("bash");
  });
});

describe("ListAgentsPayloadSchema", () => {
  it("parses empty object", () => {
    const result = ListAgentsPayloadSchema.parse({});
    expect(result).toEqual({});
  });
});

describe("HealthCheckPayloadSchema", () => {
  it("parses empty object", () => {
    const result = HealthCheckPayloadSchema.parse({});
    expect(result).toEqual({});
  });
});

describe("DelegatePayloadSchema", () => {
  it("parses with all fields", () => {
    const result = DelegatePayloadSchema.parse({
      from_agent: "a1",
      to_agent: "a2",
      content: "delegate msg",
    });
    expect(result.from_agent).toBe("a1");
    expect(result.to_agent).toBe("a2");
  });
});

describe("GetAgentInfoPayloadSchema", () => {
  it("parses with name", () => {
    const result = GetAgentInfoPayloadSchema.parse({ name: "agent-1" });
    expect(result.name).toBe("agent-1");
  });
});

describe("SubscribePayloadSchema", () => {
  it("parses with agent_names only", () => {
    const result = SubscribePayloadSchema.parse({
      agent_names: ["agent-1", "agent-2"],
    });
    expect(result.agent_names).toEqual(["agent-1", "agent-2"]);
    expect(result.event_types).toBeUndefined();
  });

  it("parses with null values", () => {
    const result = SubscribePayloadSchema.parse({
      agent_names: null,
      event_types: null,
    });
    expect(result.agent_names).toBeNull();
  });

  it("parses empty object (subscribe all)", () => {
    const result = SubscribePayloadSchema.parse({});
    expect(result.agent_names).toBeUndefined();
    expect(result.event_types).toBeUndefined();
  });
});

describe("UnsubscribePayloadSchema", () => {
  it("parses same as SubscribePayloadSchema", () => {
    const result = UnsubscribePayloadSchema.parse({
      agent_names: ["agent-1"],
    });
    expect(result.agent_names).toEqual(["agent-1"]);
  });
});

describe("ExecuteAbilityPayloadSchema", () => {
  it("parses with required fields and default tool_args", () => {
    const result = ExecuteAbilityPayloadSchema.parse({
      request_id: "req-001",
      agent_name: "agent-1",
      ability_name: "read_file",
    });
    expect(result.request_id).toBe("req-001");
    expect(result.tool_args).toEqual({});
  });

  it("parses with tool_args", () => {
    const result = ExecuteAbilityPayloadSchema.parse({
      request_id: "req-001",
      agent_name: "agent-1",
      ability_name: "read_file",
      tool_args: { path: "/tmp/test.txt" },
    });
    expect(result.tool_args).toEqual({ path: "/tmp/test.txt" });
  });
});

describe("HITLResponsePayloadSchema", () => {
  it("parses with required fields", () => {
    const result = HITLResponsePayloadSchema.parse({
      promise_id: "p-001",
      approved: true,
    });
    expect(result.promise_id).toBe("p-001");
    expect(result.approved).toBe(true);
    expect(result.reason).toBeUndefined();
  });

  it("parses with reason", () => {
    const result = HITLResponsePayloadSchema.parse({
      promise_id: "p-001",
      approved: false,
      reason: "unsafe",
    });
    expect(result.reason).toBe("unsafe");
  });
});

describe("InitClusterPayloadSchema", () => {
  it("parses with default config", () => {
    const result = InitClusterPayloadSchema.parse({});
    expect(result.config).toEqual({});
  });
});

describe("ShutdownClusterPayloadSchema", () => {
  it("parses with default config", () => {
    const result = ShutdownClusterPayloadSchema.parse({});
    expect(result.config).toEqual({});
  });
});

describe("ClusterStatusPayloadSchema", () => {
  it("parses empty object", () => {
    const result = ClusterStatusPayloadSchema.parse({});
    expect(result).toEqual({});
  });
});

describe("PersistSavePayloadSchema", () => {
  it("parses with required fields and default namespace", () => {
    const result = PersistSavePayloadSchema.parse({
      key: "ctx-1",
      data: { messages: [] },
    });
    expect(result.key).toBe("ctx-1");
    expect(result.namespace).toBe("default");
  });

  it("parses with custom namespace", () => {
    const result = PersistSavePayloadSchema.parse({
      key: "ctx-1",
      data: {},
      namespace: "agent-1",
    });
    expect(result.namespace).toBe("agent-1");
  });
});

describe("PersistLoadPayloadSchema", () => {
  it("parses with key and default namespace", () => {
    const result = PersistLoadPayloadSchema.parse({ key: "ctx-1" });
    expect(result.namespace).toBe("default");
  });
});

describe("PersistDeletePayloadSchema", () => {
  it("parses with key and default namespace", () => {
    const result = PersistDeletePayloadSchema.parse({ key: "ctx-1" });
    expect(result.namespace).toBe("default");
  });
});

describe("PersistListPayloadSchema", () => {
  it("parses with defaults", () => {
    const result = PersistListPayloadSchema.parse({});
    expect(result.namespace).toBe("default");
    expect(result.prefix).toBeUndefined();
  });

  it("parses with namespace and prefix", () => {
    const result = PersistListPayloadSchema.parse({
      namespace: "agent-1",
      prefix: "ctx",
    });
    expect(result.namespace).toBe("agent-1");
    expect(result.prefix).toBe("ctx");
  });
});

describe("Workspace command payload schemas", () => {
  it("CreateWorkspacePayloadSchema", () => {
    const result = CreateWorkspacePayloadSchema.parse({ agent_name: "agent-1" });
    expect(result.agent_name).toBe("agent-1");
  });

  it("DestroyWorkspacePayloadSchema", () => {
    const result = DestroyWorkspacePayloadSchema.parse({ agent_name: "agent-1" });
    expect(result.agent_name).toBe("agent-1");
  });

  it("WorkspaceSnapshotPayloadSchema with default message", () => {
    const result = WorkspaceSnapshotPayloadSchema.parse({ agent_name: "agent-1" });
    expect(result.message).toBe("");
  });

  it("WorkspaceRollbackPayloadSchema", () => {
    const result = WorkspaceRollbackPayloadSchema.parse({
      agent_name: "agent-1",
      snapshot_id: "snap-001",
    });
    expect(result.snapshot_id).toBe("snap-001");
  });

  it("WorkspaceDiffPayloadSchema with optional snapshot_id", () => {
    const result = WorkspaceDiffPayloadSchema.parse({ agent_name: "agent-1" });
    expect(result.snapshot_id).toBeUndefined();
  });

  it("WorkspaceStatusPayloadSchema", () => {
    const result = WorkspaceStatusPayloadSchema.parse({ agent_name: "agent-1" });
    expect(result.agent_name).toBe("agent-1");
  });
});

describe("Event payload schemas", () => {
  it("AgentSpawnedPayloadSchema", () => {
    const result = AgentSpawnedPayloadSchema.parse({
      name: "agent-1",
      config: { name: "agent-1" },
    });
    expect(result.name).toBe("agent-1");
    expect(result.config.max_iterations).toBe(10);
  });

  it("AgentTerminatedPayloadSchema", () => {
    const result = AgentTerminatedPayloadSchema.parse({ name: "agent-1" });
    expect(result.name).toBe("agent-1");
  });

  it("AgentResponsePayloadSchema with defaults", () => {
    const result = AgentResponsePayloadSchema.parse({
      sender: "agent-1",
      recipient: "user",
      content: "result",
    });
    expect(result.message_type).toBe("result");
    expect(result.metadata).toEqual({});
  });

  it("ActionChainUpdatedPayloadSchema with default node", () => {
    const result = ActionChainUpdatedPayloadSchema.parse({
      agent_name: "agent-1",
    });
    expect(result.node).toEqual({});
  });

  it("AgentErrorPayloadSchema", () => {
    const result = AgentErrorPayloadSchema.parse({
      agent_name: "agent-1",
      error: "crashed",
    });
    expect(result.error).toBe("crashed");
  });

  it("HealthStatusPayloadSchema", () => {
    const result = HealthStatusPayloadSchema.parse({
      status: { agent_1: true, agent_2: false },
    });
    expect(result.status).toEqual({ agent_1: true, agent_2: false });
  });

  it("AbilityResultPayloadSchema success", () => {
    const result = AbilityResultPayloadSchema.parse({
      request_id: "req-001",
      agent_name: "agent-1",
      ability_name: "read_file",
      success: true,
      result: { content: "file data" },
    });
    expect(result.success).toBe(true);
    expect(result.error).toBeUndefined();
  });

  it("AbilityResultPayloadSchema failure", () => {
    const result = AbilityResultPayloadSchema.parse({
      request_id: "req-002",
      agent_name: "agent-1",
      ability_name: "write_file",
      success: false,
      error: "Permission denied",
    });
    expect(result.success).toBe(false);
    expect(result.result).toBeUndefined();
  });

  it("HITLRequestPayloadSchema with defaults", () => {
    const result = HITLRequestPayloadSchema.parse({
      promise_id: "p-001",
      agent_name: "agent-1",
      ability_name: "bash",
    });
    expect(result.tool_args).toEqual({});
    expect(result.context).toEqual({});
  });
});

describe("Workspace event payload schemas", () => {
  it("WorkspaceCreatedPayloadSchema", () => {
    const result = WorkspaceCreatedPayloadSchema.parse({
      agent_name: "agent-1",
      path: "/tmp/agent-1",
    });
    expect(result.path).toBe("/tmp/agent-1");
  });

  it("WorkspaceDestroyedPayloadSchema", () => {
    const result = WorkspaceDestroyedPayloadSchema.parse({ agent_name: "agent-1" });
    expect(result.agent_name).toBe("agent-1");
  });

  it("WorkspaceSnapshotCreatedPayloadSchema with default message", () => {
    const result = WorkspaceSnapshotCreatedPayloadSchema.parse({
      agent_name: "agent-1",
      snapshot_id: "snap-001",
    });
    expect(result.message).toBe("");
  });

  it("WorkspaceRolledBackPayloadSchema", () => {
    const result = WorkspaceRolledBackPayloadSchema.parse({
      agent_name: "agent-1",
      snapshot_id: "snap-001",
    });
    expect(result.snapshot_id).toBe("snap-001");
  });
});

describe("System payload schemas", () => {
  it("CommandResultPayloadSchema success", () => {
    const result = CommandResultPayloadSchema.parse({
      request_id: "req-001",
      success: true,
      data: { name: "agent-1" },
    });
    expect(result.success).toBe(true);
    expect(result.error).toBeUndefined();
  });

  it("CommandResultPayloadSchema failure", () => {
    const result = CommandResultPayloadSchema.parse({
      request_id: "req-001",
      success: false,
      error: "Not found",
    });
    expect(result.data).toBeUndefined();
  });

  it("ErrorPayloadSchema", () => {
    const result = ErrorPayloadSchema.parse({
      code: "UNKNOWN_COMMAND",
      message: "Unknown command type: foo",
    });
    expect(result.code).toBe("UNKNOWN_COMMAND");
    expect(result.details).toBeUndefined();
  });

  it("ErrorPayloadSchema with details", () => {
    const result = ErrorPayloadSchema.parse({
      code: "VALIDATION_ERROR",
      message: "Invalid payload",
      details: { field: "name" },
    });
    expect(result.details).toEqual({ field: "name" });
  });
});
