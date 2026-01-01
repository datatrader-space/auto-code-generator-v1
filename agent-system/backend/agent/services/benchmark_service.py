import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys

from django.conf import settings

from agent.models import LLMModel, Repository, System, Task, User
from agent.services.crs_runner import _build_crs_workspace, _workspace_base_dirs

_crs_dir = Path(settings.BASE_DIR).parent / "crs"
if str(_crs_dir) not in sys.path:
    sys.path.insert(0, str(_crs_dir))

from core.benchmark_runner import BenchmarkResult, BenchmarkRunner, BenchmarkTask
from core.fs import WorkspaceFS


@dataclass
class BenchmarkRunPayload:
    run_id: str
    status: str
    started_at: str
    completed_at: Optional[str]
    summary: Dict[str, Any]
    counts: Dict[str, int]


@dataclass
class SyntheticTask:
    title: str
    description: str
    task_id: str


def run_benchmark(
    *,
    system: System,
    models: List[LLMModel],
    agent_modes: List[str],
    task_types: List[str],
    suite_size: int,
    user: User,
) -> BenchmarkRunPayload:
    repository = _get_primary_repository(system)
    workspace = _build_crs_workspace(repository)
    fs = WorkspaceFS(config_path=str(workspace.config_path))

    tasks = _build_task_suite(system, task_types, suite_size)
    model_payloads = [_serialize_model(model) for model in models]
    modes_by_model = {
        str(model.id): list(agent_modes)
        for model in models
    }

    runner = BenchmarkRunner(fs, _execute_task_suite)
    run_payload = runner.run(
        run_id=None,
        models=model_payloads,
        modes_by_model=modes_by_model,
        tasks=tasks,
        metadata={
            "system_id": system.id,
            "system_name": system.name,
            "user_id": user.id,
        },
    )

    run_id = run_payload["run_id"]
    _update_benchmark_index(user, fs.run_dir(run_id), system, run_id)

    total_modes = len(agent_modes) * max(1, len(models))
    total_tasks = len(tasks) * max(1, total_modes)
    counts = {
        "queued": 0,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "total": total_tasks,
    }

    return BenchmarkRunPayload(
        run_id=run_id,
        status=run_payload["status"],
        started_at=run_payload["started_at"],
        completed_at=run_payload.get("completed_at"),
        summary=run_payload["summary"],
        counts=counts,
    )


def load_benchmark_run(user: User, run_id: str) -> Dict[str, Any]:
    run_dir = _find_run_dir(user, run_id)
    if not run_dir:
        raise FileNotFoundError(f"Run {run_id} not found.")
    run_json = _load_json(run_dir / "run.json")
    summary_json = _load_json(run_dir / "summary.json")
    run_json["summary"] = summary_json
    run_json["counts"] = _derive_counts(summary_json)
    run_json["progress"] = 100 if run_json.get("status") == "completed" else 0
    return run_json


def list_benchmark_reports(user: User) -> List[Dict[str, Any]]:
    reports = []
    for entry in _load_benchmark_index(user):
        run_dir = Path(entry["run_dir"])
        run_json = _load_json(run_dir / "run.json")
        summary_json = _load_json(run_dir / "summary.json")
        reports.append(_build_report_payload(run_json, summary_json, run_dir))
    reports.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return reports


def get_benchmark_report(user: User, run_id: str) -> Dict[str, Any]:
    run_dir = _find_run_dir(user, run_id)
    if not run_dir:
        raise FileNotFoundError(f"Run {run_id} not found.")
    run_json = _load_json(run_dir / "run.json")
    summary_json = _load_json(run_dir / "summary.json")
    return _build_report_payload(run_json, summary_json, run_dir)


def list_benchmark_downloads(user: User, run_id: str) -> List[Dict[str, str]]:
    run_dir = _find_run_dir(user, run_id)
    if not run_dir:
        raise FileNotFoundError(f"Run {run_id} not found.")
    return _collect_downloads(run_dir)


