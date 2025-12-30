# crs_components.py
import os
import sys
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

from crs_lib import (
    read_json, write_json, read_text, write_text,
    list_py_files, normalize_path,
    iter_blueprint_entries, get_entry_raw_text,
    set_entry_raw_text, safe_relpath
)


# ============================================================
# Workspace
# ============================================================
@dataclass
class Workspace:
    root: Path
    src_dir: Path
    state_dir: Path
    runs_dir: Path
    config_path: Path

    @staticmethod
    def discover() -> "Workspace":
        # Default: ./crs_workspace next to entry file
        env = os.environ.get("CRS_WORKSPACE")
        root = Path(env).expanduser().resolve() if env else (Path(__file__).parent / "crs_workspace").resolve()

        src_dir = root / "src"
        state_dir = root / "state"
        runs_dir = root / "runs"
        config_path = root / "config.json"

        src_dir.mkdir(parents=True, exist_ok=True)
        state_dir.mkdir(parents=True, exist_ok=True)
        runs_dir.mkdir(parents=True, exist_ok=True)

        if not config_path.exists():
            write_json(config_path, {
                "version": "crs-workspace-config-v1",
                "impact": {
                    "rename_field": {
                        "enabled": False,
                        "model": "User",
                        "old": "email",
                        "new": "primary_email"
                    }
                },
                "patch_apply": {
                    "enabled": False,
                    "write_back_to_src": False,     # IMPORTANT: keep False unless you want CRS to modify src files
                    "patch_plan_path": "runs/latest/outputs/patch_plan.json"
                },
                "artifact_extractor": {
                    "script_path": "artifact_extractor_v1.py",  # put in workspace root or adjust path
                    "output_name": "artifacts.json"
                }
            })

        return Workspace(root, src_dir, state_dir, runs_dir, config_path)

    def config(self) -> Dict[str, Any]:
        return read_json(self.config_path)


# ============================================================
# Base Step
# ============================================================
class Step:
    name = "Step"

    def run(self, ws: Workspace, ctx: Dict[str, Any]) -> None:
        raise NotImplementedError


# ============================================================
# 1) Build Blueprints from src/
# ============================================================
class BlueprintBuildFromSrc(Step):
    name = "BlueprintBuildFromSrc"

    def run(self, ws: Workspace, ctx: Dict[str, Any]) -> None:
        log = ctx["log"]
        src_files = list_py_files(ws.src_dir)
        if not src_files:
            raise RuntimeError(f"workspace/src has no .py files: {ws.src_dir}")

        blueprints = []
        for p in src_files:
            rel = normalize_path(str(p.relative_to(ws.src_dir)))
            raw = read_text(p)
            blueprints.append({
                "file_path": rel,          # relative to src
                "raw_text": raw,
                "parse_ok": True,
                "parse_error": None,
                "segments": []             # placeholder (kept for compatibility)
            })

        out = {
            "version": "crs-blueprints-v1",
            "root": "src",               # logical root
            "file_count": len(blueprints),
            "blueprints": blueprints
        }

        out_path = ws.state_dir / "blueprints.json"
        write_json(out_path, out)
        log(f"✅ wrote {out_path} (files={len(blueprints)})")


# ============================================================
# 2) Regenerate snapshot from blueprint state
# ============================================================
class RegenFromBlueprint(Step):
    name = "RegenFromBlueprint"

    def run(self, ws: Workspace, ctx: Dict[str, Any]) -> None:
        log = ctx["log"]
        bp_path = ws.state_dir / "blueprints.json"
        if not bp_path.exists():
            raise RuntimeError("Missing state/blueprints.json. Run BlueprintBuildFromSrc first.")

        bp = read_json(bp_path)
        regen_dir = ctx["out_dir"] / "regen"
        regen_dir.mkdir(parents=True, exist_ok=True)

        root, entries = iter_blueprint_entries(bp)
        written = 0
        for e in entries:
            fp = e.get("file_path") or e.get("path")
            if not fp:
                continue
            raw = get_entry_raw_text(e, root)
            rel = fp if root == "src" else safe_relpath(fp, root)
            out_path = regen_dir / rel
            write_text(out_path, raw)
            written += 1

        log(f"✅ regenerated {written} files into {regen_dir}")


