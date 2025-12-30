from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.fs import WorkspaceFS


# Must match artifact extractor output types
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


@dataclass
class RelEnd:
    artifact_id: Optional[str]
    type: str
    name: str


@dataclass
class Relationship:
    rel_id: str
    type: str
    from_end: RelEnd
    to_end: RelEnd
    confidence: str  # "certain" | "probable" | "heuristic"
    evidence: List[Dict[str, Any]]
    meta: Dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_ref(s: Optional[str]) -> Optional[str]:
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    if "." in s:
        s = s.split(".")[-1]
    return s.replace("()", "")


def _end_from_art(a: Dict[str, Any]) -> RelEnd:
    return RelEnd(
        artifact_id=a.get("artifact_id"),
        type=a.get("type") or "unknown",
        name=a.get("name") or "",
    )


def _end_unresolved(name: str) -> RelEnd:
    return RelEnd(artifact_id=None, type="unresolved_ref", name=name)


def _mk_rel_id(rel_type: str, from_id: str, to_key: str) -> str:
    return f"rel:{rel_type}:{from_id}->{to_key}"


def _iter_strings(obj: Any) -> List[str]:
    out: List[str] = []
    if obj is None:
        return out
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, (int, float, bool)):
        return out
    if isinstance(obj, list):
        for x in obj:
            out.extend(_iter_strings(x))
        return out
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(_iter_strings(v))
        return out
    return out


