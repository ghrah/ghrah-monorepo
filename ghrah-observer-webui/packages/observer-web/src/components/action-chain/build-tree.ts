import type { ActionNode } from "@ghrah/protocol";

export interface TreeRow {
  node: ActionNode;
  depth: number;
  isLastChild: boolean;
  ancestorPipes: boolean[];
}

// ancestorPipes[i] = 第 i 层祖先是否还有后续兄弟（true→画 │，false→画空格）
export function buildTree(nodes: ActionNode[]): TreeRow[] {
  const childrenOf = new Map<string | null, ActionNode[]>();
  for (const n of nodes) {
    const pid = n.parent_id ?? null;
    const arr = childrenOf.get(pid) ?? [];
    arr.push(n);
    childrenOf.set(pid, arr);
  }
  for (const arr of childrenOf.values()) {
    arr.sort((a, b) => (a.timestamp ?? "").localeCompare(b.timestamp ?? ""));
  }

  const rows: TreeRow[] = [];
  function recurse(node: ActionNode, depth: number, ancestorPipes: boolean[], isLast: boolean) {
    rows.push({ node, depth, isLastChild: isLast, ancestorPipes });
    const childList = childrenOf.get(node.id) ?? [];
    const childAncestorPipes = [...ancestorPipes, !isLast];
    for (let i = 0; i < childList.length; i++) {
      recurse(childList[i], depth + 1, childAncestorPipes, i === childList.length - 1);
    }
  }

  const roots = childrenOf.get(null) ?? [];
  roots.sort((a, b) => (a.timestamp ?? "").localeCompare(b.timestamp ?? ""));
  for (let i = 0; i < roots.length; i++) {
    recurse(roots[i], 0, [], i === roots.length - 1);
  }
  return rows;
}

// ─── 增量树缓存（性能红线 2：禁止全量 rebuild） ───

interface CacheEntry {
  /** 已建树的节点列表快照（append-only 前缀）。 */
  nodes: ActionNode[];
  rows: TreeRow[];
  /** nodeId → rows 下标（splice 后整体平移维护）。 */
  indexById: Map<string, number>;
}

/**
 * per-agent 树缓存：节点 append-only 增长时增量补建新节点的行（O(子树定位)），
 * 仅在非追加变化（前缀失配/乱序时间戳/未知父节点/收缩）时回退全量 buildTree。
 * LRU 上限 `limit`（对齐 rooms store 范式，切换 agent 不清缓存）。
 */
