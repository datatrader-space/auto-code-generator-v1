# tools/artifact_extractor_v1_workspace.py

import ast
import json
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from core.fs import WorkspaceFS

"""
CRS Artifact Extractor (v2) - workspace-first refactor
=====================================================

What changed vs your current version:
- All IO is centralized via core.fs.WorkspaceFS (no direct open/write scattered)
- Workspace run exposes build_workspace_artifacts() for crs_main pipeline
- When blueprint file_path is relative (workspace/src relative), fallback reads from src properly.

What did NOT change:
- Underlying AST extraction logic and artifact schema.
"""


# -----------------------------
# Artifact Types
# -----------------------------
A_PARSE_ERROR = "parse_error"
A_DJANGO_MODEL = "django_model"
A_MODEL_FIELD = "model_field"
A_DRF_SERIALIZER = "drf_serializer"
A_SERIALIZER_FIELD = "serializer_field"
A_SERIALIZER_VALIDATOR = "serializer_validator"
A_DRF_VIEWSET = "drf_viewset"
A_DRF_APIVIEW = "drf_apiview"
A_ADMIN_REGISTER = "admin_register"
A_URLCONF = "django_urlconf"
A_URL_PATTERN = "url_pattern"
A_ROUTER_REGISTER = "router_register"
A_CELERY_TASK = "celery_task"
A_REDIS_CLIENT = "redis_client"
A_DJANGO_APP_CONFIG = "django_app_config"
A_DJANGO_SETTINGS = "django_settings"
A_REQUIREMENT = "requirement"


# -----------------------------
# Data structures
# -----------------------------
@dataclass
class Artifact:
    artifact_id: str
    type: str
    name: str
    file_path: str
    anchor: Dict[str, Any]
    confidence: str  # "certain" | "probable" | "heuristic"
    evidence: List[Dict[str, Any]]
    meta: Dict[str, Any]


# -----------------------------
# Helpers: AST / name resolution
# -----------------------------
def _anchor_for_node(file_path: str, node: ast.AST) -> Dict[str, Any]:
    start_line = getattr(node, "lineno", 1) or 1
    start_col = getattr(node, "col_offset", 0) or 0
    end_line = getattr(node, "end_lineno", start_line) or start_line
    end_col = getattr(node, "end_col_offset", 0) or 0
    return {
        "file_path": file_path,
        "start_line": int(start_line),
        "start_col": int(start_col),
        "end_line": int(end_line),
        "end_col": int(end_col),
    }


def _get_full_attr_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _get_full_attr_name(node.value)
        if not base:
            return None
        return f"{base}.{node.attr}"
    if isinstance(node, ast.Call):
        return _get_full_attr_name(node.func)
    return None


def _bases_as_names(class_node: ast.ClassDef) -> List[str]:
    out: List[str] = []
    for b in class_node.bases:
        name = _get_full_attr_name(b)
        if name:
            out.append(name)
    return out


