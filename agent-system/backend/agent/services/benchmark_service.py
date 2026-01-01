import json
import math
import random
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
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
    counts = _derive_counts(summary_json)
    run_json["counts"] = counts
    total = counts.get("total", 0)
    executed = counts.get("executed", 0)
    run_json["progress"] = int(min(100, (executed / total) * 100)) if total else 0
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
    model_id = model.get("id")
    llm_model = None
    if model_id:
        llm_model = LLMModel.objects.select_related("provider").filter(id=model_id).first()

    for task in tasks:
        start_time = time.monotonic()
        error = None
        answer = None
        citations: List[str] = []
        trace = {
            "trace_id": f"benchmark-{uuid.uuid4().hex[:12]}",
            "mode": mode,
        }

        try:
            repository = _get_repository_for_task(task)
            if not repository:
                raise ValueError("Repository not found for benchmark task.")

            response = _run_read_task(
                repository=repository,
                task=task,
                mode=mode,
                llm_model=llm_model,
            )
            answer = response.get("answer")
            citations = response.get("citations", [])
            trace.update(response.get("trace", {}))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        latency_ms = int((time.monotonic() - start_time) * 1000)
        success = error is None and bool(answer)

        results.append(
            BenchmarkResult(
                task_id=task.task_id,
                success=success,
                latency_ms=latency_ms,
                error=error,
                details={
                    "answer": answer,
                    "citations": citations,
                    "trace": trace,
                    "mode": mode,
                    "model_id": model.get("model_id") or model.get("id"),
                },
            )
        )

    return results


def _get_repository_for_task(task: BenchmarkTask) -> Optional[Repository]:
    system_id = task.metadata.get("system_id")
    if not system_id:
        return None
    system = System.objects.filter(id=system_id).first()
    if not system:
        return None
    return _get_primary_repository(system)


def _run_read_task(
    *,
    repository: Repository,
    task: BenchmarkTask,
    mode: str,
    llm_model: Optional[LLMModel],
) -> Dict[str, Any]:
    from agent.crs_tools import CRSTools
    from agent.services.crs_runner import get_crs_summary
    from llm.router import get_llm_router

    router = get_llm_router()
    llm_client = _build_llm_client(router, llm_model)
    crs_tools = CRSTools(repository=repository)
    use_tools = _mode_uses_tools(mode)

    messages = [
        {
            "role": "system",
            "content": _build_system_prompt(repository, mode, get_crs_summary(repository), crs_tools),
        },
        {
            "role": "user",
            "content": task.prompt,
        },
    ]

    tool_results: List[str] = []
    citations: List[str] = []
    tool_trace: List[Dict[str, Any]] = []
    final_answer = ""

    for _ in range(3):
        response = llm_client.query(messages)
        content = response.get("content", "")
        if not use_tools:
            final_answer = content
            break

        tool_calls = crs_tools.parse_tool_calls(content)
        if not tool_calls:
            final_answer = content
            break

        for tool_call in tool_calls:
            tool_name = tool_call.get("name", "")
            tool_params = tool_call.get("parameters", {})
            result = crs_tools.execute_tool(tool_name, tool_params)
            tool_results.append(result)
            citations.extend(_extract_citations(result))
            tool_trace.append({"name": tool_name, "parameters": tool_params})

        messages.append({"role": "assistant", "content": content})
        messages.append(
            {
                "role": "user",
                "content": (
                    "Tool Results:\n\n"
                    f"{'\n\n'.join(tool_results)}\n\n"
                    "Now answer the user's original question using this data. Provide a clear response with citations."
                ),
            }
        )

    return {
        "answer": final_answer,
        "citations": sorted(set(citations)),
        "trace": {
            "tools_called": tool_trace,
            "provider": llm_client.model if hasattr(llm_client, "model") else None,
        },
    }


def _build_llm_client(router, llm_model: Optional[LLMModel]):
    from llm.router import LLMConfig

    if llm_model and llm_model.provider:
        provider = llm_model.provider
        config = LLMConfig(
            provider=provider.provider_type,
            model=llm_model.model_id,
            base_url=provider.base_url or None,
            api_key=provider.api_key or None,
            max_tokens=llm_model.metadata.get("max_tokens")
            or provider.metadata.get("max_tokens")
            or 4000,
            temperature=llm_model.metadata.get("temperature")
            or provider.metadata.get("temperature")
            or 0.7,
        )
        return router.client_for_config(config)

    return router.local_client


def _mode_uses_tools(mode: str) -> bool:
    if not mode:
        return True
    normalized = mode.lower()
    return any(token in normalized for token in ("crs", "rag", "tool", "tools", "search"))


