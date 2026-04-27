"""ghrah-subject 应用入口。"""

from __future__ import annotations

import asyncio
import logging

from ghrah.subject.config import SubjectConfig
from ghrah.subject.service import SubjectService


async def run() -> None:
    """异步入口：创建并运行 SubjectService。"""
    config = SubjectConfig.from_env()
    service = SubjectService(config)

    try:
        await service.start()
        # 保持运行，直到被中断
        while service._running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger = logging.getLogger(__name__)
        logger.info("Received KeyboardInterrupt, shutting down...")
    finally:
        await service.stop()


def main() -> None:
    """Subject 服务入口函数。"""
    config = SubjectConfig.from_env()

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger = logging.getLogger(__name__)
    logger.info("ghrah-subject starting...")
    logger.info("  workspace_root: %s", config.workspace_root)
    logger.info("  db_path: %s", config.db_path)
    logger.info("  gateway_url: %s", config.gateway.url)

    asyncio.run(run())


if __name__ == "__main__":
    main()
