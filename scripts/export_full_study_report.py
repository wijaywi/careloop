"""Export a compact Markdown report from the completed core full study."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from careloop.simulator import load_parameters


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("out/full-study-core/result.json"))
    parser.add_argument("--output", type=Path, default=Path("out/full-study-core/report.md"))
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    parameters = load_parameters()
    arms = data["summary"]["arms"]
    intervals = data["intervals"]["arms"]
    lines = [
        "# CareLoop full core study",
        "",
        "This report is generated from `run_full_study.py`. It is a workflow simulation, not evidence of real clinical outcomes.",
        "",
        f"- Cohort per replication: **{data['config']['cohort_size']:,}** synthetic cases",
        f"- Replications: **{data['completed_runs']:,}**",
        f"- Seed: **{data['config']['seed']}**",
        f"- Virtual horizon: **{data['config']['virtual_days']} days**",
        f"- Primary scenario: **{parameters['primary_screening_type']}**",
        "- Stage 9 policy: **14 days urgent / 30 days routine (ASSUMPTION; not a verified guideline)**",
        "- Arms: **Arm A** and **B-full**; same deterministic cohort generation and paired draws",
        "",
        "| Metric | Arm A mean (95% interval) | B-full mean (95% interval) |",
        "|---|---:|---:|",
    ]
    for metric in ("closure_rate", "closure_within_sla_rate", "named_owner_documented_closure_within_sla_rate", "owner_coverage_rate", "result_flag_rate", "teach_back_rate", "unknown_rate", "consult_without_referral_rate", "backlog_events", "fatigue_alerts", "workload_hours"):
        a = intervals["Arm A"][metric]
        b = intervals["B-full"][metric]
        lines.append(f"| {metric} | {a['mean']:.6f} [{a['lower']:.6f}, {a['upper']:.6f}] | {b['mean']:.6f} [{b['lower']:.6f}, {b['upper']:.6f}] |")
    paired = data["intervals"]["paired"]["closure_rate_delta"]
    lines.extend([
        "",
        f"Paired closure-rate delta (B-full minus Arm A): **{paired['mean']:.6f}** [{paired['lower']:.6f}, {paired['upper']:.6f}].",
        "",
        "Interpretation: these values describe the configured workflow mechanisms and assumptions. They do not establish clinical effectiveness, safety, or population impact.",
        "",
        "The complete checkpoint and run-level summaries remain in `checkpoint.json` and `result.json`.",
    ])
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Exported {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
