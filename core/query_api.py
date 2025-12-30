# core/query_api.py
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass

from core.fs import WorkspaceFS


def _norm(p: str) -> str:
    return (p or "").replace("\\", "/")


def _lc(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _norm_ref(s: Optional[str]) -> Optional[str]:
    """
    Best-effort normalize symbol refs:
      "myapp.models.User" -> "User"
      "User" -> "User"
      "User()" -> "User"
    """
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    if "." in s:
        s = s.split(".")[-1]
    return s.replace("()", "")


@dataclass
class QueryIndex:
    artifacts_by_id: Dict[str, Dict[str, Any]]
    artifacts_by_type: Dict[str, List[Dict[str, Any]]]
    artifacts_by_name: Dict[str, List[Dict[str, Any]]]
    artifacts_by_name_lc: Dict[str, List[Dict[str, Any]]]          # ✅ NEW
    artifacts_by_file: Dict[str, List[Dict[str, Any]]]             # ✅ NEW (normalized)
    rels: List[Dict[str, Any]]
    rels_by_from: Dict[str, List[Dict[str, Any]]]
    rels_by_to: Dict[str, List[Dict[str, Any]]]
    rels_by_from_or_name: Dict[str, List[Dict[str, Any]]]          # ✅ NEW (supports unresolved)
    rels_by_to_or_name: Dict[str, List[Dict[str, Any]]]            # ✅ NEW (supports unresolved)


class CRSQueryAPI:
    """
    Read-only Query API over:
      - state/artifacts.json
      - state/relationships.json

    Keeps your existing methods, and ADDS:
      - find_models(...) / find_serializers(...) / find_views(...) convenience
      - resolve_* helpers (model by name, serializer by name, view by name)
      - trace_route_to_model(..., allow_all_matches=True) returns richer results
      - impacted_by_patch() reads state/impact.json if present
      - graph_walk() BFS traversal with rel_type filtering (no refactor explosion)
    """

    def __init__(self, fs: WorkspaceFS):
        self.fs = fs
        self._idx: Optional[QueryIndex] = None

    # -------------------------
    # Load / index
    # -------------------------
    def load(self, force: bool = False) -> QueryIndex:
        if self._idx is not None and not force:
            return self._idx

        artifacts_payload = self.fs.read_json(self.fs.paths.artifacts_json)
        relationships_payload = self.fs.read_json(self.fs.paths.relationships_json)

        arts = artifacts_payload.get("artifacts") if isinstance(artifacts_payload, dict) and isinstance(artifacts_payload.get("artifacts"), list) else []
        rels = relationships_payload.get("relationships") if isinstance(relationships_payload, dict) and isinstance(relationships_payload.get("relationships"), list) else []

        artifacts_by_id: Dict[str, Dict[str, Any]] = {}
        artifacts_by_type: Dict[str, List[Dict[str, Any]]] = {}
        artifacts_by_name: Dict[str, List[Dict[str, Any]]] = {}
        artifacts_by_name_lc: Dict[str, List[Dict[str, Any]]] = {}
        artifacts_by_file: Dict[str, List[Dict[str, Any]]] = {}

        for a in arts:
            if not isinstance(a, dict):
                continue

            aid = a.get("artifact_id")
            if isinstance(aid, str) and aid:
                artifacts_by_id[aid] = a

            at = str(a.get("type") or "unknown")
            artifacts_by_type.setdefault(at, []).append(a)

            nm = str(a.get("name") or "")
            if nm:
                artifacts_by_name.setdefault(nm, []).append(a)
                artifacts_by_name_lc.setdefault(_lc(nm), []).append(a)

            fp = _norm(str(a.get("file_path") or ""))
            if fp:
                artifacts_by_file.setdefault(fp, []).append(a)

        rels_by_from: Dict[str, List[Dict[str, Any]]] = {}
        rels_by_to: Dict[str, List[Dict[str, Any]]] = {}
        # ✅ include unresolved ends by using "artifact_id OR name" as key
        rels_by_from_or_name: Dict[str, List[Dict[str, Any]]] = {}
        rels_by_to_or_name: Dict[str, List[Dict[str, Any]]] = {}

        for r in rels:
            if not isinstance(r, dict):
                continue
            fr = r.get("from") if isinstance(r.get("from"), dict) else {}
            to = r.get("to") if isinstance(r.get("to"), dict) else {}
            fid = fr.get("artifact_id")
            tid = to.get("artifact_id")

            if isinstance(fid, str) and fid:
                rels_by_from.setdefault(fid, []).append(r)
            if isinstance(tid, str) and tid:
                rels_by_to.setdefault(tid, []).append(r)

            fk = fid if isinstance(fid, str) and fid else (fr.get("name") if isinstance(fr.get("name"), str) else "")
            tk = tid if isinstance(tid, str) and tid else (to.get("name") if isinstance(to.get("name"), str) else "")
            if isinstance(fk, str) and fk:
                rels_by_from_or_name.setdefault(fk, []).append(r)
            if isinstance(tk, str) and tk:
                rels_by_to_or_name.setdefault(tk, []).append(r)

        self._idx = QueryIndex(
            artifacts_by_id=artifacts_by_id,
            artifacts_by_type=artifacts_by_type,
            artifacts_by_name=artifacts_by_name,
            artifacts_by_name_lc=artifacts_by_name_lc,
            artifacts_by_file=artifacts_by_file,
            rels=rels,
            rels_by_from=rels_by_from,
            rels_by_to=rels_by_to,
            rels_by_from_or_name=rels_by_from_or_name,
            rels_by_to_or_name=rels_by_to_or_name,
        )
        return self._idx

    # -------------------------
    # Basic finders
    # -------------------------
    def find_artifacts(
        self,
        *,
        name: Optional[str] = None,
        type: Optional[str] = None,
        file_path: Optional[str] = None,
        contains_name: Optional[str] = None,
        limit: int = 50,
        case_insensitive_name: bool = False,   # ✅ NEW (default False = old behavior)
    ) -> List[Dict[str, Any]]:
        idx = self.load()

        # Start set
        if name:
            if case_insensitive_name:
                cand = list(idx.artifacts_by_name_lc.get(_lc(name), []))
            else:
                cand = list(idx.artifacts_by_name.get(name, []))
        elif type:
            cand = list(idx.artifacts_by_type.get(type, []))
        else:
            cand = list(idx.artifacts_by_id.values())

        fp_norm = _norm(file_path) if file_path else None
        contains = (contains_name or "").strip().lower() if contains_name else None

        out: List[Dict[str, Any]] = []
        for a in cand:
            if not isinstance(a, dict):
                continue

            if type and str(a.get("type")) != type:
                continue

            if fp_norm:
                ap = _norm(str(a.get("file_path") or ""))
                if ap != fp_norm and not ap.endswith(fp_norm):
                    continue

            if contains:
                nm = str(a.get("name") or "").lower()
                if contains not in nm:
                    continue

            out.append(a)
            if len(out) >= max(1, limit):
                break

        return out

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        idx = self.load()
        return idx.artifacts_by_id.get(artifact_id)

    # -------------------------
    # Convenience domain finders (NEW)
    # -------------------------
    def find_models(self, name: Optional[str] = None, *, contains: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        # artifact types must match your extractor
        return self.find_artifacts(name=name, type="django_model" if name else "django_model", contains_name=contains, limit=limit, case_insensitive_name=True)

    def find_serializers(self, name: Optional[str] = None, *, contains: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        return self.find_artifacts(name=name, type="drf_serializer" if name else "drf_serializer", contains_name=contains, limit=limit, case_insensitive_name=True)

    def find_views(self, name: Optional[str] = None, *, contains: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        # include both view kinds
        idx = self.load()
        out: List[Dict[str, Any]] = []
        for t in ("drf_viewset", "drf_apiview"):
            out.extend(self.find_artifacts(name=name, type=t if name else t, contains_name=contains, limit=limit, case_insensitive_name=True))
            if len(out) >= limit:
                return out[:limit]
        return out[:limit]

    def resolve_model(self, name_or_ref: str) -> Optional[Dict[str, Any]]:
        nm = _norm_ref(name_or_ref) or name_or_ref
        matches = self.find_artifacts(name=nm, type="django_model", limit=5, case_insensitive_name=True)
        return matches[0] if matches else None

    def resolve_serializer(self, name_or_ref: str) -> Optional[Dict[str, Any]]:
        nm = _norm_ref(name_or_ref) or name_or_ref
        matches = self.find_artifacts(name=nm, type="drf_serializer", limit=5, case_insensitive_name=True)
        return matches[0] if matches else None

    def resolve_view(self, name_or_ref: str) -> Optional[Dict[str, Any]]:
        nm = _norm_ref(name_or_ref) or name_or_ref
        m = self.find_artifacts(name=nm, type="drf_viewset", limit=5, case_insensitive_name=True)
        if m:
            return m[0]
        m = self.find_artifacts(name=nm, type="drf_apiview", limit=5, case_insensitive_name=True)
        return m[0] if m else None

    # -------------------------
    # Graph navigation
    # -------------------------
    def neighbors(
        self,
        artifact_id: str,
        *,
        rel_types: Optional[List[str]] = None,
        direction: str = "both",  # "out" | "in" | "both"
        limit: int = 200,
        include_unresolved: bool = False,  # ✅ NEW
    ) -> Dict[str, Any]:
        idx = self.load()

        allowed = set(rel_types) if rel_types else None

        if include_unresolved:
            out_rels = idx.rels_by_from_or_name.get(artifact_id, [])
            in_rels = idx.rels_by_to_or_name.get(artifact_id, [])
        else:
            out_rels = idx.rels_by_from.get(artifact_id, [])
            in_rels = idx.rels_by_to.get(artifact_id, [])

        picked: List[Dict[str, Any]] = []
        if direction in ("out", "both"):
            picked.extend(out_rels)
        if direction in ("in", "both"):
            picked.extend(in_rels)

        result_rels: List[Dict[str, Any]] = []
        seen = set()

        for r in picked:
            rid = r.get("rel_id")
            if isinstance(rid, str) and rid in seen:
                continue
            if allowed is not None and str(r.get("type") or "") not in allowed:
                continue
            if isinstance(rid, str):
                seen.add(rid)
            result_rels.append(r)
            if len(result_rels) >= max(1, limit):
                break

        # Neighbor artifacts (resolved only)
        neighbor_ids: Set[str] = set()
        unresolved_ends: List[Dict[str, Any]] = []

        for r in result_rels:
            fr = r.get("from") if isinstance(r.get("from"), dict) else {}
            to = r.get("to") if isinstance(r.get("to"), dict) else {}
            fid = fr.get("artifact_id")
            tid = to.get("artifact_id")

            if isinstance(fid, str) and fid:
                neighbor_ids.add(fid)
            elif include_unresolved and isinstance(fr.get("name"), str) and fr.get("name"):
                unresolved_ends.append({"end": "from", "name": fr.get("name"), "type": fr.get("type")})

            if isinstance(tid, str) and tid:
                neighbor_ids.add(tid)
            elif include_unresolved and isinstance(to.get("name"), str) and to.get("name"):
                unresolved_ends.append({"end": "to", "name": to.get("name"), "type": to.get("type")})

        neighbor_ids.discard(artifact_id)

        neighbors_list = []
        for nid in neighbor_ids:
            a = idx.artifacts_by_id.get(nid)
            if a:
                neighbors_list.append(a)

        return {
            "artifact_id": artifact_id,
            "relationships": result_rels,
            "neighbors": neighbors_list,
            "unresolved": unresolved_ends if include_unresolved else [],
        }

    def graph_walk(
        self,
        start_artifact_id: str,
        *,
        rel_types: Optional[List[str]] = None,
        max_nodes: int = 500,
        direction: str = "out",          # out|in|both
    ) -> Dict[str, Any]:
        """
        BFS walk over relationships (by artifact_id only; unresolved ignored).
        Useful for quick "what does this touch?" queries.
        """
        idx = self.load()
        allowed = set(rel_types) if rel_types else None

        seen: Set[str] = set()
        q: List[str] = [start_artifact_id]
        seen.add(start_artifact_id)

        edges: List[Dict[str, Any]] = []

        while q and len(seen) < max_nodes:
            cur = q.pop(0)

            rels_out = idx.rels_by_from.get(cur, []) if direction in ("out", "both") else []
            rels_in = idx.rels_by_to.get(cur, []) if direction in ("in", "both") else []

            for r in rels_out + rels_in:
                if not isinstance(r, dict):
                    continue
                if allowed is not None and str(r.get("type") or "") not in allowed:
                    continue

                fr = r.get("from") if isinstance(r.get("from"), dict) else {}
                to = r.get("to") if isinstance(r.get("to"), dict) else {}
                fid = fr.get("artifact_id")
                tid = to.get("artifact_id")
                if not isinstance(fid, str) or not isinstance(tid, str):
                    continue

                edges.append({"rel_id": r.get("rel_id"), "type": r.get("type"), "from": fid, "to": tid})

                nxt = tid if fid == cur else fid
                if isinstance(nxt, str) and nxt and nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)

        nodes = [idx.artifacts_by_id.get(aid) for aid in seen if aid in idx.artifacts_by_id]
        nodes = [n for n in nodes if isinstance(n, dict)]

        return {"start": start_artifact_id, "nodes_count": len(nodes), "nodes": nodes, "edges": edges}

    # -------------------------
    # Useful traces
    # -------------------------
    def trace_route_to_model(self, route: str, *, allow_all_matches: bool = False) -> Dict[str, Any]:
        """
        Best-effort trace:
          url_pattern(route) -> view -> serializer -> model
        Uses relationship types you already produce:
          routes_to, view_uses_serializer, serializes_model

        NEW:
          - allow_all_matches=True returns all matching url_patterns (and traces for each)
        """
        idx = self.load()
        route = (route or "").strip()

        url_patterns = idx.artifacts_by_type.get("url_pattern", [])
        matches: List[Dict[str, Any]] = []
        for a in url_patterns:
            if not isinstance(a, dict):
                continue
            if str(a.get("name") or "") == route:
                matches.append(a)
                continue
            meta = a.get("meta") if isinstance(a.get("meta"), dict) else {}
            if str(meta.get("route") or "") == route:
                matches.append(a)

        if not matches:
            return {"route": route, "found": False, "reason": "no url_pattern matched"}

        def _trace_one(url_art: Dict[str, Any]) -> Dict[str, Any]:
            url_id = url_art.get("artifact_id")
            if not isinstance(url_id, str):
                return {"found": False, "reason": "url_pattern missing artifact_id", "url_pattern": url_art}

            url_neighbors = self.neighbors(url_id, rel_types=["routes_to"], direction="out")
            views = url_neighbors.get("neighbors") or []
            if not views:
                return {"found": True, "url_pattern": url_art, "reason": "no routes_to edge"}

            view = views[0]
            view_id = view.get("artifact_id")

            ser = None
            if isinstance(view_id, str):
                view_neighbors = self.neighbors(view_id, rel_types=["view_uses_serializer"], direction="out", include_unresolved=True)
                serializers = view_neighbors.get("neighbors") or []
                if serializers:
                    ser = serializers[0]

            if not ser:
                return {"found": True, "url_pattern": url_art, "view": view, "reason": "no serializer link"}

            ser_id = ser.get("artifact_id")

            model = None
            if isinstance(ser_id, str):
                ser_neighbors = self.neighbors(ser_id, rel_types=["serializes_model"], direction="out", include_unresolved=True)
                models = ser_neighbors.get("neighbors") or []
                if models:
                    model = models[0]

            return {"found": True, "url_pattern": url_art, "view": view, "serializer": ser, "model": model}

        if allow_all_matches:
            traces = [_trace_one(m) for m in matches]
            return {"route": route, "found": True, "matches": len(matches), "traces": traces}

        return {
            "route": route,
            "found": True,
            **_trace_one(matches[0]),
        }

    # -------------------------
    # Impact convenience (NEW)
    # -------------------------
    def impacted_by_patch(self) -> Dict[str, Any]:
        """
        Reads state/impact.json (latest) if it exists.
        This keeps query layer read-only and avoids coupling to ImpactEngine.
        """
        latest = _norm(self.fs.paths.state_dir) + "/impact.json"
        abs_path = self.fs.paths.state_dir + os.sep + "impact.json"  # keep it simple / platform safe
        try:
            if self.fs.backend.exists(abs_path):
                obj = self.fs.read_json(abs_path)
                return obj if isinstance(obj, dict) else {"found": False, "reason": "impact.json invalid"}
        except Exception as e:
            return {"found": False, "reason": f"failed to read impact.json: {type(e).__name__}: {e}"}
        return {"found": False, "reason": "impact.json not found"}