def _const_str(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _list_of_str(node: ast.AST) -> Optional[List[str]]:
    if isinstance(node, (ast.List, ast.Tuple)):
        vals: List[str] = []
        for el in node.elts:
            s = _const_str(el)
            if s is None:
                return None
            vals.append(s)
        return vals
    return None


def _kwarg(call: ast.Call, name: str) -> Optional[ast.AST]:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _extract_validators_from_call(call: ast.Call) -> List[str]:
    val_node = _kwarg(call, "validators")
    if not val_node:
        return []
    out: List[str] = []
    if isinstance(val_node, (ast.List, ast.Tuple)):
        for el in val_node.elts:
            if isinstance(el, ast.Name):
                out.append(el.id)
            elif isinstance(el, ast.Attribute):
                n = _get_full_attr_name(el)
                if n:
                    out.append(n)
            elif isinstance(el, ast.Call):
                n = _get_full_attr_name(el.func)
                if n:
                    out.append(n)
    return out


# -----------------------------
# Artifact id
# -----------------------------
def make_artifact_id(a_type: str, name: str, anchor: Dict[str, Any]) -> str:
    fp = anchor.get("file_path", "")
    sl = anchor.get("start_line", 0)
    el = anchor.get("end_line", 0)
    return f"{a_type}:{name}:{fp}:{sl}-{el}"


# -----------------------------
# Extractors
# -----------------------------
def _is_django_model(
    bases: List[str],
    model_module_aliases: Set[str],
    model_class_aliases: Set[str],
) -> bool:
    for base in bases:
        if base in ("models.Model", "django.db.models.Model") or base.endswith(".models.Model"):
            return True
        if base in model_class_aliases:
            return True
        for alias in model_module_aliases:
            if base == f"{alias}.Model":
                return True
    return False


def _is_django_app_config(
    bases: List[str],
    appconfig_module_aliases: Set[str],
    appconfig_class_aliases: Set[str],
) -> bool:
    for base in bases:
        if base in ("django.apps.AppConfig",):
            return True
        if base in appconfig_class_aliases:
            return True
        for alias in appconfig_module_aliases:
            if base == f"{alias}.AppConfig":
                return True
    return False


def _is_drf_serializer(bases: List[str]) -> bool:
    return any(
        b.startswith("serializers.") and b.endswith("Serializer")
        or b in ("rest_framework.serializers.Serializer", "rest_framework.serializers.ModelSerializer")
        or b.endswith(".serializers.Serializer")
        or b.endswith(".serializers.ModelSerializer")
        for b in bases
    )


def _is_drf_viewset(bases: List[str]) -> bool:
    return any(
        b.startswith("viewsets.")
        and (b.endswith("ViewSet") or b.endswith("ModelViewSet") or b.endswith("ReadOnlyModelViewSet"))
        or b.endswith(".viewsets.ViewSet")
        or b.endswith(".viewsets.ModelViewSet")
        for b in bases
    )


def _is_drf_apiview_or_generic(bases: List[str]) -> bool:
    if any(b == "APIView" or b.endswith(".APIView") for b in bases):
        return True
    if any(b.startswith("generics.") and b.endswith("APIView") for b in bases):
        return True
    return False


def _extract_meta_model_and_fields(class_node: ast.ClassDef) -> Tuple[Optional[str], Optional[Union[str, List[str]]]]:
    meta_model = None
    meta_fields: Optional[Union[str, List[str]]] = None

    for stmt in class_node.body:
        if isinstance(stmt, ast.ClassDef) and stmt.name == "Meta":
            for s in stmt.body:
                if isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name):
                    key = s.targets[0].id
                    if key == "model":
                        meta_model = _get_full_attr_name(s.value) or _const_str(s.value)
                    if key == "fields":
                        if isinstance(s.value, ast.Constant) and isinstance(s.value.value, str):
                            meta_fields = s.value.value
                        else:
                            lst = _list_of_str(s.value)
                            if lst is not None:
                                meta_fields = lst
    return meta_model, meta_fields


