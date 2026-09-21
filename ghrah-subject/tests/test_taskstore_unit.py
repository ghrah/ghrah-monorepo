# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0

"""TaskStoreUnit 测试：四命令经 bridge_command 端到端 + enabled=False 不挂载。

内核 task 经 TASKSTORE_SERVICE facade 创建（P0 无 wire 创建命令）。
"""

from __future__ import annotations

from typing import Any

import pytest
from ghrah.taskstore.models import Verification
from ouroboros import Context  # type: ignore[import-untyped]

from ghrah.subject.config import SubjectConfig, TaskStoreConfig
from ghrah.subject.runtime.ouroboros_bridge import bridge_command, mount_dynamic_unit
from ghrah.subject.runtime.route_registry import UnitRouteRegistry
from ghrah.subject.units.taskstore import TaskStoreUnit


def _config(db_path: str, *, enabled: bool = True) -> SubjectConfig:
    return SubjectConfig(taskstore_slice=TaskStoreConfig(enabled=enabled, db_path=db_path))


async def _mounted_unit(ctx: Any, config: SubjectConfig) -> TaskStoreUnit:
    unit = TaskStoreUnit(config)
    fibers: dict[str, Any] = {}
    await mount_dynamic_unit(ctx, unit, fibers, route_registry=UnitRouteRegistry())
    return unit


async def _make_task(ctx: Any, *, checks: list[str] | None = None) -> Any:
    kernel = ctx.get("taskstore_service")
    verification = None
    if checks:
        verification = Verification(evidence_min=1, evidence_kinds=["git_commit"], checks=checks)
    return await kernel.create_task(project_id="p1", title="demo", verification=verification)


def _fake_commit_checker(evidence: Any, task: Any, config: Any) -> dict[str, Any]:
    kinds = [e.get("kind") for e in evidence["items"]]
    return {"passed": "git_commit" in kinds, "detail": None}


async def test_four_commands_end_to_end(tmp_path) -> None:
    """submit（Denial + 成功两路）/ verify / list_claims / dump 四命令端到端。"""
    async with Context() as ctx:
        unit = await _mounted_unit(ctx, _config(str(tmp_path / "ts.sqlite3")))
        task = await _make_task(ctx, checks=["commit_in_repo"])

        # 1) 无证据 submit → Denial（D18① 形状：success=False + data.gaps + error）
        result = await bridge_command(
            ctx,
            "task_submit_completion",
            {"task_id": task.task_id, "claimant_id": "agent-1"},
        )
        assert result["success"] is False
        gaps = result["data"]["gaps"]
        assert gaps["evidence_have"] == 0
        assert gaps["evidence_need"] == 1
        assert gaps["missing_evidence_kinds"] == ["git_commit"]
        assert [m["checker"] for m in gaps["missing_checks"]] == ["commit_in_repo"]
        assert result["error"] is not None

        # 2) checker 未注册 → 补证据仍 Denial（缺口含 checker）
        result = await bridge_command(
            ctx,
            "task_submit_completion",
            {
                "task_id": task.task_id,
                "claimant_id": "agent-1",
                "evidence": [{"kind": "git_commit", "ref": "abc", "digest": "d1"}],
            },
        )
        assert result["success"] is False
        assert len(result["data"]["gaps"]["missing_checks"]) == 1

        # 3) 注册 fake checker → submit 通过
        unit._kernel._checkers.register("commit_in_repo", _fake_commit_checker)
        result = await bridge_command(
            ctx,
            "task_submit_completion",
            {
                "task_id": task.task_id,
                "claimant_id": "agent-1",
                "evidence": [{"kind": "git_commit", "ref": "abc", "digest": "d1"}],
            },
        )
        assert result["success"] is True, result
        claim = result["data"]["claim"]
        assert claim["state"] == "submitted"
        assert claim["checks"] == [{"checker": "commit_in_repo", "passed": True, "detail": None}]

        # 4) task_verify（他人）→ completed
        result = await bridge_command(
            ctx,
            "task_verify",
            {
                "task_id": task.task_id,
                "claim_id": claim["claim_id"],
                "verdict": "verified",
                "verifier_id": "agent-2",
            },
        )
        assert result["success"] is True
        assert result["data"]["task_status"] == "completed"

        # 5) task_list_claims / task_dump 取回归因链（探针 1：claimant/evidence/verdict）
        result = await bridge_command(ctx, "task_list_claims", {"task_id": task.task_id})
        assert result["success"] is True
        claims = result["data"]["claims"]
        assert len(claims) == 1
        assert claims[0]["verdict_by"] == "agent-2"
        assert len(claims[0]["evidence"]) == 1

        result = await bridge_command(ctx, "task_dump", {"project_id": "p1"})
        assert result["success"] is True
        dump = result["data"]
        assert len(dump["tasks"]) == 1
        assert dump["tasks"][0]["status"] == "completed"
        assert len(dump["claims"]) == 1
        assert len(dump["evidence"]) == 1
        # claims 内嵌 evidence 与 evidence 列表同源（表级保真）
        assert dump["claims"][0]["evidence"][0]["evidence_id"] == dump["evidence"][0]["evidence_id"]