def build_relationships(artifacts_payload: Dict[str, Any], include_heuristic_mentions: bool = True) -> Dict[str, Any]:
    arts: List[Dict[str, Any]] = artifacts_payload.get("artifacts", []) or []

    models_by_name: Dict[str, Dict[str, Any]] = {}
    fields_by_fullname: Dict[str, Dict[str, Any]] = {}
    serializers_by_name: Dict[str, Dict[str, Any]] = {}
    views_by_name: Dict[str, Dict[str, Any]] = {}
    url_patterns: List[Dict[str, Any]] = []
    router_regs: List[Dict[str, Any]] = []

    for a in arts:
        at = a.get("type")
        nm = a.get("name") or ""
        if at == A_DJANGO_MODEL:
            models_by_name[_norm_ref(nm) or nm] = a
        elif at == A_MODEL_FIELD:
            fields_by_fullname[nm] = a
        elif at == A_DRF_SERIALIZER:
            serializers_by_name[_norm_ref(nm) or nm] = a
        elif at in (A_DRF_VIEWSET, A_DRF_APIVIEW):
            views_by_name[_norm_ref(nm) or nm] = a
        elif at == A_URL_PATTERN:
            url_patterns.append(a)
        elif at == A_ROUTER_REGISTER:
            router_regs.append(a)

    rels: List[Relationship] = []
    seen = set()

    def emit(rel: Relationship) -> None:
        if rel.rel_id in seen:
            return
        seen.add(rel.rel_id)
        rels.append(rel)

    # (1) declares: model -> model_field
    for _, model_art in models_by_name.items():
        from_end = _end_from_art(model_art)
        for field_art in arts:
            if field_art.get("type") != A_MODEL_FIELD:
                continue
            meta = field_art.get("meta") or {}
            if meta.get("model") != model_art.get("name"):
                continue

            to_end = _end_from_art(field_art)
            rel_id = _mk_rel_id("declares", from_end.artifact_id or "", to_end.artifact_id or to_end.name)
            emit(
                Relationship(
                    rel_id=rel_id,
                    type="declares",
                    from_end=from_end,
                    to_end=to_end,
                    confidence="certain",
                    evidence=[{"file_path": field_art.get("file_path"), "anchor": field_art.get("anchor"), "note": "field declared in model class body"}],
                    meta={"owner_kind": "model"},
                )
            )

    # (2) declares: serializer -> serializer_field/validator
    for _, ser_art in serializers_by_name.items():
        from_end = _end_from_art(ser_art)
        for a in arts:
            if a.get("type") == A_SERIALIZER_FIELD and (a.get("meta") or {}).get("serializer") == ser_art.get("name"):
                to_end = _end_from_art(a)
                rel_id = _mk_rel_id("declares", from_end.artifact_id or "", to_end.artifact_id or to_end.name)
                emit(
                    Relationship(
                        rel_id=rel_id,
                        type="declares",
                        from_end=from_end,
                        to_end=to_end,
                        confidence="certain",
                        evidence=[{"file_path": a.get("file_path"), "anchor": a.get("anchor"), "note": "declared serializer field"}],
                        meta={"owner_kind": "serializer"},
                    )
                )

            if a.get("type") == A_SERIALIZER_VALIDATOR and (a.get("meta") or {}).get("serializer") == ser_art.get("name"):
                to_end = _end_from_art(a)
                rel_id = _mk_rel_id("declares", from_end.artifact_id or "", to_end.artifact_id or to_end.name)
                emit(
                    Relationship(
                        rel_id=rel_id,
                        type="declares",
                        from_end=from_end,
                        to_end=to_end,
                        confidence="certain",
                        evidence=[{"file_path": a.get("file_path"), "anchor": a.get("anchor"), "note": "declared serializer validator"}],
                        meta={"owner_kind": "serializer"},
                    )
                )

    # (3) serializes_model: serializer -> model (Meta.model)
    for _, ser_art in serializers_by_name.items():
        meta = ser_art.get("meta") or {}
        mm = meta.get("meta_model")
        if not mm:
            continue

        from_end = _end_from_art(ser_art)
        mm_norm = _norm_ref(mm) or str(mm)
        model_art = models_by_name.get(mm_norm)

        if model_art:
            to_end = _end_from_art(model_art)
            rel_id = _mk_rel_id("serializes_model", from_end.artifact_id or "", to_end.artifact_id or to_end.name)
            emit(
                Relationship(
                    rel_id=rel_id,
                    type="serializes_model",
                    from_end=from_end,
                    to_end=to_end,
                    confidence="certain",
                    evidence=[{"file_path": ser_art.get("file_path"), "anchor": ser_art.get("anchor"), "note": f"Meta.model={mm}"}],
                    meta={"meta_model": mm},
                )
            )
        else:
            to_end = _end_unresolved(str(mm))
            rel_id = _mk_rel_id("serializes_model", from_end.artifact_id or "", to_end.name)
            emit(
                Relationship(
                    rel_id=rel_id,
                    type="serializes_model",
                    from_end=from_end,
                    to_end=to_end,
                    confidence="heuristic",
                    evidence=[{"file_path": ser_art.get("file_path"), "anchor": ser_art.get("anchor"), "note": f"Meta.model={mm} (unresolved)"}],
                    meta={"meta_model": mm, "unresolved": True},
                )
            )

    # (4) view_uses_serializer: view -> serializer
    for _, view_art in views_by_name.items():
        meta = view_art.get("meta") or {}
        from_end = _end_from_art(view_art)

        sc = meta.get("serializer_class")
        if sc:
            sc_norm = _norm_ref(sc) or str(sc)
            ser_target = serializers_by_name.get(sc_norm)
            if ser_target:
                to_end = _end_from_art(ser_target)
                rel_id = _mk_rel_id("view_uses_serializer", from_end.artifact_id or "", to_end.artifact_id or to_end.name)
                emit(
                    Relationship(
                        rel_id=rel_id,
                        type="view_uses_serializer",
                        from_end=from_end,
                        to_end=to_end,
                        confidence="certain",
                        evidence=[{"file_path": view_art.get("file_path"), "anchor": view_art.get("anchor"), "note": f"serializer_class={sc}"}],
                        meta={"via": "serializer_class"},
                    )
                )
            else:
                to_end = _end_unresolved(str(sc))
                rel_id = _mk_rel_id("view_uses_serializer", from_end.artifact_id or "", to_end.name)
                emit(
                    Relationship(
                        rel_id=rel_id,
                        type="view_uses_serializer",
                        from_end=from_end,
                        to_end=to_end,
                        confidence="heuristic",
                        evidence=[{"file_path": view_art.get("file_path"), "anchor": view_art.get("anchor"), "note": f"serializer_class={sc} (unresolved)"}],
                        meta={"via": "serializer_class", "unresolved": True},
                    )
                )

        for tgt in meta.get("get_serializer_class_targets", []) or []:
            tgt_norm = _norm_ref(tgt) or str(tgt)
            ser_target = serializers_by_name.get(tgt_norm)
            if ser_target:
                to_end = _end_from_art(ser_target)
                rel_id = _mk_rel_id("view_uses_serializer", from_end.artifact_id or "", to_end.artifact_id or to_end.name)
                emit(
                    Relationship(
                        rel_id=rel_id,
                        type="view_uses_serializer",
                        from_end=from_end,
                        to_end=to_end,
                        confidence="probable",
                        evidence=[{"file_path": view_art.get("file_path"), "anchor": view_art.get("anchor"), "note": f"get_serializer_class returns {tgt}"}],
                        meta={"via": "get_serializer_class"},
                    )
                )

    # (5) registers: router_register -> viewset
    for rr in router_regs:
        meta = rr.get("meta") or {}
        vs = meta.get("viewset")
        if not vs:
            continue

        from_end = _end_from_art(rr)
        vs_norm = _norm_ref(vs) or str(vs)
        view_art = views_by_name.get(vs_norm)

        if view_art:
            to_end = _end_from_art(view_art)
            rel_id = _mk_rel_id("registers", from_end.artifact_id or "", to_end.artifact_id or to_end.name)
            emit(
                Relationship(
                    rel_id=rel_id,
                    type="registers",
                    from_end=from_end,
                    to_end=to_end,
                    confidence="probable",
                    evidence=[{"file_path": rr.get("file_path"), "anchor": rr.get("anchor"), "note": f"router.register(..., {vs})"}],
                    meta={"router": meta.get("router"), "prefix": meta.get("prefix"), "basename": meta.get("basename")},
                )
            )
        else:
            to_end = _end_unresolved(str(vs))
            rel_id = _mk_rel_id("registers", from_end.artifact_id or "", to_end.name)
            emit(
                Relationship(
                    rel_id=rel_id,
                    type="registers",
                    from_end=from_end,
                    to_end=to_end,
                    confidence="heuristic",
                    evidence=[{"file_path": rr.get("file_path"), "anchor": rr.get("anchor"), "note": f"router.register(..., {vs}) (unresolved)"}],
                    meta={"unresolved": True},
                )
            )

    # (6) routes_to: url_pattern -> view
    for up in url_patterns:
        meta = up.get("meta") or {}
        tgt = meta.get("target")
        if not tgt:
            continue

        from_end = _end_from_art(up)
        tgt_norm = _norm_ref(tgt) or str(tgt)
        view_art = views_by_name.get(tgt_norm)

        if view_art:
            to_end = _end_from_art(view_art)
            rel_id = _mk_rel_id("routes_to", from_end.artifact_id or "", to_end.artifact_id or to_end.name)
            emit(
                Relationship(
                    rel_id=rel_id,
                    type="routes_to",
                    from_end=from_end,
                    to_end=to_end,
                    confidence="probable",
                    evidence=[{"file_path": up.get("file_path"), "anchor": up.get("anchor"), "note": f"urlpattern target={tgt}"}],
                    meta={"route": meta.get("route"), "fn": meta.get("fn"), "name": meta.get("name")},
                )
            )
        else:
            to_end = _end_unresolved(str(tgt))
            rel_id = _mk_rel_id("routes_to", from_end.artifact_id or "", to_end.name)
            emit(
                Relationship(
                    rel_id=rel_id,
                    type="routes_to",
                    from_end=from_end,
                    to_end=to_end,
                    confidence="heuristic",
                    evidence=[{"file_path": up.get("file_path"), "anchor": up.get("anchor"), "note": f"urlpattern target={tgt} (unresolved)"}],
                    meta={"route": meta.get("route"), "fn": meta.get("fn"), "name": meta.get("name"), "unresolved": True},
                )
            )

    # (7) mentions_field_string: any artifact -> model_field (HEURISTIC)
    if include_heuristic_mentions:
        field_tokens = []
        for fullname, field_art in fields_by_fullname.items():
            short = fullname.split(".")[-1] if "." in fullname else fullname
            field_tokens.append((fullname, short, field_art))

        for a in arts:
            if a.get("type") == A_PARSE_ERROR:
                continue
            strings = _iter_strings(a.get("meta") or {})
            if not strings:
                continue
            blob = "\n".join(strings)
            from_end = _end_from_art(a)

            for fullname, short, field_art in field_tokens:
                if short and short in blob:
                    to_end = _end_from_art(field_art)
                    rel_id = _mk_rel_id("mentions_field_string", from_end.artifact_id or "", to_end.artifact_id or to_end.name)
                    emit(
                        Relationship(
                            rel_id=rel_id,
                            type="mentions_field_string",
                            from_end=from_end,
                            to_end=to_end,
                            confidence="heuristic",
                            evidence=[{"file_path": a.get("file_path"), "anchor": a.get("anchor"), "note": f"meta contains '{short}'"}],
                            meta={"matched_token": short, "field": fullname},
                        )
                    )

    by_type: Dict[str, int] = {}
    for r in rels:
        by_type[r.type] = by_type.get(r.type, 0) + 1

    return {
        "version": "crs-relationships-v1",
        "generated_at": _utc_now_iso(),
        "summary": {"artifacts": len(arts), "relationships": len(rels), "by_type": by_type},
        "relationships": [
            {
                "rel_id": r.rel_id,
                "type": r.type,
                "from": asdict(r.from_end),
                "to": asdict(r.to_end),
                "confidence": r.confidence,
                "evidence": r.evidence,
                "meta": r.meta,
            }
            for r in rels
        ],
    }


