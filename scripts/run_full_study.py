"""Checkpointed full-study runner.

The interactive CLI writes a large per-case result. This runner executes the
same paired simulator core one replication at a time, stores only run-level
arm summaries and paired deltas, and checkpoints after every batch. It is
therefore resumable without pretending that a partial study is complete.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from careloop.simulator import SimulationConfig, Simulator, load_parameters  # noqa: E402


ARMS = Simulator.ARMS


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _interval(values: list[float], clamp: bool = False) -> dict[str, Any]:
    if not values:
        return {"mean": None, "lower": None, "upper": None, "n": 0}
    mean = sum(values) / len(values)
    if len(values) == 1:
        margin = 0.0
    else:
        variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        margin = 1.96 * (variance / len(values)) ** 0.5
    lower, upper = mean - margin, mean + margin
    if clamp:
        lower, upper = max(0.0, lower), min(1.0, upper)
    return {"mean": round(mean, 6), "lower": round(lower, 6), "upper": round(upper, 6), "n": len(values)}


def _aggregate(checkpoint: dict[str, Any]) -> dict[str, Any]:
    run_summaries = checkpoint["run_summaries"]
    arms_to_report = tuple(checkpoint["config"]["arms"])
    intervals: dict[str, Any] = {"confidence_level": 0.95, "method": "normal_approximation", "arms": {}, "paired": {}}
    metrics = (
        "closure_rate", "result_flag_rate", "owner_coverage_rate", "teach_back_rate",
        "unknown_rate", "evidence_rate", "consult_without_referral_rate",
        "named_owner_documented_closure_within_sla_rate", "closure_within_sla_rate",
        "workload_hours", "backlog_events", "fatigue_alerts",
    )
    for arm in arms_to_report:
        intervals["arms"][arm] = {}
        for metric in metrics:
            values = [float(run["arms"][arm].get(metric, 0.0)) for run in run_summaries]
            intervals["arms"][arm][metric] = _interval(values, clamp=metric.endswith("rate"))
    paired_keys = ("closure_rate_delta", "owner_coverage_rate_delta", "teach_back_rate_delta")
    for metric in paired_keys:
        intervals["paired"][metric] = _interval([float(row[metric]) for row in checkpoint["paired_differences"]])
    latest: dict[str, Any] = {}
    for arm in arms_to_report:
        latest[arm] = {}
        for metric in metrics:
            values = [float(run["arms"][arm].get(metric, 0.0)) for run in run_summaries]
            latest[arm][metric] = round(sum(values) / len(values), 6) if values else None
    return {
        "status": "complete" if checkpoint["completed_runs"] >= checkpoint["config"]["runs"] else "partial",
        "config": checkpoint["config"],
        "completed_runs": checkpoint["completed_runs"],
        "parameters": checkpoint["parameters"],
        "summary": {"arms": latest},
        "intervals": intervals,
        "paired_differences": checkpoint["paired_differences"],
        "run_summaries": run_summaries,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limitation": "This is a workflow simulation, not evidence of real clinical outcomes.",
    }


def _run_replication(payload: tuple[int, int, int, int, dict[str, Any], bool]) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Run one paired replication in a worker process."""

    run_index, cohort_size, seed, virtual_days, parameters, core_only = payload
    simulation = Simulator(SimulationConfig(
        cohort_size=cohort_size,
        runs=1,
        seed=seed + run_index - 1,
        virtual_days=virtual_days,
        bounded=True,
    ), parameters)
    if core_only:
        simulation.ARMS = ("Arm A", "B-full")
    result = simulation._run_core()
    run_arms = ("Arm A", "B-full") if core_only else ARMS
    arms = {arm: result.summary["arms"][arm] for arm in run_arms}
    return run_index, arms, {"run": run_index, **result.paired_differences[0]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the checkpointed CareLoop full study")
    parser.add_argument("--cohort-size", type=int, default=10000)
    parser.add_argument("--runs", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20261019)
    parser.add_argument("--virtual-days", type=int, default=90)
    parser.add_argument("--batch-runs", type=int, default=1)
    parser.add_argument("--workers", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    parser.add_argument("--core-only", action="store_true", help="run the full 10,000 x 500 study for Arm A and B-full only")
    parser.add_argument("--output", type=Path, default=Path("out/full-study"))
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args(argv)
    if min(args.cohort_size, args.runs, args.virtual_days, args.batch_runs) < 1:
        raise SystemExit("study dimensions must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = args.output / "checkpoint.json"
    if args.reset and checkpoint_path.exists():
        checkpoint_path.unlink()
    parameters = load_parameters()
    arms_to_run = ("Arm A", "B-full") if args.core_only else ARMS
    config_payload = {"cohort_size": args.cohort_size, "runs": args.runs, "seed": args.seed, "virtual_days": args.virtual_days, "arms": list(arms_to_run)}
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint["config"] != config_payload:
            raise SystemExit("checkpoint config differs; use --reset or the original dimensions")
    else:
        checkpoint = {
            "status": "running",
            "config": config_payload,
            "completed_runs": 0,
            "parameters": {"status": "assumption", "source": "not yet found / assumption", "record_count": len(parameters)},
            "run_summaries": [],
            "paired_differences": [],
        }
    remaining = args.runs - checkpoint["completed_runs"]
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        while remaining > 0:
            batch_count = min(args.batch_runs, remaining)
            first_run = checkpoint["completed_runs"] + 1
            payloads = [
                (first_run + offset, args.cohort_size, args.seed, args.virtual_days, parameters, args.core_only)
                for offset in range(batch_count)
            ]
            results = list(executor.map(_run_replication, payloads))
            for run_index, arms, paired in sorted(results, key=lambda item: item[0]):
                checkpoint["run_summaries"].append({"run": run_index, "arms": arms})
                checkpoint["paired_differences"].append(paired)
            checkpoint["run_summaries"].sort(key=lambda item: item["run"])
            checkpoint["paired_differences"].sort(key=lambda item: item["run"])
            checkpoint["completed_runs"] += batch_count
            checkpoint["status"] = "complete" if checkpoint["completed_runs"] >= args.runs else "running"
            _write_json(checkpoint_path, checkpoint)
            print(f"completed replications {first_run}-{first_run + batch_count - 1}/{args.runs}", flush=True)
            remaining -= batch_count
    aggregate = _aggregate(checkpoint)
    _write_json(args.output / "result.json", aggregate)
    if checkpoint["completed_runs"] >= args.runs:
        print(f"full study complete: {args.cohort_size} cases × {args.runs} replications", flush=True)
    else:
        print(f"checkpoint saved: {checkpoint['completed_runs']}/{args.runs} replications", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
