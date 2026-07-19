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