def build_workspace_relationships(
    artifacts_payload: Optional[Dict[str, Any]] = None,
    fs: Optional[WorkspaceFS] = None,
) -> Dict[str, Any]:
    """
    Workspace entrypoint:
    - If artifacts_payload is None -> load from fs.paths.artifacts_json
    - Build relationships
    - Write to fs.paths.relationships_json
    """
    fs = fs or WorkspaceFS()
    cfg = fs.get_cfg()
    components = (cfg.get("components") or {})
    include_heuristic = bool(components.get("relationship_include_heuristic_mentions", True))

    if artifacts_payload is None:
        if not fs.backend.exists(fs.paths.artifacts_json):
            raise FileNotFoundError(f"Artifacts JSON not found: {fs.paths.artifacts_json}")
        artifacts_payload = fs.read_json(fs.paths.artifacts_json)

    rel_payload = build_relationships(artifacts_payload, include_heuristic_mentions=include_heuristic)
    rel_payload["source_artifacts"] = fs.paths.artifacts_json

    fs.save_relationships(rel_payload)
    return rel_payload


if __name__ == "__main__":
    payload = build_workspace_relationships()
    fs = WorkspaceFS()
    print(f"✅ Wrote relationships -> {fs.paths.relationships_json}")
    print(f"Relationships: {payload.get('summary', {}).get('relationships')}")
