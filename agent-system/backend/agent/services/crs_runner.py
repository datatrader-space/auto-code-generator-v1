import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from django.conf import settings
from django.utils import timezone

from agent.models import Repository

# Add CRS directory to Python path
_crs_dir = Path(settings.BASE_DIR).parent / "crs"
if str(_crs_dir) not in sys.path:
    sys.path.insert(0, str(_crs_dir))

from crs_main import run_pipeline
from core.fs import WorkspaceFS
from core.step_runner import CRSStepRunner
from core.events import CRSEventEmitter, get_broadcaster


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
        "tools_dir": root / "agent-system" / "crs" / "tools",
    }


def _build_crs_workspace(repository: Repository) -> CRSWorkspacePaths:
    # Validate clone_path exists
    if not repository.clone_path:
        raise RuntimeError(
            f"Repository '{repository.name}' has no clone_path set. "
            f"Clone the repository first using POST /clone/ endpoint."
        )

    clone_path = Path(repository.clone_path)
    if not clone_path.exists():
        raise RuntimeError(
            f"Repository clone path does not exist: {clone_path}. "
            f"The repository may have been deleted or moved."
        )

    if not clone_path.is_dir():
        raise RuntimeError(
            f"Repository clone path is not a directory: {clone_path}"
        )

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
            "src_dir": str(clone_path.absolute()),  # Use absolute path
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
        "blueprints_count": blueprints_payload.get("file_count", 0),
        "artifact_items": len(artifacts_payload.get("artifacts", [])) if artifacts_payload else 0,
        "relationship_items": len(relationships_payload.get("relationships", [])) if relationships_payload else 0,
    }


def run_crs_step(
    repository: Repository,
    step_name: str,
    force: bool = False,
    run_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run a single CRS pipeline step with event emission

    Args:
        repository: Repository model instance
        step_name: Step to run (blueprints, artifacts, relationships, verification, impact)
        force: Force rerun even if up-to-date
        run_id: Optional run ID (generated if not provided)

    Returns:
        Step execution result
    """
    if not repository.clone_path or not Path(repository.clone_path).is_dir():
        raise RuntimeError(
            f"Repository not cloned. Clone path: '{repository.clone_path}'. "
            f"Please clone the repository first using POST /clone/ endpoint."
        )

    paths = _build_crs_workspace(repository)

    # Set up environment
    original_config = os.environ.get("CRS_CONFIG")
    os.environ["CRS_CONFIG"] = str(paths.config_path)

    try:
        # Create event emitter
        if run_id is None:
            import time
            run_id = f"step_{int(time.time())}"

        emitter = CRSEventEmitter(run_id=run_id, repository_id=repository.id)

        # Set up broadcaster callback
        broadcaster = get_broadcaster()

        def broadcast_callback(event):
            broadcaster.broadcast(repository.id, event)

        emitter.register_callback(broadcast_callback)

        # Create step runner
        fs = WorkspaceFS(config_path=str(paths.config_path))
        runner = CRSStepRunner(fs, emitter)

        # Run the requested step
        if step_name == "blueprints":
            result = runner.run_blueprints(force=force)
        elif step_name == "artifacts":
            result = runner.run_artifacts(force=force)
        elif step_name == "relationships":
            result = runner.run_relationships(force=force)
        elif step_name == "impact":
            result = runner.run_impact()
        elif step_name.startswith("verification_"):
            suite_id = step_name.replace("verification_", "")
            result = runner.run_verification(suite_id)
        else:
            raise ValueError(f"Unknown step: {step_name}")

        # Update repository stats if not skipped
        if not result.get("skipped"):
            repository.last_crs_run = timezone.now()
            repository.save(update_fields=["last_crs_run"])

        return {
            "run_id": run_id,
            "step": step_name,
            "result": result,
            "events_count": len(emitter.get_events())
        }

    finally:
        # Restore environment
        if original_config is None:
            os.environ.pop("CRS_CONFIG", None)
        else:
            os.environ["CRS_CONFIG"] = original_config


def get_crs_step_status(repository: Repository) -> Dict[str, Any]:
    """
    Get status of all CRS pipeline steps

    Returns step-by-step status showing what needs to run
    """
    if not repository.clone_path or not Path(repository.clone_path).is_dir():
        return {
            "error": "Repository not cloned",
            "steps": {}
        }

    paths = _build_crs_workspace(repository)
    original_config = os.environ.get("CRS_CONFIG")
    os.environ["CRS_CONFIG"] = str(paths.config_path)

    try:
        fs = WorkspaceFS(config_path=str(paths.config_path))
        runner = CRSStepRunner(fs, emitter=None)
        status = runner.get_step_status()
        return status

    finally:
        if original_config is None:
            os.environ.pop("CRS_CONFIG", None)
        else:
            os.environ["CRS_CONFIG"] = original_config
