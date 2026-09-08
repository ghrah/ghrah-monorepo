# ghrah-subject

ghrah 控制面/执行层 - 持有工作区、执行沙箱命令、持久化 ActionChain、裁决 HITL。

## Workspace 挂载语义

Workspace 是**登记 + 授权 + 解挂**三件事，对挂载目录零物理操作：

- `workspace_register` 仅登记已有目录（store 记录 + sandbox cwd 授权），不 git
  init、不写 git config、不 add/commit、不落 marker；`provider_type="git"` 显式拒绝。
- 解挂（`destroy_workspace` / `unregister_workspace`）只软删 store 记录 + 解除
  sandbox 授权，**永不物理删除目录**（rmtree 全域退出）。
- 版本能力命令（`workspace_snapshot`/`workspace_rollback`/`workspace_diff`）随
  legacy GitWorkspaceProvider 一并移除，路由保留但返回
  `capability_not_supported`；`workspace_status` 降级为存在性/可写性。git 观测
  由 agent 侧只读命令承担（`git status`/`git diff` 在 SAFE 子命令白名单内）。
- 快照/回滚的后续方案是 harness 侧 shadow-git checkpoint 库（存储移出挂载
  目录，backlog，见 plans 内 dogfood 前置修复计划 §A3）。
- 存量 store 记录在 `WorkspaceStore.start()` 时自动 retag：`git` → `plain`。

## 安装

```bash
uv sync
```

## 运行

```bash
ghrah-subject
```

## 配置

通过环境变量配置，前缀为 `GHRAH_SUBJECT_`。主要配置项：

| 环境变量 | 说明 | 默认值 |
|---------|------|-------|
| `GHRAH_SUBJECT_WORKSPACE_ROOT` | 工作区根路径 | `~/ghrah-workspace` |
| `GHRAH_SUBJECT_DB_PATH` | SQLite 数据库路径 | `~/.ghrah/subject.db` |
| `GHRAH_SUBJECT_LOG_LEVEL` | 日志级别 | `INFO` |