import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

from core.fs import WorkspaceFS


@dataclass(frozen=True)
class BenchmarkTask:
    task_id: str
    task_type: str
    prompt: str
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class BenchmarkResult:
    task_id: str
    success: Optional[bool]
    latency_ms: Optional[int]
    error: Optional[str]
    details: Dict[str, Any]


class BenchmarkRunner:
    def __init__(
        self,
        fs: WorkspaceFS,
        executor: Callable[[Dict[str, Any], str, List[BenchmarkTask]], List[BenchmarkResult]],
    ) -> None:
        self.fs = fs
        self.executor = executor

    def run(
        self,
        *,
        run_id: Optional[str],
        models: List[Dict[str, Any]],
        modes_by_model: Dict[str, List[str]],
        tasks: List[BenchmarkTask],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not tasks:
            raise ValueError("Benchmark requires at least one task in the suite.")

        run_id = run_id or self.fs.new_run_id(prefix="benchmark")
        run_started = time.time()
        run_meta = {
            "run_id": run_id,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(run_started)),
            "models": models,
            "modes_by_model": modes_by_model,
            "task_suite": [self._task_to_payload(task) for task in tasks],
            "metadata": metadata or {},
            "status": "running",
        }
        self.fs.write_run_json(run_id, "run.json", run_meta)

        results_index: Dict[str, Dict[str, Dict[str, Any]]] = {}

        for model in models:
            model_id = str(model.get("model_id") or model.get("id") or "unknown")
            model_key = self._safe_segment(model_id)
            modes = modes_by_model.get(model_id, modes_by_model.get(str(model.get("id")), []))
            for mode in modes:
                try:
                    results = self.executor(model, mode, tasks)
                    metrics = self._compute_metrics(results)
                    payload = {
                        "run_id": run_id,
                        "model_id": model_id,
                        "mode": mode,
                        "results": [self._result_to_payload(result) for result in results],
                        "metrics": metrics,
                        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                except Exception as exc:  # pragma: no cover - defensive logging
                    payload = {
                        "run_id": run_id,
                        "model_id": model_id,
                        "mode": mode,
                        "results": [],
                        "metrics": {
                            "success_rate": None,
                            "avg_latency_ms": None,
                            "total": 0,
                            "scored": 0,
                            "total_cases": 0,
                            "executed_cases": 0,
                            "skipped_cases": 0,
                            "success_rate_executed": None,
                            "avg_latency_ms_executed": None,
                        },
                        "error": f"{type(exc).__name__}: {exc}",
                        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }

                model_dir = os.path.join(self.fs.run_dir(run_id), model_key, self._safe_segment(mode))
                self.fs.backend.makedirs(model_dir)
                self.fs.write_json(os.path.join(model_dir, "results.json"), payload)
                results_index.setdefault(model_id, {})[mode] = payload

        summary = self._aggregate_results(run_id, results_index)
        run_meta["status"] = "completed"
        run_meta["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        run_meta["summary"] = summary
        self.fs.write_run_json(run_id, "run.json", run_meta)
        self.fs.write_run_json(run_id, "summary.json", summary)

        return {
            "run_id": run_id,
            "status": run_meta["status"],
            "started_at": run_meta["started_at"],
            "completed_at": run_meta["completed_at"],
            "summary": summary,
        }

    def _task_to_payload(self, task: BenchmarkTask) -> Dict[str, Any]:
        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "prompt": task.prompt,
            "metadata": task.metadata,
        }

    def _result_to_payload(self, result: BenchmarkResult) -> Dict[str, Any]:
        return {
            "task_id": result.task_id,
            "success": result.success,
            "latency_ms": result.latency_ms,
            "error": result.error,
            "details": result.details,
        }

    def _compute_metrics(self, results: Iterable[BenchmarkResult]) -> Dict[str, Any]:
        successes = 0
        scored = 0
        latencies = []
        executed_latencies = []
        total = 0
        for result in results:
            total += 1
            if result.success is not None:
                scored += 1
                if result.success:
                    successes += 1
                if result.latency_ms is not None:
                    executed_latencies.append(result.latency_ms)
            if result.latency_ms is not None:
                latencies.append(result.latency_ms)

        success_rate = (successes / scored) if scored else None
        avg_latency = sum(latencies) / len(latencies) if latencies else None
        avg_latency_executed = (
            sum(executed_latencies) / len(executed_latencies) if executed_latencies else None
        )
        return {
            "success_rate": success_rate,
            "avg_latency_ms": avg_latency,
            "total": total,
            "scored": scored,
            "total_cases": total,
            "executed_cases": scored,
            "skipped_cases": total - scored,
            "success_rate_executed": success_rate,
            "avg_latency_ms_executed": avg_latency_executed,
        }

    def _aggregate_results(self, run_id: str, results_index: Dict[str, Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
        model_summaries: Dict[str, Dict[str, Any]] = {}
        for model_id, mode_payloads in results_index.items():
            mode_metrics = {}
            success_rates = []
            latencies = []
            total_results = 0
            total_cases = 0
            executed_cases = 0
            skipped_cases = 0
            executed_successes = 0.0
            executed_latency_total = 0.0
            for mode, payload in mode_payloads.items():
                metrics = payload.get("metrics", {})
                mode_metrics[mode] = metrics
                if metrics.get("success_rate") is not None:
                    success_rates.append(metrics["success_rate"])
                if metrics.get("avg_latency_ms") is not None:
                    latencies.append(metrics["avg_latency_ms"])
                total_value = metrics.get("total_cases", metrics.get("total", 0))
                executed_value = metrics.get("executed_cases", metrics.get("scored", 0))
                skipped_value = metrics.get("skipped_cases", total_value - executed_value)
                total_results += total_value
                total_cases += total_value
                executed_cases += executed_value
                skipped_cases += skipped_value
                success_rate_executed = metrics.get("success_rate_executed")
                if success_rate_executed is None:
                    success_rate_executed = metrics.get("success_rate")
                if success_rate_executed is not None and executed_value:
                    executed_successes += success_rate_executed * executed_value
                avg_latency_executed = metrics.get("avg_latency_ms_executed")
                if avg_latency_executed is not None and executed_value:
                    executed_latency_total += avg_latency_executed * executed_value

            overall_score = sum(success_rates) / len(success_rates) if success_rates else None
            avg_latency = sum(latencies) / len(latencies) if latencies else None
            success_rate_executed = (
                (executed_successes / executed_cases) if executed_cases else None
            )
            avg_latency_ms_executed = (
                (executed_latency_total / executed_cases) if executed_cases else None
            )
            model_summaries[model_id] = {
                "overall_score": overall_score,
                "avg_latency_ms": avg_latency,
                "total_results": total_results,
                "total_cases": total_cases,
                "executed_cases": executed_cases,
                "skipped_cases": skipped_cases,
                "success_rate_executed": success_rate_executed,
                "avg_latency_ms_executed": avg_latency_ms_executed,
                "mode_metrics": mode_metrics,
            }

        ranking = sorted(
            (
                {
                    "model_id": model_id,
                    "overall_score": summary["overall_score"],
                    "avg_latency_ms": summary["avg_latency_ms"],
                }
                for model_id, summary in model_summaries.items()
            ),
            key=lambda item: (
                item["overall_score"] is None,
                -(item["overall_score"] or 0),
                item["avg_latency_ms"] or float("inf"),
            ),
        )
        for idx, item in enumerate(ranking, start=1):
            item["rank"] = idx

        crs_lag = []
        for model_id, summary in model_summaries.items():
            mode_metrics = summary.get("mode_metrics", {})
            crs_latencies = []
            non_crs_latencies = []
            for mode, metrics in mode_metrics.items():
                latency = metrics.get("avg_latency_ms")
                if latency is None:
                    continue
                if "crs" in mode:
                    crs_latencies.append(latency)
                else:
                    non_crs_latencies.append(latency)
            crs_avg = sum(crs_latencies) / len(crs_latencies) if crs_latencies else None
            non_crs_avg = sum(non_crs_latencies) / len(non_crs_latencies) if non_crs_latencies else None
            lag = None
            if crs_avg is not None and non_crs_avg is not None:
                lag = crs_avg - non_crs_avg
            crs_lag.append(
                {
                    "model_id": model_id,
                    "crs_avg_latency_ms": crs_avg,
                    "non_crs_avg_latency_ms": non_crs_avg,
                    "lag_ms": lag,
                }
            )

        return {
            "run_id": run_id,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model_summaries": model_summaries,
            "model_ranking": ranking,
            "crs_lag": crs_lag,
        }

    def _safe_segment(self, value: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", value)
        return safe or "unknown"
