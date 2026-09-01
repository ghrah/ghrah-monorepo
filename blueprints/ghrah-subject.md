## `ghrah-subject` 核心业务代码思维导图

以下按模块层级和依赖关系组织，排除 tests 代码。

```
ghrah-subject (Subject 端运行时)
│
├── main.py                    → 入口: 委托 ghrah.subject.app.main()
│
└── src/ghrah/subject/
    │
    ├── 📦 config.py  【配置层 — 零内部依赖】
    │   ├── HITLPolicyConfig      → auto_approve_list, require_approval_by_default,
    │   │                            allowed_paths, workspace_root
    │   ├── CoreConnectionConfig   → ws_url, reconnect_interval, ping_interval,
    │   │                            command_timeout
    │   └── SubjectConfig          → workspace_root, db_path, manifest_root,
    │                                hitl_policy, core_connection, log_level
    │                                .from_env() 从环境变量加载
    │
    ├── 📦 _utils.py  【共享工具 — 依赖 ghrah-core】
    │   ├── AbilityPathSpec        → ability 名称 → 路径参数 key 映射
    │   ├── ABILITY_PATH_SPECS     → 14 个内置 ability 的路径规格注册表
    │   ├── extract_paths()        → 从 tool_args 提取文件/目录路径
    │   └── is_subpath()           → re-export from ghrah.abilities._utils
    │
    ├── 📦 app.py  【应用入口】
    │   └── main() / run()         → SubjectConfig.from_env() → SubjectService.run_forever()
    │
    ├── 📦 service.py  【中央编排器 — 1195行, 依赖最多的模块】
    │   └── SubjectService         → 聚合所有子系统, 管理完整生命周期:
    │       ├── WebSocket 连接管理 (websockets → Core)
    │       ├── 命令分发 (execute_ability, persist_*, workspace_*,
    │       │              manifest_*, get_chain_history, spawn_agent, send_message)
    │       ├── Core 事件处理 (agent_spawned, agent_terminated,
    │       │                   action_chain_updated, hitl_request, ...)
    │       ├── HITL 流程编排 (notary + policy)
    │       └── 子系统初始化 (sandbox, persistence, manifest_store, ledger, hitl)
    │
    ├── 📦 ability_runner.py  【Ability 执行器】
    │   ├── AbilityRunnerConfig    → workspace_root, permission_checker, hitl_notary
    │   └── AbilityRunner          → 执行流程:
    │       1. AbilityRegistry 查找 ability 类
    │       2. 路径解析 (extract_paths)
    │       3. PermissionChecker 硬检查
    │       4. HITLNotary 策略检查 → 如需审批, 创建 Promise 等待
    │       5. 执行 ability → 返回 ActionResult
    │
    ├── 📦 permission_checker.py  【硬权限检查】
    │   ├── PermissionDecision     → DENY / REQUIRE_HITL / ALLOW
    │   ├── PermissionVerdict       → decision + reason
    │   └── PermissionChecker       → 基于 manifest PermissionFlags:
    │       ├── denied_paths 检查
    │       ├── denied_commands 检查
    │       ├── 路径白名单 + workspace_root 约束
    │       └── CommandSafetyChecker 命令安全分类
    │
    ├── 📦 sandbox/  【沙盒执行与工作区管理】
    │   ├── executor.py
    │   │   ├── SandboxExecutorConfig → workspace_root, blocked_commands,
    │   │   │                            timeout, max_output_length
    │   │   ├── SandboxExecutor       → asyncio.create_subprocess_exec:
    │   │   │                            cwd 约束, 超时控制, 输出截断, env 注入
    │   │   └── CommandResult         → exit_code, stdout, stderr, truncated
    │   └── workspace.py
    │       ├── WorkspaceManager      → 管理所有 Agent 的 Git 工作区
    │       ├── AgentWorkspace        → 单 Agent 工作区:
    │       │   ├── snapshot()        → git add + commit
    │       │   ├── diff()            → git diff
    │       │   ├── rollback()        → git checkout
    │       │   ├── status()          → git status
    │       │   └── list_snapshots()  → git log
    │       ├── WorkspaceStatus       → clean / dirty / error
    │       ├── SnapshotInfo          → snapshot_id, message, timestamp
    │       └── SnapshotError          → 快照操作异常
    │
    ├── 📦 hitl/  【人机协同审批】
    │   ├── policy.py
    │   │   ├── HITLVerdict           → needs_approval: bool, reason: str
    │   │   └── HITLPolicy            → 决策流程:
    │   │       1. auto_approve 白名单 → 直接允许
    │   │       2. manifest require_hitl=False → 允许
    │   │       3. 路径检查 (allowed_paths + workspace_root)
    │   │       4. 回退到 require_approval_by_default
    │   └── notary.py
    │       ├── HITLPromise           → 包装 asyncio.Future[HITLVerdict]
    │       └── HITLNotary            → 管理待审批请求:
    │           ├── check_request()    → 调用 HITLPolicy 决策
    │           ├── create_promise()  → 创建等待 Future
    │           ├── resolve_promise() → Observer 审批通过后解析
    │           ├── reject_promise()  → 拒绝
    │           └── cancel_all()      → 批量取消
    │
    ├── 📦 server/  【Observer WebSocket 服务】
    │   ├── config.py
    │   │   └── ObserverServerConfig  → host, port (默认4112), ws_path,
    │   │                                ping_interval, event_replay_capacity
    │   ├── app.py
    │   │   ├── create_app()          → FastAPI 应用工厂 (lifespan, WS端点, /health)
    │   │   └── main()                → uvicorn 启动入口
    │   ├── connection_manager.py
    │   │   └── ConnectionManager     → Observer WS 连接管理:
    │   │       ├── session_id → WebSocket 映射
    │   │       ├── 订阅过滤 (agent_name, event_type)
    │   │       ├── client_id 重连驱逐
    │   │       └── broadcast() 带订阅过滤
    │   ├── event_bus.py
    │   │   ├── EventStore            → 环形缓冲区, 事件重放
    │   │   └── EventBus              → 发布事件到订阅的 Observer:
    │   │       ├── publish()         → 通用发布
    │   │       ├── emit()            → 带类型路由
    │   │       ├── emit_hitl_request() → HITL 专用
    │   │       └── emit_core_event() → Core 事件转发
    │   ├── router.py
    │   │   └── ObserverRouter        → Observer 命令路由:
    │   │       ├── subscribe / unsubscribe (本地)
    │   │       ├── HITL 响应 (本地 → HITLNotary)
    │   │       ├── Agent 管理 (转发 → Core)
    │   │       └── workspace / manifest / persist / ability / chain-history (本地)
    │   └── server.py
    │       └── ObserverServer        → 单 WS 连接处理:
    │           ├── session_id 分配 + client_id 驱逐
    │           ├── welcome 消息 + 事件重放
    │           └── 消息循环 (ping/pong, 事件→EventBus, 命令→ObserverRouter)
    │
    ├── 📦 persistence/  【SQLite 持久化服务】
    │   ├── migrations.py
    │   │   ├── CURRENT_VERSION       → 当前 schema 版本
    │   │   ├── MIGRATIONS            → 版本迁移列表
    │   │   └── apply_migrations()    → PRAGMA user_version 驱动迁移:
    │   │       v1: sessions, agents, nodes, chain_meta, messages
    │   │       v2: sessions→runs, 新增 branch sessions,
    │   │            nodes 加 session_id, chain_meta 加 active_session_id
    │   └── service.py
    │       └── SubjectPersistenceService → Core RemoteBackend 的服务端:
    │           ├── 13 个命令处理器 (save/load node, load chain,
    │           │   save/load chain_meta, save/load messages,
    │           │   delete chain, list agents, save/load/list/delete sessions)
    │           └── 委托给 SqliteBackend (from ghrah-core)
    │
    ├── 📦 manifest_store/  【Manifest 文件存储】
    │   ├── store.py
    │   │   └── ManifestStore         → 文件系统 manifest 存储:
    │   │       ├── 目录布局: {root}/abilities/{ns}/{name}.yaml
    │   │       │            {root}/agents/{ns}/{name}.yaml
    │   │       ├── CRUD: list/get/put/delete abilities + agents
    │   │       └── 验证: parse + validate (依赖 ghrah.manifest.parser)
    │   ├── service.py
    │   │   ├── handle_manifest_command() → 10 个命令分发
    │   │   └── _MANIFEST_COMMANDS     → 命令名集合
    │   └── builtins.py
    │       └── ensure_builtins()      → 幂等写入内置 ability manifest 到 ManifestStore
    │
    └── 📦 ledger/  【ActionChain 账本】
        ├── models.py
        │   ├── LedgerNode            → Pydantic 模型, ContextNode 可序列化包装
        │   ├── ChainMeta             → agent 元数据 (branches, session)
        │   └── DAGEntry              → node + children + depth (DAG 遍历)
        └── chain.py
            └── ActionChainLedger     → 追加式不可变账本:
                ├── 接收 action_chain_updated 事件
                ├── 通过 SubjectPersistenceService 持久化节点
                ├── 维护内存 ActionChain 索引
                ├── DAG 遍历 + 分支管理
                └── chain_history 查询
```

