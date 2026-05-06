"""Subject 持久化服务：接收 Core Server 的持久化命令，委托给 SqliteBackend 执行。

SubjectPersistenceService 是 Core 的 RemoteBackend 的服务端。
Core 通过 Subject 连接发送 persist_* 命令，Subject 接收并执行实际的 SQLite I/O。
"""

from ghrah.subject.persistence.migrations import apply_migrations
from ghrah.subject.persistence.service import SubjectPersistenceService

__all__ = ["SubjectPersistenceService", "apply_migrations"]
