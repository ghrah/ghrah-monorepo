# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Ouroboros 装配增长网（阶段 2）：mount_builtin_units 工厂集成测试。

随迁移逐 unit 增长：每迁移一个 unit，工厂追加挂载 + 本文件加断言行。
统一 ``asyncio.wait_for`` 超时保护——inject 名单错导致 PENDING 时表现为
失败而非挂起。
"""

from __future__ import annotations

from pathlib import Path

from ouroboros import Context, FiberState  # type: ignore[import-untyped]

from ghrah.subject.config import SubjectConfig
from ghrah.subject.units import mount_builtin_units


def _config(tmp_path: Path) -> SubjectConfig:
    return SubjectConfig(
        workspace_root=str(tmp_path / "workspace"),
        db_path=str(tmp_path / "subject.db"),
        manifest_root=str(tmp_path / "manifests"),
    )


async def test_coexistence_assembly_all_fibers_active(tmp_path: Path) -> None:
    config = _config(tmp_path)
    async with Context() as ctx:
        fibers = await mount_builtin_units(ctx, config, profile="coexistence")
        assert fibers
        assert set(fibers) == {
            "persistence",
            "sandbox",
            "manifest_store",
            "ledger",
            "workspace",
            "hitl_policy",
            "permissions",
            "hitl_notary",
            "ability_runner",
            "task",
            "desired_state",
        }

        # 计划 0.4：逐 fiber ACTIVE 断言（工厂已等 ACTIVE，此处显式兜底）
        for fiber in fibers.values():
            assert fiber.state is FiberState.ACTIVE

        assert ctx.get("persistence") is not None
        assert ctx.get("sandbox_executor") is not None
        assert ctx.get("manifest_store") is not None
        assert ctx.get("manifest_permission_index") is not None
        assert ctx.get("ledger") is not None
        assert ctx.get("workspace_service") is not None
        assert ctx.get("workspace_manager") is not None
        assert ctx.get("hitl_policy") is not None
        assert ctx.get("permission_service") is not None
        assert ctx.get("hitl_notary") is not None
        assert ctx.get("ability_executor") is not None
        assert ctx.get("task_manager") is not None
        assert ctx.get("task_store") is not None
        assert ctx.get("desired_state_store") is not None


class _ClusterTransportStub:
    """full 装配测试的 cluster 占位（cluster_transport unit 归项① Core Unit）。

    仅满足 project/recovery 构造期的存储面；装配断言不触发 cluster 调用。
    """


async def test_full_assembly_with_cluster_stub_all_fibers_active(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    async with Context() as ctx:
        ctx.provide("cluster_transport_manager", _ClusterTransportStub())

        fibers = await mount_builtin_units(ctx, config, profile="full")
        assert set(fibers) == {
            "persistence",
            "sandbox",
            "manifest_store",
            "ledger",
            "workspace",
            "hitl_policy",
            "permissions",
            "hitl_notary",
            "ability_runner",
            "task",
            "desired_state",
            "websocket_observer_endpoint",
            "project",
            "recovery",
        }

        # 计划 0.4：逐 fiber ACTIVE 断言（工厂已等 ACTIVE，此处显式兜底）
        for fiber in fibers.values():
            assert fiber.state is FiberState.ACTIVE

        assert ctx.get("observer_endpoint") is not None
        assert ctx.get("observer_event_bus") is not None
        assert ctx.get("project_manager") is not None
        assert ctx.get("reconciliation_service") is not None
