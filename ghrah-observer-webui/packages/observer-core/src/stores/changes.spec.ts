import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useChangesStore } from "./changes.js";

describe("useChangesStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("starts with empty changes", () => {
    const store = useChangesStore();
    expect(store.changes).toHaveLength(0);
  });

  it("onAbilityResult adds change for write_file", () => {
    const store = useChangesStore();
    store.onAbilityResult(
      {
        request_id: "r1",
        agent_name: "agent-1",
        ability_name: "write_file",
        success: true,
        result: "File written",
      },
      { file_path: "/tmp/test.txt" },
    );
    expect(store.changes).toHaveLength(1);
    expect(store.changes[0].agentName).toBe("agent-1");
    expect(store.changes[0].abilityName).toBe("write_file");
    expect(store.changes[0].filePath).toBe("/tmp/test.txt");
    expect(store.changes[0].success).toBe(true);
  });

  it("onAbilityResult adds change for edit_file", () => {
    const store = useChangesStore();
    store.onAbilityResult(
      {
        request_id: "r2",
        agent_name: "agent-2",
        ability_name: "edit_file",
        success: true,
        result: "File edited",
      },
      { file_path: "/tmp/test.ts" },
    );
    expect(store.changes).toHaveLength(1);
    expect(store.changes[0].abilityName).toBe("edit_file");
  });

  it("onAbilityResult adds change for delete_file", () => {
    const store = useChangesStore();
    store.onAbilityResult({
      request_id: "r3",
      agent_name: "agent-3",
      ability_name: "delete_file",
      success: true,
      result: "File deleted",
    });
    expect(store.changes).toHaveLength(1);
    expect(store.changes[0].abilityName).toBe("delete_file");
  });

  it("onAbilityResult ignores non-file-change abilities", () => {
    const store = useChangesStore();
    store.onAbilityResult({
      request_id: "r4",
      agent_name: "agent-1",
      ability_name: "read_file",
      success: true,
      result: "Content",
    });
    expect(store.changes).toHaveLength(0);
  });

  it("onAbilityResult records failure with error", () => {
    const store = useChangesStore();
    store.onAbilityResult({
      request_id: "r5",
      agent_name: "agent-1",
      ability_name: "write_file",
      success: false,
      error: "Permission denied",
    });
    expect(store.changes).toHaveLength(1);
    expect(store.changes[0].success).toBe(false);
    expect(store.changes[0].error).toBe("Permission denied");
  });

  it("filePath is undefined when toolArgs not provided", () => {
    const store = useChangesStore();
    store.onAbilityResult({
      request_id: "r6",
      agent_name: "agent-1",
      ability_name: "write_file",
      success: true,
      result: "OK",
    });
    expect(store.changes[0].filePath).toBeUndefined();
  });

  it("clearAll removes all changes", () => {
    const store = useChangesStore();
    store.onAbilityResult({
      request_id: "r1",
      agent_name: "agent-1",
      ability_name: "write_file",
      success: true,
      result: "OK",
    });
    store.onAbilityResult({
      request_id: "r2",
      agent_name: "agent-2",
      ability_name: "edit_file",
      success: true,
      result: "OK",
    });
    store.clearAll();
    expect(store.changes).toHaveLength(0);
  });
});
