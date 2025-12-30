# core/patch_engine.py
import json
import os
import time
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.fs import WorkspaceFS
from core.pipeline_state import PipelineState


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha1_text(s: str) -> str:
    h = hashlib.sha1()
    h.update(s.encode("utf-8", errors="replace"))
    return h.hexdigest()


def _safe_json_load(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_dir(fs: WorkspaceFS, abs_dir: str) -> None:
    fs.backend.makedirs(abs_dir)


def _resolve_target_path(fs: WorkspaceFS, rel_or_abs: str) -> str:
    """
    Resolve a patch file path.
    - If absolute => keep
    - Else => relative to workspace root
    """
    if not rel_or_abs or not isinstance(rel_or_abs, str):
        raise ValueError("Patch change path must be a non-empty string")
    if os.path.isabs(rel_or_abs):
        return os.path.abspath(rel_or_abs)
    return os.path.abspath(os.path.join(fs.paths.workspace_root, rel_or_abs))


def _read_existing(fs: WorkspaceFS, abs_path: str) -> str:
    if fs.backend.exists(abs_path):
        try:
            return fs.read_text(abs_path)
        except Exception:
            return ""
    return ""


def _apply_write_file(fs: WorkspaceFS, abs_path: str, content: str) -> Tuple[str, str]:
    before = _read_existing(fs, abs_path)
    fs.write_text(abs_path, content if isinstance(content, str) else str(content))
    after = _read_existing(fs, abs_path)
    return before, after


def _apply_replace_text(
    fs: WorkspaceFS,
    abs_path: str,
    find: str,
    replace: str,
    *,
    count: int = 0,
) -> Tuple[str, str, int]:
    """
    count=0 means replace all (python str.replace behavior).
    Returns (before, after, replacements_done)
    """
    before = _read_existing(fs, abs_path)
    if not before and not fs.backend.exists(abs_path):
        raise FileNotFoundError(f"replace_text target missing: {abs_path}")

    if not isinstance(find, str) or find == "":
        raise ValueError("replace_text requires non-empty 'find' string")

    if count is None:
        count = 0
    if not isinstance(count, int) or count < 0:
        raise ValueError("replace_text 'count' must be an int >= 0 (0 = replace all)")

    if count == 0:
        replacements_done = before.count(find)
        after = before.replace(find, replace)
    else:
        # do it deterministically
        replacements_done = 0
        out = before
        start = 0
        while replacements_done < count:
            idx = out.find(find, start)
            if idx == -1:
                break
            out = out[:idx] + replace + out[idx + len(find) :]
            replacements_done += 1
            start = idx + len(replace)
        after = out

    fs.write_text(abs_path, after)
    return before, after, replacements_done


def _apply_insert_after(
    fs: WorkspaceFS,
    abs_path: str,
    anchor: str,
    insert_text: str,
    *,
    once: bool = True,
) -> Tuple[str, str, int]:
    before = _read_existing(fs, abs_path)
    if not before and not fs.backend.exists(abs_path):
        raise FileNotFoundError(f"insert_after target missing: {abs_path}")

    if not isinstance(anchor, str) or anchor == "":
        raise ValueError("insert_after requires non-empty 'anchor' string")

    occurrences = before.count(anchor)
    if occurrences == 0:
        raise ValueError(f"insert_after anchor not found in {abs_path}")

    if once:
        idx = before.find(anchor)
        after = before[: idx + len(anchor)] + insert_text + before[idx + len(anchor) :]
        inserts_done = 1
    else:
        # insert after every occurrence (simple scan)
        parts = before.split(anchor)
        after = anchor.join([p + insert_text for p in parts[:-1]] + [parts[-1]])
        inserts_done = occurrences

    fs.write_text(abs_path, after)
    return before, after, inserts_done


def _apply_insert_before(
    fs: WorkspaceFS,
    abs_path: str,
    anchor: str,
    insert_text: str,
    *,
    once: bool = True,
) -> Tuple[str, str, int]:
    before = _read_existing(fs, abs_path)
    if not before and not fs.backend.exists(abs_path):
        raise FileNotFoundError(f"insert_before target missing: {abs_path}")

    if not isinstance(anchor, str) or anchor == "":
        raise ValueError("insert_before requires non-empty 'anchor' string")

    occurrences = before.count(anchor)
    if occurrences == 0:
        raise ValueError(f"insert_before anchor not found in {abs_path}")

    if once:
        idx = before.find(anchor)
        after = before[:idx] + insert_text + before[idx:]
        inserts_done = 1
    else:
        after = insert_text.join(before.split(anchor))
        after = after.replace(insert_text, insert_text + anchor)  # re-add anchor between splits
        # The above is slightly messy; safer:
        parts = before.split(anchor)
        after = (insert_text + anchor).join(parts)
        inserts_done = occurrences

    fs.write_text(abs_path, after)
    return before, after, inserts_done


def _normalize_patch_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    raise ValueError("Patch payload must be a JSON object (dict)")


def _make_patch_id(payload: Dict[str, Any]) -> str:
    pid = payload.get("patch_id")
    if isinstance(pid, str) and pid.strip():
        return pid.strip()
    # fallback: deterministic-ish based on content
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8", errors="replace")
    h = hashlib.sha1()
    h.update(raw)
    return f"patch_{h.hexdigest()[:12]}"


def _patches_dir(fs: WorkspaceFS) -> str:
    return os.path.abspath(os.path.join(fs.paths.state_dir, "patches"))


def apply_patch(
    fs: WorkspaceFS,
    state: PipelineState,
    patch_payload: Dict[str, Any],
    *,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Apply a patch (minimal v1):
      - supports ops:
          - write_file: {op:"write_file", path:"src/x.py", content:"..."}
          - replace_text: {op:"replace_text", path:"...", find:"...", replace:"...", count?:0}
          - insert_after: {op:"insert_after", path:"...", anchor:"...", insert:"...", once?:true}
          - insert_before: {op:"insert_before", path:"...", anchor:"...", insert:"...", once?:true}

    Side effects:
      - writes patch record to state/patches/<patch_id>.json
      - marks meta_state patch dirty via state.mark_patch_applied(patch_id, note)
      - optionally writes patch logs into run folder if run_id provided
    """
    payload = _normalize_patch_payload(patch_payload)
    patch_id = _make_patch_id(payload)
    note = payload.get("note") if isinstance(payload.get("note"), str) else None

    changes = payload.get("changes")
    if not isinstance(changes, list) or not changes:
        raise ValueError("Patch payload must contain non-empty 'changes' list")

    _ensure_dir(fs, _patches_dir(fs))

    applied: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for i, ch in enumerate(changes):
        if not isinstance(ch, dict):
            errors.append({"index": i, "error": "change must be an object"})
            continue

        op = ch.get("op") or ch.get("type")
        path = ch.get("path")
        try:
            if not isinstance(op, str) or not op.strip():
                raise ValueError("change.op must be a non-empty string")
            if not isinstance(path, str) or not path.strip():
                raise ValueError("change.path must be a non-empty string")

            abs_path = _resolve_target_path(fs, path.strip())
            op = op.strip()

            before = ""
            after = ""
            meta: Dict[str, Any] = {}

            if op == "write_file":
                content = ch.get("content", "")
                before, after = _apply_write_file(fs, abs_path, content)
                meta = {"bytes_written": len((after or "").encode("utf-8", errors="replace"))}

            elif op == "replace_text":
                find = ch.get("find", "")
                replace = ch.get("replace", "")
                count = ch.get("count", 0)
                before, after, n = _apply_replace_text(fs, abs_path, find, replace, count=int(count))
                meta = {"replacements": n}

                # guardrail: if 0 replacements, treat as error (usually a bad patch)
                if n == 0:
                    raise ValueError("replace_text made 0 replacements (find not present?)")

            elif op == "insert_after":
                anchor = ch.get("anchor", "")
                insert_text = ch.get("insert", "")
                once = bool(ch.get("once", True))
                before, after, n = _apply_insert_after(fs, abs_path, anchor, insert_text, once=once)
                meta = {"insertions": n, "once": once}

            elif op == "insert_before":
                anchor = ch.get("anchor", "")
                insert_text = ch.get("insert", "")
                once = bool(ch.get("once", True))
                before, after, n = _apply_insert_before(fs, abs_path, anchor, insert_text, once=once)
                meta = {"insertions": n, "once": once}

            else:
                raise ValueError(f"Unsupported op: {op}")

            applied.append(
                {
                    "index": i,
                    "op": op,
                    "path": path,
                    "abs_path": abs_path,
                    "before_sha1": _sha1_text(before),
                    "after_sha1": _sha1_text(after),
                    "meta": meta,
                }
            )

        except Exception as e:
            errors.append(
                {
                    "index": i,
                    "op": op,
                    "path": path,
                    "error": f"{type(e).__name__}: {e}",
                }
            )

    patch_record = {
        "version": "crs-patch-v1",
        "patch_id": patch_id,
        "note": note,
        "applied_at_utc": _utc_iso(),
        "summary": {
            "total_changes": len(changes),
            "applied": len(applied),
            "errors": len(errors),
        },
        "applied": applied,
        "errors": errors,
        "input": payload,
    }

    # Always write the patch record (even if errors)
    patch_out = os.path.join(_patches_dir(fs), f"{patch_id}.json")
    fs.write_json(patch_out, patch_record)

    # Mark patch dirty if at least one change applied
    if applied:
        state.mark_patch_applied(patch_id=patch_id, note=note)

    # Optional: run logs
    if run_id:
        try:
            fs.write_run_json(run_id, "patch_record.json", patch_record)
            fs.write_run_json(run_id, "patch_summary.json", patch_record.get("summary", {}))
            fs.write_run_text(
                run_id,
                "patch.log",
                json.dumps(
                    {
                        "patch_id": patch_id,
                        "note": note,
                        "applied": len(applied),
                        "errors": errors,
                        "patch_record_path": patch_out,
                    },
                    indent=2,
                ),
            )
        except Exception:
            # patch logging must not break the run
            pass

    # If there were errors and nothing applied, raise (fail-fast)
    if errors and not applied:
        raise RuntimeError(f"Patch failed (no changes applied). See {patch_out}")

    return patch_record


def apply_patch_from_file(
    fs: WorkspaceFS,
    state: PipelineState,
    patch_json_path: str,
    *,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Load a patch JSON from disk and apply it.
    patch_json_path can be absolute or relative to cwd.
    """
    abs_path = os.path.abspath(patch_json_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Patch file not found: {abs_path}")
    payload = _safe_json_load(abs_path)
    rec = apply_patch(fs, state, payload, run_id=run_id)
    rec["source_patch_file"] = abs_path
    return rec
