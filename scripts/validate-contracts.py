#!/usr/bin/env python3
"""Validate AgentPulse OpenAPI, JSON Schemas, local refs, and fixtures."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "packages" / "contracts"
SCHEMA_DIR = CONTRACTS / "schemas"
FIXTURES = CONTRACTS / "fixtures"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def resolve_local_refs(value: Any, root: dict[str, Any], seen: set[str] | None = None) -> int:
    seen = seen or set()
    if isinstance(value, dict):
        refs = 0
        ref = value.get("$ref")
        if isinstance(ref, str):
            if not ref.startswith("#/"):
                raise ValueError(f"non-local reference: {ref}")
            if ref in seen:
                return 0
            current: Any = root
            for part in ref[2:].split("/"):
                if not isinstance(current, dict) or part not in current:
                    raise ValueError(f"unresolved reference: {ref}")
                current = current[part]
            refs += 1 + resolve_local_refs(current, root, seen | {ref})
        for child in value.values():
            refs += resolve_local_refs(child, root, seen)
        return refs
    if isinstance(value, list):
        return sum(resolve_local_refs(child, root, seen) for child in value)
    return 0


def main() -> int:
    openapi_path = CONTRACTS / "openapi.yaml"
    document = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
    if document.get("openapi") != "3.1.0":
        raise ValueError("OpenAPI version must be 3.1.0")
    paths = document.get("paths", {})
    if not isinstance(paths, dict) or not paths:
        raise ValueError("OpenAPI paths are missing")
    refs = resolve_local_refs(document, document)
    schemas = sorted(SCHEMA_DIR.glob("*.schema.json"))
    for path in schemas:
        jsonschema.Draft7Validator.check_schema(load_json(path))
    incident_validator = jsonschema.Draft7Validator(load_json(SCHEMA_DIR / "incident.schema.json"))
    fleet = load_json(FIXTURES / "fleet-response.json")
    heartbeat = load_json(FIXTURES / "heartbeat-with-incidents.json")
    error = load_json(FIXTURES / "error-response.json")
    for item in fleet["agents"][0]["incidents"]:
        errors = sorted(incident_validator.iter_errors(item), key=lambda error: error.path)
        if errors:
            raise ValueError(f"fleet fixture invalid: {errors[0].message}")
    if not isinstance(heartbeat.get("incidents"), list) or len(heartbeat["incidents"]) > 50:
        raise ValueError("heartbeat fixture has invalid incidents")
    if not isinstance(error.get("error"), dict):
        raise ValueError("error fixture is invalid")
    print(f"OpenAPI: {len(paths)} paths; local refs: {refs}; JSON schemas: {len(schemas)}; fixtures: 3")
    print("Contracts: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError, jsonschema.SchemaError) as exc:
        print(f"Contracts: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
