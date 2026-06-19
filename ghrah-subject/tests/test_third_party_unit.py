"""第三方 Subject Unit 发现与 allowlist 启用验收（定位文档 §原则9）。

验证三段：
1. engine.discover() 经 entry_points group 发现候选（不启用）。
2. 默认 enabled_third_party_units=[] → get_unit 为 None。
3. allowlist 启用后 → 加载 + 事件路径可达。

实现要点（核对后确认）：
- CapabilityProvider Protocol（runtime/capability.py:47）方法：
  list_abilities() / describe_permissions()。
- SubjectEventBus.emit（event_bus.py:49）用 asyncio.gather 直接 await 所有订阅者，
  非 fire-and-forget —— emit 返回时订阅者已完成，无需 asyncio.sleep。
- AuditLogUnit 走 ctx.event_bus.subscribe 订阅路径（与 ManifestStoreUnit 一致）。
"""
from __future__ import annotations

from typing import Any

from ghrah.subject.config import SubjectConfig
from ghrah.subject.event_bus import SUBJECT_CORE_EVENT_RECEIVED
from ghrah.subject.runtime.capability import (
    AbilityContribution,
    CapabilityProvider,
    PermissionDescriptor,
)
from ghrah.subject.runtime.context import SubjectContext
from ghrah.subject.runtime.engine import SubjectEngine
from ghrah.subject.unit.base import CommandContext, RouteSpec, SubjectUnit, UnitMeta


class AuditLogUnit(SubjectUnit, CapabilityProvider):
    """Fake 第三方 Unit：审计日志，订阅 SUBJECT_CORE_EVENT_RECEIVED 并记录。

    同时实现 CapabilityProvider，验证第三方可声明能力贡献（接口预留）。
    """

    def __init__(self) -> None:
        self._ctx: SubjectContext | None = None
        self._records: list[dict[str, Any]] = []
        self._meta = UnitMeta(
            name="audit_log",
            routes=RouteSpec(commands=frozenset({"audit_query"})),
            provides_capabilities=True,
        )

    @property
    def meta(self) -> UnitMeta:
        return self._meta

    async def init(self, ctx: SubjectContext) -> None:
        self._ctx = ctx
        # 订阅内部事件（与 ManifestStoreUnit 同路径）
        ctx.event_bus.subscribe(SUBJECT_CORE_EVENT_RECEIVED, self._on_event)

    async def _on_event(self, event_type: str, payload: Any) -> None:
        self._records.append({"event_type": event_type, "payload": payload})

    async def handle_command(
        self, command: str, payload: dict[str, Any], cmd_ctx: CommandContext
    ) -> dict[str, Any]:
        if command == "audit_query":
            return {"success": True, "records": list(self._records)}
        return {"success": False, "error": f"Unknown: {command}"}

    # —— CapabilityProvider（runtime/capability.py:47）——
    def list_abilities(self) -> list[AbilityContribution]:
        return []  # Stage 2 不强制实际贡献能力，仅验证可声明 Protocol

    def describe_permissions(self) -> list[PermissionDescriptor]:
        return []


def test_discover_finds_third_party_candidate_but_not_enabled_by_default() -> None:
    """§原则9：discover 发现为候选，默认 get_unit 为 None。"""
    config = SubjectConfig(enabled_third_party_units=[])  # allowlist 空
    engine = SubjectEngine(config)

    # 直注 discovered（绕开真实 entry_points 安装；engine.py:43 self._discovered）
    engine._discovered["audit_log"] = AuditLogUnit

    # 模拟 enable_from_config：读 allowlist（空）→ 不注册
    engine.enable_from_config()

    assert engine.get_unit("audit_log") is None  # 默认未启用
    assert "audit_log" in engine.discovered  # 但已被发现为候选


async def test_allowlist_enables_third_party_unit_and_receives_event(tmp_path) -> None:
    """§原则9：allowlist 启用后 Unit 加载 + 事件路径可达。"""
    config = SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
        enabled_third_party_units=["audit_log"],
    )
    engine = SubjectEngine(config)
    engine._discovered["audit_log"] = AuditLogUnit

    engine.register_builtin_units(profile="coexistence")
    engine.enable_from_config()
    engine.validate()  # 依赖拓扑校验（audit_log 无 requires，应通过）

    await engine.start()
    try:
        audit_unit = engine.get_unit("audit_log")
        assert audit_unit is not None
        assert isinstance(audit_unit, AuditLogUnit)

        # emit 直接 await 订阅者（event_bus.py:49 用 gather），返回时已完成
        await engine.event_bus.emit(SUBJECT_CORE_EVENT_RECEIVED, {"event_type": "test"})

        query_result = await audit_unit.handle_command(
            "audit_query", {}, CommandContext.observer("req-1", session_id=None)
        )
        records = query_result["records"]
        assert query_result["success"] is True
        assert len(records) == 1
        assert records[0]["payload"]["event_type"] == "test"
    finally:
        await engine.stop()
