# ghrah

多智能体运行时 monorepo：Python 核心栈（core / protocol / subject）+ TypeScript 观察端（WebUI / VS Code 扩展）。

## 仓库结构

| 目录 | 语言 | 说明 | 发布 |
| --- | --- | --- | --- |
| `ghrah-core/` | Python | 智能体运行时核心 | PyPI `ghrah-core` |
| `ghrah-protocol/` | Python | 协议类型与消息定义 | PyPI `ghrah-protocol` |
| `ghrah-subject/` | Python | Subject 层（项目/房间/账本/manifest） | PyPI `ghrah-subject` |
| `ghrah-observer-webui/` | TypeScript | 观察端（pnpm workspace：`@ghrah/protocol`、`@ghrah/observer-core` 发布 npm；`observer-web` 前端、`mock-server` 私有；`vscode-extension` 发 Marketplace） | npm / Marketplace |
| `shuoxi/` | Python | 本地实验（朔曦），不发布 | — |

## 工具链

- **Python**：uv workspace（单一 `uv.lock` 在根；成员内禁止 `uv lock`）
- **TypeScript**：pnpm workspace（单一 `pnpm-workspace.yaml` / `pnpm-lock.yaml` 在根）

```sh
uv sync --all-packages   # Python 全量安装
pnpm install             # TS 全量安装

uv run pytest ghrah-protocol ghrah-core ghrah-subject shuoxi   # Python 测试
pnpm -r test && pnpm type-check                                 # TS 测试 + 类型检查
```

## 发布

tag 路由（`publish.yml`）：`py/ghrah-core@<v>`、`py/ghrah-protocol@<v>`、`py/ghrah-subject@<v>` → PyPI；`npm/ghrah-protocol@<v>`、`npm/ghrah-observer-core@<v>` → npm；VS Code 扩展随 `py/ghrah-subject@*` 发布。发布前跑 `release-precheck`（workflow_dispatch）。

## 约定

见 [AGENTS.md](./AGENTS.md)（plans 目录、本地工具状态的忽略约定）。
