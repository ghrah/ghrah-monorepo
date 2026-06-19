"""ghrah-subject 应用入口。

S2.3 后改用 SubjectEngine 装配（profile="full"）：
register_builtin_units -> discover -> enable_from_config -> validate ->
start -> run_forever -> stop。
"""

from __future__ import annotations

import asyncio
import logging

from ghrah.subject.config import SubjectConfig
from ghrah.subject.runtime.engine import SubjectEngine


async def run_forever() -> None:
    """异步入口：装配 SubjectEngine 并运行（断线由 transport Unit 处理）。"""
    config = SubjectConfig.from_env()
    engine = SubjectEngine(config)
    engine.register_builtin_units(profile="full")
    engine.discover()
    engine.enable_from_config()
    engine.validate()
    try:
        # engine.run_forever 内部已 start()，不再单独 await engine.start()。
        await engine.run_forever()
    finally:
        await engine.stop()


def main() -> None:
    """Subject 服务入口函数。"""
    config = SubjectConfig.from_env()

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger = logging.getLogger(__name__)
    logger.info("ghrah-subject starting (engine, profile=full)...")
    logger.info("  workspace_root: %s", config.workspace_root)
    logger.info("  db_path: %s", config.db_path)
    logger.info("  core_url: %s", config.core.url)

    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down...")


if __name__ == "__main__":
    main()