def get_benchmark_download(user: User, run_id: str, file_path: str) -> Path:
    run_dir = _find_run_dir(user, run_id)
    if not run_dir:
        raise FileNotFoundError(f"Run {run_id} not found.")
    downloads = {entry["path"]: entry for entry in _collect_downloads(run_dir)}
    if file_path not in downloads:
        raise ValueError("Requested artifact is not available for download.")
    resolved = (run_dir / file_path).resolve()
    if not resolved.is_file() or run_dir.resolve() not in resolved.parents:
        raise FileNotFoundError("Requested artifact not found.")
    return resolved


def _build_task_suite(system: System, task_types: List[str], suite_size: int) -> List[BenchmarkTask]:
    tasks = list(Task.objects.filter(system=system).order_by("-created_at"))
    filtered = []
    for task in tasks:
        inferred = _infer_task_type(task)
        if inferred in task_types:
            filtered.append(task)

    rng = random.Random(system.id)
    rng.shuffle(filtered)
    selected = filtered[: suite_size or 1]

    if not selected:
        selected = [
            SyntheticTask(
                title=f"Generated {task_type} task",
                description=f"Generated {task_type} task for benchmarking.",
                task_id=f"generated-{idx}",
            )
            for idx, task_type in enumerate((task_types or ["read"]), start=1)
        ][: max(1, suite_size or 1)]

    suite = []
    for idx, task in enumerate(selected, start=1):
        suite.append(
            BenchmarkTask(
                task_id=getattr(task, "task_id", None) or f"generated-{idx}",
                task_type=_infer_task_type(task),
                prompt=f"{task.title or ''}\n\n{task.description}",
                metadata={
                    "system_id": system.id,
                    "task_pk": getattr(task, "id", None),
                },
            )
        )
    return suite


def _execute_task_suite(
    model: Dict[str, Any],
    mode: str,
    tasks: List[BenchmarkTask],
) -> List[BenchmarkResult]:
    results = []
    for task in tasks:
        results.append(
            BenchmarkResult(
                task_id=task.task_id,
                success=None,
                latency_ms=None,
                error=None,
                details={
                    "status": "skipped",
                    "mode": mode,
                    "model_id": model.get("model_id") or model.get("id"),
                },
            )
        )
    return results


def _infer_task_type(task: Any) -> str:
    title = (getattr(task, "title", "") or "").lower()
    description = (getattr(task, "description", "") or "").lower()
    write_keywords = ("write", "update", "modify", "change", "fix", "create", "add", "remove")
    if any(keyword in title or keyword in description for keyword in write_keywords):
        return "write"
    return "read"


def _serialize_model(model: LLMModel) -> Dict[str, Any]:
    return {
        "id": model.id,
        "model_id": model.model_id,
        "name": model.name,
        "provider": model.provider.name,
        "provider_id": model.provider_id,
    }


def _build_report_payload(run_json: Dict[str, Any], summary_json: Dict[str, Any], run_dir: Path) -> Dict[str, Any]:
    models = run_json.get("models", [])
    model_names = [model.get("name") or model.get("model_id") for model in models]
    modes = run_json.get("modes_by_model", {})
    task_types = [task.get("task_type") for task in run_json.get("task_suite", [])]
    summary_metrics = _summarize_scores(summary_json, run_json)
    failed_cases = _collect_failed_cases(run_dir, run_json)
    downloads = _collect_downloads(run_dir)
    model_lookup = [
        {
            "model_id": str(model.get("model_id") or model.get("id") or ""),
            "name": model.get("name") or model.get("model_id") or model.get("id"),
            "provider": model.get("provider"),
        }
        for model in models
    ]

    return {
        "id": run_json.get("run_id"),
        "title": run_json.get("metadata", {}).get("title"),
        "created_at": run_json.get("started_at"),
        "system": run_json.get("metadata", {}).get("system_id"),
        "system_name": run_json.get("metadata", {}).get("system_name"),
        "models": model_lookup,
        "models_summary": ", ".join(model_names),
        "model_count": len(models),
        "mode_summary": ", ".join(sorted({mode for modes in modes.values() for mode in modes})),
        "agent_modes": sorted({mode for modes in modes.values() for mode in modes}),
        "task_summary": ", ".join(sorted(set(task_types))) if task_types else None,
        "task_types": sorted(set(task_types)),
        "summary_metrics": summary_metrics,
        "model_summaries": summary_json.get("model_summaries", {}),
        "model_ranking": summary_json.get("model_ranking", []),
        "crs_lag": summary_json.get("crs_lag", []),
        "failed_cases": failed_cases,
        "downloads": downloads,
        "failure_taxonomy": {
            "retrieval_misses": 0,
            "representation_drift": 0,
            "ambiguous_instructions": 0,
        },
        "write_verification": {
            "verified": 0,
            "failed_tests": 0,
            "manual_review": 0,
        },
        "crs_backlog": {
            "index_gaps": 0,
            "prompt_updates": 0,
            "workflow_changes": 0,
        },
    }


