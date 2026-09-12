# SPDX-FileCopyrightText: 2026 chenxya <chenxya@ghrah.org>
#
# SPDX-License-Identifier: Apache-2.0
"""共享协议类型定义（兼容门面）。

定义所有 WebSocket 消息的信封格式和载荷模型。
使用 Pydantic 确保类型安全和 JSON 序列化兼容性。

历史单文件 types.py 已按域拆分为 enums / routing / payloads / envelope /
factories 子模块；本模块保留原导入路径 ``ghrah.protocol.types`` 的完整
符号面（新代码请直接从域子模块导入）。
"""

from __future__ import annotations

import time  # noqa: F401
import uuid  # noqa: F401
from enum import StrEnum  # noqa: F401
from typing import Any, TypeVar  # noqa: F401

from pydantic import BaseModel, ConfigDict, Field  # noqa: F401

from ghrah.protocol.enums import *  # noqa: F403
from ghrah.protocol.envelope import *  # noqa: F403
from ghrah.protocol.factories import *  # noqa: F403
from ghrah.protocol.payloads import *  # noqa: F403
from ghrah.protocol.routing import *  # noqa: F403

# Message = Envelope 别名（向后兼容；新代码应直接使用 Envelope）。
# 因 Envelope 非泛型，别名稳定，不再绑定泛型参数。
Message = Envelope  # noqa: F405
