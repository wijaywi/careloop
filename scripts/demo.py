"""Generate the deterministic CareLoop API demo artefact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.service import CareLoopService


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline CareLoop demo scenario")
    parser.add_argument("--output", type=Path, default=Path("out/demo.json"))
    args = parser.parse_args()
    service = CareLoopService(":memory:")
    try:
        seeded = service.load_demo_data(seed=20261019, case_count=12)
        scenario = service.run_stalled_case_scenario(actor_id="manager-1")
        payload = {
            "synthetic_only": True,
            "seeded": seeded,
            "scenario": scenario,
            "notes": [
                "This is a workflow demonstration, not a clinical decision.",
                "The case is closed by a clinician with recorded synthetic evidence.",
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Demo output: {args.output}")
        print(f"Scenario case: {scenario['case']['id']} ({scenario['case']['status']})")
        print("Workflow: stall_detected -> escalation -> handoff -> evidence_closure")
        return 0
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
