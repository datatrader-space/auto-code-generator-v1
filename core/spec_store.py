# core/spec_store.py
import os
import json
import time
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.fs import WorkspaceFS


def _utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _norm(p: str) -> str:
    return (p or "").replace("\\", "/")


def _safe_filename(s: str) -> str:
    s = (s or "").strip()
    s = s.replace(" ", "_").replace("/", "_").replace("\\", "_").replace(":", "_")
    s = "".join(ch for ch in s if ch.isalnum() or ch in ("_", "-", ".", "@"))
    return s[:180] if len(s) > 180 else s


def _sha1_json(obj: Any) -> str:
    try:
        raw = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8", errors="replace")
    except Exception:
        raw = repr(obj).encode("utf-8", errors="replace")
    h = hashlib.sha1()
    h.update(raw)
    return h.hexdigest()


@dataclass
class SpecPaths:
    specs_dir: str
    index_json: str
    artifact_types_json: str
    relationship_types_json: str
    attributes_json: str
    pipeline_steps_json: str
    invariants_json: str
    playbooks_json: str
    # NEW: docs subtree root for agent-generated spec objects
    docs_dir: str


class SpecStore:
    """
    CRS Spec Store (v1)
    -------------------
    Stores "AI-first internal documentation" as structured specs.

    Two layers:

    (A) Canonical fixed spec files (existing):
        state/specs/
          - index.json
          - artifact_types.json
          - relationship_types.json
          - attributes.json
          - pipeline_steps.json
          - invariants.json
          - playbooks.json

    (B) NEW (optional): Spec documents sub-store (agent writable):
        state/specs/docs/<kind>/<spec_id>.json

    Why add (B)?
      - So AI can create/maintain specs without editing the big canonical files every time.
      - Keeps long-lived “tables” stable while allowing flexible expansion.

    Design goals:
      - Minimal surface area (stable)
      - Non-fatal initialization
      - Backend-friendly (uses WorkspaceFS)
      - Easy to extend (append new specs, keep old)
    """

    VERSION = "crs-spec-store-v1"

    def __init__(self, fs: WorkspaceFS):
        self.fs = fs
        self.cfg = fs.get_cfg() or {}
        self.paths = self._resolve_paths()

    # -------------------------
    # Paths
    # -------------------------
    def _resolve_paths(self) -> SpecPaths:
        specs_dir = os.path.join(self.fs.paths.state_dir, "specs")
        docs_dir = os.path.join(specs_dir, "docs")
        return SpecPaths(
            specs_dir=specs_dir,
            index_json=os.path.join(specs_dir, "index.json"),
            artifact_types_json=os.path.join(specs_dir, "artifact_types.json"),
            relationship_types_json=os.path.join(specs_dir, "relationship_types.json"),
            attributes_json=os.path.join(specs_dir, "attributes.json"),
            pipeline_steps_json=os.path.join(specs_dir, "pipeline_steps.json"),
            invariants_json=os.path.join(specs_dir, "invariants.json"),
            playbooks_json=os.path.join(specs_dir, "playbooks.json"),
            docs_dir=docs_dir,
        )

    def ensure_dirs(self) -> None:
        self.fs.backend.makedirs(self.paths.specs_dir)
        # docs dir is optional but safe to ensure
        self.fs.backend.makedirs(self.paths.docs_dir)

    # -------------------------
    # IO helpers
    # -------------------------
    def _read_json_if_exists(self, path: str) -> Optional[Dict[str, Any]]:
        try:
            if self.fs.backend.exists(path):
                obj = self.fs.read_json(path)
                return obj if isinstance(obj, dict) else None
        except Exception:
            return None
        return None

    def _write_json(self, path: str, payload: Any) -> None:
        self.ensure_dirs()
        self.fs.write_json(path, payload)

    # -------------------------
    # NEW: Spec documents (docs/<kind>/<spec_id>.json)
    # -------------------------
    def doc_kind_dir(self, kind: str) -> str:
        return os.path.join(self.paths.docs_dir, _safe_filename(kind))

    def doc_path(self, kind: str, spec_id: str) -> str:
        return os.path.join(self.doc_kind_dir(kind), f"{_safe_filename(spec_id)}.json")

    def ensure_doc_kind(self, kind: str) -> None:
        self.ensure_dirs()
        self.fs.backend.makedirs(self.doc_kind_dir(kind))

    def upsert_doc(
        self,
        *,
        kind: str,
        spec_id: str,
        payload: Dict[str, Any],
        run_id: Optional[str] = None,
        patch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create/update a single spec document:
          state/specs/docs/<kind>/<spec_id>.json

        Adds:
          - store_version, kind, spec_id
          - created_at/updated_at
          - provenance.run_id / provenance.patch_id (if provided)
          - _sha1 hash for change detection
        """
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dict")

        kind = (kind or "").strip()
        spec_id = (spec_id or "").strip()
        if not kind or not spec_id:
            raise ValueError("kind and spec_id are required")

        self.ensure_doc_kind(kind)
        path = self.doc_path(kind, spec_id)

        now = _utc_iso()

        existing = self._read_json_if_exists(path)
        created_at = now
        if isinstance(existing, dict) and existing.get("created_at"):
            created_at = str(existing.get("created_at"))

        out = dict(payload)
        out["store_version"] = self.VERSION
        out["kind"] = kind
        out["spec_id"] = spec_id
        out["created_at"] = created_at
        out["updated_at"] = now

        prov = out.get("provenance") if isinstance(out.get("provenance"), dict) else {}
        if run_id:
            prov["run_id"] = run_id
        if patch_id:
            prov["patch_id"] = patch_id
        out["provenance"] = prov

        out["_sha1"] = _sha1_json(out)

        self._write_json(path, out)
        return out

    def get_doc(self, *, kind: str, spec_id: str) -> Optional[Dict[str, Any]]:
        path = self.doc_path(kind, spec_id)
        return self._read_json_if_exists(path)

    def list_docs(self, *, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lists doc specs (best-effort). Returns parsed docs, not just filenames.
        """
        self.ensure_dirs()

        out: List[Dict[str, Any]] = []
        root = self.paths.docs_dir
        if not os.path.isdir(root):
            return out

        if kind:
            kd = self.doc_kind_dir(kind)
            if not os.path.isdir(kd):
                return out
            for fn in os.listdir(kd):
                if fn.endswith(".json"):
                    p = os.path.join(kd, fn)
                    obj = self._read_json_if_exists(p)
                    if isinstance(obj, dict):
                        out.append(obj)
            return out

        for k in os.listdir(root):
            kd = os.path.join(root, k)
            if not os.path.isdir(kd):
                continue
            for fn in os.listdir(kd):
                if fn.endswith(".json"):
                    p = os.path.join(kd, fn)
                    obj = self._read_json_if_exists(p)
                    if isinstance(obj, dict):
                        out.append(obj)
        return out

    def search_docs(self, *, q: str, kinds: Optional[List[str]] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Best-effort search in docs store:
          - spec_id contains q
          - description contains q
          - tags contains q
        """
        ql = (q or "").strip().lower()
        if not ql:
            return []

        allowed = set([str(x) for x in kinds]) if isinstance(kinds, list) and kinds else None

        results: List[Dict[str, Any]] = []
        for doc in self.list_docs(kind=None):
            if not isinstance(doc, dict):
                continue
            dk = str(doc.get("kind") or "")
            if allowed is not None and dk not in allowed:
                continue

            sid = str(doc.get("spec_id") or "")
            desc = str(doc.get("description") or "")
            tags = doc.get("tags") if isinstance(doc.get("tags"), list) else []
            tags_l = [str(t).lower() for t in tags]

            if ql in sid.lower() or ql in desc.lower() or any(ql in t for t in tags_l):
                results.append(doc)
                if len(results) >= max(1, limit):
                    break

        return results

    # -------------------------
    # Defaults (existing)
    # -------------------------
    def ensure_defaults(self, overwrite: bool = False) -> Dict[str, Any]:
        """
        Creates minimal spec files if missing.
        Safe to call on every run.
        """
        self.ensure_dirs()

        created: List[str] = []
        updated: List[str] = []
        existing: List[str] = []

        def write_if_missing(path: str, payload: Dict[str, Any]) -> None:
            nonlocal created, updated, existing
            already = bool(self.fs.backend.exists(path))
            if already and not overwrite:
                existing.append(_norm(path))
                return
            self._write_json(path, payload)
            if already and overwrite:
                updated.append(_norm(path))
            elif not already:
                created.append(_norm(path))
            else:
                # already existed and overwrite=False would have returned above,
                # so this is a safe fallback
                updated.append(_norm(path))

        # 1) index.json: “table of contents”
        index_payload = {
            "version": self.VERSION,
            "generated_at": _utc_iso(),
            "specs_dir": _norm(self.paths.specs_dir),
            "files": {
                "artifact_types": _norm(self.paths.artifact_types_json),
                "relationship_types": _norm(self.paths.relationship_types_json),
                "attributes": _norm(self.paths.attributes_json),
                "pipeline_steps": _norm(self.paths.pipeline_steps_json),
                "invariants": _norm(self.paths.invariants_json),
                "playbooks": _norm(self.paths.playbooks_json),
                "docs_dir": _norm(self.paths.docs_dir),
            },
            "notes": [
                "These specs are AI-first internal documentation for CRS.",
                "Treat as operational truth for agents: meaning, constraints, usage, examples, and graph connections.",
                "Do not store prose-only docs here; store structured specs.",
                "Use state/specs/docs/<kind>/<spec_id>.json for agent-writable spec documents.",
            ],
        }
        write_if_missing(self.paths.index_json, index_payload)

        # 2) artifact_types.json
        artifact_types_payload = {
            "version": "crs-artifact-type-spec-v1",
            "generated_at": _utc_iso(),
            "artifact_types": [
                {
                    "type": "django_model",
                    "purpose": "Represents a Django model class.",
                    "key_fields": ["artifact_id", "name", "file_path", "anchor", "meta.bases", "meta.fields"],
                    "examples": [
                        {
                            "name": "User",
                            "meta_example": {"bases": ["models.Model"], "fields": [{"name": "email", "type": "models.EmailField"}]},
                        }
                    ],
                    "constraints": [
                        {"id": "inv:model_has_name", "statement": "Model artifacts must have a stable class name.", "severity": "high"}
                    ],
                },
                {
                    "type": "model_field",
                    "purpose": "Represents a model field declared on a Django model.",
                    "key_fields": ["name", "meta.model", "meta.field_name", "meta.field_type", "meta.validators", "meta.kwargs"],
                    "examples": [
                        {
                            "name": "User.email",
                            "meta_example": {"model": "User", "field_name": "email", "field_type": "models.EmailField"},
                        }
                    ],
                },
                {
                    "type": "drf_serializer",
                    "purpose": "Represents a DRF Serializer / ModelSerializer class.",
                    "key_fields": ["name", "meta.meta_model", "meta.meta_fields", "meta.declared_fields", "meta.validators", "meta.overrides"],
                },
                {
                    "type": "serializer_field",
                    "purpose": "Represents a declared serializer field.",
                    "key_fields": ["name", "meta.serializer", "meta.field_name", "meta.call", "meta.kwargs", "meta.validators"],
                },
                {
                    "type": "serializer_validator",
                    "purpose": "Represents validate()/validate_<field> methods inside serializer.",
                    "key_fields": ["name", "meta.serializer", "meta.method"],
                },
                {
                    "type": "drf_viewset",
                    "purpose": "Represents a DRF viewset class.",
                    "key_fields": ["name", "meta.serializer_class", "meta.queryset_model", "meta.permission_classes", "meta.methods"],
                },
                {
                    "type": "drf_apiview",
                    "purpose": "Represents DRF APIView/generic view class.",
                    "key_fields": ["name", "meta.serializer_class", "meta.queryset_model", "meta.methods"],
                },
                {
                    "type": "url_pattern",
                    "purpose": "Represents a Django URL pattern entry (path/re_path/include).",
                    "key_fields": ["name", "meta.fn", "meta.route", "meta.target", "meta.name"],
                },
                {
                    "type": "router_register",
                    "purpose": "Represents router.register(prefix, viewset, basename=...).",
                    "key_fields": ["name", "meta.router", "meta.prefix", "meta.viewset", "meta.basename"],
                },
                {
                    "type": "parse_error",
                    "purpose": "Represents a file parse error or missing file referenced by blueprint.",
                    "key_fields": ["name", "meta.error", "meta.abs_path"],
                },
            ],
        }
        write_if_missing(self.paths.artifact_types_json, artifact_types_payload)

        # 3) relationship_types.json
        relationship_types_payload = {
            "version": "crs-relationship-type-spec-v1",
            "generated_at": _utc_iso(),
            "relationship_types": [
                {
                    "type": "declares",
                    "purpose": "Owner declares a child component (model->field, serializer->field/validator).",
                    "from_types": ["django_model", "drf_serializer"],
                    "to_types": ["model_field", "serializer_field", "serializer_validator"],
                    "confidence_rules": ["certain when derived from explicit ownership meta keys"],
                    "examples": [{"from": "django_model:User", "to": "model_field:User.email"}],
                },
                {
                    "type": "serializes_model",
                    "purpose": "Serializer Meta.model points to model.",
                    "from_types": ["drf_serializer"],
                    "to_types": ["django_model", "unresolved_ref"],
                    "examples": [{"from": "UserSerializer", "to": "User"}],
                },
                {
                    "type": "view_uses_serializer",
                    "purpose": "View references serializer_class or get_serializer_class return targets.",
                    "from_types": ["drf_viewset", "drf_apiview"],
                    "to_types": ["drf_serializer", "unresolved_ref"],
                },
                {
                    "type": "routes_to",
                    "purpose": "URL pattern targets a view callable/class (best-effort).",
                    "from_types": ["url_pattern"],
                    "to_types": ["drf_viewset", "drf_apiview", "unresolved_ref"],
                },
                {
                    "type": "registers",
                    "purpose": "router.register(...) registers a viewset.",
                    "from_types": ["router_register"],
                    "to_types": ["drf_viewset", "unresolved_ref"],
                },
                {
                    "type": "mentions_field_string",
                    "purpose": "Heuristic string mention of a model field token inside artifact meta.",
                    "from_types": ["*"],
                    "to_types": ["model_field"],
                    "notes": ["Heuristic; can produce false positives; used for hints not truth."],
                },
            ],
        }
        write_if_missing(self.paths.relationship_types_json, relationship_types_payload)

        # 4) attributes.json
        attributes_payload = {
            "version": "crs-attribute-spec-v1",
            "generated_at": _utc_iso(),
            "attributes": [
                {
                    "attr_id": "artifact.anchor",
                    "owner_kind": "artifact",
                    "type": "object",
                    "meaning": "Source range anchor for artifact in file.",
                    "examples": [{"start_line": 10, "end_line": 42}],
                    "constraints": [{"id": "inv:anchor_has_lines", "statement": "anchor.start_line/end_line should be ints >= 1", "severity": "medium"}],
                },
                {
                    "attr_id": "artifact.meta.serializer_class",
                    "owner_kind": "artifact",
                    "artifact_type": "drf_viewset",
                    "type": "string|null",
                    "meaning": "Serializer class referenced by view/viewset.",
                    "used_by": [{"engine": "relationship_builder", "relationship": "view_uses_serializer", "rule": "resolve serializer by normalized name"}],
                    "fallbacks": ["unresolved_ref if serializer not found"],
                },
                {
                    "attr_id": "artifact.meta.meta_model",
                    "owner_kind": "artifact",
                    "artifact_type": "drf_serializer",
                    "type": "string|null",
                    "meaning": "Model referenced by Serializer.Meta.model.",
                    "used_by": [{"engine": "relationship_builder", "relationship": "serializes_model", "rule": "resolve model by normalized name"}],
                },
            ],
        }
        write_if_missing(self.paths.attributes_json, attributes_payload)

        # 5) pipeline_steps.json
        pipeline_steps_payload = {
            "version": "crs-pipeline-step-spec-v1",
            "generated_at": _utc_iso(),
            "steps": [
                {
                    "id": "patch",
                    "purpose": "Apply patch (file edits) and mark meta_state.patch.dirty=True.",
                    "inputs": [{"env": "CRS_PATCH_IN", "type": "path-to-patch.json"}],
                    "outputs": ["state/patches/<patch_id>.json", "meta_state.patch"],
                    "notes": ["Patch step may be skipped if CRS_PATCH_IN is not set."],
                },
                {"id": "blueprints", "purpose": "Index workspace src into blueprints.json (file inventory + raw_text optional).", "outputs": ["state/blueprints.json"]},
                {"id": "artifacts", "purpose": "Extract semantic artifacts from blueprints/source.", "outputs": ["state/artifacts.json"]},
                {"id": "relationships", "purpose": "Build relationship graph edges from artifacts.", "outputs": ["state/relationships.json"]},
                {
                    "id": "impact",
                    "purpose": "Compute affected artifacts and invalidated relationships after patch.",
                    "outputs": ["state/impact/impact_<patch_id>.json"],
                    "notes": ["Diagnostic; should not fail pipeline if it errors."],
                },
                {"id": "query", "purpose": "Read-only access API over artifacts + relationships.", "outputs": ["in-memory index", "optional run snapshot"]},
            ],
        }
        write_if_missing(self.paths.pipeline_steps_json, pipeline_steps_payload)

        # 6) invariants.json
        invariants_payload = {
            "version": "crs-invariants-v1",
            "generated_at": _utc_iso(),
            "invariants": [
                {
                    "id": "inv:artifact_id_unique",
                    "statement": "artifact_id should be unique within artifacts.json.",
                    "severity": "high",
                    "detection": {"where": "query_api.load", "how": "duplicate key collision in artifacts_by_id"},
                    "repair_playbook": "pb:fix_duplicate_artifact_id",
                },
                {"id": "inv:relationship_endpoints_have_types", "statement": "Every relationship must have from.type and to.type (even unresolved).", "severity": "medium"},
            ],
        }
        write_if_missing(self.paths.invariants_json, invariants_payload)

        # 7) playbooks.json
        playbooks_payload = {
            "version": "crs-playbooks-v1",
            "generated_at": _utc_iso(),
            "playbooks": [
                {
                    "id": "pb:rename_model_field",
                    "purpose": "Safely rename a Django model field and refresh CRS state.",
                    "steps": [
                        "Apply patch that renames field in model class.",
                        "Run pipeline (blueprints/artifacts/relationships).",
                        "Run impact and confirm affected serializer fields and routes.",
                        "Query for references to old field name and fix remaining uses.",
                    ],
                    "queries": [
                        {"goal": "Find impacted nodes", "call": "ImpactEngine.build_workspace_impact"},
                        {"goal": "Find mentions", "call": "CRSQueryAPI.find_artifacts(contains_name='<old_field>')"},
                    ],
                },
                {
                    "id": "pb:fix_duplicate_artifact_id",
                    "purpose": "Resolve duplicate artifact_id collisions by adjusting make_artifact_id() or anchors.",
                    "steps": [
                        "Identify duplicates in artifacts.json.",
                        "Adjust artifact_id generation to include more stable uniqueness (anchor or qualified name).",
                        "Re-run pipeline.",
                    ],
                },
            ],
        }
        write_if_missing(self.paths.playbooks_json, playbooks_payload)

        return {
            "version": self.VERSION,
            "generated_at": _utc_iso(),
            "specs_dir": _norm(self.paths.specs_dir),
            "created": created,
            "updated": updated,
            "existing": existing,
        }

    # -------------------------
    # Read APIs (lightweight)
    # -------------------------
    def load_index(self) -> Dict[str, Any]:
        obj = self._read_json_if_exists(self.paths.index_json)
        return obj or {}

    def load_artifact_type_specs(self) -> List[Dict[str, Any]]:
        obj = self._read_json_if_exists(self.paths.artifact_types_json) or {}
        v = obj.get("artifact_types")
        return v if isinstance(v, list) else []

    def load_relationship_type_specs(self) -> List[Dict[str, Any]]:
        obj = self._read_json_if_exists(self.paths.relationship_types_json) or {}
        v = obj.get("relationship_types")
        return v if isinstance(v, list) else []

    def load_attribute_specs(self) -> List[Dict[str, Any]]:
        obj = self._read_json_if_exists(self.paths.attributes_json) or {}
        v = obj.get("attributes")
        return v if isinstance(v, list) else []

    def load_pipeline_step_specs(self) -> List[Dict[str, Any]]:
        obj = self._read_json_if_exists(self.paths.pipeline_steps_json) or {}
        v = obj.get("steps")
        return v if isinstance(v, list) else []

    def load_invariants(self) -> List[Dict[str, Any]]:
        obj = self._read_json_if_exists(self.paths.invariants_json) or {}
        v = obj.get("invariants")
        return v if isinstance(v, list) else []

    def load_playbooks(self) -> List[Dict[str, Any]]:
        obj = self._read_json_if_exists(self.paths.playbooks_json) or {}
        v = obj.get("playbooks")
        return v if isinstance(v, list) else []
