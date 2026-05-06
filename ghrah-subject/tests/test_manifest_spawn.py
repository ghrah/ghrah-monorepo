from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ghrah.subject.manifest_store.store import ManifestStore

VALID_AGENT_YAML = """\
manifest: agent
version: "1"
metadata:
  namespace: ghrah
  name: coder
  description: A coder agent
model:
  agent_config_name: default
  temperature: 0.3
system_prompt: You are a coder.
max_iterations: 20
abilities:
  - type: read_file
  - type: write_file
    permissions:
      require_hitl: true
  - type: conversation
  - type: end_task
"""


@pytest.fixture
def store(tmp_path: Path) -> ManifestStore:
    s = ManifestStore(tmp_path / "manifests")
    s.ensure_dirs()
    return s


def _make_service_with_store(store: ManifestStore) -> MagicMock:
    svc = MagicMock()
    svc._manifest_store = store

    return svc


class TestResolveSpawnManifest:
    @pytest.fixture
    def service(self, store: ManifestStore) -> MagicMock:
        store.put_agent("ghrah.coder", VALID_AGENT_YAML)
        return _make_service_with_store(store)

    def test_expands_config_from_manifest(self, service: MagicMock) -> None:
        from ghrah.subject.service import SubjectService

        payload = {
            "manifest_ref": "ghrah.coder",
            "config": {"name": "my-coder"},
            "abilities": None,
        }
        result = SubjectService._resolve_spawn_manifest(service, payload)

        assert result["manifest_ref"] is None
        config = result["config"]
        assert config["name"] == "my-coder"
        assert config["agent_config_name"] == "default"
        assert config["system_prompt"] == "You are a coder."
        assert config["max_iterations"] == 20
        assert config["communication_timeout"] == 300.0
        assert config["description"] == ""

    def test_expands_abilities_from_manifest(self, service: MagicMock) -> None:
        from ghrah.subject.service import SubjectService

        payload = {
            "manifest_ref": "ghrah.coder",
            "config": {"name": "my-coder"},
            "abilities": None,
        }
        result = SubjectService._resolve_spawn_manifest(service, payload)

        abilities = result["abilities"]
        assert abilities is not None
        ability_types = [a["ability_type"] for a in abilities]
        assert "read_file" in ability_types
        assert "write_file" in ability_types
        assert "conversation" in ability_types
        assert "end_task" in ability_types

    def test_model_overrides_present(self, service: MagicMock) -> None:
        from ghrah.subject.service import SubjectService

        payload = {
            "manifest_ref": "ghrah.coder",
            "config": {"name": "my-coder"},
            "abilities": None,
        }
        result = SubjectService._resolve_spawn_manifest(service, payload)

        model_overrides = result["config"]["model_overrides"]
        assert model_overrides is not None
        assert model_overrides["temperature"] == 0.3

    def test_manifest_ref_cleared(self, service: MagicMock) -> None:
        from ghrah.subject.service import SubjectService

        payload = {
            "manifest_ref": "ghrah.coder",
            "config": {"name": "my-coder"},
            "abilities": None,
        }
        result = SubjectService._resolve_spawn_manifest(service, payload)

        assert result["manifest_ref"] is None

    def test_manifest_not_found_raises(self, store: ManifestStore) -> None:
        from ghrah.manifest.errors import ManifestNotFoundError

        from ghrah.subject.service import SubjectService

        service = _make_service_with_store(store)
        payload = {
            "manifest_ref": "nonexistent.agent",
            "config": {"name": "test"},
            "abilities": None,
        }
        with pytest.raises(ManifestNotFoundError):
            SubjectService._resolve_spawn_manifest(service, payload)

    def test_manifest_store_none_raises(self) -> None:
        from ghrah.subject.service import SubjectService

        service = MagicMock()
        service._manifest_store = None
        payload = {
            "manifest_ref": "ghrah.coder",
            "config": {"name": "test"},
            "abilities": None,
        }
        with pytest.raises(RuntimeError, match="ManifestStore is not initialized"):
            SubjectService._resolve_spawn_manifest(service, payload)
