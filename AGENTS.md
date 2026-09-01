# ghrah monorepo

## 仓库结构

- `ghrah-core/` — Python 核心包（PyPI: ghrah-core）
- `ghrah-protocol/` — Python 协议包（PyPI: ghrah-protocol）
- `ghrah-subject/` — Python subject 包（PyPI: ghrah-subject）
- `ghrah-observer-webui/` — TS 观察端（pnpm workspace: packages/* + vscode-extension）
- `shuoxi/` — 本地实验（uv workspace 成员，不发布）

## 工具链

- Python：uv（单一 `uv.lock` 在根；成员内禁止 `uv lock`）
- Web：pnpm（单一 `pnpm-workspace.yaml` 在根）

## plans 目录约定（强制）

所有设计/计划文档落盘到根 **`plans/`**，该目录被 `.gitignore` 整体忽略——**本地专用，禁止提交、禁止推送**。

- Kilo plan 模式默认写 `.kilo/plans`——**不要**使用该默认路径，一律写 `plans/`。
- 分类：`plans/done/`（已完成归档）、`plans/todo/`（待办）、`plans/planning/`（进行中设计）、`plans/shelved/`（搁置）、`plans/<repo>/`（仓专属主题，如 `plans/ghrah-core/`）。
- `.kilo/` 同样整体忽略（本地工具状态：agent-manager.json、worktrees、kilo.jsonc 等），不得提交。