export function createTreeCache(limit = 20) {
  const cache = new Map<string, CacheEntry>();

  function evict(): void {
    while (cache.size > limit) {
      const oldest = cache.keys().next().value;
      if (oldest === undefined) break;
      cache.delete(oldest);
    }
  }

  function fullBuild(entry: CacheEntry, nodes: ActionNode[]): TreeRow[] {
    const rows = buildTree(nodes);
    const indexById = new Map<string, number>();
    for (let i = 0; i < rows.length; i++) indexById.set(rows[i].node.id, i);
    entry.nodes = [...nodes];
    entry.rows = rows;
    entry.indexById = indexById;
    return rows;
  }

  /** 在 parent 行之后找到其子树末尾（连续 depth > parentDepth 的行）。 */
  function subtreeEnd(rows: TreeRow[], parentIdx: number): number {
    const parentDepth = rows[parentIdx]!.depth;
    let i = parentIdx + 1;
    while (i < rows.length && rows[i]!.depth > parentDepth) i += 1;
    return i;
  }

  /**
   * 追加式插入一个新节点行；返回 false 表示无法增量（触发全量回退）。
   *
   * 语义约束（append-only + 时间戳有序）：
   * - 新节点插入为「父的最后一个子节点」或「最后一个根」；
   * - 原末位子/根的 isLastChild 翻转为 false，其子树行的 ancestorPipes 对应层
   *   翻转为 true（克隆受影响行，未受影响行对象原样复用）；
   * - rows 数组每次浅拷贝出新引用（Vue computed 依赖值变化触发渲染），
   *   行对象层面零重建。
   */
  function appendNode(entry: CacheEntry, node: ActionNode): boolean {
    const { rows, indexById } = entry;

    let insertAt: number;
    let row: TreeRow;
    /** 受 isLastChild 翻转影响的「原末位子节点」下标（无则 -1；根追加时为原末根）。 */
    let demotedIdx = -1;

    if (node.parent_id == null) {
      insertAt = rows.length;
      row = { node, depth: 0, isLastChild: true, ancestorPipes: [] };
      // 根按时间戳排序：新根必须不早于最后一个既有根，否则回退全量
      for (let i = rows.length - 1; i >= 0; i -= 1) {
        if (rows[i]!.depth === 0) {
          if ((node.timestamp ?? "") < (rows[i]!.node.timestamp ?? "")) return false;
          if (rows[i]!.isLastChild) demotedIdx = i;
          break;
        }
      }
    } else {
      const parentIdx = indexById.get(node.parent_id);
      if (parentIdx === undefined) return false; // 未知父节点 → 全量
      const parent = rows[parentIdx]!;
      insertAt = subtreeEnd(rows, parentIdx);
      row = {
        node,
        depth: parent.depth + 1,
        isLastChild: true,
        ancestorPipes: [...parent.ancestorPipes, !parent.isLastChild],
      };
      // 时间戳守卫：新子节点必须不早于父节点当前最后一个子节点
      // 定位原末位直接子节点（子树尾回退到第一个 depth === parent.depth+1 的行）
      let i = insertAt - 1;
      while (i > parentIdx && rows[i]!.depth > parent.depth + 1) i -= 1;
      if (i > parentIdx) {
        const prevLast = rows[i]!;
        if ((node.timestamp ?? "") < (prevLast.node.timestamp ?? "")) return false;
        if (prevLast.isLastChild) demotedIdx = i;
      }
    }

    // 新 rows 数组（浅拷贝保持新引用）；受影响行以克隆替换
    const next = rows.slice();
    next.splice(insertAt, 0, row);
    if (demotedIdx >= 0) {
      const demoted = rows[demotedIdx]!;
      next[demotedIdx] = { ...demoted, isLastChild: false };
      // demoted 子树行（depth > demoted.depth）：ancestorPipes[demoted.depth] → true
      const pipeIdx = demoted.depth;
      for (let i = demotedIdx + 1; i < next.length && next[i]!.depth > demoted.depth; i += 1) {
        if (i === insertAt) continue; // 新插入行不属于 demoted 子树
        const r = next[i]!;
        if (r.ancestorPipes[pipeIdx] !== true) {
          const pipes = [...r.ancestorPipes];
          pipes[pipeIdx] = true;
          next[i] = { ...r, ancestorPipes: pipes };
        }
      }
    }

    // 索引平移（insertAt 之后 +1）+ 新节点登记
    for (let i = rows.length - 1; i >= insertAt; i -= 1) {
      const id = rows[i]!.node.id;
      if (id) indexById.set(id, i + 1);
    }
    if (row.node.id) indexById.set(row.node.id, insertAt);

    entry.rows = next;
    return true;
  }

  function rowsFor(agent: string, nodes: ActionNode[]): TreeRow[] {
    const hit = cache.get(agent);
    if (hit) {
      cache.delete(agent);
      cache.set(agent, hit); // LRU touch（重插到尾部）
      // 同列表（append-only 前缀完全一致）→ 直接复用
      if (prefixMatches(hit.nodes, nodes) && hit.nodes.length === nodes.length) {
        return hit.rows;
      }
      if (hit.nodes.length < nodes.length && prefixMatches(hit.nodes, nodes)) {
        let ok = true;
        for (let i = hit.nodes.length; i < nodes.length; i += 1) {
          if (!appendNode(hit, nodes[i]!)) {
            ok = false;
            break;
          }
        }
        if (ok) {
          hit.nodes = [...nodes];
          return hit.rows;
        }
      }
      // 长度相同但内容不同 / 前缀失配 / 收缩 / 增量失败 → 全量重建
      fullBuild(hit, nodes);
      return hit.rows;
    }
    const fresh: CacheEntry = { nodes: [], rows: [], indexById: new Map() };
    cache.set(agent, fresh);
    evict();
    return fullBuild(fresh, nodes);
  }

  return { rowsFor, clear: () => cache.clear() };
}

function prefixMatches(prefix: ActionNode[], nodes: ActionNode[]): boolean {
  if (prefix.length > nodes.length) return false;
  for (let i = 0; i < prefix.length; i += 1) {
    if (prefix[i] !== nodes[i]) return false;
  }
  return true;
}