# ============================================================
# 3) Compare regen snapshot with src/
# ============================================================
class CompareRegenWithSrc(Step):
    name = "CompareRegenWithSrc"

    def run(self, ws: Workspace, ctx: Dict[str, Any]) -> None:
        log = ctx["log"]
        regen_dir = ctx["out_dir"] / "regen"
        if not regen_dir.exists():
            raise RuntimeError("Missing regen output. Run RegenFromBlueprint first.")

        mismatches = []
        missing = []
        ok = 0

        regen_files = [p for p in regen_dir.rglob("*.py") if p.is_file()]
        for rf in regen_files:
            rel = rf.relative_to(regen_dir)
            sf = ws.src_dir / rel
            if not sf.exists():
                missing.append(str(rel))
                continue
            if read_text(rf) == read_text(sf):
                ok += 1
            else:
                mismatches.append(str(rel))

        report = {
            "version": "crs-compare-report-v1",
            "ok": ok,
            "mismatches": mismatches,
            "missing_in_src": missing,
            "total_regen": len(regen_files)
        }
        out = ctx["out_dir"] / "compare_report.json"
        write_json(out, report)

        log(f"✅ compare_report: ok={ok}, mismatches={len(mismatches)}, missing={len(missing)} -> {out}")


# ============================================================
# 4) Build Artifacts from blueprint state (calls your extractor script)
# ============================================================
class ArtifactsBuildFromBlueprint(Step):
    name = "ArtifactsBuildFromBlueprint"

    def run(self, ws: Workspace, ctx: Dict[str, Any]) -> None:
        log = ctx["log"]
        cfg = ws.config()

        bp_path = ws.state_dir / "blueprints.json"
        if not bp_path.exists():
            raise RuntimeError("Missing state/blueprints.json. Run BlueprintBuildFromSrc first.")

        extractor_path = (ws.root / cfg["artifact_extractor"]["script_path"]).resolve()
        if not extractor_path.exists():
            raise RuntimeError(
                f"Missing artifact extractor at: {extractor_path}\n"
                f"Put artifact_extractor_v1.py into workspace root or update config.json artifact_extractor.script_path"
            )

        out_path = ws.state_dir / cfg["artifact_extractor"].get("output_name", "artifacts.json")

        # We assume your extractor can be run as a script.
        # If your current extractor uses hard-coded paths, we’ll adjust it next step.
        #
        # For now: we run it with TWO env vars so you can update extractor to read them:
        #   CRS_BLUEPRINTS_IN = path
        #   CRS_ARTIFACTS_OUT = path
        env = os.environ.copy()
        env["CRS_BLUEPRINTS_IN"] = str(bp_path)
        env["CRS_ARTIFACTS_OUT"] = str(out_path)

        # Run: python artifact_extractor_v1.py
        res = subprocess.run([sys.executable, str(extractor_path)], env=env, capture_output=True, text=True)

        log(res.stdout.strip() if res.stdout else "")
        if res.returncode != 0:
            log(res.stderr.strip() if res.stderr else "")
            raise RuntimeError(f"Artifact extractor failed (exit={res.returncode})")

        if not out_path.exists():
            raise RuntimeError(f"Extractor ran but did not create: {out_path}")

        log(f"✅ wrote {out_path}")


# ============================================================
# 5) Impact Rename Field (writes patch_plan.json + impact_report.json)
# ============================================================
class ImpactRenameField(Step):
    name = "ImpactRenameField"

    def run(self, ws: Workspace, ctx: Dict[str, Any]) -> None:
        log = ctx["log"]
        cfg = ws.config()
        impact_cfg = cfg.get("impact", {}).get("rename_field", {})
        if not impact_cfg.get("enabled", False):
            log("↪️ impact.rename_field disabled in config.json (skipping)")
            return

        bp_path = ws.state_dir / "blueprints.json"
        art_path = ws.state_dir / "artifacts.json"
        if not bp_path.exists():
            raise RuntimeError("Missing state/blueprints.json")
        if not art_path.exists():
            raise RuntimeError("Missing state/artifacts.json")

        # Here we expect your impact script code to be integrated later.
        # For v1, we assume you'll drop crs_impact_rename_field_v1.py in workspace root and it reads env vars similarly.
        script = ws.root / "crs_impact_rename_field_v1.py"
        if not script.exists():
            raise RuntimeError(f"Missing: {script}. Put your impact script there.")

        out_impact = ctx["out_dir"] / "impact_report.json"
        out_plan = ctx["out_dir"] / "patch_plan.json"

        env = os.environ.copy()
        env["CRS_BLUEPRINTS_IN"] = str(bp_path)
        env["CRS_ARTIFACTS_IN"] = str(art_path)
        env["CRS_IMPACT_OUT"] = str(out_impact)
        env["CRS_PATCHPLAN_OUT"] = str(out_plan)
        env["CRS_MODEL"] = impact_cfg["model"]
        env["CRS_OLD"] = impact_cfg["old"]
        env["CRS_NEW"] = impact_cfg["new"]

        res = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True)
        log(res.stdout.strip() if res.stdout else "")
        if res.returncode != 0:
            log(res.stderr.strip() if res.stderr else "")
            raise RuntimeError(f"Impact script failed (exit={res.returncode})")

        log(f"✅ wrote {out_impact}")
        log(f"✅ wrote {out_plan}")


