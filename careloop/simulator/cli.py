"""Command-line entry point for fast deterministic CareLoop runs."""

from __future__ import annotations

import argparse
from pathlib import Path

from .engine import SimulationConfig, Simulator
from .params import load_parameters


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run paired Arm A/B-full event simulation")
    parser.add_argument("--full", action="store_true", help="use the 10,000-person, 500-run study defaults")
    parser.add_argument("--bounded", action="store_true", help="cap a run for deterministic offline verification")
    parser.add_argument("--sensitivity", action="store_true", help="include OAT, Latin-hypercube, and tornado analyses")
    parser.add_argument("--stress", action="store_true", help="include configured stress scenarios")
    parser.add_argument("--pathway", default=None, help="run one pathway (colorectal, mammogram, or lab)")
    parser.add_argument("--cohort-size", type=int, default=None)
    parser.add_argument("--runs", type=int, default=None)
    parser.add_argument("--virtual-days", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--queue-policy", choices=("fifo", "priority"), default="fifo")
    parser.add_argument("--disable-module", action="append", choices=(
        "closure_gate", "absence_detector", "positive_handoff", "multilingual_passport", "econsult"),
        default=[], help="disable a switchable V2 module (repeatable)")
    parser.add_argument("--max-cohort-size", type=int, default=1000, help="bound used with --bounded")
    parser.add_argument("--max-runs", type=int, default=20, help="bound used with --bounded")
    parser.add_argument("--params", type=Path, default=None, help="YAML parameter record file")
    parser.add_argument("--json", type=Path, default=None, help="write structured JSON output")
    parser.add_argument("--csv", type=Path, default=None, help="write flat metrics CSV output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    values = load_parameters(args.params)
    # Full-study values live in the manifest and SimulationConfig.  The CLI's
    # ordinary invocation is intentionally a quick, reproducible smoke run;
    # --full opts into the published 10,000 x 500 defaults.
    cohort_override = args.cohort_size if args.cohort_size is not None else (None if args.full else 1000)
    runs_override = args.runs if args.runs is not None else (None if args.full else 10)
    if args.bounded:
        cohort_override = min(cohort_override or 1000, max(1, args.max_cohort_size))
        runs_override = min(runs_override or 10, max(1, args.max_runs))
    config = SimulationConfig.from_parameters(
        values,
        cohort_size=cohort_override,
        runs=runs_override,
        virtual_days=args.virtual_days,
        seed=args.seed,
        parameter_file=str(args.params) if args.params else None,
        pathway=args.pathway,
        queue_policy=args.queue_policy,
        bounded=args.bounded,
        modules={name: False for name in args.disable_module},
    )
    result = Simulator(config, values).run(include_sensitivity=args.sensitivity, include_stress=args.stress)
    if args.json:
        result.write_json(args.json)
    if args.csv:
        result.write_csv(args.csv)
    if not args.json and not args.csv:
        import json
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
