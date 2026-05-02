export enum ClientType {
  SUBJECT = "subject",
  OBSERVER = "observer",
  CORE = "core",
}

export enum CommandType {
  SPAWN_AGENT = "spawn_agent",
  TERMINATE_AGENT = "terminate_agent",
  SEND_MESSAGE = "send_message",
  BROADCAST_MESSAGE = "broadcast_message",
  REGISTER_ABILITY = "register_ability",
  UNREGISTER_ABILITY = "unregister_ability",
  LIST_AGENTS = "list_agents",
  HEALTH_CHECK = "health_check",
  DELEGATE = "delegate",
  GET_AGENT_INFO = "get_agent_info",

  INIT_CLUSTER = "init_cluster",
  SHUTDOWN_CLUSTER = "shutdown_cluster",
  CLUSTER_STATUS = "cluster_status",

  SUBSCRIBE = "subscribe",
  UNSUBSCRIBE = "unsubscribe",

  EXECUTE_ABILITY = "execute_ability",

  HITL_RESPONSE = "hitl_response",

  PERSIST_SAVE_NODE = "persist_save_node",
  PERSIST_LOAD_NODE = "persist_load_node",
  PERSIST_LOAD_CHAIN = "persist_load_chain",
  PERSIST_SAVE_CHAIN_META = "persist_save_chain_meta",
  PERSIST_LOAD_CHAIN_META = "persist_load_chain_meta",
  PERSIST_SAVE_MESSAGES = "persist_save_messages",
  PERSIST_LOAD_MESSAGES = "persist_load_messages",
  PERSIST_DELETE_CHAIN = "persist_delete_chain",
  PERSIST_LIST_AGENTS = "persist_list_agents",

  CREATE_WORKSPACE = "create_workspace",
  DESTROY_WORKSPACE = "destroy_workspace",
  WORKSPACE_SNAPSHOT = "workspace_snapshot",
  WORKSPACE_ROLLBACK = "workspace_rollback",
  WORKSPACE_DIFF = "workspace_diff",
  WORKSPACE_STATUS = "workspace_status",

  MANIFEST_LIST_ABILITIES = "manifest_list_abilities",
  MANIFEST_GET_ABILITY = "manifest_get_ability",
  MANIFEST_PUT_ABILITY = "manifest_put_ability",
  MANIFEST_DELETE_ABILITY = "manifest_delete_ability",
  MANIFEST_LIST_AGENTS = "manifest_list_agents",
  MANIFEST_GET_AGENT = "manifest_get_agent",
  MANIFEST_PUT_AGENT = "manifest_put_agent",
  MANIFEST_DELETE_AGENT = "manifest_delete_agent",
  MANIFEST_RESOLVE_AGENT = "manifest_resolve_agent",
  MANIFEST_VALIDATE = "manifest_validate",
}

export enum EventType {
  AGENT_SPAWNED = "agent_spawned",
  AGENT_TERMINATED = "agent_terminated",
  AGENT_RESPONSE = "agent_response",
  ACTION_CHAIN_UPDATED = "action_chain_updated",
  AGENT_ERROR = "agent_error",
  HEALTH_STATUS = "health_status",
  ABILITY_RESULT = "ability_result",
  HITL_REQUEST = "hitl_request",
  HITL_RESPONSE = "hitl_response",
  WORKSPACE_CREATED = "workspace_created",
  WORKSPACE_DESTROYED = "workspace_destroyed",
  WORKSPACE_SNAPSHOT_CREATED = "workspace_snapshot_created",
  WORKSPACE_ROLLED_BACK = "workspace_rolled_back",

  MANIFEST_ABILITY_CREATED = "manifest_ability_created",
  MANIFEST_ABILITY_UPDATED = "manifest_ability_updated",
  MANIFEST_ABILITY_DELETED = "manifest_ability_deleted",
  MANIFEST_AGENT_CREATED = "manifest_agent_created",
  MANIFEST_AGENT_UPDATED = "manifest_agent_updated",
  MANIFEST_AGENT_DELETED = "manifest_agent_deleted",
}

export enum SystemType {
  COMMAND_RESULT = "command_result",
  PING = "ping",
  PONG = "pong",
  ERROR = "error",
}

export const PERSIST_COMMANDS: ReadonlySet<string> = new Set([
  CommandType.PERSIST_SAVE_NODE,
  CommandType.PERSIST_LOAD_NODE,
  CommandType.PERSIST_LOAD_CHAIN,
  CommandType.PERSIST_SAVE_CHAIN_META,
  CommandType.PERSIST_LOAD_CHAIN_META,
  CommandType.PERSIST_SAVE_MESSAGES,
  CommandType.PERSIST_LOAD_MESSAGES,
  CommandType.PERSIST_DELETE_CHAIN,
  CommandType.PERSIST_LIST_AGENTS,
]);

export const CORE_COMMANDS: ReadonlySet<string> = new Set([
  CommandType.SPAWN_AGENT,
  CommandType.TERMINATE_AGENT,
  CommandType.SEND_MESSAGE,
  CommandType.BROADCAST_MESSAGE,
  CommandType.REGISTER_ABILITY,
  CommandType.UNREGISTER_ABILITY,
  CommandType.LIST_AGENTS,
  CommandType.HEALTH_CHECK,
  CommandType.DELEGATE,
  CommandType.GET_AGENT_INFO,
  CommandType.INIT_CLUSTER,
  CommandType.SHUTDOWN_CLUSTER,
  CommandType.CLUSTER_STATUS,
]);

export const WORKSPACE_COMMANDS: ReadonlySet<string> = new Set([
  CommandType.CREATE_WORKSPACE,
  CommandType.DESTROY_WORKSPACE,
  CommandType.WORKSPACE_SNAPSHOT,
  CommandType.WORKSPACE_ROLLBACK,
  CommandType.WORKSPACE_DIFF,
  CommandType.WORKSPACE_STATUS,
]);

export const MANIFEST_COMMANDS: ReadonlySet<string> = new Set([
  CommandType.MANIFEST_LIST_ABILITIES,
  CommandType.MANIFEST_GET_ABILITY,
  CommandType.MANIFEST_PUT_ABILITY,
  CommandType.MANIFEST_DELETE_ABILITY,
  CommandType.MANIFEST_LIST_AGENTS,
  CommandType.MANIFEST_GET_AGENT,
  CommandType.MANIFEST_PUT_AGENT,
  CommandType.MANIFEST_DELETE_AGENT,
  CommandType.MANIFEST_RESOLVE_AGENT,
  CommandType.MANIFEST_VALIDATE,
]);

export type MessageType = CommandType | EventType | SystemType;
