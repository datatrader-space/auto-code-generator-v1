import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Optional

from datetime import datetime
class CRSFileIOError(Exception):
    pass


def _abspath(p: str) -> str:
    return os.path.abspath(p)


def _norm_join(root: str, p: str) -> str:
    # if p is absolute, keep it, else join to root
    if os.path.isabs(p):
        return p
    return os.path.join(root, p)


@dataclass
class WorkspacePaths:
    workspace_root: str
    src_dir: str
    state_dir: str
    inputs_dir: str
    tools_dir: str
    runs_dir: str
    # canonical outputs
    blueprints_json: str
    artifacts_json: str
    relationships_json: str


class StorageBackend:
    """
    Interface: later you can implement DataHouse/StorageHouse backends.
    """

    def read_text(self, path: str) -> str:
        raise NotImplementedError

    def write_text(self, path: str, data: str) -> None:
        raise NotImplementedError

    def exists(self, path: str) -> bool:
        raise NotImplementedError

    def makedirs(self, path: str) -> None:
        raise NotImplementedError


class LocalDiskBackend(StorageBackend):
    def read_text(self, path: str) -> str:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def write_text(self, path: str, data: str) -> None:
        # ensure parent exists
        parent = os.path.dirname(path) or "."
        os.makedirs(parent, exist_ok=True)

        # atomic write: write temp file then replace
        fd, tmp_path = tempfile.mkstemp(prefix=".crs_tmp_", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp_path, path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def makedirs(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)


class WorkspaceFS:
    """
    Central filing system.
    - Reads config.json (once)
    - Resolves all paths relative to workspace root
    - Provides JSON/text read/write helpers
    - Owns folder creation (no script should mkdir)
    """

    def __init__(self, config_path: Optional[str] = None, backend: Optional[StorageBackend] = None):
        self.config_path = config_path or os.environ.get("CRS_CONFIG", "config.json")
        self.backend: StorageBackend = backend or LocalDiskBackend()

        if not os.path.exists(self.config_path):
            raise CRSFileIOError(f"Workspace config not found: {self.config_path}")

        self.workspace_root = _abspath(os.path.dirname(self.config_path) or ".")
        self.cfg = self._load_json(self.config_path)

        self.paths = self._resolve_paths(self.cfg)

        # Create only core dirs up front (one place does it)
        
        self.backend.makedirs(self.paths.state_dir)
        self.backend.makedirs(self.paths.inputs_dir)
        self.backend.makedirs(self.paths.runs_dir)   # ✅ ADD

    # --------------------
    # config / path resolve
    # --------------------
    from datetime import datetime


    def new_run_id(self, prefix: str = "run") -> str:
        """
        Generates a filesystem-safe run id.
        Example: 20250101_153012__pipeline
        """
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"{ts}__{prefix}"

    def run_dir(self, run_id: str) -> str:
        return os.path.join(self.paths.runs_dir, run_id)

    def ensure_run_dir(self, run_id: str) -> str:
        d = self.run_dir(run_id)
        self.backend.makedirs(d)
        return d

    def run_path(self, run_id: str, filename: str) -> str:
        return os.path.join(self.ensure_run_dir(run_id), filename)

    def write_run_text(self, run_id: str, filename: str, text: str) -> None:
        self.write_text(self.run_path(run_id, filename), text)

    def write_run_json(self, run_id: str, filename: str, payload: Any) -> None:
        self.write_json(self.run_path(run_id, filename), payload)

    def _load_json(self, path: str) -> Any:
        raw = self.backend.read_text(path)
        return json.loads(raw)

    def _resolve_paths(self, cfg: Dict[str, Any]) -> WorkspacePaths:
        p = cfg.get("paths", {}) or {}

        src_dir = _abspath(_norm_join(self.workspace_root, p.get("src_dir", "src")))
        state_dir = _abspath(_norm_join(self.workspace_root, p.get("state_dir", "state")))
        inputs_dir = _abspath(_norm_join(self.workspace_root, p.get("inputs_dir", "inputs")))
        tools_dir = _abspath(_norm_join(self.workspace_root, p.get("tools_dir", "tools")))
        runs_dir = _abspath(_norm_join(state_dir, "runs"))

        # canonical outputs (single truth)
        blueprints_json = _abspath(_norm_join(self.workspace_root, p.get("blueprints_out", "state/blueprints.json")))
        artifacts_json = _abspath(_norm_join(self.workspace_root, p.get("artifacts_out", "state/artifacts.json")))
        relationships_json = _abspath(_norm_join(self.workspace_root, p.get("relationships_out", "state/relationships.json")))

        return WorkspacePaths(
                workspace_root=self.workspace_root,
                src_dir=src_dir,
                state_dir=state_dir,
                inputs_dir=inputs_dir,
                tools_dir=tools_dir,
                runs_dir=runs_dir,                     # ✅ HERE
                blueprints_json=blueprints_json,
                artifacts_json=artifacts_json,
                relationships_json=relationships_json,
            )

    # --------------------
    # public helpers
    # --------------------
    def get_cfg(self) -> Dict[str, Any]:
        return self.cfg

    def component_enabled(self, key: str, default: bool = True) -> bool:
        c = self.cfg.get("components", {}) or {}
        return bool(c.get(key, default))

    def read_json(self, path: str) -> Any:
        raw = self.backend.read_text(path)
        return json.loads(raw)

    def write_json(self, path: str, payload: Any) -> None:
        self.backend.write_text(path, json.dumps(payload, indent=2))

    def read_text(self, path: str) -> str:
        return self.backend.read_text(path)

    def write_text(self, path: str, data: str) -> None:
        self.backend.write_text(path, data)

    # canonical writes
    def save_blueprints(self, payload: Any) -> None:
        self.write_json(self.paths.blueprints_json, payload)

    def save_artifacts(self, payload: Any) -> None:
        self.write_json(self.paths.artifacts_json, payload)

    def save_relationships(self, payload: Any) -> None:
        self.write_json(self.paths.relationships_json, payload)
