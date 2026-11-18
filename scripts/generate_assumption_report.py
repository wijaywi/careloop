"""Generate the English assumption list from the parameter registry."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    source = ROOT / "careloop" / "simulator" / "params" / "registry.csv"
    destination = ROOT / "docs" / "ASSUMPTION_REGISTRY.md"
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    lines = [
        "# CareLoop simulator assumption registry",
        "",
        "This file is generated from `careloop/simulator/params/registry.csv`.",
        "Every row is currently marked `assumption` because no parameter source",
        "was verified for this revision. These values are not clinical evidence.",
        "",
        f"Total records: **{len(rows)}**; assumption records: **{sum(row['status'].lower() == 'assumption' for row in rows)}**; sourced records: **{sum(row['status'].lower() != 'assumption' for row in rows)}**.",
        "",
        "| Parameter | Range | Distribution | Source | Status | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        values = [row[key].replace("|", "\\|").replace("\n", " ") for key in ("parameter", "value_range", "distribution", "source", "status", "notes")]
        lines.append("| " + " | ".join(values) + " |")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated {len(rows)} assumptions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