---

### 模块依赖关系图 (箭头 = "依赖于")

```
                    ┌──────────────────────────────────────────────┐
                    │          ghrah-core (外部依赖)                │
                    │                                              │
                    │  ghrah.abilities.*                           │
                    │  ghrah.manifest.*                            │
                    │  ghrah.context.{chain,node,persistence}       │
                    │  ghrah.protocol.types                        │
                    └──┬──────────┬──────────┬──────────┬──────────┘
                       │          │          │          │
                       ▼          ▼          ▼          ▼
              ┌────────┴──────────┴──────────┴──────────┴─────────┐
              │              ghrah-subject 内部                     │
              │                                                   │
              │  config ─────────────────────────────┐            │
              │    │                                  │            │
              │    ├──► _utils ──► permission_checker │            │
              │    │                  │               │            │
              │    │                  ├──► hitl/policy│            │
              │    │                  │       │       │            │
              │    │                  │       └──► hitl/notary    │
              │    │                  │               │            │
              │    │                  ├──► ability_runner         │
              │    │                  │       │                    │
              │    │                  │       └──► sandbox/executor│
              │    │                  │               │            │
              │    │                  │               └──► sandbox/workspace
              │    │                  │                            │
              │    ├──► persistence/service                       │
              │    │       └──► persistence/migrations            │
              │    │                                             │
              │    ├──► manifest_store/store                     │
              │    │       ├──► manifest_store/service           │
              │    │       └──► manifest_store/builtins          │
              │    │                                             │
              │    ├──► ledger/models ──► ledger/chain           │
              │    │                                             │
              │    └──► server/config                            │
              │            ├──► server/connection_manager        │
              │            ├──► server/event_bus                  │
              │            ├──► server/router                    │
              │            ├──► server/server                     │
              │            └──► server/app                        │
              │                                                  │
              └────────────────────┬─────────────────────────────┘
                                   │
                                   ▼
                          ┌────────────────┐
                          │  service.py    │  ← 中央编排器
                          │ SubjectService │     聚合所有子系统
                          └────────┬───────┘
                                   │
                                   ▼
                          ┌────────────────┐
                          │    app.py      │  ← 应用入口
                          │  main()/run()  │
                          └────────┬───────┘
                                   │
                                   ▼
                          ┌────────────────┐
                          │    main.py     │  ← 最外层入口
                          └────────────────┘
```