def _build_system_prompt(
    repository: Repository,
    mode: str,
    summary: Dict[str, Any],
    crs_tools,
) -> str:
    tool_definitions = crs_tools.get_tool_definitions()
    status_message = summary.get("status")
    crs_status_context = f"""
# Repository CRS Status

- Repository: {repository.name}
- Status: {summary.get('status', 'unknown')}
- Django Models: ~{summary.get('artifacts', 0) // 4} (estimated)
- Total Artifacts: {summary.get('artifacts', 0)}
- Blueprint Files: {summary.get('blueprint_files', 0)}
- Relationships: {summary.get('relationships', 0)}

Execution mode: {mode or 'default'}
"""

    if status_message != "ready":
        return f"""You are analyzing a code repository.

CRS Status: Analysis incomplete ({summary.get('status', 'unknown')}).

# LIMITED MODE
- Semantic Search (SEARCH_CRS, CRS_RELATIONSHIPS) is unavailable.
- File Access (READ_FILE, LIST_ARTIFACTS) is AVAILABLE.

Please:
1. Use `LIST_ARTIFACTS` to find files/models (best effort).
2. Use `READ_FILE` to read code directly.
3. Determine if you can answer based on file contents.

---

{tool_definitions}

---

Now answer the user's question using the available tools."""

    return f"""You are a code repository assistant with access to CRS (Contextual Retrieval System) tools.

{crs_status_context}

# YOUR JOB

1. **PLAN** which tools to use
2. **REQUEST** tools in the JSON format below
3. **WAIT** for tool results
4. **ANSWER** the user's question with citations

---

{tool_definitions}

---

# CRITICAL: Inventory Questions

For "list/show all/what X exist" questions, you MUST use LIST_ARTIFACTS.
NEVER answer from memory or make assumptions.

Now answer the user's question using the appropriate tools."""


def _extract_citations(result: str) -> List[str]:
    citations = []
    for token in result.split():
        if ":" in token and "/" in token:
            cleaned = token.strip(".,;()[]")
            if ":" in cleaned:
                citations.append(cleaned)
    return citations


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



def _build_report_payload(
    run_json: Dict[str, Any],
    summary_json: Dict[str, Any],
    run_dir: Optional[Path] = None,
) -> Dict[str, Any]:
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
    results_payloads = _load_results_payloads(run_dir)
    task_index = {task.get("task_id"): task for task in run_json.get("task_suite", [])}
    computed_metrics = _compute_report_metrics(results_payloads, task_index)
    trace_links = _build_trace_links(run_dir, run_json.get("run_id"))

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
        "summary_metrics": {
            **summary_metrics,
            "latency": computed_metrics["latency_summary"],
            "correctness": computed_metrics["correctness_summary"],
            "grounding": computed_metrics["grounding_summary"],
        },
        "model_ranking": summary_json.get("model_ranking", []),
        "crs_lag": summary_json.get("crs_lag", []),
        "failure_taxonomy": computed_metrics["failure_taxonomy"],
        "write_verification": computed_metrics["write_verification"],
        "crs_backlog": computed_metrics["crs_backlog"],
        "lag_taxonomy": computed_metrics["lag_taxonomy"],
        "chart_metrics": computed_metrics["chart_metrics"],
        "trace_links": trace_links,
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


def _load_results_payloads(run_dir: Optional[Path]) -> List[Dict[str, Any]]:
    if not run_dir or not run_dir.exists():
        return []
    payloads = []
    for path in run_dir.glob("**/results.json"):
        payload = _load_json(path)
        if payload:
            payloads.append(payload)
    return payloads


