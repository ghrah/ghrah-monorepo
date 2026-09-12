# @ghrah/protocol

TypeScript protocol types, enums, builders, and Zod validators for the ghrah multi-agent runtime.

```sh
pnpm add @ghrah/protocol
```

This package follows the Python `ghrah-protocol` wire contract. Payload schemas live in
`src/payloads/` split by domain (`agent`, `persist`, `workspace`, `manifest`, `session`,
`task`, `project`, `room`, `system`), mirroring the Python `ghrah/protocol/payloads/`
modules one-to-one; `src/payloads.ts` re-exports them all. See the
[ghrah monorepo](https://github.com/ghrah/ghrah-monorepo) for documentation and source.
