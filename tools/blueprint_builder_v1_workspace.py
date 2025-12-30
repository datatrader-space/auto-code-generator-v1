# tools/blueprint_builder_v1_workspace.py

import ast
import re
import os
import hashlib
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

from core.fs import WorkspaceFS


SEG_IMPORT = "import"
SEG_CLASS = "class_def"
SEG_FUNC = "func_def"
SEG_MODULE_BLOCK = "module_block"
SEG_UNRESOLVED = "unresolved"


# -----------------------------
# Small pure helpers (kept)
# -----------------------------
def _sha1_text(txt: str) -> str:
    h = hashlib.sha1()
    h.update(txt.encode("utf-8", errors="replace"))
    return h.hexdigest()


def _norm_path(p: str) -> str:
    return p.replace("\\", "/")


# -----------------------------
# Data structures (kept same + safe additions)
# -----------------------------
@dataclass
class Anchor:
    file_path: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def to_id(self) -> str:
        return f"{self.file_path}:{self.start_line}:{self.start_col}-{self.end_line}:{self.end_col}"


@dataclass
class Segment:
    segment_id: str
    kind: str
    name: Optional[str]
    anchor: Anchor
    confidence: str  # "certain" | "probable" | "heuristic"
    notes: Optional[str] = None


@dataclass
class BlueprintFile:
    file_path: str
    parse_ok: bool
    parse_error: Optional[str]
    raw_text: str
    segments: List[Segment]

    # Non-breaking additions
    sha1: Optional[str] = None
    line_count: Optional[int] = None
    lines: Optional[List[Dict[str, Any]]] = None  # [{i:1,t:"..."}]


def _safe_end_lineno(node: ast.AST) -> int:
    return getattr(node, "end_lineno", getattr(node, "lineno", 1))


def _safe_end_col(node: ast.AST) -> int:
    return getattr(node, "end_col_offset", getattr(node, "col_offset", 0))


def _mk_anchor(file_path: str, node: ast.AST) -> Anchor:
    return Anchor(
        file_path=file_path,
        start_line=getattr(node, "lineno", 1),
        start_col=getattr(node, "col_offset", 0),
        end_line=_safe_end_lineno(node),
        end_col=_safe_end_col(node),
    )


def _segment(kind: str, file_path: str, node: ast.AST, name: Optional[str], confidence: str, notes: str = None) -> Segment:
    anchor = _mk_anchor(file_path, node)
    seg_id = f"{kind}:{name or 'anon'}:{anchor.to_id()}"
    return Segment(segment_id=seg_id, kind=kind, name=name, anchor=anchor, confidence=confidence, notes=notes)


def _extract_segments_ast(file_path: str, text: str) -> Tuple[List[Segment], List[str]]:
    """
    Extract top-level segments using AST.
    Also detects module-level executable blocks (loose code).
    """
    warnings: List[str] = []
    tree = ast.parse(text)
    segments: List[Segment] = []

    for n in getattr(tree, "body", []):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            segments.append(_segment(SEG_IMPORT, file_path, n, name=None, confidence="certain"))
        elif isinstance(n, ast.ClassDef):
            segments.append(_segment(SEG_CLASS, file_path, n, name=n.name, confidence="certain"))
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            segments.append(_segment(SEG_FUNC, file_path, n, name=n.name, confidence="certain"))
        else:
            kind = type(n).__name__
            segments.append(
                _segment(
                    SEG_MODULE_BLOCK,
                    file_path,
                    n,
                    name=kind,
                    confidence="probable",
                    notes=f"Top-level executable statement: {kind}",
                )
            )

    return segments, warnings


_FALLBACK_IMPORT_RE = re.compile(r"^\s*(from\s+\S+\s+import\s+.+|import\s+.+)\s*$")
_FALLBACK_DEF_RE = re.compile(r"^\s*(class|def|async\s+def)\s+([A-Za-z_][A-Za-z0-9_]*)")


def _extract_segments_fallback(file_path: str, text: str, err: str) -> List[Segment]:
    """
    Best-effort fallback when AST parse fails.
    We still identify imports/classes/defs via regex and mark the rest unresolved.
    """
    segments: List[Segment] = []
    lines = text.splitlines()

    for i, line in enumerate(lines, start=1):
        if _FALLBACK_IMPORT_RE.match(line):
            fake_node = type("N", (), {"lineno": i, "col_offset": 0, "end_lineno": i, "end_col_offset": len(line)})()
            segments.append(_segment(SEG_IMPORT, file_path, fake_node, name=None, confidence="heuristic", notes="Fallback regex import"))

        m = _FALLBACK_DEF_RE.match(line)
        if m:
            kind, name = m.group(1), m.group(2)
            seg_kind = SEG_CLASS if kind == "class" else SEG_FUNC
            fake_node = type("N", (), {"lineno": i, "col_offset": 0, "end_lineno": i, "end_col_offset": len(line)})()
            segments.append(_segment(seg_kind, file_path, fake_node, name=name, confidence="heuristic", notes="Fallback regex def/class"))

    fake_node = type("N", (), {"lineno": 1, "col_offset": 0, "end_lineno": max(1, len(lines)), "end_col_offset": 0})()
    segments.append(
        _segment(
            SEG_UNRESOLVED,
            file_path,
            fake_node,
            name=None,
            confidence="certain",
            notes=f"AST parse failed: {err}",
        )
    )
    return segments