---

### 事件与数据流

```
                    ┌──────────┐
                    │   Core   │ (ghrah-core)
                    └────┬─────┘
                         │ WebSocket
                         ▼
              ┌─────────────────────┐
              │   SubjectService     │
              │                     │
              │  ┌─────────────────┐ │
              │  │ 命令分发        │ │
              │  │ execute_ability │─┼──► AbilityRunner ──► SandboxExecutor
              │  │ persist_*       │─┼──► SubjectPersistenceService
              │  │ workspace_*     │─┼──► WorkspaceManager
              │  │ manifest_*      │─┼──► ManifestStore
              │  │ chain_history   │─┼──► ActionChainLedger
              │  └─────────────────┘ │
              │                     │
              │  ┌─────────────────┐ │
              │  │ 事件处理        │ │
              │  │ action_chain    │─┼──► ActionChainLedger (追加)
              │  │ _updated        │ │
              │  │ hitl_request    │─┼──► HITLNotary (创建 Promise)
              │  │ agent_spawned   │─┼──► WorkspaceManager (创建工作区)
              │  │ agent_terminated│─┼──► 清理资源
              │  └─────────────────┘ │
              └─────────┬───────────┘
                        │
                        │ FastAPI/WebSocket (port 4112)
                        ▼
              ┌─────────────────────┐
              │   Observer Server    │
              │                     │
              │  ObserverServer     │ ← 单连接处理
              │  ConnectionManager  │ ← 连接池 + 订阅
              │  EventBus           │ ← 事件广播 + 重放
              │  ObserverRouter     │ ← 命令路由
              │                     │
              │  ┌─────────────────┐ │
              │  │ Observer 命令   │ │
              │  │ subscribe       │ │ ← 本地: ConnectionManager
              │  │ HITL response   │ │ ← 本地: → HITLNotary.resolve()
              │  │ agent manage    │ │ ← 转发: → Core (via SubjectService)
              │  │ workspace/...   │ │ ← 本地: → 各子系统
              │  └─────────────────┘ │
              └─────────┬───────────┘
                        │
                        │ WebSocket
                        ▼
              ┌─────────────────────┐
              │   Observer(s)       │ (ghrah-observer-*)
              │   渲染 + 审批        │
              └─────────────────────┘
```

