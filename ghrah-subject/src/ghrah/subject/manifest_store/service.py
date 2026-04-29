from __future__ import annotations

import logging
from typing import Any

from ghrah.manifest.errors import (
    DuplicateManifestError,
    ManifestError,
    ManifestNotFoundError,
    ManifestValidationError,
)
from ghrah.manifest.resolver import ManifestResolver
from ghrah.subject.manifest_store.store import ManifestStore

logger = logging.getLogger(__name__)

__all__ = ["handle_manifest_command"]

_MANIFEST_COMMANDS = frozenset({
    "manifest_list_abilities",
    "manifest_get_ability",
    "manifest_put_ability",
    "manifest_delete_ability",
    "manifest_list_agents",
    "manifest_get_agent",
    "manifest_put_agent",
    "manifest_delete_agent",
    "manifest_resolve_agent",
    "manifest_validate",
})


def handle_manifest_command(
    command: str,
    payload: dict[str, Any],
    store: ManifestStore,
) -> dict[str, Any]:
    """分发 manifest 命令，返回响应 dict。

    Args:
        command: 命令类型，如 'manifest_list_abilities'
        payload: 命令载荷
        store: ManifestStore 实例

    Returns:
        响应 dict，包含 success 字段
    """
    try:
        if command == "manifest_list_abilities":
            namespace = payload.get("namespace")
            names = store.list_abilities(namespace=namespace)
            return {"success": True, "data": {"abilities": names}}

        elif command == "manifest_get_ability":
            full_name = payload.get("full_name", "")
            manifest = store.get_ability(full_name)
            return {
                "success": True,
                "data": {"manifest": manifest.model_dump(mode="python")},
            }

        elif command == "manifest_put_ability":
            full_name = payload.get("full_name", "")
            content = payload.get("content", "")
            overwrite = payload.get("overwrite", False)
            store.put_ability(full_name, content, overwrite=overwrite)
            return {"success": True, "data": {"full_name": full_name}}

        elif command == "manifest_delete_ability":
            full_name = payload.get("full_name", "")
            store.delete_ability(full_name)
            return {"success": True, "data": {"full_name": full_name}}

        elif command == "manifest_list_agents":
            namespace = payload.get("namespace")
            names = store.list_agents(namespace=namespace)
            return {"success": True, "data": {"agents": names}}

        elif command == "manifest_get_agent":
            full_name = payload.get("full_name", "")
            manifest = store.get_agent(full_name)
            return {
                "success": True,
                "data": {"manifest": manifest.model_dump(mode="python")},
            }

        elif command == "manifest_put_agent":
            full_name = payload.get("full_name", "")
            content = payload.get("content", "")
            overwrite = payload.get("overwrite", False)
            store.put_agent(full_name, content, overwrite=overwrite)
            return {"success": True, "data": {"full_name": full_name}}

        elif command == "manifest_delete_agent":
            full_name = payload.get("full_name", "")
            store.delete_agent(full_name)
            return {"success": True, "data": {"full_name": full_name}}

        elif command == "manifest_resolve_agent":
            agent_full_name = payload.get("agent_full_name", "")
            runtime_name = payload.get("runtime_name")
            manifest = store.get_agent(agent_full_name)
            resolver = ManifestResolver(store)
            resolved = resolver.resolve(manifest, runtime_name=runtime_name)
            return {
                "success": True,
                "data": {
                    "config": resolved.config.model_dump()
                    if hasattr(resolved.config, "model_dump")
                    else resolved.config.__dict__,
                    "abilities": [
                        {
                            "ability_name": a.ability_name,
                            "permissions": a.permissions.model_dump(mode="python"),
                            "implementation": a.implementation.model_dump(mode="python"),
                        }
                        for a in resolved.abilities
                    ],
                },
            }

        elif command == "manifest_validate":
            content = payload.get("content", "")
            is_valid, errors = store.validate_manifest(content)
            return {"success": True, "data": {"valid": is_valid, "errors": errors}}

        else:
            return {"success": False, "error": f"Unknown manifest command: {command}"}

    except ManifestNotFoundError as e:
        logger.warning("Manifest not found: %s", e)
        return {"success": False, "error": str(e)}
    except DuplicateManifestError as e:
        logger.warning("Duplicate manifest: %s", e)
        return {"success": False, "error": str(e)}
    except ManifestValidationError as e:
        logger.warning("Manifest validation error: %s", e)
        return {"success": False, "error": str(e)}
    except ManifestError as e:
        logger.error("Manifest error: %s", e)
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error handling manifest command %s", command)
        return {"success": False, "error": f"Internal error: {e}"}
