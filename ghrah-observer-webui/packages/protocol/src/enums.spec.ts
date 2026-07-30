import { describe, expect, it } from "vitest";
import {
  ClientType,
  CommandType,
  CORE_COMMANDS,
  EventType,
  MANIFEST_COMMANDS,
  PERSIST_COMMANDS,
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
    "list_clusters",
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
    "manifest_list_abilities",
    "manifest_get_ability",
    "manifest_put_ability",
    "manifest_delete_ability",
    "manifest_list_agents",
    "manifest_get_agent",
    "manifest_put_agent",
    "manifest_delete_agent",
    "manifest_resolve_agent",
    "manifest_validate",
  ]);

  it("has exactly 38 values matching Python CommandType", () => {
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
    "manifest_ability_created",
    "manifest_ability_updated",
    "manifest_ability_deleted",
    "manifest_agent_created",
    "manifest_agent_updated",
    "manifest_agent_deleted",
  ]);

  it("has exactly 19 values matching Python EventType", () => {
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

describe("CORE_COMMANDS", () => {
  const PYTHON_CORE_COMMANDS = new Set([
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
    "list_clusters",
  ]);

  it("contains exactly 14 core command values", () => {
    expect(CORE_COMMANDS).toEqual(PYTHON_CORE_COMMANDS);
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

describe("MANIFEST_COMMANDS", () => {
  const PYTHON_MANIFEST = new Set([
    "manifest_list_abilities",
    "manifest_get_ability",
    "manifest_put_ability",
    "manifest_delete_ability",
    "manifest_list_agents",
    "manifest_get_agent",
    "manifest_put_agent",
    "manifest_delete_agent",
    "manifest_resolve_agent",
    "manifest_validate",
  ]);

  it("contains exactly 10 manifest command values", () => {
    expect(MANIFEST_COMMANDS).toEqual(PYTHON_MANIFEST);
  });
});
