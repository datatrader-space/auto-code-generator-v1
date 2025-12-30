# core/pipeline_state.py
import json
import os
import time
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional, List

from core.fs import WorkspaceFS


def _utc_iso() -> str:
    # simple ISO-ish without timezone dependency
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _sha1_text(s: str) -> str:
    h = hashlib.sha1()
    h.update(s.encode("utf-8", errors="replace"))
    return h.hexdigest()


def _sha1_json(obj: Any) -> str:
    # stable-ish JSON hash for payloads
    try:
        raw = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8", errors="replace")
    except Exception:
        raw = repr(obj).encode("utf-8", errors="replace")
    h = hashlib.sha1()
    h.update(raw)
    return h.hexdigest()


@dataclass
class StepDecision:
    run_blueprints: bool
    run_artifacts: bool
    run_relationships: bool
    reason: Dict[str, Any]


class PipelineState:
    """
    Orchestrator state:
    - Computes src fingerprint (based on workspace/src *.py contents)
    - Stores meta state in state/meta_state.json
    - Decides which steps must run based on changes / missing outputs / dirty flags

    Patch v1 additions:
    - state/patches/*.json queue (pending/applied/failed)
    - apply_pending_patches() applies patches BEFORE decide()/pipeline run
    - writes state/impact.json (v1: changed_files only)
    """

    META_VERSION = "crs-meta-state-v1"
    IMPACT_VERSION = "crs-impact-v1"

    def __init__(self, fs: WorkspaceFS):
        self.fs = fs
        self.cfg = fs.get_cfg() or {}

        # meta_state path configurable, but default under state/
        p = (self.cfg.get("paths") or {})
        meta_rel = p.get("meta_state_out") or os.path.join(os.path.basename(self.fs.paths.state_dir), "meta_state.json")

        # resolve meta_state to workspace root
        if os.path.isabs(meta_rel):
            self.meta_path = meta_rel
        else:
            self.meta_path = os.path.abspath(os.path.join(self.fs.paths.workspace_root, meta_rel))

        # Patch queue folder + impact file (always under state/)
        self.patches_dir = os.path.join(self.fs.paths.state_dir, "patches")
        self.impact_path = os.path.join(self.fs.paths.state_dir, "impact.json")

        # Ensure patch dir exists (centralized enough; backend will later swap)
        try:
            self.fs.backend.makedirs(self.patches_dir)
        except Exception:
            # last-resort local mkdir
            os.makedirs(self.patches_dir, exist_ok=True)

    # -------------------------
    # Meta read/write
    # -------------------------
    def load_meta(self) -> Dict[str, Any]:
        obj = self.fs.read_json(self.meta_path) if self.fs.backend.exists(self.meta_path) else None
        if isinstance(obj, dict):
            return obj
        return {"version": self.META_VERSION}

    def save_meta(self, meta: Dict[str, Any]) -> None:
        meta = meta or {}
        meta["version"] = self.META_VERSION
        self.fs.write_json(self.meta_path, meta)

    # -------------------------
    # Fingerprinting
    # -------------------------
    def compute_src_fingerprint(self) -> Dict[str, Any]:
        """
        Stable fingerprint for workspace/src.
        NOTE: uses text hashing via WorkspaceFS.read_text (cloud backend friendly).
        """
        src_root = self.fs.paths.src_dir
        file_hashes: Dict[str, str] = {}
        total_files = 0

        for dirpath, _, filenames in os.walk(src_root):
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                total_files += 1
                abs_fp = os.path.join(dirpath, fn)
                rel_fp = _norm(os.path.relpath(abs_fp, src_root))

                try:
                    txt = self.fs.read_text(abs_fp)
                except Exception:
                    txt = ""
                file_hashes[rel_fp] = _sha1_text(txt)

        joined = "\n".join(f"{k}:{file_hashes[k]}" for k in sorted(file_hashes.keys()))
        return {
            "src_root": _norm(src_root),
            "file_count": total_files,
            "file_hashes": file_hashes,
            "src_fingerprint": _sha1_text(joined),
        }

    # -------------------------
    # Dirty / patch markers
    # -------------------------
    def mark_patch_applied(self, patch_id: Optional[str] = None, note: Optional[str] = None) -> Dict[str, Any]:
        meta = self.load_meta()
        patch = meta.get("patch") if isinstance(meta.get("patch"), dict) else {}
        patch["dirty"] = True
        patch["last_patch_at"] = _utc_iso()
        if patch_id:
            patch["patch_id"] = patch_id
        if note:
            patch["note"] = note
        meta["patch"] = patch
        self.save_meta(meta)
        return meta

    def clear_patch_dirty(self) -> Dict[str, Any]:
        meta = self.load_meta()
        patch = meta.get("patch") if isinstance(meta.get("patch"), dict) else {}
        patch["dirty"] = False
        patch["cleared_at"] = _utc_iso()
        meta["patch"] = patch
        self.save_meta(meta)
        return meta

    # -------------------------
    # Patch queue (v1)
    # -------------------------
    def list_pending_patches(self) -> List[Dict[str, Any]]:
        """
        Reads state/patches/*.json and returns those with status == "pending".
        Adds an internal key: _abs_path for persistence.
        """
        if not os.path.isdir(self.patches_dir):
            return []

        out: List[Dict[str, Any]] = []
        for fn in sorted(os.listdir(self.patches_dir)):
            if not fn.endswith(".json"):
                continue
            abs_path = os.path.join(self.patches_dir, fn)
            obj = self.fs.read_json(abs_path)
            if isinstance(obj, dict) and obj.get("status") == "pending":
                obj["_abs_path"] = abs_path
                out.append(obj)
        return out

    def _apply_replace_range(self, file_abs: str, start_line: int, end_line: int, new_text: str) -> None:
        """
        Replace inclusive 1-indexed line range [start_line, end_line] in file_abs with new_text.
        """
        raw = self.fs.read_text(file_abs)
        lines = raw.splitlines(keepends=True)

        s = max(1, int(start_line))
        e = max(s, int(end_line))

        # allow s == len(lines)+1 (append), but disallow beyond that
        if s > len(lines) + 1:
            raise ValueError(f"start_line out of range: {s} for {file_abs} (line_count={len(lines)})")

        before = lines[: s - 1]
        after = lines[e:] if e <= len(lines) else []
        replacement = (new_text or "").splitlines(keepends=True)

        out = "".join(before + replacement + after)
        self.fs.write_text(file_abs, out)

    def apply_pending_patches(self) -> Dict[str, Any]:
        """
        Applies all pending patches under state/patches.
        Patch v1 supports:
          - op: "replace_range"
            target: { "file": "rel/path.py", "anchor": {"start_line": N, "end_line": M}, "text": "..." }

        Writes:
          - updates patch files: status -> applied/failed
          - marks meta.patch.dirty = True when any patch applied
          - writes state/impact.json (v1: changed_files + patch_results)
        """
        pending = self.list_pending_patches()
        if not pending:
            return {"applied": 0, "failed": 0, "changed_files": []}

        changed_files: set = set()
        results: List[Dict[str, Any]] = []

        for patch in pending:
            patch_id = patch.get("patch_id") or os.path.basename(str(patch.get("_abs_path", "patch.json")))
            abs_path = patch.get("_abs_path")

            try:
                targets = patch.get("targets") or []
                if not isinstance(targets, list) or not targets:
                    raise ValueError("patch.targets missing/invalid (expected non-empty list)")

                for t in targets:
                    if not isinstance(t, dict):
                        raise ValueError("patch.targets contains non-object entry")

                    rel_file = str(t.get("file") or "").strip()
                    if not rel_file:
                        raise ValueError("target.file missing")

                    op = str(t.get("op") or "").strip()
                    anchor = t.get("anchor") or {}
                    if not isinstance(anchor, dict):
                        anchor = {}

                    file_abs = os.path.join(self.fs.paths.src_dir, rel_file)

                    if op == "replace_range":
                        self._apply_replace_range(
                            file_abs=file_abs,
                            start_line=int(anchor.get("start_line", 1)),
                            end_line=int(anchor.get("end_line", 1)),
                            new_text=str(t.get("text") or ""),
                        )
                    else:
                        raise ValueError(f"unsupported op: {op}")

                    changed_files.add(_norm(rel_file))

                patch["status"] = "applied"
                patch["applied_at"] = _utc_iso()
                results.append({"patch_id": patch_id, "status": "applied"})
            except Exception as e:
                patch["status"] = "failed"
                patch["failed_at"] = _utc_iso()
                patch["error"] = str(e)
                results.append({"patch_id": patch_id, "status": "failed", "error": str(e)})

            # Persist patch file updates
            if abs_path:
                patch.pop("_abs_path", None)
                self.fs.write_json(abs_path, patch)

        applied_count = len([r for r in results if r.get("status") == "applied"])
        failed_count = len([r for r in results if r.get("status") == "failed"])

        if applied_count > 0:
            self.mark_patch_applied(note=f"Applied {applied_count} patch(es)")

        # Impact v1: files-only + recommended steps (safe: rerun all downstream)
        impact = {
            "version": self.IMPACT_VERSION,
            "generated_at": _utc_iso(),
            "patch_results": results,
            "changed_files": sorted(list(changed_files)),
            "recommended": {
                "run_blueprints": True,
                "run_artifacts": True,
                "run_relationships": True,
            },
        }
        self.fs.write_json(self.impact_path, impact)

        return {"applied": applied_count, "failed": failed_count, "changed_files": sorted(list(changed_files))}

    # -------------------------
    # Step completion markers
    # -------------------------
    def mark_step_done(self, step: str, src_fingerprint: str, output_sha1: Optional[str] = None) -> Dict[str, Any]:
        meta = self.load_meta()
        steps = meta.get("steps") if isinstance(meta.get("steps"), dict) else {}
        steps[step] = {
            "done_at": _utc_iso(),
            "src_fingerprint": src_fingerprint,
            "output_sha1": output_sha1,
        }
        meta["steps"] = steps
        # keep a copy of last computed src_fingerprint for easier debugging
        meta["last_src_fingerprint"] = src_fingerprint
        self.save_meta(meta)
        return meta

    # -------------------------
    # Decisions
    # -------------------------
    def decide(self) -> StepDecision:
        meta = self.load_meta()
        src_info = self.compute_src_fingerprint()
        cur_fp = src_info["src_fingerprint"]

        steps = meta.get("steps") if isinstance(meta.get("steps"), dict) else {}
        patch = meta.get("patch") if isinstance(meta.get("patch"), dict) else {}
        patch_dirty = bool(patch.get("dirty", False))

        # existence checks
        bp_exists = self.fs.backend.exists(self.fs.paths.blueprints_json)
        art_exists = self.fs.backend.exists(self.fs.paths.artifacts_json)
        rel_exists = self.fs.backend.exists(self.fs.paths.relationships_json)

        bp_step = steps.get("blueprints") if isinstance(steps.get("blueprints"), dict) else {}
        art_step = steps.get("artifacts") if isinstance(steps.get("artifacts"), dict) else {}
        rel_step = steps.get("relationships") if isinstance(steps.get("relationships"), dict) else {}

        bp_fp_ok = (bp_step.get("src_fingerprint") == cur_fp) and bp_exists
        art_fp_ok = (art_step.get("src_fingerprint") == cur_fp) and art_exists
        rel_fp_ok = (rel_step.get("src_fingerprint") == cur_fp) and rel_exists

        # If src changed OR patch dirty OR output missing -> rerun that step and downstream
        run_blueprints = (not bp_fp_ok) or patch_dirty or (not bp_exists)
        run_artifacts = (not art_fp_ok) or patch_dirty or (not art_exists) or run_blueprints
        run_relationships = (not rel_fp_ok) or patch_dirty or (not rel_exists) or run_artifacts

        reason = {
            "src_fingerprint": cur_fp,
            "patch_dirty": patch_dirty,
            "exists": {"blueprints": bp_exists, "artifacts": art_exists, "relationships": rel_exists},
            "fp_ok": {"blueprints": bp_fp_ok, "artifacts": art_fp_ok, "relationships": rel_fp_ok},
            "will_run": {"blueprints": run_blueprints, "artifacts": run_artifacts, "relationships": run_relationships},
        }
        return StepDecision(run_blueprints, run_artifacts, run_relationships, reason)

    # -------------------------
    # Convenience: hash outputs
    # -------------------------
    def hash_output_file(self, abs_path: str) -> Optional[str]:
        if not self.fs.backend.exists(abs_path):
            return None
        try:
            obj = self.fs.read_json(abs_path)
            return _sha1_json(obj)
        except Exception:
            try:
                txt = self.fs.read_text(abs_path)
                return _sha1_text(txt)
            except Exception:
                return None
