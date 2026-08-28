import { describe, expect, it } from "vitest";
import { makeAgentKey } from "./identity.js";

describe("makeAgentKey", () => {
  it("uses the stable Project and Agent IDs", () => {
    expect(makeAgentKey("proj-001", "agent-001")).toBe("proj-001:agent-001");
  });
});
