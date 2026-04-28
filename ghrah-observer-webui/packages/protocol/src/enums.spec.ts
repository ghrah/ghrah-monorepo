import { describe, expect, it } from "vitest";
import {
  ClientType,
  CommandType,
  EventType,
  PERSIST_COMMANDS,
  SUBJECT_FORWARD_COMMANDS,
  SystemType,
  WORKSPACE_COMMANDS,
} from "./enums.js";

describe("ClientType", () => {
  it("has correct values matching Python protocol", () => {
    expect(ClientType.SUBJECT).toBe("subject");
    expect(ClientType.OBSERVER).toBe("observer");
    expect(ClientType.CORE).toBe("core");
  });

  it("has exactly 3 members", () => {
    expect(Object.values(ClientType)).toHaveLength(3);
  });
});

describe("CommandType", () => {
  const PYTHON_COMMAND_VALUES = new Set([
    "spawn_agent",
    "terminate_agent",
    "send_message",
    "broadcast_message",
    "register_ability",
    "unregister_ability",
    "list_agents",
    "health_check",
    "delegate",
    "get_agent_info",
    "init_cluster",
    "shutdown_cluster",
    "cluster_status",
    "subscribe",
    "unsubscribe",
    "execute_ability",
    "hitl_response",
    "persist_save_node",
    "persist_load_node",
    "persist_load_chain",
    "persist_save_chain_meta",
    "persist_load_chain_meta",
    "persist_save_messages",
    "persist_load_messages",
    "persist_delete_chain",
    "persist_list_agents",
    "create_workspace",
    "destroy_workspace",
    "workspace_snapshot",
    "workspace_rollback",
    "workspace_diff",
    "workspace_status",
  ]);

  it("has exactly 27 values matching Python CommandType", () => {
    const tsValues = new Set(Object.values(CommandType));
    expect(tsValues).toEqual(PYTHON_COMMAND_VALUES);
  });

  it("has no duplicate values", () => {
    const values = Object.values(CommandType);
    expect(new Set(values).size).toBe(values.length);
  });
});

describe("EventType", () => {
  const PYTHON_EVENT_VALUES = new Set([
    "agent_spawned",
    "agent_terminated",
    "agent_response",
    "action_chain_updated",
    "agent_error",
    "health_status",
    "ability_result",
    "hitl_request",
    "hitl_response",
    "workspace_created",
    "workspace_destroyed",
    "workspace_snapshot_created",
    "workspace_rolled_back",
  ]);

  it("has exactly 13 values matching Python EventType", () => {
    const tsValues = new Set(Object.values(EventType));
    expect(tsValues).toEqual(PYTHON_EVENT_VALUES);
  });
});

describe("SystemType", () => {
  it("has correct values matching Python SystemType", () => {
    expect(SystemType.COMMAND_RESULT).toBe("command_result");
    expect(SystemType.PING).toBe("ping");
    expect(SystemType.PONG).toBe("pong");
    expect(SystemType.ERROR).toBe("error");
  });

  it("has exactly 4 members", () => {
    expect(Object.values(SystemType)).toHaveLength(4);
  });
});

describe("PERSIST_COMMANDS", () => {
  const PYTHON_PERSIST = new Set([
    "persist_save_node",
    "persist_load_node",
    "persist_load_chain",
    "persist_save_chain_meta",
    "persist_load_chain_meta",
    "persist_save_messages",
    "persist_load_messages",
    "persist_delete_chain",
    "persist_list_agents",
  ]);

  it("contains exactly 9 persist command values", () => {
    expect(PERSIST_COMMANDS).toEqual(PYTHON_PERSIST);
  });
});

describe("SUBJECT_FORWARD_COMMANDS", () => {
  const PYTHON_SUBJECT_FORWARD = new Set([
    "spawn_agent",
    "terminate_agent",
    "send_message",
    "broadcast_message",
    "register_ability",
    "unregister_ability",
    "list_agents",
    "health_check",
    "delegate",
    "get_agent_info",
    "init_cluster",
    "shutdown_cluster",
    "cluster_status",
  ]);

  it("contains exactly 13 subject-forward command values", () => {
    expect(SUBJECT_FORWARD_COMMANDS).toEqual(PYTHON_SUBJECT_FORWARD);
  });
});

describe("WORKSPACE_COMMANDS", () => {
  const PYTHON_WORKSPACE = new Set([
    "create_workspace",
    "destroy_workspace",
    "workspace_snapshot",
    "workspace_rollback",
    "workspace_diff",
    "workspace_status",
  ]);

  it("contains exactly 6 workspace command values", () => {
    expect(WORKSPACE_COMMANDS).toEqual(PYTHON_WORKSPACE);
  });
});
