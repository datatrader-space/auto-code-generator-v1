# core/query_runner.py
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from core.fs import WorkspaceFS
from core.query_api import CRSQueryAPI
from typing import Callable
# Optional integration (non-fatal if file not present in older workspaces)
try:
    from core.spec_store import SpecStore
except Exception:  # pragma: no cover
    SpecStore = None  # type: ignore


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _norm(s: str) -> str:
    return (s or "").replace("\\", "/").strip()


def _lower(s: str) -> str:
    return (s or "").strip().lower()


def _norm_ref(s: Optional[str]) -> Optional[str]:
    """
    Best-effort normalize:
      "myapp.models.User" -> "User"
      "User" -> "User"
    """
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    if "." in s:
        s = s.split(".")[-1]
    return s.replace("()", "")


# Optional: keep type strings in one place for callers
A_PARSE_ERROR = "parse_error"
A_DJANGO_MODEL = "django_model"
A_MODEL_FIELD = "model_field"
A_DRF_SERIALIZER = "drf_serializer"
A_SERIALIZER_FIELD = "serializer_field"
A_SERIALIZER_VALIDATOR = "serializer_validator"
A_DRF_VIEWSET = "drf_viewset"
A_DRF_APIVIEW = "drf_apiview"
A_URL_PATTERN = "url_pattern"
A_ROUTER_REGISTER = "router_register"

UNRESOLVED_TYPE = "unresolved_ref"


@dataclass
class TraceResult:
    found: bool
    reason: Optional[str]
    chain: Dict[str, Optional[Dict[str, Any]]]  # url_pattern/view/serializer/model
    relationships: List[Dict[str, Any]]


