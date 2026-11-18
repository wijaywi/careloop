"""Parameter record loading without a mandatory third-party YAML dependency."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_PATH = Path(__file__).with_name("default.yml")


def validate_parameter_document(document: Any) -> list[dict[str, Any]]:
    """Validate the small, dependency-free parameter manifest schema.

    Parameter provenance is deliberately strict: this simulator is an
    assumption model, so every record must explicitly say ``ASSUMPTION`` and
    carry a null source until a verifiable source is supplied.
    """
    if not isinstance(document, dict):
        raise ValueError("parameter manifest must be an object")
    if str(document.get("status", "")).lower() != "assumption" or document.get("source") not in (None, "not yet found / assumption"):
        raise ValueError("parameter manifest must have assumption status and an assumption source")
    records = document.get("records")
    if not isinstance(records, list):
        raise ValueError("parameter manifest records must be a list")
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("each parameter record must be an object")
        name = record.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("each parameter record needs a non-empty name")
        if name in seen:
            raise ValueError(f"duplicate parameter {name}")
        seen.add(name)
        if "value" not in record:
            raise ValueError(f"parameter {name} has no value")
        if str(record.get("status", "")).lower() != "assumption" or record.get("source") not in (None, "not yet found / assumption"):
            raise ValueError(f"invalid status/source for parameter {name}")
    return records


def load_parameters(path: str | Path | None = None) -> dict[str, Any]:
    """Load parameter records and expose them as a dotted-key dictionary.

    ``default.yml`` is JSON-compatible YAML, so deterministic offline runs use
    the standard library.  If PyYAML is installed, ordinary YAML files are also
    accepted.
    """
    parameter_path = Path(path) if path else DEFAULT_PATH
    text = parameter_path.read_text(encoding="utf-8")
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ValueError("parameter file is YAML; install PyYAML or use JSON-compatible YAML") from exc
        document = yaml.safe_load(text)
    records = validate_parameter_document(document)
    result: dict[str, Any] = {}
    for record in records:
        result[record["name"]] = record["value"]
    return result


__all__ = ["DEFAULT_PATH", "load_parameters", "validate_parameter_document"]
