"""ghrah-subject 应用入口。"""

from __future__ import annotations

import logging

from ghrah.subject.config import SubjectConfig


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

    # TODO: 初始化 Subject 服务（后续步骤实现）


if __name__ == "__main__":
    main()
