# crs_main.py
import os
import sys
import time
import json
import traceback
import importlib.util
import contextlib
import io
from typing import Any, Dict, Optional, Tuple

from core.impact_engine import ImpactEngine
from core.query_api import CRSQueryAPI
from core.fs import WorkspaceFS
from core.pipeline_state import PipelineState
from core.patch_engine import apply_patch_from_file  # ✅ PATCH INTEGRATION (minimal)
from core.spec_store import SpecStore
from core.verification_engine import VerificationEngine

def _load_module_from_path(name: str, abs_path: str):
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Tool not found: {abs_path}")
    spec = importlib.util.spec_from_file_location(name, abs_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load spec for {name} from {abs_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def _get_tool_path(fs: WorkspaceFS, filename: str) -> str:
    return os.path.abspath(os.path.join(fs.paths.tools_dir, filename))


def _ensure_python_path(fs: WorkspaceFS) -> None:
    root = fs.paths.workspace_root
    if root not in sys.path:
        sys.path.insert(0, root)


def _capture_call(fn, *args, **kwargs) -> Tuple[Any, str, str, float]:
    """
    Capture stdout/stderr for any call (tools print a lot).
    Returns: (result, stdout_text, stderr_text, duration_seconds)
    """
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    t0 = time.time()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        result = fn(*args, **kwargs)
    dt = time.time() - t0
    return result, out_buf.getvalue(), err_buf.getvalue(), dt


def _run_blueprint_builder(fs: WorkspaceFS) -> Dict[str, Any]:
    bp_path = _get_tool_path(fs, "blueprint_builder_v1_workspace.py")
    mod = _load_module_from_path("crs_blueprint_builder", bp_path)

    fn = getattr(mod, "index_workspace_blueprints", None)
    if not callable(fn):
        raise RuntimeError("Blueprint builder must expose index_workspace_blueprints()")

    payload = fn()
    return payload if isinstance(payload, dict) else {"payload": payload}


def _run_artifact_extractor(fs: WorkspaceFS) -> Dict[str, Any]:
    ax_path = _get_tool_path(fs, "artifact_extractor_v1_workspace.py")
    mod = _load_module_from_path("crs_artifact_extractor", ax_path)

    fn = getattr(mod, "extract_all", None)
    if not callable(fn):
        raise RuntimeError("Artifact extractor must expose extract_all(blueprints_path, out_path)")

    payload = fn(fs.paths.blueprints_json, fs.paths.artifacts_json)
    return payload if isinstance(payload, dict) else {"payload": payload}


def _run_relationship_builder(fs: WorkspaceFS, artifacts_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rb_path = _get_tool_path(fs, "relationship_builder_v1_workspace.py")
    mod = _load_module_from_path("crs_relationship_builder", rb_path)

    fn = getattr(mod, "build_relationships", None)
    if not callable(fn):
        raise RuntimeError("Relationship builder must expose build_relationships(artifacts_payload, ...)")

    if artifacts_payload is None:
        artifacts_payload = fs.read_json(fs.paths.artifacts_json)
        if not isinstance(artifacts_payload, dict):
            raise FileNotFoundError(f"Artifacts JSON not found/invalid: {fs.paths.artifacts_json}")

    cfg = fs.get_cfg() or {}
    components = (cfg.get("components") or {})
    include_heuristic = bool(components.get("relationship_include_heuristic_mentions", True))

    rel_payload = fn(artifacts_payload, include_heuristic_mentions=include_heuristic)
    if not isinstance(rel_payload, dict):
        rel_payload = {"payload": rel_payload}

    rel_payload["source_artifacts"] = fs.paths.artifacts_json
    fs.save_relationships(rel_payload)
    return rel_payload


def run_pipeline() -> None:
    fs = WorkspaceFS()
    _ensure_python_path(fs)

    run_id = fs.new_run_id(prefix="pipeline")
    fs.ensure_run_dir(run_id)

    # basic run header
    fs.write_run_json(
        run_id,
        "run.json",
        {
            "run_id": run_id,
            "workspace_root": fs.paths.workspace_root,
            "tools_dir": fs.paths.tools_dir,
            "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "running",
            "steps": {},
        },
    )
        # ------------------------------------
    # ✅ SPEC STORE INIT (non-fatal)
    # Creates state/specs/* if missing.
    # ------------------------------------
    try:
        spec_store = SpecStore(fs)
        spec_result = spec_store.ensure_defaults(overwrite=False)
        fs.write_run_json(run_id, "spec_store_init.json", spec_result)
        print(f"\n=== Step: SpecStore ===\n✅ SpecStore OK -> {spec_result.get('specs_dir')}")
    except Exception as e:
        # Do NOT fail pipeline for specs init
        fs.write_run_text(run_id, "spec_store_init_error.log", f"{type(e).__name__}: {e}")
        print(f"\n=== Step: SpecStore ===\n⚠️ SpecStore init failed (non-fatal): {type(e).__name__}: {e}")

    state = PipelineState(fs)

    # -------------------------------------------------
    # ✅ PATCH STEP (minimal integration)
    # If CRS_PATCH_IN is set, apply patch now.
    # This will mark patch dirty in meta_state.json.
    # Then decision will correctly rerun downstream steps.
    # -------------------------------------------------
    patch_in = os.environ.get("CRS_PATCH_IN")
    if patch_in:
        print("\n=== Step: Patch ===")
        patch_record = apply_patch_from_file(fs, state, patch_in, run_id=run_id)
        summ = patch_record.get("summary", {}) if isinstance(patch_record, dict) else {}
        print(
            f"✅ Patch applied -> id={patch_record.get('patch_id')} "
            f"applied={summ.get('applied')} errors={summ.get('errors')}"
        )

    decision = state.decide()

    # persist decision for debugging
    fs.write_run_json(
        run_id,
        "decision.json",
        {
            "reason": decision.reason,
            "run_blueprints": bool(decision.run_blueprints),
            "run_artifacts": bool(decision.run_artifacts),
            "run_relationships": bool(decision.run_relationships),
        },
    )

    print("\n=== CRS Pipeline Decision ===")
    print(decision.reason)

    src_info = state.compute_src_fingerprint()
    cur_fp = src_info["src_fingerprint"]
    fs.write_run_json(run_id, "src_fingerprint.json", src_info)

    steps_meta: Dict[str, Any] = {}

    def _record_step(step: str, ok: bool, dt: float, out: str, err: str, extra: Optional[Dict[str, Any]] = None) -> None:
        steps_meta[step] = {
            "ok": ok,
            "duration_seconds": dt,
            "stdout_len": len(out or ""),
            "stderr_len": len(err or ""),
            "extra": extra or {},
        }
        # update run.json each step (so if crash, you still have partial state)
        run_json_path = fs.run_path(run_id, "run.json")
        try:
            current = fs.read_json(run_json_path)
        except Exception:
            current = {}
        if not isinstance(current, dict):
            current = {}
        current["steps"] = steps_meta
        fs.write_json(run_json_path, current)

    try:
        # Step 1: Blueprints
        print("\n=== Step: Blueprints ===")
        if decision.run_blueprints:
            payload, out, err, dt = _capture_call(_run_blueprint_builder, fs)
            fs.write_run_text(run_id, "blueprints.log", out + ("\n\n[stderr]\n" + err if err else ""))
            fs.write_run_json(run_id, "blueprints_payload.json", payload)

            bp_sha = state.hash_output_file(fs.paths.blueprints_json)
            state.mark_step_done("blueprints", src_fingerprint=cur_fp, output_sha1=bp_sha)

            extra = {
                "file_count": payload.get("file_count") if isinstance(payload, dict) else None,
                "output": fs.paths.blueprints_json,
            }
            _record_step("blueprints", True, dt, out, err, extra)

            print(f"✅ Blueprints OK -> {fs.paths.blueprints_json}")
            if isinstance(payload, dict):
                print(f"   Files: {payload.get('file_count')}")
        else:
            print("⏭️  Skipped (up-to-date)")
            _record_step("blueprints", True, 0.0, "", "", {"skipped": True})

        # Step 2: Artifacts
        print("\n=== Step: Artifacts ===")
        if decision.run_artifacts:
            payload, out, err, dt = _capture_call(_run_artifact_extractor, fs)
            fs.write_run_text(run_id, "artifacts.log", out + ("\n\n[stderr]\n" + err if err else ""))
            fs.write_run_json(run_id, "artifacts_payload.json", payload)

            art_sha = state.hash_output_file(fs.paths.artifacts_json)
            state.mark_step_done("artifacts", src_fingerprint=cur_fp, output_sha1=art_sha)

            arts_count = None
            if isinstance(payload, dict) and isinstance(payload.get("artifacts"), list):
                arts_count = len(payload["artifacts"])
            extra = {"artifacts": arts_count, "output": fs.paths.artifacts_json}
            _record_step("artifacts", True, dt, out, err, extra)

            print(f"✅ Artifacts OK -> {fs.paths.artifacts_json}")
            if arts_count is not None:
                print(f"   Artifacts: {arts_count}")
        else:
            print("⏭️  Skipped (up-to-date)")
            _record_step("artifacts", True, 0.0, "", "", {"skipped": True})

        # Step 3: Relationships
        print("\n=== Step: Relationships ===")
        if decision.run_relationships:
            artifacts_payload = fs.read_json(fs.paths.artifacts_json)
            payload, out, err, dt = _capture_call(
                _run_relationship_builder,
                fs,
                artifacts_payload=artifacts_payload if isinstance(artifacts_payload, dict) else None,
            )
            fs.write_run_text(run_id, "relationships.log", out + ("\n\n[stderr]\n" + err if err else ""))
            fs.write_run_json(run_id, "relationships_payload.json", payload)

            rel_sha = state.hash_output_file(fs.paths.relationships_json)
            state.mark_step_done("relationships", src_fingerprint=cur_fp, output_sha1=rel_sha)

            rel_count = None
            if isinstance(payload, dict) and isinstance(payload.get("summary"), dict):
                rel_count = payload["summary"].get("relationships")
            extra = {"relationships": rel_count, "output": fs.paths.relationships_json}
            _record_step("relationships", True, dt, out, err, extra)

            print(f"✅ Relationships OK -> {fs.paths.relationships_json}")
            if isinstance(payload, dict):
                summary = payload.get("summary")
                if isinstance(summary, dict):
                    print(f"   Relationships: {summary.get('relationships')}  by_type={summary.get('by_type')}")
        else:
            print("⏭️  Skipped (up-to-date)")
            _record_step("relationships", True, 0.0, "", "", {"skipped": True})
        # In run_pipeline(), near the end (after relationships + impact + query index), append this block:
        # -----------------------------
        # NEW (non-fatal): Verification Suite
        # Runs if env CRS_VERIFY_SUITE is set (default: none)
        # -----------------------------
        suite_id = (os.environ.get("CRS_VERIFY_SUITE") or "").strip()
        if suite_id:
            try:
                print("\n=== Step: Verification ===")
                v = VerificationEngine(fs)
                v_payload = v.run_suite(suite_id, run_id=run_id)
                # record it in run.json steps summary
                _record_step("verification", bool(v_payload.get("ok")), 0.0, "", "", {"suite_id": suite_id, "summary": v_payload.get("summary")})
                print(f"✅ Verification done -> suite={suite_id} ok={v_payload.get('ok')}")
            except Exception as e:
                fs.write_run_text(run_id, "verification_error.log", f"{type(e).__name__}: {e}")
                _record_step("verification", False, 0.0, "", "", {"suite_id": suite_id, "error": f"{type(e).__name__}: {e}"})
                print(f"⚠️ Verification failed (non-fatal): {type(e).__name__}: {e}")

        # Clear patch dirty if needed (we need meta for impact step too)
        meta = state.load_meta()
        patch = meta.get("patch") if isinstance(meta.get("patch"), dict) else {}
        patch_dirty = bool(patch.get("dirty", False))
        patch_id = str(patch.get("patch_id") or "").strip()

        # -----------------------------
        # NEW STEP (minimal): Impact
        # Runs only when patch is dirty (or patch id exists)
        # -----------------------------
        if patch_dirty or patch_id:
            try:
                print("\n=== Step: Impact ===")
                impact_engine = ImpactEngine(fs)
                impact_payload = impact_engine.build_workspace_impact(run_id=run_id)
                fs.write_run_json(
                    run_id,
                    "impact_summary.json",
                    {"summary": impact_payload.get("summary"), "patch_id": impact_payload.get("patch_id")},
                )
                _record_step(
                    "impact",
                    True,
                    0.0,
                    "",
                    "",
                    {"patch_id": impact_payload.get("patch_id"), "summary": impact_payload.get("summary")},
                )
                print(f"✅ Impact written (patch_id={impact_payload.get('patch_id')})")
            except Exception as e:
                # Do NOT fail pipeline for impact; it’s diagnostic.
                fs.write_run_text(run_id, "impact_error.log", f"{type(e).__name__}: {e}")
                _record_step("impact", False, 0.0, "", "", {"error": f"{type(e).__name__}: {e}"})
                print(f"⚠️ Impact step failed (non-fatal): {type(e).__name__}: {e}")

        # Optional: warm-load the QueryAPI index and store a tiny snapshot (non-fatal)
        try:
            q = CRSQueryAPI(fs)
            idx = q.load(force=True)
            fs.write_run_json(
                run_id,
                "query_index_summary.json",
                {
                    "artifacts": len(idx.artifacts_by_id),
                    "relationship_edges": len(idx.rels),
                    "artifact_types": {k: len(v) for k, v in idx.artifacts_by_type.items()},
                },
            )
        except Exception as e:
            fs.write_run_text(run_id, "query_index_error.log", f"{type(e).__name__}: {e}")

        if bool(patch.get("dirty", False)):
            state.clear_patch_dirty()

        # finish run.json
        run_json_path = fs.run_path(run_id, "run.json")
        final_run = fs.read_json(run_json_path)
        if not isinstance(final_run, dict):
            final_run = {}
        final_run["status"] = "ok"
        final_run["ended_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        fs.write_json(run_json_path, final_run)

        print("\n✅ Pipeline OK")
        print(f"🧾 Run logs -> {fs.run_dir(run_id)}")

    except Exception as e:
        tb = traceback.format_exc()

        fs.write_run_text(run_id, "errors.log", tb)

        run_json_path = fs.run_path(run_id, "run.json")
        try:
            cur = fs.read_json(run_json_path)
        except Exception:
            cur = {}
        if not isinstance(cur, dict):
            cur = {}
        cur["status"] = "error"
        cur["error"] = {"type": type(e).__name__, "message": str(e)}
        cur["ended_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        cur["steps"] = steps_meta
        fs.write_json(run_json_path, cur)

        print("\n❌ Pipeline failed")
        print(f"Error: {type(e).__name__}: {e}")
        print(f"🧾 Run logs -> {fs.run_dir(run_id)}")
        raise


def main() -> None:
    run_pipeline()


if __name__ == "__main__":
    main()