def _summarize_scores(summary_json: Dict[str, Any], run_json: Dict[str, Any]) -> Dict[str, Any]:
    model_summaries = summary_json.get("model_summaries", {})
    scores = [summary.get("overall_score") for summary in model_summaries.values() if summary.get("overall_score") is not None]
    overall_score = sum(scores) / len(scores) if scores else None

    return {
        "overall_score": overall_score,
        "read_success": None,
        "write_success": None,
    }


def _derive_counts(summary_json: Dict[str, Any]) -> Dict[str, int]:
    total = 0
    succeeded = 0
    failed = 0
    for summary in summary_json.get("model_summaries", {}).values():
        total += summary.get("total_results", 0)
    return {
        "queued": 0,
        "running": 0,
        "succeeded": succeeded,
        "failed": failed,
        "total": total,
    }


def _get_primary_repository(system: System) -> Repository:
    repository = system.repositories.order_by("created_at").first()
    if not repository:
        raise ValueError("System has no repositories configured.")
    return repository


def _benchmark_index_path(user: User) -> Path:
    base_dirs = _workspace_base_dirs()
    return base_dirs["crs_root"] / str(user.id) / "benchmark_index.json"


def _load_benchmark_index(user: User) -> List[Dict[str, Any]]:
    path = _benchmark_index_path(user)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _update_benchmark_index(user: User, run_dir: str, system: System, run_id: str) -> None:
    path = _benchmark_index_path(user)
    index = _load_benchmark_index(user)
    payload = {
        "run_id": run_id,
        "run_dir": run_dir,
        "system_id": system.id,
        "system_name": system.name,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    index = [entry for entry in index if entry.get("run_id") != run_id]
    index.append(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2), encoding="utf-8")


def _find_run_dir(user: User, run_id: str) -> Optional[Path]:
    index = _load_benchmark_index(user)
    for entry in index:
        if entry.get("run_id") == run_id:
            return Path(entry["run_dir"])
    return None


def _collect_failed_cases(run_dir: Path, run_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    task_lookup = {
        task.get("task_id"): task
        for task in run_json.get("task_suite", [])
    }
    failed_cases = []
    for result_path in run_dir.rglob("results.json"):
        payload = _load_json(result_path)
        results = payload.get("results", [])
        for result in results:
            success = result.get("success")
            error = result.get("error")
            if success is False or error:
                task_id = result.get("task_id")
                task = task_lookup.get(task_id, {})
                failed_cases.append(
                    {
                        "model_id": payload.get("model_id"),
                        "mode": payload.get("mode"),
                        "task_id": task_id,
                        "task_type": task.get("task_type"),
                        "prompt": task.get("prompt"),
                        "error": error,
                        "details": result.get("details", {}),
                    }
                )
    return failed_cases


def _collect_downloads(run_dir: Path) -> List[Dict[str, str]]:
    downloads = []
    for filename, label, kind in (
        ("run.jsonl", "run.jsonl", "run_jsonl"),
        ("context_trace.json", "context_trace.json", "context_trace"),
    ):
        path = run_dir / filename
        if path.exists():
            downloads.append(
                {
                    "label": label,
                    "path": filename,
                    "kind": kind,
                }
            )

    diff_candidates = []
    for diff_path in run_dir.rglob("*diff*"):
        if diff_path.is_file():
            try:
                relative = diff_path.relative_to(run_dir).as_posix()
            except ValueError:
                continue
            diff_candidates.append(relative)

    for relative in sorted(set(diff_candidates))[:50]:
        downloads.append(
            {
                "label": relative,
                "path": relative,
                "kind": "diff",
            }
        )
    return downloads


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
