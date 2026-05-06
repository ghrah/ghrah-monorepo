# ghrah-subject

ghrah 控制面/执行层 - 持有工作区、执行沙箱命令、持久化 ActionChain、裁决 HITL。

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