def _extract_model_fields(
    class_node: ast.ClassDef,
    model_module_aliases: Set[str],
    model_field_aliases: Set[str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for stmt in class_node.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            field_name = stmt.targets[0].id
            if isinstance(stmt.value, ast.Call):
                callee = _get_full_attr_name(stmt.value.func)
                if not callee:
                    continue

                base = None
                if "." in callee:
                    base = callee.split(".", 1)[0]

                is_module_field = base in model_module_aliases
                is_direct_field = callee in model_field_aliases
                if not (is_module_field or is_direct_field):
                    continue

                is_field = callee.endswith("Field") or callee.endswith(("ForeignKey", "OneToOneField", "ManyToManyField"))
                if not is_field:
                    continue

                validators = _extract_validators_from_call(stmt.value)

                related_model = None
                if callee.endswith(("ForeignKey", "OneToOneField", "ManyToManyField")) and stmt.value.args:
                    related_model = _get_full_attr_name(stmt.value.args[0]) or _const_str(stmt.value.args[0])

                kwargs: Dict[str, Any] = {}
                for kw in stmt.value.keywords:
                    if kw.arg is None:
                        continue
                    if isinstance(kw.value, ast.Constant):
                        kwargs[kw.arg] = kw.value.value
                    elif isinstance(kw.value, (ast.List, ast.Tuple)):
                        v = _list_of_str(kw.value)
                        if v is not None:
                            kwargs[kw.arg] = v

                out.append(
                    {
                        "name": field_name,
                        "type": callee,
                        "validators": validators,
                        "related_model": related_model,
                        "kwargs": kwargs,
                        "lineno": getattr(stmt, "lineno", None),
                    }
                )
    return out


def _collect_import_aliases(tree: ast.Module) -> Dict[str, Set[str]]:
    model_module_aliases: Set[str] = {"models"}
    model_class_aliases: Set[str] = {"Model"}
    model_field_aliases: Set[str] = set()
    appconfig_module_aliases: Set[str] = {"apps"}
    appconfig_class_aliases: Set[str] = {"AppConfig"}
    redis_module_aliases: Set[str] = {"redis"}
    redis_class_aliases: Set[str] = {"Redis", "StrictRedis"}

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                as_name = alias.asname or name.split(".")[-1]
                if name in ("django.db.models", "django.db"):
                    model_module_aliases.add(as_name)
                if name == "django.apps":
                    appconfig_module_aliases.add(as_name)
                if name == "redis":
                    redis_module_aliases.add(as_name)
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "django.db":
                for alias in node.names:
                    if alias.name == "models":
                        model_module_aliases.add(alias.asname or alias.name)
            if module == "django.apps":
                for alias in node.names:
                    name = alias.name
                    as_name = alias.asname or name
                    if name == "AppConfig":
                        appconfig_class_aliases.add(as_name)
            if module == "django.db.models":
                for alias in node.names:
                    name = alias.name
                    as_name = alias.asname or name
                    if name == "Model":
                        model_class_aliases.add(as_name)
                    if name.endswith("Field") or name in ("ForeignKey", "OneToOneField", "ManyToManyField"):
                        model_field_aliases.add(as_name)
            if module == "redis":
                for alias in node.names:
                    name = alias.name
                    as_name = alias.asname or name
                    if name in ("Redis", "StrictRedis"):
                        redis_class_aliases.add(as_name)

    return {
        "model_module_aliases": model_module_aliases,
        "model_class_aliases": model_class_aliases,
        "model_field_aliases": model_field_aliases,
        "appconfig_module_aliases": appconfig_module_aliases,
        "appconfig_class_aliases": appconfig_class_aliases,
        "redis_module_aliases": redis_module_aliases,
        "redis_class_aliases": redis_class_aliases,
    }


def _is_celery_task_decorator(name: Optional[str]) -> bool:
    if not name:
        return False
    return name == "shared_task" or name.endswith(".shared_task") or name.endswith(".task")


def _extract_celery_tasks(tree: ast.Module, file_path: str) -> List[Artifact]:
    artifacts: List[Artifact] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                dec_name = None
                if isinstance(dec, ast.Call):
                    dec_name = _get_full_attr_name(dec.func)
                else:
                    dec_name = _get_full_attr_name(dec)
                if _is_celery_task_decorator(dec_name):
                    anchor = _anchor_for_node(file_path, node)
                    artifacts.append(
                        Artifact(
                            artifact_id=make_artifact_id(A_CELERY_TASK, node.name, anchor),
                            type=A_CELERY_TASK,
                            name=node.name,
                            file_path=file_path,
                            anchor=anchor,
                            confidence="probable",
                            evidence=[{"anchor": anchor, "note": f"celery task decorator {dec_name}"}],
                            meta={"decorator": dec_name},
                        )
                    )
                    break
    return artifacts


def _extract_redis_clients(
    tree: ast.Module,
    file_path: str,
    redis_module_aliases: Set[str],
    redis_class_aliases: Set[str],
) -> List[Artifact]:
    artifacts: List[Artifact] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            callee = _get_full_attr_name(node.func)
            if not callee:
                continue
            if callee in redis_class_aliases:
                matched = callee
            else:
                base = callee.split(".", 1)[0]
                if base not in redis_module_aliases:
                    continue
                if not callee.endswith((".Redis", ".StrictRedis")):
                    continue
                matched = callee

            anchor = _anchor_for_node(file_path, node)
            artifacts.append(
                Artifact(
                    artifact_id=make_artifact_id(A_REDIS_CLIENT, matched, anchor),
                    type=A_REDIS_CLIENT,
                    name=matched,
                    file_path=file_path,
                    anchor=anchor,
                    confidence="probable",
                    evidence=[{"anchor": anchor, "note": f"redis client instantiation {matched}"}],
                    meta={"client": matched},
                )
            )
    return artifacts


def _extract_app_configs(
    tree: ast.Module,
    file_path: str,
    appconfig_module_aliases: Set[str],
    appconfig_class_aliases: Set[str],
) -> List[Artifact]:
    artifacts: List[Artifact] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = _bases_as_names(node)
        if not _is_django_app_config(bases, appconfig_module_aliases, appconfig_class_aliases):
            continue
        anchor = _anchor_for_node(file_path, node)
        app_label = None
        verbose_name = None
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                key = stmt.targets[0].id
                if key == "name":
                    app_label = _const_str(stmt.value) or _get_full_attr_name(stmt.value)
                if key == "verbose_name":
                    verbose_name = _const_str(stmt.value)
        artifacts.append(
            Artifact(
                artifact_id=make_artifact_id(A_DJANGO_APP_CONFIG, node.name, anchor),
                type=A_DJANGO_APP_CONFIG,
                name=node.name,
                file_path=file_path,
                anchor=anchor,
                confidence="probable",
                evidence=[{"anchor": anchor, "note": f"class {node.name} inherits from AppConfig"}],
                meta={
                    "bases": bases,
                    "app_label": app_label,
                    "verbose_name": verbose_name,
                },
            )
        )
    return artifacts


def _node_repr(node: ast.AST) -> Optional[str]:
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _extract_settings_value(node: ast.AST) -> Any:
    s = _const_str(node)
    if s is not None:
        return s
    lst = _list_of_str(node)
    if lst is not None:
        return lst
    if isinstance(node, ast.Dict):
        keys: List[str] = []
        for key in node.keys:
            k = _const_str(key) if key is not None else None
            if k:
                keys.append(k)
        if keys:
            return {"keys": keys}
    return _node_repr(node)


def _extract_django_settings(tree: ast.Module, file_path: str) -> List[Artifact]:
    if not file_path.endswith("settings.py"):
        return []

    tracked = {
        "INSTALLED_APPS",
        "MIDDLEWARE",
        "AUTH_USER_MODEL",
        "DATABASES",
        "CACHES",
        "TEMPLATES",
        "REST_FRAMEWORK",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "CELERY_TASK_ALWAYS_EAGER",
    }

    artifacts: List[Artifact] = []
    for node in tree.body:
        target = None
        value_node = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
            value_node = node.value

        if not target or target not in tracked or value_node is None:
            continue

        anchor = _anchor_for_node(file_path, node)
        artifacts.append(
            Artifact(
                artifact_id=make_artifact_id(A_DJANGO_SETTINGS, target, anchor),
                type=A_DJANGO_SETTINGS,
                name=target,
                file_path=file_path,
                anchor=anchor,
                confidence="probable",
                evidence=[{"anchor": anchor, "note": f"{target} setting assignment"}],
                meta={"setting": target, "value": _extract_settings_value(value_node)},
            )
        )
    return artifacts


def _extract_requirements(file_path: str, raw_text: str) -> List[Artifact]:
    if not (
        file_path.endswith("requirements.txt")
        or "/requirements/" in file_path.replace("\\", "/")
        and file_path.endswith(".txt")
    ):
        return []

    artifacts: List[Artifact] = []
    for idx, line in enumerate(raw_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = stripped
        for sep in ("==", ">=", "<=", "~=", ">", "<"):
            if sep in name:
                name = name.split(sep, 1)[0].strip()
                break
        if name.startswith("-"):
            continue
        anchor = {
            "file_path": file_path,
            "start_line": idx,
            "start_col": 0,
            "end_line": idx,
            "end_col": 0,
        }
        artifacts.append(
            Artifact(
                artifact_id=make_artifact_id(A_REQUIREMENT, name or "requirement", anchor),
                type=A_REQUIREMENT,
                name=name or stripped,
                file_path=file_path,
                anchor=anchor,
                confidence="probable",
                evidence=[{"anchor": anchor, "note": "requirements entry"}],
                meta={"raw": stripped},
            )
        )
    return artifacts


def _extract_serializer_declared_fields(class_node: ast.ClassDef) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for stmt in class_node.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            field_name = stmt.targets[0].id
            if isinstance(stmt.value, ast.Call):
                callee = _get_full_attr_name(stmt.value.func)
                if not callee:
                    continue

                is_drf_field = callee.startswith("serializers.")
                validators = _extract_validators_from_call(stmt.value) if is_drf_field else []

                kwargs: Dict[str, Any] = {}
                for kw in stmt.value.keywords:
                    if kw.arg is None:
                        continue
                    if isinstance(kw.value, ast.Constant):
                        kwargs[kw.arg] = kw.value.value

                out.append(
                    {
                        "name": field_name,
                        "call": callee,
                        "is_drf_field": bool(is_drf_field),
                        "validators": validators,
                        "kwargs": kwargs,
                        "lineno": getattr(stmt, "lineno", None),
                    }
                )
    return out


def _extract_serializer_methods(class_node: ast.ClassDef) -> Dict[str, Any]:
    validators: List[Dict[str, Any]] = []
    overrides: List[str] = []
    for stmt in class_node.body:
        if isinstance(stmt, ast.FunctionDef):
            nm = stmt.name
            if nm == "validate" or nm.startswith("validate_"):
                validators.append({"name": nm, "lineno": getattr(stmt, "lineno", None)})
            if nm in ("create", "update", "to_representation"):
                overrides.append(nm)
    return {"validators": validators, "overrides": overrides}


def _extract_view_common_attrs(class_node: ast.ClassDef) -> Dict[str, Any]:
    out: Dict[str, Any] = {"queryset_model": None, "serializer_class": None, "permission_classes": None}

    for stmt in class_node.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            k = stmt.targets[0].id
            if k == "serializer_class":
                out["serializer_class"] = _get_full_attr_name(stmt.value)
            if k == "permission_classes":
                if isinstance(stmt.value, (ast.List, ast.Tuple)):
                    vals = []
                    for el in stmt.value.elts:
                        n = _get_full_attr_name(el)
                        if n:
                            vals.append(n)
                    out["permission_classes"] = vals
            if k == "queryset":
                if isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Attribute):
                    base = _get_full_attr_name(stmt.value.func.value)
                    if base and base.endswith(".objects"):
                        out["queryset_model"] = base[:-len(".objects")]
    return out


def _extract_get_serializer_class_targets(func: ast.FunctionDef) -> List[str]:
    targets: List[str] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Return):
            n = _get_full_attr_name(node.value)
            if n:
                targets.append(n)

    seen = set()
    uniq = []
    for t in targets:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def _extract_urlconf(tree: ast.Module, file_path: str) -> Tuple[List[Artifact], bool]:
    artifacts: List[Artifact] = []

    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            fn = _get_full_attr_name(call.func)
            if fn and fn.endswith(".register") and isinstance(call.func, ast.Attribute):
                obj = _get_full_attr_name(call.func.value)
                if obj and obj.endswith("router") or obj:
                    prefix = _const_str(call.args[0]) if call.args else None
                    viewset = _get_full_attr_name(call.args[1]) if len(call.args) >= 2 else None
                    basename = None
                    bnode = _kwarg(call, "basename")
                    if bnode:
                        basename = _const_str(bnode) or _get_full_attr_name(bnode)

                    anchor = _anchor_for_node(file_path, node)
                    artifacts.append(
                        Artifact(
                            artifact_id=make_artifact_id(A_ROUTER_REGISTER, f"{obj}.register", anchor),
                            type=A_ROUTER_REGISTER,
                            name=f"{obj}.register",
                            file_path=file_path,
                            anchor=anchor,
                            confidence="probable",
                            evidence=[{"anchor": anchor, "note": "router.register(...) call"}],
                            meta={"router": obj, "prefix": prefix, "viewset": viewset, "basename": basename},
                        )
                    )

        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "urlpatterns":
                anchor = _anchor_for_node(file_path, node)
                artifacts.append(
                    Artifact(
                        artifact_id=make_artifact_id(A_URLCONF, "urlpatterns", anchor),
                        type=A_URLCONF,
                        name="urlpatterns",
                        file_path=file_path,
                        anchor=anchor,
                        confidence="certain",
                        evidence=[{"anchor": anchor, "note": "urlpatterns assignment"}],
                        meta={},
                    )
                )
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    for el in node.value.elts:
                        if isinstance(el, ast.Call):
                            fn = _get_full_attr_name(el.func)
                            if fn in ("path", "re_path"):
                                route = _const_str(el.args[0]) if el.args else None
                                target = None
                                if len(el.args) >= 2:
                                    target = _get_full_attr_name(el.args[1]) or _const_str(el.args[1])
                                name = None
                                nnode = _kwarg(el, "name")
                                if nnode:
                                    name = _const_str(nnode)
                                pa = _anchor_for_node(file_path, el)
                                artifacts.append(
                                    Artifact(
                                        artifact_id=make_artifact_id(A_URL_PATTERN, route or "path", pa),
                                        type=A_URL_PATTERN,
                                        name=route or "path",
                                        file_path=file_path,
                                        anchor=pa,
                                        confidence="probable",
                                        evidence=[{"anchor": pa, "note": f"{fn}(...) in urlpatterns"}],
                                        meta={"fn": fn, "route": route, "target": target, "name": name},
                                    )
                                )
                            elif fn == "include":
                                pa = _anchor_for_node(file_path, el)
                                arg0 = el.args[0] if el.args else None
                                inc = _get_full_attr_name(arg0) if arg0 else None
                                artifacts.append(
                                    Artifact(
                                        artifact_id=make_artifact_id(A_URL_PATTERN, "include", pa),
                                        type=A_URL_PATTERN,
                                        name="include",
                                        file_path=file_path,
                                        anchor=pa,
                                        confidence="probable",
                                        evidence=[{"anchor": pa, "note": "include(...) in urlpatterns"}],
                                        meta={"include": inc},
                                    )
                                )

    return artifacts, bool(artifacts)


def _extract_admin(tree: ast.Module, file_path: str) -> List[Artifact]:
    artifacts: List[Artifact] = []

    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            fn = _get_full_attr_name(call.func)
            if fn == "admin.site.register":
                for arg in call.args:
                    model = _get_full_attr_name(arg) or _const_str(arg)
                    if not model:
                        continue
                    anchor = _anchor_for_node(file_path, node)
                    artifacts.append(
                        Artifact(
                            artifact_id=make_artifact_id(A_ADMIN_REGISTER, f"admin.site.register({model})", anchor),
                            type=A_ADMIN_REGISTER,
                            name=f"admin.site.register({model})",
                            file_path=file_path,
                            anchor=anchor,
                            confidence="certain",
                            evidence=[{"anchor": anchor, "note": "admin.site.register(...)"}],
                            meta={"model": model},
                        )
                    )

        if isinstance(node, ast.ClassDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and _get_full_attr_name(dec.func) == "admin.register":
                    model = _get_full_attr_name(dec.args[0]) if dec.args else None
                    if model:
                        anchor = _anchor_for_node(file_path, dec)
                        artifacts.append(
                            Artifact(
                                artifact_id=make_artifact_id(A_ADMIN_REGISTER, f"admin.register({model})", anchor),
                                type=A_ADMIN_REGISTER,
                                name=f"admin.register({model})",
                                file_path=file_path,
                                anchor=anchor,
                                confidence="probable",
                                evidence=[{"anchor": anchor, "note": "decorator @admin.register(...)"}],
                                meta={"model": model, "admin_class": node.name},
                            )
                        )
    return artifacts


def extract_artifacts_from_file(file_path: str, raw_text: str) -> List[Artifact]:
    artifacts: List[Artifact] = []

    artifacts.extend(_extract_requirements(file_path, raw_text))
    if artifacts:
        return artifacts

    try:
        tree = ast.parse(raw_text)
    except SyntaxError as e:
        anchor = {
            "file_path": file_path,
            "start_line": getattr(e, "lineno", 1) or 1,
            "start_col": 0,
            "end_line": getattr(e, "lineno", 1) or 1,
            "end_col": 0,
        }
        artifacts.append(
            Artifact(
                artifact_id=make_artifact_id(A_PARSE_ERROR, "parse_error", anchor),
                type=A_PARSE_ERROR,
                name="parse_error",
                file_path=file_path,
                anchor=anchor,
                confidence="certain",
                evidence=[{"anchor": anchor, "note": f"SyntaxError: {e.msg}"}],
                meta={"error": {"msg": e.msg, "lineno": getattr(e, "lineno", None), "offset": getattr(e, "offset", None)}},
            )
        )
        return artifacts

    aliases = _collect_import_aliases(tree)
    artifacts.extend(_extract_urlconf(tree, file_path)[0])
    artifacts.extend(_extract_admin(tree, file_path))
    artifacts.extend(_extract_celery_tasks(tree, file_path))
    artifacts.extend(
        _extract_redis_clients(
            tree,
            file_path,
            aliases["redis_module_aliases"],
            aliases["redis_class_aliases"],
        )
    )
    artifacts.extend(
        _extract_app_configs(
            tree,
            file_path,
            aliases["appconfig_module_aliases"],
            aliases["appconfig_class_aliases"],
        )
    )
    artifacts.extend(_extract_django_settings(tree, file_path))

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        class_name = node.name
        bases = _bases_as_names(node)
        class_anchor = _anchor_for_node(file_path, node)

        if _is_django_model(
            bases,
            aliases["model_module_aliases"],
            aliases["model_class_aliases"],
        ):
            fields = _extract_model_fields(
                node,
                aliases["model_module_aliases"],
                aliases["model_field_aliases"],
            )

            artifacts.append(
                Artifact(
                    artifact_id=make_artifact_id(A_DJANGO_MODEL, class_name, class_anchor),
                    type=A_DJANGO_MODEL,
                    name=class_name,
                    file_path=file_path,
                    anchor=class_anchor,
                    confidence="certain",
                    evidence=[{"anchor": class_anchor, "note": f"class {class_name} inherits from models.Model"}],
                    meta={"bases": bases, "fields": [{"name": f["name"], "type": f["type"]} for f in fields]},
                )
            )

            for f in fields:
                fa = {
                    "file_path": file_path,
                    "start_line": f.get("lineno") or class_anchor["start_line"],
                    "start_col": 0,
                    "end_line": f.get("lineno") or class_anchor["start_line"],
                    "end_col": 0,
                }
                artifacts.append(
                    Artifact(
                        artifact_id=make_artifact_id(A_MODEL_FIELD, f"{class_name}.{f['name']}", fa),
                        type=A_MODEL_FIELD,
                        name=f"{class_name}.{f['name']}",
                        file_path=file_path,
                        anchor=fa,
                        confidence="probable",
                        evidence=[{"anchor": fa, "note": f"model field {f['name']} = {f['type']}"}],
                        meta={
                            "model": class_name,
                            "field_name": f["name"],
                            "field_type": f["type"],
                            "validators": f.get("validators", []),
                            "related_model": f.get("related_model"),
                            "kwargs": f.get("kwargs", {}),
                        },
                    )
                )

        if _is_drf_serializer(bases):
            meta_model, meta_fields = _extract_meta_model_and_fields(node)
            declared_fields = _extract_serializer_declared_fields(node)
            methods = _extract_serializer_methods(node)

            artifacts.append(
                Artifact(
                    artifact_id=make_artifact_id(A_DRF_SERIALIZER, class_name, class_anchor),
                    type=A_DRF_SERIALIZER,
                    name=class_name,
                    file_path=file_path,
                    anchor=class_anchor,
                    confidence="certain",
                    evidence=[{"anchor": class_anchor, "note": f"class {class_name} is a DRF serializer"}],
                    meta={
                        "bases": bases,
                        "meta_model": meta_model,
                        "meta_fields": meta_fields,
                        "declared_fields": [{"name": f["name"], "call": f["call"]} for f in declared_fields],
                        "overrides": methods["overrides"],
                        "validators": [v["name"] for v in methods["validators"]],
                    },
                )
            )

            for f in declared_fields:
                fa = {
                    "file_path": file_path,
                    "start_line": f.get("lineno") or class_anchor["start_line"],
                    "start_col": 0,
                    "end_line": f.get("lineno") or class_anchor["start_line"],
                    "end_col": 0,
                }
                artifacts.append(
                    Artifact(
                        artifact_id=make_artifact_id(A_SERIALIZER_FIELD, f"{class_name}.{f['name']}", fa),
                        type=A_SERIALIZER_FIELD,
                        name=f"{class_name}.{f['name']}",
                        file_path=file_path,
                        anchor=fa,
                        confidence="probable",
                        evidence=[{"anchor": fa, "note": f"serializer declared field {f['name']}"}],
                        meta={
                            "serializer": class_name,
                            "field_name": f["name"],
                            "call": f["call"],
                            "is_drf_field": f["is_drf_field"],
                            "validators": f.get("validators", []),
                            "kwargs": f.get("kwargs", {}),
                        },
                    )
                )

            for v in methods["validators"]:
                va = {
                    "file_path": file_path,
                    "start_line": v.get("lineno") or class_anchor["start_line"],
                    "start_col": 0,
                    "end_line": v.get("lineno") or class_anchor["start_line"],
                    "end_col": 0,
                }
                artifacts.append(
                    Artifact(
                        artifact_id=make_artifact_id(A_SERIALIZER_VALIDATOR, f"{class_name}.{v['name']}", va),
                        type=A_SERIALIZER_VALIDATOR,
                        name=f"{class_name}.{v['name']}",
                        file_path=file_path,
                        anchor=va,
                        confidence="certain",
                        evidence=[{"anchor": va, "note": "serializer validate method"}],
                        meta={"serializer": class_name, "method": v["name"]},
                    )
                )

        if _is_drf_viewset(bases):
            common = _extract_view_common_attrs(node)
            methods = [s.name for s in node.body if isinstance(s, ast.FunctionDef)]
            serializer_targets: List[str] = []
            for s in node.body:
                if isinstance(s, ast.FunctionDef) and s.name == "get_serializer_class":
                    serializer_targets = _extract_get_serializer_class_targets(s)

            artifacts.append(
                Artifact(
                    artifact_id=make_artifact_id(A_DRF_VIEWSET, class_name, class_anchor),
                    type=A_DRF_VIEWSET,
                    name=class_name,
                    file_path=file_path,
                    anchor=class_anchor,
                    confidence="certain",
                    evidence=[{"anchor": class_anchor, "note": f"class {class_name} is a DRF ViewSet"}],
                    meta={"bases": bases, **common, "methods": methods, "get_serializer_class_targets": serializer_targets},
                )
            )

        if _is_drf_apiview_or_generic(bases):
            common = _extract_view_common_attrs(node)
            methods = [s.name for s in node.body if isinstance(s, ast.FunctionDef)]
            artifacts.append(
                Artifact(
                    artifact_id=make_artifact_id(A_DRF_APIVIEW, class_name, class_anchor),
                    type=A_DRF_APIVIEW,
                    name=class_name,
                    file_path=file_path,
                    anchor=class_anchor,
                    confidence="probable",
                    evidence=[{"anchor": class_anchor, "note": f"class {class_name} is a DRF APIView/generic view"}],
                    meta={"bases": bases, **common, "methods": methods},
                )
            )

    return artifacts


# -----------------------------
# Workspace-aware extract_all
# -----------------------------
def _load_blueprints_payload(blueprints_in: Any) -> Dict[str, Any]:
    """
    Accepts either:
      - dict payload (already loaded)
      - str path to JSON file
    Returns a dict payload.
    """
    if isinstance(blueprints_in, dict):
        return blueprints_in

    if isinstance(blueprints_in, str):
        with open(blueprints_in, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return obj
        raise TypeError(f"Blueprints JSON must be an object/dict. Got: {type(obj).__name__}")

    raise TypeError(f"blueprints_in must be dict or str path. Got: {type(blueprints_in).__name__}")

def extract_all(blueprints_in: Any, out_path: str) -> Dict[str, Any]:
    """
    blueprints_in can be:
      - path to blueprints json (str)
      - already loaded blueprints payload (dict)
    """
    blueprints_payload = _load_blueprints_payload(blueprints_in)

    artifacts: List[Artifact] = []

    # ✅ everything below should use blueprints_payload (dict)
    if isinstance(blueprints_payload.get("blueprints"), list) and blueprints_payload["blueprints"]:
        for info in blueprints_payload["blueprints"]:
            fp = info.get("file_path") or info.get("path")
            raw = info.get("raw_text")
            if fp is None:
                continue

            
            if raw is None:
                # Blueprint must be lossless in workspace mode
                raise RuntimeError(
                    f"Blueprint missing raw_text for file: {fp}. "
                    f"Enable blueprints.store_raw_text in config.json."
                )


            artifacts.extend(extract_artifacts_from_file(fp, raw))
    else:
        files = blueprints_payload.get("files", []) or []
        repo_root = blueprints_payload.get("repo_root") or blueprints_payload.get("root") or ""
        for info in files:
            fp = info.get("file_path") or info.get("path")
            abs_path = info.get("abs_path")

            if not abs_path:
                if repo_root and fp:
                    abs_path = os.path.join(repo_root, fp)
                else:
                    abs_path = fp

            if not abs_path or not fp:
                continue

            if not os.path.exists(abs_path):
                anchor = {"file_path": fp, "start_line": 1, "start_col": 0, "end_line": 1, "end_col": 0}
                artifacts.append(
                    Artifact(
                        artifact_id=make_artifact_id(A_PARSE_ERROR, "missing_file", anchor),
                        type=A_PARSE_ERROR,
                        name="missing_file",
                        file_path=fp,
                        anchor=anchor,
                        confidence="certain",
                        evidence=[{"anchor": anchor, "note": "file referenced by blueprint but missing on disk"}],
                        meta={"abs_path": abs_path},
                    )
                )
                continue

            raw = _safe_read(abs_path)
            artifacts.extend(extract_artifacts_from_file(fp, raw))

    payload = {
        "version": "crs-artifacts-v2",
        "blueprints": blueprints_in if isinstance(blueprints_in, str) else "(in-memory-payload)",
        "artifacts": [asdict(a) for a in artifacts],
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return payload

def build_workspace_artifacts(fs: Optional[WorkspaceFS] = None) -> Dict[str, Any]:
    """
    Main pipeline entrypoint:
      - loads blueprints from workspace state
      - extracts artifacts
      - saves artifacts into workspace state
    """
    fs = fs or WorkspaceFS()

    bp_path = fs.paths.blueprints_json
    if not os.path.exists(bp_path):
        raise FileNotFoundError(f"Blueprints not found: {bp_path}. Run blueprint builder first.")

    blueprints_payload = fs.read_json(bp_path) if hasattr(fs, "read_json") else json.loads(fs.read_text(bp_path))
    artifacts_payload = extract_all(blueprints_payload, fs)

    # Prefer dedicated helper if exists
    if hasattr(fs, "save_artifacts"):
        fs.save_artifacts(artifacts_payload)
    else:
        out_path = getattr(fs.paths, "artifacts_json", os.path.join(fs.paths.state_dir, "artifacts.json"))
        fs.write_json(out_path, artifacts_payload)

    return artifacts_payload


if __name__ == "__main__":
    payload = build_workspace_artifacts()
    fs = WorkspaceFS()
    out_path = getattr(fs.paths, "artifacts_json", os.path.join(fs.paths.state_dir, "artifacts.json"))
    print(f"✅ Wrote artifacts -> {out_path}")
    print(f"Artifacts: {len(payload.get('artifacts', []))}")
