# @ghrah/plugin-registry

TS half plugin infrastructure for ghrah observer hosts: spec validation, host capability checks, bucketed registry, negotiation report builder and loader adapter.

## Vue sharing via import map

Plugins must treat `vue` as external (peer). The host maps the bare specifier `"vue"` to a shim (`/plugins/shared/vue.js`) that re-exports a **whitelisted** subset of the host Vue instance (`defineComponent/h/ref/computed/reactive/readonly/watch/watchEffect/onMounted/onUnmounted/inject/provide/nextTick/Fragment`). Using an API outside the whitelist fails at runtime — extend the whitelist in the host assets explicitly when needed.

## Plugin contract

Plugin ESM exports `activate(api)`; `api.registerBadgeRenderer(kind, component)` registers host-Vue components. Plugins must not import this package at runtime — `import type` only.