class CRSQueryRunner:
    """
    CRS Query Runner (v1)
    ---------------------
    A single usable class that exposes "all the practical queries":

    Core graph:
      - find_artifacts()
      - get_artifact()
      - neighbors()

    Traces:
      - trace_route_to_model(route)
      - trace_model_to_routes(model_name_or_id)

    Model helpers:
      - find_models()
      - find_model(name_contains or exact)
      - get_model_fields(model_artifact_id or model_name)

    Impact helpers (reads outputs from ImpactEngine):
      - load_latest_impact()
      - load_impact(patch_id)
      - impact_affected_artifacts()
      - impact_invalidated_relationships()

    Extra utilities (added):
      - list_unresolved_refs()
      - serializers_for_model()
      - views_for_serializer()
      - routes_for_view()
      - explain_artifact_type() / explain_relationship_type() (via SpecStore if present)

    This is read-only. It does not mutate workspace.
    """

    VERSION = "crs-query-runner-v1"

    def __init__(self, fs: WorkspaceFS):
        self.fs = fs
        self.api = CRSQueryAPI(fs)
        self._spec = None
        if SpecStore is not None:
            try:
                self._spec = SpecStore(fs)
            except Exception:
                self._spec = None

    # -------------------------
    # Internal resolvers (CRITICAL FIX)
    # -------------------------
    def _resolve_artifact(self, maybe_id_or_name: str, *, type_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Resolve by:
          1) artifact_id exact lookup
          2) (optional) type+name exact match
          3) (optional) type+contains match
        """
        s = (maybe_id_or_name or "").strip()
        if not s:
            return None

        # 1) artifact_id direct
        a = self.get_artifact(s)
        if a:
            if type_hint and str(a.get("type") or "") != type_hint:
                # if caller insists on type and id points to other type, treat as not found
                return None
            return a

        # 2) name resolution
        if type_hint:
            exact = self.find_artifacts(type=type_hint, name=s, limit=5)
            if exact:
                return exact[0]

            # allow normalized ref match
            s2 = _norm_ref(s)
            if s2 and s2 != s:
                exact2 = self.find_artifacts(type=type_hint, name=s2, limit=5)
                if exact2:
                    return exact2[0]

            contains = self.find_artifacts(type=type_hint, contains_name=s, limit=5)
            if contains:
                return contains[0]

        # fallback any-type contains
        any_hit = self.find_artifacts(contains_name=s, limit=5)
        if any_hit:
            return any_hit[0]
        return None

    def _resolve_model(self, model: str) -> Optional[Dict[str, Any]]:
        return self._resolve_artifact(model, type_hint=A_DJANGO_MODEL)

    def _resolve_serializer(self, serializer: str) -> Optional[Dict[str, Any]]:
        return self._resolve_artifact(serializer, type_hint=A_DRF_SERIALIZER)

    def _resolve_view(self, view: str) -> Optional[Dict[str, Any]]:
        # view could be viewset or apiview
        a = self.get_artifact(view)
        if a and a.get("type") in (A_DRF_VIEWSET, A_DRF_APIVIEW):
            return a
        # try both types by name
        hit = self.find_artifacts(type=A_DRF_VIEWSET, name=view, limit=3)
        if hit:
            return hit[0]
        hit = self.find_artifacts(type=A_DRF_APIVIEW, name=view, limit=3)
        if hit:
            return hit[0]
        # contains fallback
        hit = self.find_artifacts(type=A_DRF_VIEWSET, contains_name=view, limit=3)
        if hit:
            return hit[0]
        hit = self.find_artifacts(type=A_DRF_APIVIEW, contains_name=view, limit=3)
        if hit:
            return hit[0]
        return None

    # -------------------------
    # Index helpers
    # -------------------------
    def load(self, force: bool = False) -> Dict[str, Any]:
        """
        Loads/refreshes the underlying CRSQueryAPI index.
        """
        idx = self.api.load(force=force)
        return {
            "version": self.VERSION,
            "generated_at": _utc_iso(),
            "artifacts": len(idx.artifacts_by_id),
            "relationships": len(idx.rels),
            "artifact_types": {k: len(v) for k, v in idx.artifacts_by_type.items()},
        }

    def stats(self) -> Dict[str, Any]:
        """
        Quick stats snapshot.
        """
        idx = self.api.load()
        return {
            "artifacts": len(idx.artifacts_by_id),
            "relationships": len(idx.rels),
            "artifact_types": {k: len(v) for k, v in idx.artifacts_by_type.items()},
        }

    # -------------------------
    # Basic finders (wrapper)
    # -------------------------
    def find_artifacts(
        self,
        *,
        name: Optional[str] = None,
        type: Optional[str] = None,
        file_path: Optional[str] = None,
        contains_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return self.api.find_artifacts(
            name=name,
            type=type,
            file_path=file_path,
            contains_name=contains_name,
            limit=limit,
        )

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        return self.api.get_artifact(artifact_id)

    def neighbors(
        self,
        artifact_id: str,
        *,
        rel_types: Optional[List[str]] = None,
        direction: str = "both",
        limit: int = 200,
    ) -> Dict[str, Any]:
        return self.api.neighbors(
            artifact_id,
            rel_types=rel_types,
            direction=direction,
            limit=limit,
        )

    # -------------------------
    # Model helpers
    # -------------------------
    def find_models(self, *, contains: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Find Django models quickly.
        """
        if contains:
            return self.find_artifacts(type=A_DJANGO_MODEL, contains_name=contains, limit=limit)
        return self.find_artifacts(type=A_DJANGO_MODEL, limit=limit)

    def find_model(self, model_name: str) -> Optional[Dict[str, Any]]:
        """
        Best-effort find model by:
          1) artifact_id direct
          2) exact name match
          3) normalized exact name match
          4) contains_name match
        """
        return self._resolve_model(model_name)

    def get_model_fields(self, model: str, *, include_field_artifacts: bool = True) -> Dict[str, Any]:
        """
        Get fields for a model.
        model can be:
          - model artifact_id (recommended)
          - model class name ("User")
          - fully qualified ("myapp.models.User")
        """
        model_art = self._resolve_model(model)
        if not model_art:
            return {"found": False, "reason": "model not found", "model": model, "fields": []}

        meta = model_art.get("meta") if isinstance(model_art.get("meta"), dict) else {}
        summary_fields = meta.get("fields") if isinstance(meta.get("fields"), list) else []

        field_arts: List[Dict[str, Any]] = []
        if include_field_artifacts:
            mid = model_art.get("artifact_id")
            if isinstance(mid, str) and mid:
                nb = self.neighbors(mid, rel_types=["declares"], direction="out", limit=2000)
                for a in (nb.get("neighbors") or []):
                    if isinstance(a, dict) and a.get("type") == A_MODEL_FIELD:
                        field_arts.append(a)

        return {
            "found": True,
            "model": model_art,
            "fields_summary": summary_fields,
            "fields": field_arts,
        }

    # -------------------------
    # Forward trace: route -> view -> serializer -> model
    # -------------------------
    def trace_route_to_model(self, route: str) -> Dict[str, Any]:
        """
        Wrapper around CRSQueryAPI.trace_route_to_model, but also returns relationships used.
        """
        result = self.api.trace_route_to_model(route)
        if not isinstance(result, dict):
            return {"route": route, "found": False, "reason": "trace returned invalid result"}

        if not result.get("found"):
            return result

        used_rels: List[Dict[str, Any]] = []

        def _collect_edge(from_art: Optional[Dict[str, Any]], rel_type: str) -> None:
            if not isinstance(from_art, dict):
                return
            aid = from_art.get("artifact_id")
            if not isinstance(aid, str) or not aid:
                return
            nb = self.neighbors(aid, rel_types=[rel_type], direction="out", limit=50)
            for r in nb.get("relationships") or []:
                if isinstance(r, dict) and str(r.get("type")) == rel_type:
                    used_rels.append(r)

        _collect_edge(result.get("url_pattern"), "routes_to")
        _collect_edge(result.get("view"), "view_uses_serializer")
        _collect_edge(result.get("serializer"), "serializes_model")

        return {**result, "relationships_used": used_rels}

    # -------------------------
    # Reverse trace: model -> serializers -> views -> routes
    # -------------------------
    def trace_model_to_routes(self, model_name_or_id: str, *, limit: int = 50) -> Dict[str, Any]:
        """
        Reverse trace:
          model <- serializes_model - serializer <- view_uses_serializer - view <- routes_to - url_pattern
        Returns multiple possible routes.
        """
        model_art = self._resolve_model(model_name_or_id)
        if not model_art:
            return {"found": False, "reason": "model not found", "model": model_name_or_id, "routes": []}

        model_id = model_art.get("artifact_id")
        if not isinstance(model_id, str) or not model_id:
            return {"found": False, "reason": "model missing artifact_id", "model": model_art, "routes": []}

        ser_rels = self.neighbors(model_id, rel_types=["serializes_model"], direction="in", limit=5000)
        serializers = [a for a in (ser_rels.get("neighbors") or []) if isinstance(a, dict) and a.get("type") == A_DRF_SERIALIZER]

        routes_out: List[Dict[str, Any]] = []

        for ser in serializers:
            ser_id = ser.get("artifact_id")
            if not isinstance(ser_id, str) or not ser_id:
                continue

            view_rels = self.neighbors(ser_id, rel_types=["view_uses_serializer"], direction="in", limit=5000)
            views = [a for a in (view_rels.get("neighbors") or []) if isinstance(a, dict) and a.get("type") in (A_DRF_VIEWSET, A_DRF_APIVIEW)]

            for view in views:
                view_id = view.get("artifact_id")
                if not isinstance(view_id, str) or not view_id:
                    continue

                url_rels = self.neighbors(view_id, rel_types=["routes_to"], direction="in", limit=5000)
                url_patterns = [a for a in (url_rels.get("neighbors") or []) if isinstance(a, dict) and a.get("type") == A_URL_PATTERN]

                for up in url_patterns:
                    meta = up.get("meta") if isinstance(up.get("meta"), dict) else {}
                    routes_out.append(
                        {
                            "route": meta.get("route") or up.get("name"),
                            "url_pattern": up,
                            "view": view,
                            "serializer": ser,
                            "model": model_art,
                        }
                    )
                    if len(routes_out) >= max(1, limit):
                        return {"found": True, "model": model_art, "routes": routes_out}

        return {"found": True, "model": model_art, "routes": routes_out}

    # -------------------------
    # New: “graph convenience” helpers
    # -------------------------
    def serializers_for_model(self, model: str, *, limit: int = 200) -> Dict[str, Any]:
        model_art = self._resolve_model(model)
        if not model_art:
            return {"found": False, "reason": "model not found", "model": model, "serializers": []}
        mid = model_art.get("artifact_id")
        if not isinstance(mid, str) or not mid:
            return {"found": False, "reason": "model missing artifact_id", "model": model_art, "serializers": []}

        nb = self.neighbors(mid, rel_types=["serializes_model"], direction="in", limit=5000)
        serializers = [a for a in (nb.get("neighbors") or []) if isinstance(a, dict) and a.get("type") == A_DRF_SERIALIZER]
        return {"found": True, "model": model_art, "serializers": serializers[: max(1, limit)]}

    def views_for_serializer(self, serializer: str, *, limit: int = 200) -> Dict[str, Any]:
        ser_art = self._resolve_serializer(serializer)
        if not ser_art:
            return {"found": False, "reason": "serializer not found", "serializer": serializer, "views": []}
        sid = ser_art.get("artifact_id")
        if not isinstance(sid, str) or not sid:
            return {"found": False, "reason": "serializer missing artifact_id", "serializer": ser_art, "views": []}

        nb = self.neighbors(sid, rel_types=["view_uses_serializer"], direction="in", limit=5000)
        views = [a for a in (nb.get("neighbors") or []) if isinstance(a, dict) and a.get("type") in (A_DRF_VIEWSET, A_DRF_APIVIEW)]
        return {"found": True, "serializer": ser_art, "views": views[: max(1, limit)]}

    def routes_for_view(self, view: str, *, limit: int = 200) -> Dict[str, Any]:
        view_art = self._resolve_view(view)
        if not view_art:
            return {"found": False, "reason": "view not found", "view": view, "routes": []}
        vid = view_art.get("artifact_id")
        if not isinstance(vid, str) or not vid:
            return {"found": False, "reason": "view missing artifact_id", "view": view_art, "routes": []}

        nb = self.neighbors(vid, rel_types=["routes_to"], direction="in", limit=5000)
        url_patterns = [a for a in (nb.get("neighbors") or []) if isinstance(a, dict) and a.get("type") == A_URL_PATTERN]

        out = []
        for up in url_patterns:
            meta = up.get("meta") if isinstance(up.get("meta"), dict) else {}
            out.append({"route": meta.get("route") or up.get("name"), "url_pattern": up})
            if len(out) >= max(1, limit):
                break
        return {"found": True, "view": view_art, "routes": out}

    def list_unresolved_refs(self, *, limit: int = 200) -> Dict[str, Any]:
        """
        Find unresolved edges:
          - relationship.to.type == unresolved_ref OR relationship.from.type == unresolved_ref
          - or missing artifact_id on an endpoint
        """
        idx = self.api.load()
        out: List[Dict[str, Any]] = []

        for r in idx.rels:
            if not isinstance(r, dict):
                continue
            fr = r.get("from") if isinstance(r.get("from"), dict) else {}
            to = r.get("to") if isinstance(r.get("to"), dict) else {}

            fr_type = str(fr.get("type") or "")
            to_type = str(to.get("type") or "")

            fr_id = fr.get("artifact_id")
            to_id = to.get("artifact_id")

            unresolved = (
                fr_type == UNRESOLVED_TYPE
                or to_type == UNRESOLVED_TYPE
                or (fr_id is None and fr_type != "")
                or (to_id is None and to_type != "")
            )
            if not unresolved:
                continue

            out.append(
                {
                    "rel_id": r.get("rel_id"),
                    "type": r.get("type"),
                    "from": fr,
                    "to": to,
                    "evidence": r.get("evidence"),
                    "meta": r.get("meta"),
                }
            )
            if len(out) >= max(1, limit):
                break

        return {"count": len(out), "unresolved": out}

    # -------------------------
    # Impact queries (read output of ImpactEngine)
    # -------------------------
    def _impact_dir(self) -> str:
        return os.path.join(self.fs.paths.state_dir, "impact")

    def load_impact(self, patch_id: str) -> Optional[Dict[str, Any]]:
        patch_id = (patch_id or "").strip()
        if not patch_id:
            return None
        p = os.path.join(self._impact_dir(), f"impact_{patch_id}.json")
        if not self.fs.backend.exists(p):
            return None
        obj = self.fs.read_json(p)
        return obj if isinstance(obj, dict) else None

    def load_latest_impact(self) -> Optional[Dict[str, Any]]:
        """
        Best-effort latest impact file by filesystem mtime.
        (LocalDiskBackend assumed; for cloud backends, this will be replaced later.)
        """
        d = self._impact_dir()
        if not os.path.isdir(d):
            return None

        best_path = None
        best_mtime = -1.0
        try:
            for fn in os.listdir(d):
                if not fn.startswith("impact_") or not fn.endswith(".json"):
                    continue
                ap = os.path.join(d, fn)
                try:
                    mt = os.path.getmtime(ap)
                except Exception:
                    continue
                if mt > best_mtime:
                    best_mtime = mt
                    best_path = ap
        except Exception:
            return None

        if not best_path or not self.fs.backend.exists(best_path):
            return None

        obj = self.fs.read_json(best_path)
        return obj if isinstance(obj, dict) else None

    def impact_affected_artifacts(self, impact: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(impact, dict):
            return []
        aa = impact.get("affected_artifacts") if isinstance(impact.get("affected_artifacts"), dict) else {}
        arts = aa.get("artifacts") if isinstance(aa.get("artifacts"), list) else []
        return [a for a in arts if isinstance(a, dict)]

    def impact_invalidated_relationships(self, impact: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(impact, dict):
            return []
        ir = impact.get("invalidated_relationships") if isinstance(impact.get("invalidated_relationships"), dict) else {}
        rels = ir.get("relationships") if isinstance(ir.get("relationships"), list) else []
        return [r for r in rels if isinstance(r, dict)]

    # -------------------------
    # SpecStore explainers (optional but powerful now)
    # -------------------------
    def explain_artifact_type(self, artifact_type: str) -> Dict[str, Any]:
        """
        Returns the spec entry for an artifact type from state/specs/artifact_types.json.
        Non-fatal if SpecStore isn't present.
        """
        if self._spec is None:
            return {"found": False, "reason": "SpecStore not available", "artifact_type": artifact_type}

        try:
            types = self._spec.load_artifact_type_specs()
        except Exception as e:
            return {"found": False, "reason": f"SpecStore read failed: {type(e).__name__}: {e}", "artifact_type": artifact_type}

        at = str(artifact_type or "").strip()
        for t in types:
            if isinstance(t, dict) and str(t.get("type") or "") == at:
                return {"found": True, "artifact_type": at, "spec": t}
        return {"found": False, "artifact_type": at, "reason": "no spec matched"}

    def explain_relationship_type(self, rel_type: str) -> Dict[str, Any]:
        """
        Returns the spec entry for a relationship type from state/specs/relationship_types.json.
        """
        if self._spec is None:
            return {"found": False, "reason": "SpecStore not available", "relationship_type": rel_type}

        try:
            rels = self._spec.load_relationship_type_specs()
        except Exception as e:
            return {"found": False, "reason": f"SpecStore read failed: {type(e).__name__}: {e}", "relationship_type": rel_type}

        rt = str(rel_type or "").strip()
        for r in rels:
            if isinstance(r, dict) and str(r.get("type") or "") == rt:
                return {"found": True, "relationship_type": rt, "spec": r}
        return {"found": False, "relationship_type": rt, "reason": "no spec matched"}

    # -------------------------
    # “One-call” user operations
    # -------------------------
    def find_endpoint_for_route(self, route: str) -> Dict[str, Any]:
        """
        Alias: route -> view -> serializer -> model
        This is what real users want most.
        """
        return self.trace_route_to_model(route)

    def find_routes_for_model(self, model_name: str, *, limit: int = 50) -> Dict[str, Any]:
        """
        Alias: model -> routes
        """
        return self.trace_model_to_routes(model_name, limit=limit)

    def search(self, q: str, *, limit: int = 50) -> Dict[str, Any]:
        """
        Simple "search box" behavior:
          - search models, serializers, views, url patterns by contains_name
        """
        q = (q or "").strip()
        if not q:
            return {"query": q, "results": []}

        priority_types = [A_DJANGO_MODEL, A_DRF_SERIALIZER, A_DRF_VIEWSET, A_DRF_APIVIEW, A_URL_PATTERN]
        results: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        for t in priority_types:
            found = self.find_artifacts(type=t, contains_name=q, limit=limit)
            for a in found:
                aid = a.get("artifact_id")
                if isinstance(aid, str) and aid in seen:
                    continue
                if isinstance(aid, str):
                    seen.add(aid)
                results.append(a)
                if len(results) >= max(1, limit):
                    return {"query": q, "results": results}

        found = self.find_artifacts(contains_name=q, limit=limit)
        for a in found:
            aid = a.get("artifact_id")
            if isinstance(aid, str) and aid in seen:
                continue
            if isinstance(aid, str):
                seen.add(aid)
            results.append(a)
            if len(results) >= max(1, limit):
                break

        return {"query": q, "results": results}


    from typing import Callable


    # -------------------------
    def ops(self) -> Dict[str, Any]:
        """
        Returns a machine-readable list of supported operations for agents/UIs.
        """
        return {
            "version": self.VERSION,
            "operations": [
                # core
                {"op": "load", "args": {"force": "bool"}, "returns": "dict"},
                {"op": "stats", "args": {}, "returns": "dict"},
                {"op": "find_artifacts", "args": {"name": "str?", "type": "str?", "file_path": "str?", "contains_name": "str?", "limit": "int"}, "returns": "list[artifact]"},
                {"op": "get_artifact", "args": {"artifact_id": "str"}, "returns": "artifact?"},
                {"op": "neighbors", "args": {"artifact_id": "str", "rel_types": "list[str]?", "direction": "out|in|both", "limit": "int"}, "returns": "dict"},
                # traces
                {"op": "trace_route_to_model", "args": {"route": "str"}, "returns": "dict"},
                {"op": "trace_model_to_routes", "args": {"model_name_or_id": "str", "limit": "int"}, "returns": "dict"},
                # model helpers
                {"op": "find_models", "args": {"contains": "str?", "limit": "int"}, "returns": "list[artifact]"},
                {"op": "find_model", "args": {"model_name": "str"}, "returns": "artifact?"},
                {"op": "get_model_fields", "args": {"model": "str", "include_field_artifacts": "bool"}, "returns": "dict"},
                # impact helpers
                {"op": "load_latest_impact", "args": {}, "returns": "impact?"},
                {"op": "load_impact", "args": {"patch_id": "str"}, "returns": "impact?"},
                {"op": "impact_affected_artifacts", "args": {"impact": "impact"}, "returns": "list[artifact]"},
                {"op": "impact_invalidated_relationships", "args": {"impact": "impact"}, "returns": "list[relationship]"},
                # one-call aliases
                {"op": "find_endpoint_for_route", "args": {"route": "str"}, "returns": "dict"},
                {"op": "find_routes_for_model", "args": {"model_name": "str", "limit": "int"}, "returns": "dict"},
                {"op": "search", "args": {"q": "str", "limit": "int"}, "returns": "dict"}
            ],
        }

    def run_op(self, op: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generic operation runner for agents.

        Example:
          runner.run_op("trace_route_to_model", {"route": "/api/users/"})

        Returns:
          {"ok": bool, "op": str, "args": dict, "result": any, "error": str?}
        """
        op = (op or "").strip()
        args = args if isinstance(args, dict) else {}

        dispatch: Dict[str, Callable[..., Any]] = {
            "load": self.load,
            "stats": self.stats,
            "find_artifacts": self.find_artifacts,
            "get_artifact": self.get_artifact,
            "neighbors": self.neighbors,
            "trace_route_to_model": self.trace_route_to_model,
            "trace_model_to_routes": self.trace_model_to_routes,
            "find_models": self.find_models,
            "find_model": self.find_model,
            "get_model_fields": self.get_model_fields,
            "load_latest_impact": self.load_latest_impact,
            "load_impact": self.load_impact,
            "impact_affected_artifacts": self.impact_affected_artifacts,
            "impact_invalidated_relationships": self.impact_invalidated_relationships,
            "find_endpoint_for_route": self.find_endpoint_for_route,
            "find_routes_for_model": self.find_routes_for_model,
            "search": self.search,
        }

        fn = dispatch.get(op)
        if fn is None:
            return {
                "ok": False,
                "op": op,
                "args": args,
                "error": f"unknown op: {op}. call ops() to list supported operations.",
            }

        try:
            result = fn(**args) if args else fn()
            return {"ok": True, "op": op, "args": args, "result": result}
        except TypeError as e:
            # common for wrong args
            return {"ok": False, "op": op, "args": args, "error": f"TypeError: {e}"}
        except Exception as e:
            return {"ok": False, "op": op, "args": args, "error": f"{type(e).__name__}: {e}"}

    def run_ops(self, ops: List[Dict[str, Any]], *, stop_on_error: bool = False) -> Dict[str, Any]:
        """
        Batch runner: executes a list of {"op": "...", "args": {...}}.
        Returns a list of results plus a summary.
        """
        ops = ops if isinstance(ops, list) else []
        results: List[Dict[str, Any]] = []
        ok_count = 0
        err_count = 0

        for item in ops:
            if not isinstance(item, dict):
                continue
            op = item.get("op")
            args = item.get("args") if isinstance(item.get("args"), dict) else {}
            r = self.run_op(str(op or ""), args)
            results.append(r)
            if r.get("ok"):
                ok_count += 1
            else:
                err_count += 1
                if stop_on_error:
                    break

        return {
            "ok": err_count == 0,
            "summary": {"total": len(results), "ok": ok_count, "errors": err_count},
            "results": results,
        }

    def explain_artifact(self, artifact_id: str) -> Dict[str, Any]:
        """
        AI-friendly helper:
          - returns artifact
          - returns immediate neighbors (in/out/both)
          - returns a compact 'signature' view for prompting/patch planning
        """
        art = self.get_artifact(artifact_id)
        if not isinstance(art, dict):
            return {"found": False, "reason": "artifact not found", "artifact_id": artifact_id}

        nb_out = self.neighbors(artifact_id, direction="out", limit=200)
        nb_in = self.neighbors(artifact_id, direction="in", limit=200)

        sig = {
            "artifact_id": art.get("artifact_id"),
            "type": art.get("type"),
            "name": art.get("name"),
            "file_path": art.get("file_path"),
            "anchor": art.get("anchor"),
            "meta_keys": sorted(list((art.get("meta") or {}).keys())) if isinstance(art.get("meta"), dict) else [],
        }

        return {
            "found": True,
            "artifact": art,
            "signature": sig,
            "neighbors_out": {"relationships": nb_out.get("relationships"), "neighbors": nb_out.get("neighbors")},
            "neighbors_in": {"relationships": nb_in.get("relationships"), "neighbors": nb_in.get("neighbors")},
        }

    # ADD AT BOTTOM of CRSQueryRunner

    # -------------------------
    # Verification wrappers
    # -------------------------
    def run_verification_suite(
        self,
        suite_id: str,
        *,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        from core.verification_engine import VerificationEngine

        ve = VerificationEngine(self.fs)
        return ve.run_suite(suite_id, run_id=run_id)

    def load_last_verification(self, run_id: str) -> Optional[Dict[str, Any]]:
        try:
            return self.fs.read_json(self.fs.run_path(run_id, "verification.json"))
        except Exception:
            return None
