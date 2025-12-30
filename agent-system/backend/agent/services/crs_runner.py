import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from django.conf import settings
from django.utils import timezone

from crs_main import run_pipeline
from agent.models import Repository


@dataclass
class CRSWorkspacePaths:
    workspace_root: Path
    config_path: Path
    state_dir: Path
    inputs_dir: Path
    blueprints_path: Path
    artifacts_path: Path
    relationships_path: Path


def _repo_root() -> Path:
    return Path(settings.BASE_DIR).parents[1]


def _workspace_base_dirs() -> Dict[str, Path]:
    root = _repo_root()
    return {
        "repo_root": root,
        "clone_root": root / "workspaces",
        "crs_root": root / "crs_workspaces",
        "tools_dir": root / "tools",
    }


def _build_crs_workspace(repository: Repository) -> CRSWorkspacePaths:
    base_dirs = _workspace_base_dirs()
    crs_workspace_root = (
        base_dirs["crs_root"]
        / str(repository.system.user_id)
        / str(repository.system_id)
        / f"{repository.name}_crs"
    )
    state_dir = crs_workspace_root / "state"
    inputs_dir = crs_workspace_root / "inputs"

    blueprints_path = state_dir / "blueprints.json"
    artifacts_path = state_dir / "artifacts.json"
    relationships_path = state_dir / "relationships.json"

    crs_workspace_root.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    inputs_dir.mkdir(parents=True, exist_ok=True)

    config_path = crs_workspace_root / "config.json"
    config = {
        "version": "crs-workspace-config-v1",
        "paths": {
            "src_dir": repository.clone_path,
            "state_dir": str(state_dir),
            "inputs_dir": str(inputs_dir),
            "tools_dir": str(base_dirs["tools_dir"]),
            "blueprints_out": str(blueprints_path),
            "artifacts_out": str(artifacts_path),
            "relationships_out": str(relationships_path),
        },
        "blueprints": {
            "store_raw_text": True,
            "store_lines": True,
        },
    }
    config_path.write_text(json.dumps(config, indent=2))

    if repository.crs_workspace_path != str(crs_workspace_root):
        repository.crs_workspace_path = str(crs_workspace_root)
        repository.save(update_fields=["crs_workspace_path"])

    return CRSWorkspacePaths(
        workspace_root=crs_workspace_root,
        config_path=config_path,
        state_dir=state_dir,
        inputs_dir=inputs_dir,
        blueprints_path=blueprints_path,
        artifacts_path=artifacts_path,
        relationships_path=relationships_path,
    )


def run_crs_pipeline(repository: Repository) -> Dict[str, Any]:
    if not repository.clone_path or not Path(repository.clone_path).is_dir():
        raise RuntimeError("Repository clone not found. Clone the repository before running CRS.")
    paths = _build_crs_workspace(repository)
    original_config = os.environ.get("CRS_CONFIG")
    os.environ["CRS_CONFIG"] = str(paths.config_path)
    try:
        run_pipeline()
    finally:
        if original_config is None:
            os.environ.pop("CRS_CONFIG", None)
        else:
            os.environ["CRS_CONFIG"] = original_config

    artifacts_payload = _load_payload(paths.artifacts_path)
    relationships_payload = _load_payload(paths.relationships_path)

    artifacts_count = len(artifacts_payload.get("artifacts", [])) if isinstance(artifacts_payload, dict) else 0
    relationships_count = len(relationships_payload.get("relationships", [])) if isinstance(relationships_payload, dict) else 0

    repository.artifacts_count = artifacts_count
    repository.relationships_count = relationships_count
    repository.last_crs_run = timezone.now()
    repository.crs_status = "ready"
    repository.status = "ready"
    repository.save(
        update_fields=[
            "artifacts_count",
            "relationships_count",
            "last_crs_run",
            "crs_status",
            "status",
        ]
    )

    return {
        "artifacts_count": artifacts_count,
        "relationships_count": relationships_count,
        "blueprints_path": str(paths.blueprints_path),
        "artifacts_path": str(paths.artifacts_path),
        "relationships_path": str(paths.relationships_path),
    }


def _load_payload(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_crs_payload(repository: Repository, payload_type: str) -> Dict[str, Any]:
    paths = _build_crs_workspace(repository)
    payload_map = {
        "blueprints": paths.blueprints_path,
        "artifacts": paths.artifacts_path,
        "relationships": paths.relationships_path,
    }
    target_path = payload_map.get(payload_type)
    if not target_path:
        raise ValueError(f"Unknown CRS payload type: {payload_type}")
    return _load_payload(target_path)


def get_crs_summary(repository: Repository) -> Dict[str, Any]:
    paths = _build_crs_workspace(repository)
    blueprints_payload = _load_payload(paths.blueprints_path)
    artifacts_payload = _load_payload(paths.artifacts_path)
    relationships_payload = _load_payload(paths.relationships_path)

    return {
        "status": repository.status,
        "crs_status": repository.crs_status,
        "last_crs_run": repository.last_crs_run,
        "artifacts_count": repository.artifacts_count,
        "relationships_count": repository.relationships_count,
        "blueprints_count": blueprints_payload.get("file_count", 0),
        "artifact_items": len(artifacts_payload.get("artifacts", [])) if artifacts_payload else 0,
        "relationship_items": len(relationships_payload.get("relationships", [])) if relationships_payload else 0,
    }
