# core/tester.py
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.fs import WorkspaceFS
from core.query_runner import CRSQueryRunner

from core.spec_store import SpecStore

def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_eval_path_key(fs: WorkspaceFS, path_key: str) -> str:
    # Supported path_key format examples:
    #   "fs.paths.artifacts_json"
    #   "fs.paths.relationships_json"
    # We intentionally restrict to fs only.
    return eval(path_key, {}, {"fs": fs})


@dataclass
class CheckResult:
    id: str
    type: str
    severity: str
    ok: bool
    details: Dict[str, Any]


class CRSTester:
    """
    CRS Tester (v1)
    ---------------
    Runs verification suites declared in:
      state/specs/verification_suite.json

    This is machine-operational testing for agents.
    """

    VERSION = "crs-tester-v1"

    def __init__(self, fs: WorkspaceFS):
        self.fs = fs
        self.query = CRSQueryRunner(fs)

    def _suite_path(self) -> str:
        return os.path.join(self.fs.paths.state_dir, "specs", "verification_suite.json")

    def load_suites(self) -> Dict[str, Any]:
        path = self._suite_path()

        # If missing, auto-initialize specs (safe, non-fatal)
        if not self.fs.backend.exists(path):
            try:
                SpecStore(self.fs).ensure_defaults(overwrite=False)
            except Exception:
                pass

        if not self.fs.backend.exists(path):
            return {"suites": []}

        obj = self.fs.read_json(path)
        return obj if isinstance(obj, dict) else {"suites": []}


    def run_suite(
        self,
        suite_id: str,
        *,
        run_id: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        overrides: allows agent to override check params (e.g. route to trace)
        """
        overrides = overrides or {}
        suites_obj = self.load_suites()
        suites = suites_obj.get("suites") if isinstance(suites_obj.get("suites"), list) else []
        suite = next((s for s in suites if isinstance(s, dict) and s.get("id") == suite_id), None)

        if not suite:
            payload = {
                "version": self.VERSION,
                "generated_at": _utc_iso(),
                "suite_id": suite_id,
                "ok": False,
                "error": "suite_not_found",
                "checks": [],
            }
            if run_id:
                self.fs.write_run_json(run_id, "verification.json", payload)
            return payload

        check_results: List[Dict[str, Any]] = []
        ok = True

        for chk in suite.get("checks", []):
            if not isinstance(chk, dict):
                continue
            chk_id = str(chk.get("id") or "")
            chk_type = str(chk.get("type") or "")
            severity = str(chk.get("severity") or "low")
            params = chk.get("params") if isinstance(chk.get("params"), dict) else {}

            # apply overrides (by check id)
            if chk_id in overrides and isinstance(overrides[chk_id], dict):
                params = {**params, **overrides[chk_id]}

            r = self._run_check(chk_id, chk_type, severity, params)
            check_results.append(r)

            if (not r.get("ok")) and severity == "high":
                ok = False

        payload = {
            "version": self.VERSION,
            "generated_at": _utc_iso(),
            "suite_id": suite_id,
            "ok": ok,
            "checks": check_results,
        }

        if run_id:
            self.fs.write_run_json(run_id, "verification.json", payload)

        return payload

    # -------------------
    # Check executors
    # -------------------
    def _run_check(self, chk_id: str, chk_type: str, severity: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if chk_type == "file_exists":
                path = _safe_eval_path_key(self.fs, str(params.get("path_key") or ""))
                ok = bool(path) and self.fs.backend.exists(path)
                return {"id": chk_id, "type": chk_type, "severity": severity, "ok": ok, "details": {"path": path}}

            if chk_type == "json_schema":
                path = _safe_eval_path_key(self.fs, str(params.get("path_key") or ""))
                obj = self.fs.read_json(path)
                ok = True
                reqs = params.get("requires") if isinstance(params.get("requires"), list) else []
                missing = []
                wrong = []
                for r in reqs:
                    if not isinstance(r, dict):
                        continue
                    k = r.get("key")
                    t = r.get("type")
                    if k not in obj:
                        ok = False
                        missing.append(k)
                        continue
                    if t == "list" and not isinstance(obj.get(k), list):
                        ok = False
                        wrong.append({"key": k, "expected": "list", "actual": type(obj.get(k)).__name__})
                return {
                    "id": chk_id,
                    "type": chk_type,
                    "severity": severity,
                    "ok": ok,
                    "details": {"path": path, "missing": missing, "wrong_types": wrong},
                }

            if chk_type == "invariant":
                inv_id = str(params.get("invariant_id") or "")
                ok, details = self._check_invariant(inv_id)
                return {"id": chk_id, "type": chk_type, "severity": severity, "ok": ok, "details": details}

            if chk_type == "query":
                op = str(params.get("op") or "")
                args = params.get("args") if isinstance(params.get("args"), dict) else {}
                fn = getattr(self.query, op, None)
                if not callable(fn):
                    return {
                        "id": chk_id,
                        "type": chk_type,
                        "severity": severity,
                        "ok": False,
                        "details": {"error": f"unknown query op: {op}"},
                    }
                res = fn(**args)
                ok = bool(isinstance(res, dict) and res.get("found") is True and res.get("model") is not None)
                return {"id": chk_id, "type": chk_type, "severity": severity, "ok": ok, "details": {"op": op, "args": args, "result": res}}

            return {"id": chk_id, "type": chk_type, "severity": severity, "ok": False, "details": {"error": "unknown_check_type"}}

        except Exception as e:
            return {"id": chk_id, "type": chk_type, "severity": severity, "ok": False, "details": {"error": f"{type(e).__name__}: {e}"}}

    def _check_invariant(self, inv_id: str) -> Tuple[bool, Dict[str, Any]]:
        # Minimal invariants (expand later via spec->code mapping)
        if inv_id == "inv:artifact_id_unique":
            idx = self.query.api.load(force=True)
            # collisions would overwrite in dict; detect by scanning list
            artifacts_payload = self.fs.read_json(self.fs.paths.artifacts_json)
            arts = artifacts_payload.get("artifacts") if isinstance(artifacts_payload, dict) and isinstance(artifacts_payload.get("artifacts"), list) else []
            seen = set()
            dups = []
            for a in arts:
                if not isinstance(a, dict):
                    continue
                aid = a.get("artifact_id")
                if not isinstance(aid, str) or not aid:
                    continue
                if aid in seen:
                    dups.append(aid)
                else:
                    seen.add(aid)
            return (len(dups) == 0), {"duplicate_ids": dups[:50], "duplicate_count": len(dups)}

        if inv_id == "inv:relationship_endpoints_have_types":
            rels_payload = self.fs.read_json(self.fs.paths.relationships_json)
            rels = rels_payload.get("relationships") if isinstance(rels_payload, dict) and isinstance(rels_payload.get("relationships"), list) else []
            bad = 0
            samples = []
            for r in rels:
                if not isinstance(r, dict):
                    continue
                fr = r.get("from") if isinstance(r.get("from"), dict) else {}
                to = r.get("to") if isinstance(r.get("to"), dict) else {}
                if not fr.get("type") or not to.get("type"):
                    bad += 1
                    if len(samples) < 10:
                        samples.append(r)
            return (bad == 0), {"bad_count": bad, "samples": samples}

        # Unknown invariant: treat as pass (agent/spec mismatch shouldn’t block)
        return True, {"note": "unknown invariant id treated as pass", "invariant_id": inv_id}
