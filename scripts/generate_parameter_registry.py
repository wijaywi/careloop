"""Generate the complete parameter registry from the manifest."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _range_for(name: str, value: object, record: dict[str, object]) -> str:
    if "range" in record and record["range"] is not None:
        return str(record["range"])
    lowered = name.lower()
    if isinstance(value, (int, float)):
        if lowered == "seed":
            return "0..2147483647"
        if any(token in lowered for token in ("probability", "rate", "quality", "weight", "multiplier", "_add")):
            return "0..1"
        if any(token in lowered for token in ("delay", "hours", "days", "distance")):
            return "0..720"
        if any(token in lowered for token in ("capacity", "cohort", "runs", "threshold")):
            return "1..10000"
        return "0..100"
    if isinstance(value, dict):
        return "categorical map; each probability 0..1"
    return "configured category"


def main() -> int:
    manifest_path = ROOT / "careloop" / "simulator" / "params" / "default.yml"
    output_path = ROOT / "careloop" / "simulator" / "params" / "registry.csv"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    for record in document["records"]:
        name = str(record["name"])
        value = record.get("value")
        rows.append({
            "parameter": name,
            "value_range": _range_for(name, value, record),
            "distribution": str(record.get("distribution") or ("categorical" if isinstance(value, dict) else "configured")),
            "source": str(record.get("source") or "not yet found / assumption"),
            "status": str(record.get("status") or "assumption").lower(),
            "notes": str(record.get("notes") or "Current model input; range is an assumption until a source is verified."),
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["parameter", "value_range", "distribution", "source", "status", "notes"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Generated {len(rows)} parameter records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
