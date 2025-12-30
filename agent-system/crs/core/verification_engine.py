# core/verification_engine.py
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.fs import WorkspaceFS
from core.query_api import CRSQueryAPI


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _norm(p: str) -> str:
    return (p or "").replace("\\", "/").strip()


def _safe_read_json(fs: WorkspaceFS, path: str) -> Optional[Dict[str, Any]]:
    try:
        if fs.backend.exists(path):
            obj = fs.read_json(path)
            return obj if isinstance(obj, dict) else None
    except Exception:
        return None
    return None


def _safe_read_any_json(fs: WorkspaceFS, path: str) -> Optional[Any]:
    try:
        if fs.backend.exists(path):
            return fs.read_json(path)
    except Exception:
        return None
    return None


@dataclass
class CheckResult:
    id: str
    ok: bool
    severity: str  # "low"|"medium"|"high"
    type: str      # "invariant"|"file_exists"|"json_schema"|"query"|"graph"
    pass_condition: str
    message: str
    details: Dict[str, Any]


class VerificationEngine:
    """
    CRS Verification Engine (v1)
    ----------------------------
    Executes suites defined in:
      state/specs/verification_suite.json

    Your suite schema supports check types:
      - file_exists
      - json_schema
      - invariant
      - query
      - graph (reserved for later)

    This engine is intentionally minimal:
      - It reads suite definitions
      - Executes checks
      - Writes run outputs when run_id is provided
      - Caller decides whether failures are fatal
    """

    VERSION = "crs-verification-engine-v1"

    def __init__(self, fs: WorkspaceFS):
        self.fs = fs
        self.api = CRSQueryAPI(fs)

    # -------------------------
    # Paths / spec loading
    # -------------------------
    def _spec_path(self) -> str:
        return os.path.join(self.fs.paths.state_dir, "specs", "verification_suite.json")

    def _invariants_path(self) -> str:
        return os.path.join(self.fs.paths.state_dir, "specs", "invariants.json")

    def load_spec(self) -> Dict[str, Any]:
        spec_path = self._spec_path()
        spec = _safe_read_json(self.fs, spec_path)
        if not isinstance(spec, dict):
            return {
                "version": "crs-verification-suite-v1",
                "generated_at": _utc_iso(),
                "suites": [],
                "error": f"verification_suite.json missing/invalid at: {spec_path}",
            }
        return spec

    def get_suite(self, suite_id: str) -> Optional[Dict[str, Any]]:
        spec = self.load_spec()
        suites = spec.get("suites")
        if not isinstance(suites, list):
            return None
        for s in suites:
            if isinstance(s, dict) and str(s.get("id") or "") == str(suite_id):
                return s
        return None

    # -------------------------
    # Helpers
    # -------------------------
    def _resolve_path_key(self, path_key: str) -> Optional[str]:
        """
        Supports the suite's convention:
          params: { "path_key": "fs.paths.artifacts_json" }

        Allowed:
          - fs.paths.<attr>
          - paths.<attr>   (also accepted)
        """
        pk = (path_key or "").strip()
        if not pk:
            return None

        if pk.startswith("fs.paths."):
            attr = pk.split("fs.paths.", 1)[1].strip()
            return getattr(self.fs.paths, attr, None)

        if pk.startswith("paths."):
            attr = pk.split("paths.", 1)[1].strip()
            return getattr(self.fs.paths, attr, None)

        # raw path fallback (discouraged but allowed)
        return pk

    def _severity(self, chk: Dict[str, Any]) -> str:
        sev = str(chk.get("severity") or "medium").strip().lower()
        return sev if sev in ("low", "medium", "high") else "medium"

    def _pass_condition(self, chk: Dict[str, Any]) -> str:
        return str(chk.get("pass_condition") or "").strip()

    # -------------------------
    # Check implementations
    # -------------------------
    def _check_file_exists(self, chk: Dict[str, Any]) -> CheckResult:
        params = chk.get("params") if isinstance(chk.get("params"), dict) else {}
        path_key = str(params.get("path_key") or "").strip()
        abs_path = self._resolve_path_key(path_key)

        ok = bool(abs_path) and self.fs.backend.exists(abs_path)  # type: ignore[arg-type]
        msg = "exists" if ok else "missing"
        return CheckResult(
            id=str(chk.get("id") or "file_exists"),
            ok=ok,
            severity=self._severity(chk),
            type="file_exists",
            pass_condition=self._pass_condition(chk),
            message=f"{msg}: {abs_path if abs_path else path_key}",
            details={"path_key": path_key, "path": _norm(abs_path or "")},
        )

    def _type_matches(self, value: Any, type_str: str) -> bool:
        t = (type_str or "").strip().lower()
        if t == "list":
            return isinstance(value, list)
        if t == "dict" or t == "object":
            return isinstance(value, dict)
        if t == "string" or t == "str":
            return isinstance(value, str)
        if t == "int" or t == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if t == "bool" or t == "boolean":
            return isinstance(value, bool)
        if t == "null" or t == "none":
            return value is None
        # unknown type string => fail-safe false
        return False

    def _check_json_schema(self, chk: Dict[str, Any]) -> CheckResult:
        params = chk.get("params") if isinstance(chk.get("params"), dict) else {}
        path_key = str(params.get("path_key") or "").strip()
        abs_path = self._resolve_path_key(path_key)
        requires = params.get("requires")

        if not abs_path:
            return CheckResult(
                id=str(chk.get("id") or "json_schema"),
                ok=False,
                severity=self._severity(chk),
                type="json_schema",
                pass_condition=self._pass_condition(chk),
                message=f"invalid path_key: {path_key}",
                details={"path_key": path_key},
            )

        obj = _safe_read_any_json(self.fs, abs_path)
        if obj is None:
            return CheckResult(
                id=str(chk.get("id") or "json_schema"),
                ok=False,
                severity=self._severity(chk),
                type="json_schema",
                pass_condition=self._pass_condition(chk),
                message=f"missing/invalid json: {abs_path}",
                details={"path": _norm(abs_path)},
            )

        if not isinstance(requires, list) or not requires:
            # if no requires, schema check is basically "json parse ok"
            return CheckResult(
                id=str(chk.get("id") or "json_schema"),
                ok=True,
                severity=self._severity(chk),
                type="json_schema",
                pass_condition=self._pass_condition(chk),
                message="json loaded",
                details={"path": _norm(abs_path)},
            )

        if not isinstance(obj, dict):
            return CheckResult(
                id=str(chk.get("id") or "json_schema"),
                ok=False,
                severity=self._severity(chk),
                type="json_schema",
                pass_condition=self._pass_condition(chk),
                message=f"expected top-level object/dict, got: {type(obj).__name__}",
                details={"path": _norm(abs_path)},
            )

        missing: List[Dict[str, Any]] = []
        wrong_type: List[Dict[str, Any]] = []
        for req in requires:
            if not isinstance(req, dict):
                continue
            key = str(req.get("key") or "").strip()
            typ = str(req.get("type") or "").strip()
            if not key:
                continue
            if key not in obj:
                missing.append({"key": key, "expected": typ})
                continue
            if typ and not self._type_matches(obj.get(key), typ):
                wrong_type.append({"key": key, "expected": typ, "got": type(obj.get(key)).__name__})

        ok = (len(missing) == 0) and (len(wrong_type) == 0)
        msg = "ok" if ok else f"missing={len(missing)} wrong_type={len(wrong_type)}"
        return CheckResult(
            id=str(chk.get("id") or "json_schema"),
            ok=ok,
            severity=self._severity(chk),
            type="json_schema",
            pass_condition=self._pass_condition(chk),
            message=msg,
            details={"path": _norm(abs_path), "missing": missing, "wrong_type": wrong_type},
        )

    def _load_invariants(self) -> List[Dict[str, Any]]:
        obj = _safe_read_json(self.fs, self._invariants_path()) or {}
        inv = obj.get("invariants")
        return inv if isinstance(inv, list) else []

    def _check_invariant(self, chk: Dict[str, Any]) -> CheckResult:
        """
        Invariants supported (v1, matches your current invariants.json defaults):
          - inv:artifact_id_unique
          - inv:relationship_endpoints_have_types
        """
        params = chk.get("params") if isinstance(chk.get("params"), dict) else {}
        inv_id = str(params.get("invariant_id") or "").strip()

        if inv_id == "inv:artifact_id_unique":
            # artifacts.json: artifact_id unique
            ap = self.fs.paths.artifacts_json
            payload = _safe_read_json(self.fs, ap)
            if not isinstance(payload, dict):
                return CheckResult(
                    id=str(chk.get("id") or inv_id),
                    ok=False,
                    severity=self._severity(chk),
                    type="invariant",
                    pass_condition=self._pass_condition(chk),
                    message=f"missing/invalid artifacts.json: {ap}",
                    details={"path": _norm(ap)},
                )
            arts = payload.get("artifacts")
            if not isinstance(arts, list):
                return CheckResult(
                    id=str(chk.get("id") or inv_id),
                    ok=False,
                    severity=self._severity(chk),
                    type="invariant",
                    pass_condition=self._pass_condition(chk),
                    message="artifacts.json missing 'artifacts' list",
                    details={"path": _norm(ap)},
                )
            seen: Dict[str, int] = {}
            dups: Dict[str, int] = {}
            for a in arts:
                if not isinstance(a, dict):
                    continue
                aid = a.get("artifact_id")
                if not isinstance(aid, str) or not aid:
                    continue
                if aid in seen:
                    dups[aid] = dups.get(aid, 1) + 1
                else:
                    seen[aid] = 1
            ok = len(dups) == 0
            return CheckResult(
                id=str(chk.get("id") or inv_id),
                ok=ok,
                severity=self._severity(chk),
                type="invariant",
                pass_condition=self._pass_condition(chk),
                message="ok" if ok else f"duplicate artifact_id(s): {len(dups)}",
                details={"duplicates": dups, "total_artifacts": len(arts)},
            )

        if inv_id == "inv:relationship_endpoints_have_types":
            rp = self.fs.paths.relationships_json
            payload = _safe_read_json(self.fs, rp)
            if not isinstance(payload, dict):
                return CheckResult(
                    id=str(chk.get("id") or inv_id),
                    ok=False,
                    severity=self._severity(chk),
                    type="invariant",
                    pass_condition=self._pass_condition(chk),
                    message=f"missing/invalid relationships.json: {rp}",
                    details={"path": _norm(rp)},
                )
            rels = payload.get("relationships")
            if not isinstance(rels, list):
                return CheckResult(
                    id=str(chk.get("id") or inv_id),
                    ok=False,
                    severity=self._severity(chk),
                    type="invariant",
                    pass_condition=self._pass_condition(chk),
                    message="relationships.json missing 'relationships' list",
                    details={"path": _norm(rp)},
                )
            bad: List[Dict[str, Any]] = []
            for r in rels:
                if not isinstance(r, dict):
                    continue
                fr = r.get("from") if isinstance(r.get("from"), dict) else {}
                to = r.get("to") if isinstance(r.get("to"), dict) else {}
                ft = fr.get("type")
                tt = to.get("type")
                if not isinstance(ft, str) or not ft.strip() or not isinstance(tt, str) or not tt.strip():
                    bad.append({"rel_id": r.get("rel_id"), "type": r.get("type"), "from": fr, "to": to})
                    if len(bad) >= 25:
                        break
            ok = len(bad) == 0
            return CheckResult(
                id=str(chk.get("id") or inv_id),
                ok=ok,
                severity=self._severity(chk),
                type="invariant",
                pass_condition=self._pass_condition(chk),
                message="ok" if ok else f"found {len(bad)} missing-endpoint-type rel(s) (sample capped at 25)",
                details={"sample": bad, "total_relationships": len(rels)},
            )

        # Unknown invariant id: report clearly (do not silently pass)
        known = [i.get("id") for i in self._load_invariants() if isinstance(i, dict) and isinstance(i.get("id"), str)]
        return CheckResult(
            id=str(chk.get("id") or inv_id or "invariant"),
            ok=False,
            severity=self._severity(chk),
            type="invariant",
            pass_condition=self._pass_condition(chk),
            message=f"unsupported invariant_id: {inv_id}",
            details={"known_invariants": known},
        )

    def _check_query(self, chk: Dict[str, Any]) -> CheckResult:
        """
        query check schema:
          params: { op: "trace_route_to_model", args: { ... } }
        """
        params = chk.get("params") if isinstance(chk.get("params"), dict) else {}
        op = str(params.get("op") or "").strip()
        args = params.get("args") if isinstance(params.get("args"), dict) else {}

        if not op:
            return CheckResult(
                id=str(chk.get("id") or "query"),
                ok=False,
                severity=self._severity(chk),
                type="query",
                pass_condition=self._pass_condition(chk),
                message="missing params.op",
                details={"params": params},
            )

        # Ensure index loaded
        self.api.load(force=True)

        # Supported ops (v1)
        if op == "trace_route_to_model":
            route = str(args.get("route") or "").strip()
            res = self.api.trace_route_to_model(route)
            found = bool(isinstance(res, dict) and res.get("found"))
            model_ok = bool(isinstance(res, dict) and res.get("model") is not None)
            ok = found and model_ok
            return CheckResult(
                id=str(chk.get("id") or "trace_route_to_model"),
                ok=ok,
                severity=self._severity(chk),
                type="query",
                pass_condition=self._pass_condition(chk),
                message="ok" if ok else "trace failed or model is null",
                details={"op": op, "args": {"route": route}, "result": res if isinstance(res, dict) else {"raw": res}},
            )

        if op == "find_artifacts":
            # args: { type?, name?, contains_name?, file_path?, limit? }
            res = self.api.find_artifacts(
                name=args.get("name"),
                type=args.get("type"),
                file_path=args.get("file_path"),
                contains_name=args.get("contains_name"),
                limit=int(args.get("limit") or 50),
            )
            ok = isinstance(res, list) and len(res) > 0
            return CheckResult(
                id=str(chk.get("id") or "find_artifacts"),
                ok=ok,
                severity=self._severity(chk),
                type="query",
                pass_condition=self._pass_condition(chk),
                message="ok" if ok else "no artifacts matched",
                details={"op": op, "args": args, "count": len(res) if isinstance(res, list) else None, "results": res[:10] if isinstance(res, list) else res},
            )

        return CheckResult(
            id=str(chk.get("id") or "query"),
            ok=False,
            severity=self._severity(chk),
            type="query",
            pass_condition=self._pass_condition(chk),
            message=f"unsupported query op: {op}",
            details={"supported_ops": ["trace_route_to_model", "find_artifacts"], "op": op},
        )

    # -------------------------
    # Dispatcher
    # -------------------------
    def _run_check(self, chk: Dict[str, Any]) -> CheckResult:
        ctype = str(chk.get("type") or "").strip()

        if ctype == "file_exists":
            return self._check_file_exists(chk)
        if ctype == "json_schema":
            return self._check_json_schema(chk)
        if ctype == "invariant":
            return self._check_invariant(chk)
        if ctype == "query":
            return self._check_query(chk)
        if ctype == "graph":
            return CheckResult(
                id=str(chk.get("id") or "graph"),
                ok=False,
                severity=self._severity(chk),
                type="graph",
                pass_condition=self._pass_condition(chk),
                message="graph checks not implemented in v1",
                details={"check": chk},
            )

        return CheckResult(
            id=str(chk.get("id") or "unknown_check"),
            ok=False,
            severity=self._severity(chk),
            type=ctype or "unknown",
            pass_condition=self._pass_condition(chk),
            message=f"unknown check type: {ctype}",
            details={"check": chk},
        )

    # -------------------------
    # Public API
    # -------------------------
    def run_suite(self, suite_id: str, *, run_id: Optional[str] = None) -> Dict[str, Any]:
        suite = self.get_suite(suite_id)
        if not isinstance(suite, dict):
            payload = {
                "version": self.VERSION,
                "generated_at": _utc_iso(),
                "suite_id": suite_id,
                "ok": False,
                "summary": {"total": 0, "passed": 0, "failed": 0},
                "results": [],
                "error": f"suite not found: {suite_id}",
            }
            if run_id:
                self.fs.write_run_json(run_id, "verification.json", payload)
            return payload

        checks = suite.get("checks")
        if not isinstance(checks, list):
            checks = []

        results: List[Dict[str, Any]] = []
        passed = 0
        failed = 0
        failed_high = 0
        failed_medium = 0

        for chk in checks:
            if not isinstance(chk, dict):
                continue
            r = self._run_check(chk)
            results.append(
                {
                    "id": r.id,
                    "type": r.type,
                    "ok": r.ok,
                    "severity": r.severity,
                    "pass_condition": r.pass_condition,
                    "message": r.message,
                    "details": r.details,
                }
            )
            if r.ok:
                passed += 1
            else:
                failed += 1
                if r.severity == "high":
                    failed_high += 1
                elif r.severity == "medium":
                    failed_medium += 1

        # v1 policy: suite is ok only if no failures
        ok = failed == 0

        payload = {
            "version": self.VERSION,
            "generated_at": _utc_iso(),
            "suite_id": suite_id,
            "suite_description": suite.get("description"),
            "when_to_run": suite.get("when_to_run"),
            "ok": ok,
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "failed_high": failed_high,
                "failed_medium": failed_medium,
            },
            "results": results,
        }

        if run_id:
            self.fs.write_run_json(run_id, "verification.json", payload)

        return payload
