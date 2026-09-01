# ghrah-observer-webui

ghrah 观察端 WebUI 与 VS Code 扩展（Vue 3 + Vite + pnpm workspace）。

## 包结构

- `packages/protocol` — `@ghrah/protocol`，TS 协议类型/校验（zod schema + snapshot 测试）
- `packages/observer-core` — `@ghrah/observer-core`，WS 客户端 + Pinia stores + 投影逻辑
- `packages/observer-web` — `@ghrah/observer-web`，Vue 3 Web 前端（私有，不发布）
- `packages/mock-server` — `@ghrah/mock-server`，协议层 mock 服务器（开发/测试用）
- `vscode-extension` — VS Code 扩展（Marketplace 发布）

## 环境要求

- Node.js `^20.19.0 || >=22.12.0`
- pnpm `>=9.0.0`

## 构建与测试（在 monorepo 根目录执行）

```sh
pnpm install        # 安装整个 workspace（单一 pnpm-lock.yaml 在仓库根）

# 构建发布面（observer-web / observer-core 依赖 protocol 的 dist，须先构建）
pnpm --filter @ghrah/protocol build
pnpm --filter @ghrah/observer-core build

# 测试
pnpm --filter @ghrah/protocol test
pnpm --filter @ghrah/observer-core test
pnpm -r test        # 全部包（含 mock-server、observer-web）

# 类型检查（递归所有包）
pnpm type-check
```

## 本目录下的 scripts

```sh
pnpm dev            # ./scripts/dev.sh — 起 observer-web vite dev server
pnpm build          # ./scripts/build.sh
pnpm lint           # i18n / ui-tokens 检查 + biome
```

## IDE

VS Code + [Vue (Official)](https://marketplace.visualstudio.com/items?itemName=Vue.volar) 扩展。`.vue` 的类型检查由 `vue-tsc` 承担（`pnpm type-check`）。