def _iter_py_files(root: str) -> List[str]:
    out: List[str] = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".py"):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def blueprint_file_from_text(
    text: str,
    file_path_for_ids: str,
    store_lines: bool = True,
    store_raw_text: bool = True,
) -> BlueprintFile:
    """
    Pure (no IO):
    - file_path_for_ids: relative id used inside anchors/segment IDs (stable across machines)
    """
    sha1 = _sha1_text(text)
    line_list = text.splitlines(keepends=True)
    line_count = len(line_list)

    try:
        segments, _warnings = _extract_segments_ast(file_path_for_ids, text)
        return BlueprintFile(
            file_path=file_path_for_ids,
            parse_ok=True,
            parse_error=None,
            raw_text=text if store_raw_text else "",
            segments=segments,
            sha1=sha1,
            line_count=line_count,
            lines=[{"i": i + 1, "t": line} for i, line in enumerate(line_list)] if store_lines else None,
        )
    except SyntaxError as e:
        segs = _extract_segments_fallback(file_path_for_ids, text, err=str(e))
        return BlueprintFile(
            file_path=file_path_for_ids,
            parse_ok=False,
            parse_error=str(e),
            raw_text=text if store_raw_text else "",
            segments=segs,
            sha1=sha1,
            line_count=line_count,
            lines=[{"i": i + 1, "t": line} for i, line in enumerate(line_list)] if store_lines else None,
        )


def index_workspace_blueprints(fs: Optional[WorkspaceFS] = None) -> Dict[str, Any]:
    """
    Workspace runner (no args):
    - Uses core/fs.py as the single source of truth for:
      config, paths, reads, writes, directory creation.
    """
    fs = fs or WorkspaceFS()
    cfg = fs.get_cfg()

    src_dir = fs.paths.src_dir

    store_lines = bool(cfg.get("blueprints", {}).get("store_lines", True))
    store_raw_text = bool(cfg.get("blueprints", {}).get("store_raw_text", True))

    files = _iter_py_files(src_dir)
    if not files:
        raise RuntimeError(f"No .py files found in workspace src_dir: {src_dir}")

    blueprints: List[BlueprintFile] = []
    src_abs = os.path.abspath(src_dir)

    for fp in files:
        fp_abs = os.path.abspath(fp)
        rel = _norm_path(os.path.relpath(fp_abs, src_abs))
        text = fs.read_text(fp_abs)
        blueprints.append(
            blueprint_file_from_text(
                text=text,
                file_path_for_ids=rel,
                store_lines=store_lines,
                store_raw_text=store_raw_text,
            )
        )

    payload = {
        "version": "crs-blueprints-v1",
        "workspace_root": fs.paths.workspace_root,
        "src_root": src_abs,
        "file_count": len(blueprints),
        "blueprints": [asdict(b) for b in blueprints],
        "notes": [
            "file_path values are relative to workspace/src for stable anchors and patching.",
            "segments logic unchanged from v1 (imports/classes/funcs/module_block + fallback unresolved).",
            "All file IO is routed through core.fs.WorkspaceFS.",
        ],
    }

    fs.save_blueprints(payload)
    return payload


# -----------------------------
# Optional: legacy CLI (kept minimal)
# -----------------------------
def index_blueprints(root: str, out_json: str, fs: Optional[WorkspaceFS] = None) -> Dict[str, Any]:
    """
    Legacy entrypoint (kept for compatibility):
    Reads from disk via WorkspaceFS to keep IO centralized.
    """
    fs = fs or WorkspaceFS()

    files = _iter_py_files(root)
    blueprints: List[BlueprintFile] = []

    root_abs = os.path.abspath(root)
    for fp in files:
        fp_abs = os.path.abspath(fp)
        rel = _norm_path(os.path.relpath(fp_abs, root_abs))
        text = fs.read_text(fp_abs)
        blueprints.append(
            blueprint_file_from_text(
                text=text,
                file_path_for_ids=rel,
                store_lines=False,
                store_raw_text=True,
            )
        )

    payload = {
        "root": root_abs,
        "file_count": len(blueprints),
        "blueprints": [asdict(b) for b in blueprints],
    }

    fs.write_json(out_json, payload)
    return payload


if __name__ == "__main__":
    import sys
    import argparse

    fs = WorkspaceFS()

    # No-args = workspace run
    if len(sys.argv) == 1:
        payload = index_workspace_blueprints(fs=fs)
        print(f"✅ Wrote blueprints -> {fs.paths.blueprints_json}")
        print(f"Files: {payload.get('file_count')}")
        raise SystemExit(0)

    ap = argparse.ArgumentParser(description="CRS Blueprint Builder v1 (workspace-first)")
    ap.add_argument("root", help="Folder to index")
    ap.add_argument("--out", default="crs_blueprints.json", help="Output JSON path")
    args = ap.parse_args()

    index_blueprints(args.root, args.out, fs=fs)
    print(f"✅ Wrote {args.out}")
