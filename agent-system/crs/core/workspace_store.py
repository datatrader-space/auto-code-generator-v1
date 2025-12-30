import os
import json
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _sha1_bytes(b: bytes) -> str:
    h = hashlib.sha1()
    h.update(b)
    return h.hexdigest()


def _sha1_text(s: str) -> str:
    return _sha1_bytes(s.encode("utf-8", errors="replace"))


@dataclass
class WorkspacePaths:
    src_dir: str
    state_dir: str
    blueprints_out: str
    artifacts_out: str
    relationships_out: str
    meta_state_out: str


class WorkspaceStore:
    """
    Central IO layer for CRS.
    - All paths resolved here
    - All file read/write goes through here
    - Later you can swap implementation to DataHouse/StorageHouse
    """

    def __init__(self, workspace_root: str, config: Dict[str, Any]):
        self.workspace_root = os.path.abspath(workspace_root)
        self.config = config or {}

        paths_cfg = (self.config.get("paths") or {})
        state_dir_rel = paths_cfg.get("state_dir", "state")
        src_dir_rel = paths_cfg.get("src_dir", "src")

        self.paths = WorkspacePaths(
            src_dir=os.path.join(self.workspace_root, src_dir_rel),
            state_dir=os.path.join(self.workspace_root, state_dir_rel),
            blueprints_out=os.path.join(self.workspace_root, paths_cfg.get("blueprints_out", f"{state_dir_rel}/blueprints.json")),
            artifacts_out=os.path.join(self.workspace_root, paths_cfg.get("artifacts_out", f"{state_dir_rel}/artifacts.json")),
            relationships_out=os.path.join(self.workspace_root, paths_cfg.get("relationships_out", f"{state_dir_rel}/relationships.json")),
            meta_state_out=os.path.join(self.workspace_root, paths_cfg.get("meta_state_out", f"{state_dir_rel}/meta_state.json")),
        )

        os.makedirs(self.paths.src_dir, exist_ok=True)
        os.makedirs(self.paths.state_dir, exist_ok=True)

    # -------------------------
    # Basic IO
    # -------------------------
    def read_json(self, abs_path: str) -> Any:
        if not os.path.exists(abs_path):
            return None
        with open(abs_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_json(self, abs_path: str, payload: Any) -> None:
        os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def read_text(self, abs_path: str) -> str:
        if not os.path.exists(abs_path):
            return ""
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def write_text(self, abs_path: str, text: str) -> None:
        os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
        with open(abs_path, "w", encoding="utf-8", errors="replace") as f:
            f.write(text)

    # -------------------------
    # Typed state files
    # -------------------------
    def load_blueprints(self) -> Optional[Dict[str, Any]]:
        obj = self.read_json(self.paths.blueprints_out)
        return obj if isinstance(obj, dict) else None

    def load_artifacts(self) -> Optional[Dict[str, Any]]:
        obj = self.read_json(self.paths.artifacts_out)
        return obj if isinstance(obj, dict) else None

    def load_relationships(self) -> Optional[Dict[str, Any]]:
        obj = self.read_json(self.paths.relationships_out)
        return obj if isinstance(obj, dict) else None

    def load_meta_state(self) -> Dict[str, Any]:
        obj = self.read_json(self.paths.meta_state_out)
        return obj if isinstance(obj, dict) else {}

    def save_meta_state(self, meta: Dict[str, Any]) -> None:
        self.write_json(self.paths.meta_state_out, meta)

    # -------------------------
    # Fingerprinting (decide regen)
    # -------------------------
    def compute_src_fingerprint(self) -> Dict[str, Any]:
        """
        Computes a stable fingerprint for workspace/src.
        This is how main decides whether to regen blueprints/artifacts/relationships.
        """
        file_hashes: Dict[str, str] = {}
        total_files = 0

        for dirpath, _, filenames in os.walk(self.paths.src_dir):
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                total_files += 1
                abs_fp = os.path.join(dirpath, fn)
                rel_fp = _norm(os.path.relpath(abs_fp, self.paths.src_dir))

                with open(abs_fp, "rb") as f:
                    b = f.read()
                file_hashes[rel_fp] = _sha1_bytes(b)

        # fingerprint of fingerprints
        joined = "\n".join(f"{k}:{file_hashes[k]}" for k in sorted(file_hashes.keys()))
        return {
            "src_root": _norm(self.paths.src_dir),
            "file_count": total_files,
            "file_hashes": file_hashes,
            "src_fingerprint": _sha1_text(joined),
        }


def discover_workspace_root() -> str:
    """
    Workspace discovery:
    - CRS_WORKSPACE env var wins
    - else current working directory
    """
    env = os.environ.get("CRS_WORKSPACE")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.abspath(os.getcwd())


def load_workspace_config(workspace_root: str) -> Dict[str, Any]:
    cfg_path = os.path.join(workspace_root, "config.json")
    if not os.path.exists(cfg_path):
        return {"version": "crs-workspace-config-v1", "paths": {"src_dir": "src", "state_dir": "state"}, "components": {}}
    with open(cfg_path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    return obj if isinstance(obj, dict) else {}
