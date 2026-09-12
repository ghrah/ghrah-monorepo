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
    ├── __init__.py       # Package re-exports (via the types.py facade)
    ├── types.py          # Compatibility facade: re-exports everything below
    ├── enums.py          # Enums: ClientType / CommandType / EventType / SystemType / domain enums
    ├── routing.py        # Command routing groups (*_COMMANDS) + agent-scoped event contract
    ├── payloads/         # Payload models by domain (agent, persist, workspace, manifest,
    │                     #   session, task, project, room, system)
    ├── envelope.py       # Envelope, type → payload registries, envelope_from_dict
    └── factories.py      # create_command_result / create_event / ... helpers
```

## License

Apache 2.0