async def test_self_approval_denied_via_wire(tmp_path) -> None:
    """探针 2（wire 面）：approver 非空时 claimant 自批拒。"""
    async with Context() as ctx:
        await _mounted_unit(ctx, _config(str(tmp_path / "ts.sqlite3")))
        kernel = ctx.get("taskstore_service")
        task = await kernel.create_task(
            project_id="p1",
            title="demo",
            verification=Verification(evidence_min=0, approver="human"),
        )
        submit = await bridge_command(
            ctx,
            "task_submit_completion",
            {"task_id": task.task_id, "claimant_id": "agent-1"},
        )
        assert submit["success"] is True
        claim_id = submit["data"]["claim"]["claim_id"]

        result = await bridge_command(
            ctx,
            "task_verify",
            {
                "task_id": task.task_id,
                "claim_id": claim_id,
                "verdict": "verified",
                "verifier_id": "agent-1",
            },
        )
        assert result["success"] is False


async def test_dump_limit_semantics(tmp_path) -> None:
    """D18②：limit 仅限 tasks，claims/evidence 随所选 tasks 收敛。"""
    async with Context() as ctx:
        await _mounted_unit(ctx, _config(str(tmp_path / "ts.sqlite3")))
        kernel = ctx.get("taskstore_service")
        t1 = await kernel.create_task(project_id="p1", title="t1")
        t2 = await kernel.create_task(project_id="p1", title="t2")
        for t in (t1, t2):
            result = await bridge_command(
                ctx,
                "task_submit_completion",
                {"task_id": t.task_id, "claimant_id": "a"},
            )
            assert result["success"] is True

        full = await bridge_command(ctx, "task_dump", {})
        assert len(full["data"]["tasks"]) == 2
        assert len(full["data"]["claims"]) == 2

        limited = await bridge_command(ctx, "task_dump", {"limit": 1})
        assert len(limited["data"]["tasks"]) == 1
        assert len(limited["data"]["claims"]) == 1
        assert limited["data"]["claims"][0]["task_id"] == limited["data"]["tasks"][0]["task_id"]


async def test_enabled_false_returns_unknown(tmp_path) -> None:
    """enabled=False 不挂载 → 归因命令回落 Unknown command（零隐式）。"""
    async with Context() as ctx:
        result = await bridge_command(ctx, "task_dump", {})
        assert result["success"] is False
        assert "Unknown command" in result["error"]

    config = _config(str(tmp_path / "x.sqlite3"), enabled=False)
    assert config.taskstore.enabled is False


async def test_taskstore_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GHRAH_SUBJECT_TASKSTORE_ENABLED", "false")
    monkeypatch.setenv("GHRAH_SUBJECT_TASKSTORE_DB", "/tmp/x/taskstore.sqlite3")
    config = SubjectConfig.from_env()
    assert config.taskstore.enabled is False
    assert config.taskstore.db_path == "/tmp/x/taskstore.sqlite3"

    monkeypatch.setenv("GHRAH_SUBJECT_TASKSTORE_ENABLED", "true")
    monkeypatch.delenv("GHRAH_SUBJECT_TASKSTORE_DB", raising=False)
    config = SubjectConfig.from_env()
    assert config.taskstore.enabled is True
    assert config.taskstore.db_path.endswith("taskstore.sqlite3")