---

### 功能组织总结

| 层级 | 模块 | 职责 |
|------|------|------|
| **L0 配置** | `config` | 纯数据配置 (HITL策略、Core连接、Observer服务)，零内部依赖 |
| **L0 工具** | `_utils` | 路径提取规格表，依赖 ghrah.abilities._utils |
| **L1 权限** | `permission_checker` | 硬权限决策 (DENY/REQUIRE_HITL/ALLOW)，基于 manifest PermissionFlags + 命令安全 |
| **L1 审批** | `hitl` | HITL 策略决策 (policy) + Promise/Future 管理 (notary) |
| **L1 沙盒** | `sandbox` | 命令执行 (executor) + Git 工作区管理 (workspace) |
| **L1 持久化** | `persistence` | SQLite schema 迁移 + RemoteBackend 服务端 (13个命令处理器) |
| **L1 清单** | `manifest_store` | 文件系统 manifest CRUD + 内置种子 + 命令分发 |
| **L1 账本** | `ledger` | ActionChain 追加式不可变账本 + DAG 遍历 |
| **L1 服务** | `server` | Observer WebSocket 服务 (FastAPI + 连接管理 + 事件总线 + 路由) |
| **L2 编排** | `service` | SubjectService 中央编排器，聚合所有 L1 子系统，管理 Core WS 连接 |
| **L3 入口** | `app` + `main.py` | 配置加载 → 服务启动 → 优雅关闭 |

---

### 外部依赖总览

| 外部包 | 使用的模块 | 用途 |
|--------|-----------|------|
| `ghrah.abilities` | base, context, registry, _utils, builtin.command_safety | Ability 查找、执行上下文、路径工具、命令安全检查 |
| `ghrah.manifest` | ability, agent, builtins, errors, parser, resolver, types | Manifest 解析、验证、解析、权限标志 |
| `ghrah.context` | chain, node, persistence.serialization, persistence.sqlite_backend | 链式上下文、节点序列化、SQLite 后端 |
| `ghrah.protocol` | types (Message, EventType, CommandType, 各种 Payload, 辅助函数) | Core ↔ Subject ↔ Observer 通信协议 |
| `websockets` | — | Core WebSocket 客户端连接 |
| `fastapi` + `uvicorn` | — | Observer HTTP/WebSocket 服务器 |
| `pydantic` | — | Ledger 数据模型 |
| `yaml` (PyYAML) | — | Manifest 文件序列化 |
| `aiosqlite` | — | 异步 SQLite 操作 |
