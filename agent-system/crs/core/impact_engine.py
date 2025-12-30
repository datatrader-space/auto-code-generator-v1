# core/impact_engine.py
import os
import time
import json
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from core.fs import WorkspaceFS


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _norm(p: str) -> str:
    return (p or "").replace("\\", "/")


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _anchor_range(anchor: Dict[str, Any]) -> Tuple[int, int]:
    sl = _safe_int(anchor.get("start_line"), 1)
    el = _safe_int(anchor.get("end_line"), sl)
    if el < sl:
        el = sl
    return sl, el


def _ranges_overlap(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    # inclusive ranges
    return not (a[1] < b[0] or b[1] < a[0])


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _sha1_json(obj: Any) -> str:
    try:
        raw = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8", errors="replace")
    except Exception:
        raw = repr(obj).encode("utf-8", errors="replace")
    h = hashlib.sha1()
    h.update(raw)
    return h.hexdigest()


def _index_by_id(items: Any, id_key: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        k = it.get(id_key)
        if isinstance(k, str) and k:
            out[k] = it
    return out


def _build_adj(rels: List[Dict[str, Any]]) -> Dict[str, List[Tuple[str, str]]]:
    """
    adjacency[from_artifact_id_or_name] -> [(to_artifact_id_or_name, rel_type)]
    Keeps unresolved ends as name keys.
    """
    adj: Dict[str, List[Tuple[str, str]]] = {}
    for r in rels:
        if not isinstance(r, dict):
            continue
        rt = str(r.get("type") or "unknown")
        f = r.get("from") if isinstance(r.get("from"), dict) else {}
        t = r.get("to") if isinstance(r.get("to"), dict) else {}
        f_id = f.get("artifact_id") or f.get("name")
        t_id = t.get("artifact_id") or t.get("name")
        if not isinstance(f_id, str) or not f_id:
            continue
        if not isinstance(t_id, str) or not t_id:
            continue
        adj.setdefault(f_id, []).append((t_id, rt))
    return adj


def _bfs_downstream(
    adj: Dict[str, List[Tuple[str, str]]],
    start: List[str],
    max_nodes: int = 5000,
    max_path_len: int = 12,
    sample_paths: int = 25,
) -> Dict[str, Any]:
    seen: Set[str] = set()
    q: List[str] = []
    parent: Dict[str, Tuple[str, str]] = {}  # node -> (parent, rel_type)

    for s in start:
        if isinstance(s, str) and s:
            if s not in seen:
                seen.add(s)
                q.append(s)

    while q and len(seen) < max_nodes:
        cur = q.pop(0)
        for nxt, rt in adj.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                parent[nxt] = (cur, rt)
                q.append(nxt)

    def _path_to(node: str) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        cur = node
        steps = 0
        while cur in parent and steps < max_path_len:
            p, rt = parent[cur]
            out.append({"from": p, "to": cur, "type": rt})
            cur = p
            steps += 1
        out.reverse()
        return out

    nodes = sorted(seen)
    sample = nodes[: min(sample_paths, len(nodes))]
    return {
        "impacted_nodes_count": len(nodes),
        "impacted_nodes": nodes,
        "sample_paths": [{"to": n, "path": _path_to(n)} for n in sample],
        "limits": {"max_nodes": max_nodes, "max_path_len": max_path_len, "sample_paths": sample_paths},
    }


@dataclass
class ImpactResult:
    version: str
    generated_at: str
    patch_id: str
    changed_files: List[str]
    affected_blueprints: Dict[str, Any]
    affected_artifacts: Dict[str, Any]
    invalidated_relationships: Dict[str, Any]
    summary: Dict[str, Any]


class ImpactEngine:
    """
    Patch Impact Engine (v1)
    -----------------------
    Keeps your current behavior (file/range -> affected artifacts -> invalidated relationships)
    and ADDS (without breaking existing output):
      - affected_graph: downstream impacted nodes via current relationships
      - optional snapshot bookkeeping (latest snapshots) for debug-friendly diffs
      - writes a canonical "state/impact.json" (latest) in addition to "state/impact/impact_<patch>.json"
    """

    VERSION = "crs-impact-v1"

    def __init__(self, fs: WorkspaceFS):
        self.fs = fs
        self.cfg = fs.get_cfg() or {}

    # ---------------------------
    # Patch discovery / parsing
    # ---------------------------
    def _load_latest_patch_payload(self) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Minimal, non-invasive:
        - reads meta_state.patch.patch_id if present
        - tries to load state/patches/<patch_id>.json (convention)
        - if missing, returns (patch_id_or_unknown, None)
        """
        p = (self.cfg.get("paths") or {})
        meta_rel = p.get("meta_state_out") or os.path.join(os.path.basename(self.fs.paths.state_dir), "meta_state.json")
        meta_path = meta_rel if os.path.isabs(meta_rel) else os.path.abspath(os.path.join(self.fs.paths.workspace_root, meta_rel))

        meta = None
        try:
            if self.fs.backend.exists(meta_path):
                meta = self.fs.read_json(meta_path)
        except Exception:
            meta = None

        patch = (meta.get("patch") if isinstance(meta, dict) and isinstance(meta.get("patch"), dict) else {}) or {}
        patch_id = str(patch.get("patch_id") or "unknown").strip() or "unknown"

        patches_dir = os.path.join(self.fs.paths.state_dir, "patches")
        patch_path = os.path.join(patches_dir, f"{patch_id}.json")

        if patch_id != "unknown" and self.fs.backend.exists(patch_path):
            try:
                payload = self.fs.read_json(patch_path)
                return patch_id, payload if isinstance(payload, dict) else None
            except Exception:
                return patch_id, None

        return patch_id, None

    def _extract_changed_files_and_ranges(
        self, patch_payload: Optional[Dict[str, Any]]
    ) -> Tuple[List[str], Dict[str, List[Tuple[int, int]]]]:
        """
        Expected patch payload formats (support multiple):
          A) { "files": [ {"path":"a.py","ranges":[[10,20],[50,55]]}, ... ] }
          B) { "changed_files": ["a.py","b.py"] }  (no ranges)
          C) { "patch": {"files": ...} }           (nested)

        Returns:
          changed_files: list[str] normalized relative-ish
          file_ranges: { "a.py": [(10,20), ...] }
        """
        changed: List[str] = []
        ranges: Dict[str, List[Tuple[int, int]]] = {}

        if not isinstance(patch_payload, dict):
            return changed, ranges

        root = patch_payload
        if isinstance(root.get("patch"), dict):
            root = root["patch"]

        files = root.get("files")
        if isinstance(files, list):
            for f in files:
                if not isinstance(f, dict):
                    continue
                path = _norm(str(f.get("path") or f.get("file") or "")).strip()
                if not path:
                    continue
                changed.append(path)
                rr = f.get("ranges") or f.get("affected_ranges") or f.get("line_ranges")
                if isinstance(rr, list):
                    out_rr: List[Tuple[int, int]] = []
                    for r in rr:
                        if isinstance(r, (list, tuple)) and len(r) >= 2:
                            out_rr.append((_safe_int(r[0], 1), _safe_int(r[1], _safe_int(r[0], 1))))
                    if out_rr:
                        ranges[path] = out_rr

        cf = root.get("changed_files")
        if isinstance(cf, list):
            for p in cf:
                sp = _norm(str(p)).strip()
                if sp:
                    changed.append(sp)

        # de-dup keep order
        seen = set()
        uniq = []
        for p in changed:
            if p not in seen:
                seen.add(p)
                uniq.append(p)

        return uniq, ranges

    # ---------------------------
    # Loads
    # ---------------------------
    def _load_artifacts(self) -> Dict[str, Any]:
        obj = self.fs.read_json(self.fs.paths.artifacts_json)
        if not isinstance(obj, dict):
            raise FileNotFoundError(f"Invalid or missing artifacts: {self.fs.paths.artifacts_json}")
        return obj

    def _load_relationships(self) -> Dict[str, Any]:
        obj = self.fs.read_json(self.fs.paths.relationships_json)
        if not isinstance(obj, dict):
            raise FileNotFoundError(f"Invalid or missing relationships: {self.fs.paths.relationships_json}")
        return obj

    # ---------------------------
    # Matching logic
    # ---------------------------
    def _artifact_matches_file_and_ranges(
        self,
        art: Dict[str, Any],
        changed_files_set: Set[str],
        file_ranges: Dict[str, List[Tuple[int, int]]],
    ) -> bool:
        fp = _norm(art.get("file_path") or "")
        if not fp:
            anch = art.get("anchor") if isinstance(art.get("anchor"), dict) else {}
            fp = _norm(anch.get("file_path") or "")
        if not fp:
            return False

        # exact match
        if fp not in changed_files_set:
            return False

        rr = file_ranges.get(fp)
        if not rr:
            return True  # whole file changed

        anchor = art.get("anchor") if isinstance(art.get("anchor"), dict) else {}
        a_range = _anchor_range(anchor)
        for r in rr:
            if _ranges_overlap(a_range, r):
                return True
        return False

    # ---------------------------
    # Snapshot helpers (NEW, non-breaking)
    # ---------------------------
    def _snapshots_dir(self) -> str:
        return os.path.join(self.fs.paths.state_dir, "snapshots")

    def _snapshot_paths(self) -> Tuple[str, str]:
        d = self._snapshots_dir()
        return (
            os.path.join(d, "latest_artifacts.json"),
            os.path.join(d, "latest_relationships.json"),
        )

    def _load_snapshot(self, path: str) -> Dict[str, Any]:
        if not self.fs.backend.exists(path):
            return {}
        try:
            obj = self.fs.read_json(path)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def _update_snapshots(self, artifacts_payload: Dict[str, Any], relationships_payload: Dict[str, Any]) -> None:
        d = self._snapshots_dir()
        _ensure_dir(d)
        a_path, r_path = self._snapshot_paths()
        try:
            arts = artifacts_payload.get("artifacts") if isinstance(artifacts_payload.get("artifacts"), list) else []
            rels = relationships_payload.get("relationships") if isinstance(relationships_payload.get("relationships"), list) else []
        except Exception:
            arts, rels = [], []
        self.fs.write_json(a_path, {"version": "crs-snapshot-v1", "generated_at": _utc_iso(), "artifacts": arts})
        self.fs.write_json(r_path, {"version": "crs-snapshot-v1", "generated_at": _utc_iso(), "relationships": rels})

    # ---------------------------
    # Impact calculation
    # ---------------------------
    def build_impact(
        self,
        patch_id: str,
        patch_payload: Optional[Dict[str, Any]] = None,
        *,
        include_graph_impact: bool = True,         # ✅ NEW (default on)
        update_snapshots: bool = True,             # ✅ NEW (default on)
        graph_max_nodes: int = 5000,               # ✅ NEW
    ) -> Dict[str, Any]:
        changed_files, file_ranges = self._extract_changed_files_and_ranges(patch_payload)

        # Conservative fallback: treat all src/*.py as changed
        if not changed_files:
            src_root = self.fs.paths.src_dir
            for dirpath, _, filenames in os.walk(src_root):
                for fn in filenames:
                    if fn.endswith(".py"):
                        abs_fp = os.path.join(dirpath, fn)
                        rel_fp = _norm(os.path.relpath(abs_fp, src_root))
                        changed_files.append(rel_fp)

        changed_files_set = set(changed_files)

        artifacts_payload = self._load_artifacts()
        relationships_payload = self._load_relationships()

        arts = artifacts_payload.get("artifacts") if isinstance(artifacts_payload.get("artifacts"), list) else []
        rels = relationships_payload.get("relationships") if isinstance(relationships_payload.get("relationships"), list) else []

        affected_artifacts: List[Dict[str, Any]] = []
        affected_ids: Set[str] = set()

        # artifacts impacted
        for a in arts:
            if not isinstance(a, dict):
                continue
            if self._artifact_matches_file_and_ranges(a, changed_files_set, file_ranges):
                affected_artifacts.append(a)
                aid = a.get("artifact_id")
                if isinstance(aid, str) and aid:
                    affected_ids.add(aid)

        # relationships invalidated if touching affected artifact ids
        invalidated_relationships: List[Dict[str, Any]] = []
        by_type: Dict[str, int] = {}

        for r in rels:
            if not isinstance(r, dict):
                continue
            fr = r.get("from") if isinstance(r.get("from"), dict) else {}
            to = r.get("to") if isinstance(r.get("to"), dict) else {}
            fid = fr.get("artifact_id")
            tid = to.get("artifact_id")

            if (isinstance(fid, str) and fid in affected_ids) or (isinstance(tid, str) and tid in affected_ids):
                invalidated_relationships.append(r)
                rt = str(r.get("type") or "unknown")
                by_type[rt] = by_type.get(rt, 0) + 1

        affected_blueprints = {
            "changed_files": changed_files,
            "ranges": {k: [[a, b] for (a, b) in v] for k, v in file_ranges.items()},
        }

        summary = {
            "changed_files": len(changed_files),
            "affected_artifacts": len(affected_artifacts),
            "invalidated_relationships": len(invalidated_relationships),
            "invalidated_relationships_by_type": by_type,
        }

        # ✅ NEW: graph impact (downstream traversal)
        affected_graph: Optional[Dict[str, Any]] = None
        if include_graph_impact and affected_ids:
            adj = _build_adj(rels)
            affected_graph = _bfs_downstream(adj, start=sorted(list(affected_ids)), max_nodes=int(graph_max_nodes))

            # enrich summary without breaking existing keys
            summary["graph_impacted_nodes"] = affected_graph.get("impacted_nodes_count")

        payload = ImpactResult(
            version=self.VERSION,
            generated_at=_utc_iso(),
            patch_id=patch_id,
            changed_files=changed_files,
            affected_blueprints=affected_blueprints,
            affected_artifacts={
                "artifact_ids": sorted(list(affected_ids)),
                "artifacts": affected_artifacts,
            },
            invalidated_relationships={
                "relationships": invalidated_relationships,
            },
            summary=summary,
        )

        out: Dict[str, Any] = {
            "version": payload.version,
            "generated_at": payload.generated_at,
            "patch_id": payload.patch_id,
            "summary": payload.summary,
            "changed_files": payload.changed_files,
            "affected_blueprints": payload.affected_blueprints,
            "affected_artifacts": payload.affected_artifacts,
            "invalidated_relationships": payload.invalidated_relationships,
            "sources": {
                "artifacts_json": self.fs.paths.artifacts_json,
                "relationships_json": self.fs.paths.relationships_json,
            },
        }

        # ✅ NEW fields (additive only)
        if affected_graph is not None:
            out["affected_graph"] = affected_graph

        # ✅ NEW: optional snapshot diff metadata (additive only)
        # This is purely for debugging; it does NOT change core impact behavior.
        try:
            _ensure_dir(self._snapshots_dir())
            prev_a_path, prev_r_path = self._snapshot_paths()
            prev_a = self._load_snapshot(prev_a_path)
            prev_r = self._load_snapshot(prev_r_path)

            prev_arts = prev_a.get("artifacts") if isinstance(prev_a.get("artifacts"), list) else []
            prev_rels = prev_r.get("relationships") if isinstance(prev_r.get("relationships"), list) else []

            cur_arts = arts
            cur_rels = rels

            prev_arts_by_id = _index_by_id(prev_arts, "artifact_id")
            cur_arts_by_id = _index_by_id(cur_arts, "artifact_id")
            prev_rels_by_id = _index_by_id(prev_rels, "rel_id")
            cur_rels_by_id = _index_by_id(cur_rels, "rel_id")

            def _diff(prev_map: Dict[str, Dict[str, Any]], cur_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
                prev_ids = set(prev_map.keys())
                cur_ids = set(cur_map.keys())
                added = sorted(cur_ids - prev_ids)
                removed = sorted(prev_ids - cur_ids)
                modified: List[str] = []
                for _id in sorted(prev_ids & cur_ids):
                    if _sha1_json(prev_map[_id]) != _sha1_json(cur_map[_id]):
                        modified.append(_id)
                return {"added": added, "removed": removed, "modified": modified, "counts": {"added": len(added), "removed": len(removed), "modified": len(modified)}}

            out["snapshot_diff"] = {
                "prev": {"artifacts": prev_a_path, "relationships": prev_r_path},
                "artifacts": _diff(prev_arts_by_id, cur_arts_by_id),
                "relationships": _diff(prev_rels_by_id, cur_rels_by_id),
            }

            # update snapshots after computing
            if update_snapshots:
                self._update_snapshots(artifacts_payload, relationships_payload)

        except Exception:
            # snapshots are best-effort; never fail impact because of them
            pass

        return out

    def build_workspace_impact(
        self,
        run_id: Optional[str] = None,
        patch_payload: Optional[Dict[str, Any]] = None,
        *,
        include_graph_impact: bool = True,     # ✅ NEW passthrough
        update_snapshots: bool = True,         # ✅ NEW passthrough
    ) -> Dict[str, Any]:
        """
        Workspace entrypoint:
          - auto-load patch payload if not provided (from state/patches/<patch_id>.json)
          - compute impact
          - write to:
              - state/impact/impact_<patch_id>.json   (existing behavior)
              - state/impact.json                     (NEW: "latest" canonical)
          - if run_id provided, also write to runs/<run_id>/impact.json
        """
        patch_id, auto_patch_payload = self._load_latest_patch_payload()
        if patch_payload is None:
            patch_payload = auto_patch_payload

        impact = self.build_impact(
            patch_id=patch_id,
            patch_payload=patch_payload,
            include_graph_impact=include_graph_impact,
            update_snapshots=update_snapshots,
        )

        impact_dir = os.path.join(self.fs.paths.state_dir, "impact")
        _ensure_dir(impact_dir)

        # existing
        out_path = os.path.join(impact_dir, f"impact_{patch_id}.json")
        self.fs.write_json(out_path, impact)

        # ✅ NEW canonical latest
        latest_path = os.path.join(self.fs.paths.state_dir, "impact.json")
        self.fs.write_json(latest_path, impact)

        if run_id:
            self.fs.write_run_json(run_id, "impact.json", impact)

        return impact
