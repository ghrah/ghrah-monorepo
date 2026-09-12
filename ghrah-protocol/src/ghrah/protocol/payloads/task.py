# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0
"""Task 域载荷模型（命令与事件）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ghrah.protocol.enums import TaskPriority, TaskStatus

# ─── Task 命令和事件载荷模型 ───


class TaskInfoPayload(BaseModel):
    """Task 信息载荷，用于 task 命令结果和事件。"""

    task_id: str
    project_id: str
    title: str
    description: str = ""
    agent_id: str | None = None
    agent_name: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    parent_id: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    result: Any = None
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskCreatePayload(BaseModel):
    """task_create 命令载荷。"""

    title: str
    project_id: str
    description: str = ""
    agent_id: str | None = None
    agent_name: str | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    parent_id: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdatePayload(BaseModel):
    """task_update 命令载荷。"""

    task_id: str
    title: str | None = None
    description: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    parent_id: str | None = None
    dependencies: list[str] | None = None
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    metadata_patch: dict[str, Any] | None = None
    expected_version: int | None = None


class TaskIdPayload(BaseModel):
    """task_* 单任务命令载荷。"""

    task_id: str


class TaskAssignPayload(TaskIdPayload):
    """task_assign 命令载荷。"""

    agent_id: str = ""
    agent_name: str


class TaskCompletePayload(TaskIdPayload):
    """task_complete 命令载荷。"""

    result: Any = None


class TaskFailPayload(TaskIdPayload):
    """task_fail 命令载荷。"""

    error: str


class TaskCancelPayload(TaskIdPayload):
    """task_cancel 命令载荷。"""

    reason: str | None = None


class TaskBlockPayload(TaskIdPayload):
    """task_block 命令载荷。"""

    reason: str | None = None


class TaskListPayload(BaseModel):
    """task_list 命令载荷。"""

    agent_id: str | None = None
    agent_name: str | None = None
    status: TaskStatus | list[TaskStatus] | None = None
    parent_id: str | None = None
    project_id: str | None = None
    include_terminal: bool = True
    limit: int = 100


class TaskDeletePayload(TaskIdPayload):
    """task_delete 命令载荷。"""

    force: bool = False


class TaskListResultPayload(BaseModel):
    """task_list 命令响应载荷。"""

    tasks: list[TaskInfoPayload] = Field(default_factory=list)
    count: int = 0


class TaskEventPayload(BaseModel):
    """task_* 事件载荷。"""

    task: TaskInfoPayload
    previous_status: TaskStatus | None = None
    reason: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
