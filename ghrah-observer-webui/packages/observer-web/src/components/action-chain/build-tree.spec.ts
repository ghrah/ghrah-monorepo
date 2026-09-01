import type { ActionNode } from "@ghrah/protocol";
import { ActionNodeSchema } from "@ghrah/protocol";
import { describe, expect, it } from "vitest";
import { buildTree, createTreeCache } from "./build-tree.js";

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

// ─── 增量树缓存（性能红线 2） ───

describe("createTreeCache", () => {
  it("append-only growth produces rows identical to full buildTree", () => {
    const cache = createTreeCache();
    const nodes = [
      node({ id: "a", parent_id: null, timestamp: "t1" }),
      node({ id: "b", parent_id: "a", timestamp: "t2" }),
      node({ id: "c", parent_id: "a", timestamp: "t3" }),
      node({ id: "d", parent_id: "b", timestamp: "t4" }),
      node({ id: "e", parent_id: null, timestamp: "t5" }),
    ];
    let growing = nodes.slice(0, 2);
    cache.rowsFor("agent", growing);
    for (let i = 2; i <= nodes.length; i += 1) {
      growing = nodes.slice(0, i);
      const rows = cache.rowsFor("agent", growing);
      const full = buildTree(growing);
      expect(rows.map((r) => r.node.id)).toEqual(full.map((r) => r.node.id));
      expect(rows.map((r) => r.depth)).toEqual(full.map((r) => r.depth));
      expect(rows.map((r) => r.isLastChild)).toEqual(full.map((r) => r.isLastChild));
      expect(rows.map((r) => r.ancestorPipes)).toEqual(full.map((r) => r.ancestorPipes));
    }
  });

  it("appends reuse row objects with a fresh array ref (no full rebuild)", () => {
    const cache = createTreeCache();
    const base = [
      node({ id: "a", parent_id: null, timestamp: "2026-01-01T00:00:01Z" }),
      node({ id: "b", parent_id: "a", timestamp: "2026-01-01T00:00:02Z" }),
    ];
    const rows0 = cache.rowsFor("agent", base);
    const rowA0 = rows0[0]!;
    const rowB0 = rows0[1]!;
    // 追加千节点（模拟千节点会话）：逐次新数组引用 + 前缀行对象复用
    let rows = rows0;
    let growing = base.slice();
    for (let i = 3; i <= 1000; i += 1) {
      const ts = `2026-01-01T00:${String(Math.floor(i / 60)).padStart(2, "0")}:${String(i % 60).padStart(2, "0")}Z`;
      growing = [...growing, node({ id: `n${i}`, parent_id: i % 2 ? "a" : "b", timestamp: ts })];
      rows = cache.rowsFor("agent", growing);
    }
    expect(rows).not.toBe(rows0); // 新引用（Vue 依赖值变化）
    expect(rows).toHaveLength(1000);
    expect(rows[0]).toBe(rowA0); // 未受影响行零重建（对象复用）
    // b 被后续子节点 demote → 克隆替换（对象不同但内容正确）
    expect(rows[1]).not.toBe(rowB0);
    expect(rows[1]!.isLastChild).toBe(false);
    // 与全量 buildTree 终态一致（正确性兜底）
    const full = buildTree(growing);
    expect(rows.map((r) => r.node.id)).toEqual(full.map((r) => r.node.id));
    expect(rows.map((r) => r.isLastChild)).toEqual(full.map((r) => r.isLastChild));
    expect(rows.map((r) => r.ancestorPipes)).toEqual(full.map((r) => r.ancestorPipes));
  });

  it("switching agents keeps independent caches (no rebuild on switch-back)", () => {
    const cache = createTreeCache();
    const nodesA = [node({ id: "a1", parent_id: null, timestamp: "t1" })];
    const nodesB = [node({ id: "b1", parent_id: null, timestamp: "t1" })];
    const rowsA = cache.rowsFor("A", nodesA);
    cache.rowsFor("B", nodesB);
    const rowsA2 = cache.rowsFor("A", nodesA);
    expect(rowsA2).toBe(rowsA); // 同一数组引用 = 未重建
  });

  it("falls back to full rebuild on non-append mutation", () => {
    const cache = createTreeCache();
    const base = [
      node({ id: "a", parent_id: null, timestamp: "t1" }),
      node({ id: "b", parent_id: "a", timestamp: "t2" }),
    ];
    cache.rowsFor("agent", base);
    // 前缀失配（b 被替换）→ 全量重建，结果与 buildTree 一致
    const mutated = [
      node({ id: "a", parent_id: null, timestamp: "t1" }),
      node({ id: "c", parent_id: "a", timestamp: "t9" }),
    ];
    const rows = cache.rowsFor("agent", mutated);
    expect(rows.map((r) => r.node.id)).toEqual(["a", "c"]);
  });

  it("out-of-order timestamp append falls back (correctness guard)", () => {
    const cache = createTreeCache();
    const base = [
      node({ id: "root", parent_id: null, timestamp: "t1" }),
      node({ id: "c1", parent_id: "root", timestamp: "t5" }),
    ];
    cache.rowsFor("agent", base);
    // 新子节点时间戳早于既有末子节点 → 增量守卫触发全量，排序正确
    const appended = [...base, node({ id: "c0", parent_id: "root", timestamp: "t2" })];
    const rows = cache.rowsFor("agent", appended);
    expect(rows.map((r) => r.node.id)).toEqual(["root", "c0", "c1"]);
  });

  it("evicts least-recently-used agents beyond limit", () => {
    const cache = createTreeCache(2);
    const mk = (id: string) => [node({ id, parent_id: null, timestamp: "t1" })];
    cache.rowsFor("a", mk("n1"));
    cache.rowsFor("b", mk("n2"));
    cache.rowsFor("c", mk("n3")); // 超限淘汰 a
    const rowsA = cache.rowsFor("a", mk("n1")); // 重建（新数组）
    expect(rowsA.map((r) => r.node.id)).toEqual(["n1"]);
  });
});
