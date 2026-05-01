# ghrah-protocol

[简体中文](./README_zh.md)

Shared protocol type definitions for the ghrah distributed agent cluster framework.

Defines all WebSocket message envelope formats, command types, event types, and payload models using Pydantic for type safety and JSON serialization compatibility.

## Project Structure

```
ghrah-protocol/
├── pyproject.toml
├── LICENSES/
│   └── Apache-2.0.txt
└── src/ghrah/protocol/
    ├── __init__.py       # Public API re-exports
    └── types.py          # All type definitions: enums, payload models, Message envelope, helpers
```

## License

Apache 2.0