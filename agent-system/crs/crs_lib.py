# crs_lib.py
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional


def read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p: Path, data: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def normalize_path(p: str) -> str:
    return p.replace("\\", "/")


def iter_blueprint_entries(bp: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    if isinstance(bp.get("blueprints"), list):
        return bp.get("root") or "", bp["blueprints"]
    if isinstance(bp.get("files"), list):
        return bp.get("repo_root") or bp.get("root") or "", bp["files"]
    return "", []


def get_entry_raw_text(entry: Dict[str, Any], root: str) -> str:
    if entry.get("raw_text") is not None:
        return entry.get("raw_text") or ""
    abs_path = entry.get("abs_path")
    fp = entry.get("file_path") or entry.get("path")
    if not abs_path and root and fp:
        abs_path = str(Path(root) / fp)
    if abs_path and Path(abs_path).exists():
        return Path(abs_path).read_text(encoding="utf-8", errors="replace")
    return ""


def set_entry_raw_text(entry: Dict[str, Any], txt: str) -> None:
    entry["raw_text"] = txt
    entry["parse_ok"] = entry.get("parse_ok", True)
    entry["parse_error"] = None


def safe_relpath(file_path: str, root: str) -> str:
    fp = normalize_path(file_path)
    if root:
        try:
            return normalize_path(str(Path(fp).relative_to(Path(root))))
        except Exception:
            return fp.split("/")[-1]
    return fp.split("/")[-1]


def list_py_files(src_dir: Path) -> List[Path]:
    return [p for p in src_dir.rglob("*.py") if p.is_file()]


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def write_text(p: Path, txt: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8", errors="replace")
