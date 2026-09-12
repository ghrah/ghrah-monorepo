# ghrah-protocol

ghrah 分布式智能体集群框架的组件间共享协议定义。

定义了所有 WebSocket 消息信封格式、命令类型、事件类型和载荷模型，使用 Pydantic 确保类型安全和 JSON 序列化兼容性。

## 项目结构

```
ghrah-protocol/
├── pyproject.toml
├── LICENSES/
│   └── Apache-2.0.txt
└── src/ghrah/protocol/
    ├── __init__.py       # 包级重导出（经 types.py 门面）
    ├── types.py          # 兼容门面：再导出下列全部内容
    ├── enums.py          # 枚举：ClientType / CommandType / EventType / SystemType / 各域附属枚举
    ├── routing.py        # 命令路由分组（*_COMMANDS）与 Agent 作用域事件契约
    ├── payloads/         # 按域拆分的载荷模型（agent、persist、workspace、manifest、
    │                     #   session、task、project、room、system）
    ├── envelope.py       # Envelope 信封、type → payload 注册表、envelope_from_dict
    └── factories.py      # create_command_result / create_event 等构造辅助
```

## 许可证

Apache 2.0