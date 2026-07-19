import type { ActionNode } from "@ghrah/protocol";
import { ActionNodeSchema } from "@ghrah/protocol";
import { describe, expect, it } from "vitest";
import { buildTree } from "./build-tree.js";

function node(overrides: Partial<ActionNode> = {}): ActionNode {
  return ActionNodeSchema.parse(overrides);
}

describe("buildTree", () => {
  it("empty input → no rows", () => {
    expect(buildTree([])).toHaveLength(0);
  });

  it("linear chain: depth and isLastChild per level", () => {
    const rows = buildTree([
      node({ id: "a", parent_id: null, timestamp: "t1" }),
      node({ id: "b", parent_id: "a", timestamp: "t2" }),
      node({ id: "c", parent_id: "b", timestamp: "t3" }),
    ]);
    expect(rows.map((r) => r.node.id)).toEqual(["a", "b", "c"]);
    expect(rows.map((r) => r.depth)).toEqual([0, 1, 2]);
    expect(rows.map((r) => r.isLastChild)).toEqual([true, true, true]);
  });

  it("siblings: first not-last, last is-last", () => {
    const rows = buildTree([
      node({ id: "root", parent_id: null, timestamp: "t0" }),
      node({ id: "c1", parent_id: "root", timestamp: "t1" }),
      node({ id: "c2", parent_id: "root", timestamp: "t2" }),
      node({ id: "c3", parent_id: "root", timestamp: "t3" }),
    ]);
    // root, then c1, c2, c3
    expect(rows.map((r) => r.node.id)).toEqual(["root", "c1", "c2", "c3"]);
    const children = rows.filter((r) => r.depth === 1);
    expect(children.map((r) => r.isLastChild)).toEqual([false, false, true]);
  });

  it("ancestorPipes: parent continues → child draws pipe at parent level", () => {
    const rows = buildTree([
      node({ id: "root", parent_id: null, timestamp: "t0" }),
      node({ id: "c1", parent_id: "root", timestamp: "t1" }),
      node({ id: "c1a", parent_id: "c1", timestamp: "t1a" }),
      node({ id: "c2", parent_id: "root", timestamp: "t2" }),
      node({ id: "c2a", parent_id: "c2", timestamp: "t2a" }),
    ]);
    const c1a = rows.find((r) => r.node.id === "c1a")!;
    // root is the only root (last) → ancestorPipes[0]=false (no pipe at root level);
    // c1 has sibling c2 following → ancestorPipes[1]=true (pipe at c1 level)
    expect(c1a.ancestorPipes).toEqual([false, true]);
    const c2a = rows.find((r) => r.node.id === "c2a")!;
    // root last → [0]=false; c2 last → [1]=false
    expect(c2a.ancestorPipes).toEqual([false, false]);
  });

  it("sorts siblings by timestamp", () => {
    const rows = buildTree([
      node({ id: "root", parent_id: null, timestamp: "2026-01-01T00:00:00Z" }),
      node({ id: "late", parent_id: "root", timestamp: "2026-01-01T10:00:00Z" }),
      node({ id: "early", parent_id: "root", timestamp: "2026-01-01T05:00:00Z" }),
    ]);
    expect(rows.map((r) => r.node.id)).toEqual(["root", "early", "late"]);
  });

  it("multiple roots", () => {
    const rows = buildTree([
      node({ id: "r1", parent_id: null, timestamp: "t1" }),
      node({ id: "r2", parent_id: null, timestamp: "t2" }),
      node({ id: "r2c", parent_id: "r2", timestamp: "t3" }),
    ]);
    expect(rows.map((r) => r.node.id)).toEqual(["r1", "r2", "r2c"]);
    expect(rows[0].isLastChild).toBe(false);
    expect(rows[1].isLastChild).toBe(true);
  });

  it("multiple roots sorted by timestamp", () => {
    const rows = buildTree([
      node({ id: "late", parent_id: null, timestamp: "2026-01-01T10:00:00Z" }),
      node({ id: "early", parent_id: null, timestamp: "2026-01-01T05:00:00Z" }),
      node({ id: "mid", parent_id: null, timestamp: "2026-01-01T07:00:00Z" }),
    ]);
    expect(rows.map((r) => r.node.id)).toEqual(["early", "mid", "late"]);
  });

  it("nodes missing parent_id treated as roots", () => {
    const rows = buildTree([node({ id: "orphan", timestamp: "t1" })]);
    expect(rows).toHaveLength(1);
    expect(rows[0].depth).toBe(0);
  });
});
