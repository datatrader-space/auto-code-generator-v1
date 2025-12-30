"""
CRS Step Runner - Execute individual pipeline steps with event emission
"""
import os
import time
import traceback
from typing import Any, Dict, Optional
from pathlib import Path

from core.fs import WorkspaceFS
from core.pipeline_state import PipelineState
from core.events import CRSEventEmitter, LogLevel
from core.impact_engine import ImpactEngine
from core.query_api import CRSQueryAPI
from core.patch_engine import apply_patch_from_file
from core.spec_store import SpecStore
from core.verification_engine import VerificationEngine


def _get_tool_path(fs: WorkspaceFS, filename: str) -> str:
    return os.path.abspath(os.path.join(fs.paths.tools_dir, filename))


def _load_module_from_path(name: str, abs_path: str):
    import importlib.util

    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Tool not found: {abs_path}")
    spec = importlib.util.spec_from_file_location(name, abs_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load spec for {name} from {abs_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CRSStepRunner:
    """
    Executes individual CRS pipeline steps with event emission
    """

    def __init__(self, fs: WorkspaceFS, emitter: Optional[CRSEventEmitter] = None):
        self.fs = fs
        self.emitter = emitter
        self.state = PipelineState(fs)

    def _log(self, step_name: str, message: str, level: LogLevel = LogLevel.INFO) -> None:
        """Emit log event"""
        print(message)  # Also print to console
        if self.emitter:
            self.emitter.emit_step_log(step_name, message, level)

    def run_blueprints(self, force: bool = False) -> Dict[str, Any]:
        """Run blueprints indexing step"""
        step_name = "blueprints"
        t0 = time.time()

        try:
            if self.emitter:
                self.emitter.emit_step_start(step_name, {"force": force})

            self._log(step_name, "Loading blueprint builder tool...")

            # Check if we need to run
            if not force:
                decision = self.state.decide()
                if not decision.run_blueprints:
                    self._log(step_name, "Blueprints up-to-date, skipping", LogLevel.INFO)
                    return {"skipped": True, "reason": "up-to-date"}

            # Load and run blueprint builder
            bp_path = _get_tool_path(self.fs, "blueprint_builder_v1_workspace.py")
            mod = _load_module_from_path("crs_blueprint_builder", bp_path)
            fn = getattr(mod, "index_workspace_blueprints", None)
            if not callable(fn):
                raise RuntimeError("Blueprint builder must expose index_workspace_blueprints()")

            self._log(step_name, f"Scanning source directory: {self.fs.paths.src_dir}")

            payload = fn(self.fs)
            if not isinstance(payload, dict):
                payload = {"payload": payload}

            file_count = payload.get("file_count", 0)
            self._log(step_name, f"Indexed {file_count} files")

            # Update state
            src_info = self.state.compute_src_fingerprint()
            bp_sha = self.state.hash_output_file(self.fs.paths.blueprints_json)
            self.state.mark_step_done("blueprints",
                                     src_fingerprint=src_info["src_fingerprint"],
                                     output_sha1=bp_sha)

            duration = time.time() - t0
            result = {
                "file_count": file_count,
                "output": self.fs.paths.blueprints_json,
                "duration": duration
            }

            if self.emitter:
                self.emitter.emit_step_complete(step_name, duration, result)

            return result

        except Exception as e:
            duration = time.time() - t0
            error_msg = str(e)
            error_trace = traceback.format_exc()

            self._log(step_name, f"Error: {error_msg}", LogLevel.ERROR)

            if self.emitter:
                self.emitter.emit_step_error(
                    step_name,
                    error_msg,
                    type(e).__name__,
                    error_trace
                )

            raise

    def run_artifacts(self, force: bool = False) -> Dict[str, Any]:
        """Run artifact extraction step"""
        step_name = "artifacts"
        t0 = time.time()

        try:
            if self.emitter:
                self.emitter.emit_step_start(step_name, {"force": force})

            self._log(step_name, "Loading artifact extractor tool...")

            # Check if we need to run
            if not force:
                decision = self.state.decide()
                if not decision.run_artifacts:
                    self._log(step_name, "Artifacts up-to-date, skipping", LogLevel.INFO)
                    return {"skipped": True, "reason": "up-to-date"}

            # Load and run artifact extractor
            ax_path = _get_tool_path(self.fs, "artifact_extractor_v1_workspace.py")
            mod = _load_module_from_path("crs_artifact_extractor", ax_path)
            fn = getattr(mod, "extract_all", None)
            if not callable(fn):
                raise RuntimeError("Artifact extractor must expose extract_all()")

            self._log(step_name, "Extracting artifacts from blueprints...")

            payload = fn(self.fs.paths.blueprints_json, self.fs.paths.artifacts_json)
            if not isinstance(payload, dict):
                payload = {"payload": payload}

            arts_count = len(payload.get("artifacts", []))
            self._log(step_name, f"Extracted {arts_count} artifacts")

            # Update state
            src_info = self.state.compute_src_fingerprint()
            art_sha = self.state.hash_output_file(self.fs.paths.artifacts_json)
            self.state.mark_step_done("artifacts",
                                     src_fingerprint=src_info["src_fingerprint"],
                                     output_sha1=art_sha)

            duration = time.time() - t0
            result = {
                "artifacts_count": arts_count,
                "output": self.fs.paths.artifacts_json,
                "duration": duration
            }

            if self.emitter:
                self.emitter.emit_step_complete(step_name, duration, result)

            return result

        except Exception as e:
            duration = time.time() - t0
            error_msg = str(e)
            error_trace = traceback.format_exc()

            self._log(step_name, f"Error: {error_msg}", LogLevel.ERROR)

            if self.emitter:
                self.emitter.emit_step_error(
                    step_name,
                    error_msg,
                    type(e).__name__,
                    error_trace
                )

            raise

    def run_relationships(self, force: bool = False) -> Dict[str, Any]:
        """Run relationship building step"""
        step_name = "relationships"
        t0 = time.time()

        try:
            if self.emitter:
                self.emitter.emit_step_start(step_name, {"force": force})

            self._log(step_name, "Loading relationship builder tool...")

            # Check if we need to run
            if not force:
                decision = self.state.decide()
                if not decision.run_relationships:
                    self._log(step_name, "Relationships up-to-date, skipping", LogLevel.INFO)
                    return {"skipped": True, "reason": "up-to-date"}

            # Load and run relationship builder
            rb_path = _get_tool_path(self.fs, "relationship_builder_v1_workspace.py")
            mod = _load_module_from_path("crs_relationship_builder", rb_path)
            fn = getattr(mod, "build_relationships", None)
            if not callable(fn):
                raise RuntimeError("Relationship builder must expose build_relationships()")

            # Load artifacts
            artifacts_payload = self.fs.read_json(self.fs.paths.artifacts_json)
            if not isinstance(artifacts_payload, dict):
                raise FileNotFoundError(f"Artifacts JSON not found/invalid")

            self._log(step_name, "Building relationships from artifacts...")

            cfg = self.fs.get_cfg() or {}
            components = (cfg.get("components") or {})
            include_heuristic = bool(components.get("relationship_include_heuristic_mentions", True))

            rel_payload = fn(artifacts_payload, include_heuristic_mentions=include_heuristic)
            if not isinstance(rel_payload, dict):
                rel_payload = {"payload": rel_payload}

            rel_payload["source_artifacts"] = self.fs.paths.artifacts_json
            self.fs.save_relationships(rel_payload)

            rel_count = rel_payload.get("summary", {}).get("relationships", 0)
            self._log(step_name, f"Built {rel_count} relationships")

            # Update state
            src_info = self.state.compute_src_fingerprint()
            rel_sha = self.state.hash_output_file(self.fs.paths.relationships_json)
            self.state.mark_step_done("relationships",
                                     src_fingerprint=src_info["src_fingerprint"],
                                     output_sha1=rel_sha)

            duration = time.time() - t0
            result = {
                "relationships_count": rel_count,
                "output": self.fs.paths.relationships_json,
                "summary": rel_payload.get("summary"),
                "duration": duration
            }

            if self.emitter:
                self.emitter.emit_step_complete(step_name, duration, result)

            return result

        except Exception as e:
            duration = time.time() - t0
            error_msg = str(e)
            error_trace = traceback.format_exc()

            self._log(step_name, f"Error: {error_msg}", LogLevel.ERROR)

            if self.emitter:
                self.emitter.emit_step_error(
                    step_name,
                    error_msg,
                    type(e).__name__,
                    error_trace
                )

            raise

    def run_verification(self, suite_id: str) -> Dict[str, Any]:
        """Run verification suite"""
        step_name = f"verification_{suite_id}"
        t0 = time.time()

        try:
            if self.emitter:
                self.emitter.emit_step_start(step_name, {"suite_id": suite_id})

            self._log(step_name, f"Running verification suite: {suite_id}")

            v = VerificationEngine(self.fs)
            v_payload = v.run_suite(suite_id, run_id=None)

            ok = v_payload.get("ok", False)
            summary = v_payload.get("summary", {})

            self._log(step_name, f"Verification {'passed' if ok else 'failed'}: {summary}")

            duration = time.time() - t0
            result = {
                "ok": ok,
                "summary": summary,
                "duration": duration
            }

            if self.emitter:
                self.emitter.emit_step_complete(step_name, duration, result)

            return result

        except Exception as e:
            duration = time.time() - t0
            error_msg = str(e)
            error_trace = traceback.format_exc()

            self._log(step_name, f"Error: {error_msg}", LogLevel.ERROR)

            if self.emitter:
                self.emitter.emit_step_error(
                    step_name,
                    error_msg,
                    type(e).__name__,
                    error_trace
                )

            raise

    def run_impact(self) -> Dict[str, Any]:
        """Run impact analysis"""
        step_name = "impact"
        t0 = time.time()

        try:
            if self.emitter:
                self.emitter.emit_step_start(step_name)

            # Check if patch exists
            meta = self.state.load_meta()
            patch = meta.get("patch") if isinstance(meta.get("patch"), dict) else {}
            patch_dirty = bool(patch.get("dirty", False))
            patch_id = str(patch.get("patch_id") or "").strip()

            if not patch_dirty and not patch_id:
                self._log(step_name, "No patch to analyze, skipping")
                return {"skipped": True, "reason": "no_patch"}

            self._log(step_name, f"Running impact analysis for patch: {patch_id}")

            impact_engine = ImpactEngine(self.fs)
            impact_payload = impact_engine.build_workspace_impact(run_id=None)

            summary = impact_payload.get("summary", {})
            self._log(step_name, f"Impact analysis complete: {summary}")

            duration = time.time() - t0
            result = {
                "patch_id": impact_payload.get("patch_id"),
                "summary": summary,
                "duration": duration
            }

            if self.emitter:
                self.emitter.emit_step_complete(step_name, duration, result)

            return result

        except Exception as e:
            duration = time.time() - t0
            error_msg = str(e)
            error_trace = traceback.format_exc()

            self._log(step_name, f"Error: {error_msg}", LogLevel.ERROR)

            if self.emitter:
                self.emitter.emit_step_error(
                    step_name,
                    error_msg,
                    type(e).__name__,
                    error_trace
                )

            raise

    def get_step_status(self) -> Dict[str, Any]:
        """Get status of all pipeline steps"""
        decision = self.state.decide()
        meta = self.state.load_meta()

        return {
            "decision": {
                "reason": decision.reason,
                "run_blueprints": decision.run_blueprints,
                "run_artifacts": decision.run_artifacts,
                "run_relationships": decision.run_relationships,
            },
            "meta": meta,
            "paths": {
                "blueprints": self.fs.paths.blueprints_json,
                "artifacts": self.fs.paths.artifacts_json,
                "relationships": self.fs.paths.relationships_json,
            },
            "files_exist": {
                "blueprints": Path(self.fs.paths.blueprints_json).exists(),
                "artifacts": Path(self.fs.paths.artifacts_json).exists(),
                "relationships": Path(self.fs.paths.relationships_json).exists(),
            }
        }
