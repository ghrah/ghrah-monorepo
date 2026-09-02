# ghrah monorepo

多智能体运行时 monorepo。项目定位与快速开始见根 [README](./README.md)；本文是开发/协作规范。

## 仓库结构

- `ghrah-core/` — Python 核心包（PyPI: ghrah-core）
- `ghrah-protocol/` — Python 协议包（PyPI: ghrah-protocol）
- `ghrah-subject/` — Python subject 包（PyPI: ghrah-subject）
- `ghrah-observer-webui/` — TS 观察端（pnpm workspace: packages/* + vscode-extension）
- `scripts/start_all.py` — 全栈一键启动入口（subject :4112 内嵌 Core + webui dev :5173）

## 工具链

- Python：uv（单一 `uv.lock` 在根；**成员内禁止 `uv lock`**）
- Web：pnpm（单一 `pnpm-workspace.yaml` / `pnpm-lock.yaml` 在仓库根）
- Node 版本：**须 ≥ 22**（pnpm 11 依赖 `node:sqlite`，Node 20 下任何 pnpm 命令直接崩；`nvm use 24`）

```sh
uv sync --all-packages      # Python 全量安装（含 dev 组另加 --group dev）
pnpm install                # TS 全量安装（webui 目录或根均可，workspace 在根）
```

## 代码规范

### Python

- lint/format：`uv run ruff check . && uv run ruff format --check .`（规则 `E,F,I,N,W,UP`，行宽 100，target py311）。提交前必须全绿。
- 类型：现代语法（`str | None`，禁 `Optional`）；公开函数带类型标注与中文 docstring。
- 测试：pytest（`asyncio_mode = "auto"`）；测试文件与被测模块同构放在 `tests/`。
- 命令一律 `uv run <cmd>`（解析到根 workspace 环境），勿用系统 python。

### TypeScript（ghrah-observer-webui）

- lint：`pnpm lint`（biome + i18n 门禁 + ui-token 门禁）；format：`pnpm format`。
- i18n：用户可见文案 **en 源 + zh-CN 双侧同步**（`check-i18n` 防中文残留）；新增组件文案先加 en 再补 zh。
- 样式：字号/间距/颜色走 token（`check-ui-tokens` 禁魔法数字）；不写内联裸色值。
- 构建：`packages/protocol` 与 `packages/observer-core` 改动后须 `pnpm build`（exports 指向 `dist/`，type-check 解析 dist；**dist 陈旧会让 type-check 与测试结果分裂**）。

### 通用

- **零隐式行为**：新功能必须显式声明（配置/Filter/白名单驱动），不做"顺便帮用户做了"的隐式默认。
- 不做顺手的无关重构/重命名/重排版；改动范围最小化。
- 新增依赖须入对应 workspace 清单，禁止本地 path 依赖混入锁文件。

## 测试与验收

```sh
# Python 三包（根目录执行；成员目录跑测试须 env -u PYTHONPATH uv run pytest -q）
uv run pytest ghrah-protocol ghrah-core ghrah-subject

# TS（webui 目录执行）
pnpm vitest run        # 注意：根级无 test script，用 vitest run
pnpm type-check        # 根级递归；vue-tsc 在 observer-web 包级
pnpm lint
```

- 删除型重构的验证顺序：**先 `rm` 工作树文件 → 再 pytest → 最后 `git add`**（仅 `git add` 前文件仍在磁盘，会被测试收集，造成"已删仍绿"假象）。
- 收编跨包漂移的修复，须跑双侧测试（协议改动 → Python + TS 两侧）。

## 提交约定

- Conventional Commits，中文描述：`feat(subject): …` / `fix(core)!…`（破坏性加 `!`）；范围用包短名（core/protocol/subject/observer/webui/ci/docs）。
- 本机 GPG 签名在 headless 会话会因 pinentry 超时失败：用 `git commit --no-gpg-sign`（一次性 flag，不改配置）。

## plans 目录约定（强制）

所有设计/计划文档落盘到根 **`plans/`**，该目录被 `.gitignore` 整体忽略——**本地专用，禁止提交、禁止推送**。

- Kilo plan 模式默认写 `.kilo/plans`——**不要**使用该默认路径，一律写 `plans/`。
- 分类：`plans/done/`（已完成归档）、`plans/todo/`（待办）、`plans/planning/`（进行中设计）、`plans/shelved/`（搁置）、`plans/<repo>/`（仓专属主题，如 `plans/ghrah-core/`）。
- `.kilo/` 同样整体忽略（本地工具状态：agent-manager.json、worktrees、kilo.jsonc 等），不得提交。