def _percentile(values: List[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[int(position)])
    weight = position - lower
    return float(values[lower] + (values[upper] - values[lower]) * weight)


def _mean(values: Iterable[float]) -> Optional[float]:
    values = list(values)
    if not values:
        return None
    return sum(values) / len(values)


def _compute_report_metrics(
    results_payloads: List[Dict[str, Any]],
    task_index: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    all_results = []
    failure_taxonomy = {
        "retrieval_misses": 0,
        "representation_drift": 0,
        "ambiguous_instructions": 0,
    }
    write_verification = {
        "verified": 0,
        "failed_tests": 0,
        "manual_review": 0,
    }

    for payload in results_payloads:
        for result in payload.get("results", []):
            all_results.append(result)
            error_text = (result.get("error") or "").lower()
            if "retrieval" in error_text:
                failure_taxonomy["retrieval_misses"] += 1
            if "representation" in error_text or "drift" in error_text:
                failure_taxonomy["representation_drift"] += 1
            if "ambiguous" in error_text:
                failure_taxonomy["ambiguous_instructions"] += 1

            task_info = task_index.get(result.get("task_id"))
            if task_info and task_info.get("task_type") == "write":
                success = result.get("success")
                if success is True:
                    write_verification["verified"] += 1
                elif success is False:
                    if "test" in error_text:
                        write_verification["failed_tests"] += 1
                    else:
                        write_verification["manual_review"] += 1
                else:
                    write_verification["manual_review"] += 1

    latencies = [result.get("latency_ms") for result in all_results if result.get("latency_ms") is not None]
    scored = [result for result in all_results if result.get("success") is not None]
    failures = [result for result in scored if result.get("success") is False or result.get("error")]

    overall_error_rate = (len(failures) / len(scored)) if scored else None

    per_task_breakdown = []
    task_results: Dict[str, List[Dict[str, Any]]] = {}
    for result in all_results:
        task_results.setdefault(result.get("task_id"), []).append(result)

    for task_id, results in task_results.items():
        task_info = task_index.get(task_id, {})
        task_latencies = [res.get("latency_ms") for res in results if res.get("latency_ms") is not None]
        task_scored = [res for res in results if res.get("success") is not None]
        task_failures = [res for res in task_scored if res.get("success") is False or res.get("error")]
        per_task_breakdown.append(
            {
                "task_id": task_id,
                "task_type": task_info.get("task_type"),
                "task_pk": (task_info.get("metadata") or {}).get("task_pk"),
                "total": len(results),
                "scored": len(task_scored),
                "success_rate": (len(task_scored) - len(task_failures)) / len(task_scored) if task_scored else None,
                "error_rate": (len(task_failures) / len(task_scored)) if task_scored else None,
                "latency_p50_ms": _percentile(task_latencies, 0.5),
                "latency_p95_ms": _percentile(task_latencies, 0.95),
            }
        )

    lag_taxonomy = [
        {"tag": "retrieval", "count": failure_taxonomy["retrieval_misses"], "backlog_item": "index_gaps"},
        {"tag": "representation", "count": failure_taxonomy["representation_drift"], "backlog_item": "prompt_updates"},
        {"tag": "ambiguous", "count": failure_taxonomy["ambiguous_instructions"], "backlog_item": "workflow_changes"},
    ]
    crs_backlog = {
        "index_gaps": failure_taxonomy["retrieval_misses"],
        "prompt_updates": failure_taxonomy["representation_drift"],
        "workflow_changes": failure_taxonomy["ambiguous_instructions"],
    }

    latency_summary = {
        "p50_ms": _percentile(latencies, 0.5),
        "p95_ms": _percentile(latencies, 0.95),
        "avg_ms": _mean(latencies),
    }
    correctness_summary = {
        "score": None,
        "error_rate": overall_error_rate,
    }
    grounding_summary = {
        "score": None,
        "error_rate": overall_error_rate,
    }

    chart_metrics = {
        "latency_ms": {
            "p50": latency_summary["p50_ms"],
            "p95": latency_summary["p95_ms"],
            "avg": latency_summary["avg_ms"],
        },
        "error_rate": {
            "overall": overall_error_rate,
        },
        "per_task_breakdown": per_task_breakdown,
    }

    return {
        "latency_summary": latency_summary,
        "correctness_summary": correctness_summary,
        "grounding_summary": grounding_summary,
        "failure_taxonomy": failure_taxonomy,
        "write_verification": write_verification,
        "crs_backlog": crs_backlog,
        "lag_taxonomy": lag_taxonomy,
        "chart_metrics": chart_metrics,
    }


def _build_trace_links(run_dir: Optional[Path], run_id: Optional[str]) -> List[Dict[str, Any]]:
    if not run_dir or not run_dir.exists():
        return []
    trace_links = [
        {"crs_id": run_id, "file_path": str(run_dir / "run.json"), "label": "run.json"},
        {"crs_id": run_id, "file_path": str(run_dir / "summary.json"), "label": "summary.json"},
    ]
    for path in run_dir.glob("**/results.json"):
        trace_links.append(
            {"crs_id": run_id, "file_path": str(path), "label": "results.json"}
        )
    return trace_links


def _derive_counts(summary_json: Dict[str, Any]) -> Dict[str, int]:
    total = 0
    executed = 0
    skipped = 0
    succeeded_estimate = 0.0
    for summary in summary_json.get("model_summaries", {}).values():
        mode_metrics = summary.get("mode_metrics", {})
        if mode_metrics:
            for metrics in mode_metrics.values():
                total_cases = metrics.get("total_cases", metrics.get("total", 0))
                executed_cases = metrics.get("executed_cases", metrics.get("scored", 0))
                skipped_cases = metrics.get("skipped_cases", total_cases - executed_cases)
                total += total_cases
                executed += executed_cases
                skipped += skipped_cases
                success_rate = metrics.get("success_rate_executed", metrics.get("success_rate"))
                if success_rate is not None and executed_cases:
                    succeeded_estimate += success_rate * executed_cases
        else:
            total_cases = summary.get("total_cases", summary.get("total_results", 0))
            executed_cases = summary.get("executed_cases", 0)
            skipped_cases = summary.get("skipped_cases", total_cases - executed_cases)
            total += total_cases
            executed += executed_cases
            skipped += skipped_cases
            success_rate = summary.get("success_rate_executed")
            if success_rate is not None and executed_cases:
                succeeded_estimate += success_rate * executed_cases
    succeeded = int(round(succeeded_estimate)) if executed else 0
    failed = max(executed - succeeded, 0)
    return {
        "queued": 0,
        "running": 0,
        "succeeded": succeeded,
        "failed": failed,
        "total": total,
        "executed": executed,
        "skipped": skipped,
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