# ============================================================
# 6) Patch Apply + update state blueprints (+ optional write-back to src)
# ============================================================
class PatchApplyAndUpdateState(Step):
    name = "PatchApplyAndUpdateState"

    def run(self, ws: Workspace, ctx: Dict[str, Any]) -> None:
        log = ctx["log"]
        cfg = ws.config()
        patch_cfg = cfg.get("patch_apply", {})
        if not patch_cfg.get("enabled", False):
            log("↪️ patch_apply disabled in config.json (skipping)")
            return

        bp_path = ws.state_dir / "blueprints.json"
        if not bp_path.exists():
            raise RuntimeError("Missing state/blueprints.json")

        # default patch plan is the one generated in this run
        patch_plan_path = ctx["out_dir"] / "patch_plan.json"
        if patch_cfg.get("patch_plan_path"):
            # allow config override; supports "runs/latest/outputs/patch_plan.json"
            override = ws.root / patch_cfg["patch_plan_path"]
            if override.exists():
                patch_plan_path = override

        if not patch_plan_path.exists():
            raise RuntimeError(f"Missing patch plan: {patch_plan_path}")

        bp = read_json(bp_path)
        plan = read_json(patch_plan_path)

        root, entries = iter_blueprint_entries(bp)
        entry_map = {normalize_path((e.get("file_path") or e.get("path") or "")): e for e in entries if (e.get("file_path") or e.get("path"))}

        # group patches by file
        patches_by_file: Dict[str, List[Dict[str, Any]]] = {}
        for p in plan.get("patches", []):
            fp = normalize_path(p["file_path"])
            patches_by_file.setdefault(fp, []).append(p)

        outcomes = []
        applied = 0
        failed = 0
        missing_files = 0

        # apply per file, bottom-to-top
        for fp, plist in patches_by_file.items():
            entry = entry_map.get(fp)
            if not entry:
                missing_files += 1
                for p in plist:
                    outcomes.append({**p, "applied": False, "message": "file not found in state blueprints"})
                continue

            raw = get_entry_raw_text(entry, root)
            lines = raw.splitlines(keepends=True)

            plist_sorted = sorted(plist, key=lambda x: (int(x["start_line"]), int(x["end_line"])), reverse=True)

            for p in plist_sorted:
                s = int(p["start_line"])
                e = int(p["end_line"])
                old_slice = "".join(lines[s-1:e]) if 1 <= s <= len(lines) else ""
                guard = p.get("expected_old_text")
                if guard is not None and guard != old_slice:
                    failed += 1
                    outcomes.append({**p, "applied": False, "message": "guard failed"})
                    continue

                replace_with = p["replace_with"].splitlines(keepends=True)
                if len(lines) == 0:
                    lines = replace_with
                else:
                    s = max(1, min(s, len(lines)))
                    e = max(s, min(e, len(lines)))
                    lines = lines[:s-1] + replace_with + lines[e:]

                applied += 1
                outcomes.append({**p, "applied": True, "message": "applied"})

            set_entry_raw_text(entry, "".join(lines))

        # write updated blueprint state
        write_json(bp_path, bp)
        log(f"✅ updated state blueprint: {bp_path}")

        # optionally write back to src
        if patch_cfg.get("write_back_to_src", False):
            regen_dir = ws.src_dir
            # write all blueprint files back
            root, entries = iter_blueprint_entries(bp)
            for e in entries:
                fp = e.get("file_path") or e.get("path")
                if not fp:
                    continue
                raw = get_entry_raw_text(e, root)
                write_text(regen_dir / fp, raw)
            log("✅ wrote patched content back to workspace/src")

        report = {
            "version": "crs-patch-apply-report-v1",
            "patches_total": len(plan.get("patches", [])),
            "applied": applied,
            "failed": failed,
            "missing_files": missing_files,
            "outcomes": outcomes,
        }
        out = ctx["out_dir"] / "patch_apply_report.json"
        write_json(out, report)
        log(f"✅ patch_apply_report: {out}")
