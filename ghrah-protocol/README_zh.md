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
    ├── __init__.py       # 公共 API 重导出
    └── types.py          # 所有类型定义：枚举、载荷模型、消息信封、辅助函数
```

## 许可证

Apache 2.0