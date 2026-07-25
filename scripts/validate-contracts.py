#!/usr/bin/env python3
"""Validate AgentPulse OpenAPI, schemas, security metadata, and fixtures."""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import jsonschema
import yaml
from openapi_spec_validator import validate

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "packages" / "contracts"
SCHEMA_DIR = CONTRACTS / "schemas"
FIXTURES = CONTRACTS / "fixtures"

REQUIRED_OPERATIONS: dict[tuple[str, str], dict[str, Any]] = {
    ("/v1/browser/enrollment-tokens", "post"): {"security": [{"BrowserSession": []}], "csrf": True},
    ("/v1/billing/checkout", "post"): {"security": [], "csrf": False},
    ("/v1/onboarding/claim", "post"): {"security": [], "csrf": False},
    ("/v1/session", "delete"): {"security": [{"BrowserSession": []}], "csrf": True},
    ("/v1/account", "get"): {"security": [{"BrowserSession": []}], "csrf": False},
    ("/v1/billing/portal", "post"): {"security": [{"BrowserSession": []}], "csrf": True},
}

REQUIRED_FIXTURES = {
    "checkout-response.json": ("/v1/billing/checkout", "post", "201"),
    "claim-response.json": ("/v1/onboarding/claim", "post", "200"),
    "account-response.json": ("/v1/account", "get", "200"),
    "portal-response.json": ("/v1/billing/portal", "post", "200"),
}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def local_ref(value: str, root: dict[str, Any]) -> Any:
    if not value.startswith("#/"):
        raise ValueError(f"non-local reference: {value}")
    current: Any = root
    for part in value[2:].split("/"):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"unresolved reference: {value}")
        current = current[part]
    return current


def resolve_local_refs(value: Any, root: dict[str, Any], seen: set[str] | None = None) -> int:
    seen = seen or set()
    if isinstance(value, dict):
        refs = 0
        ref = value.get("$ref")
        if isinstance(ref, str):
            if ref in seen:
                return 0
            current = local_ref(ref, root)
            refs += 1 + resolve_local_refs(current, root, seen | {ref})
        for child in value.values():
            refs += resolve_local_refs(child, root, seen)
        return refs
    if isinstance(value, list):
        return sum(resolve_local_refs(child, root, seen) for child in value)
    return 0


def dereference_schema(value: Any, root: dict[str, Any], seen: set[str] | None = None) -> Any:
    seen = seen or set()
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            if ref in seen:
                raise ValueError(f"cyclic fixture schema reference: {ref}")
            resolved = dereference_schema(copy.deepcopy(local_ref(ref, root)), root, seen | {ref})
            siblings = {key: item for key, item in value.items() if key != "$ref"}
            if siblings:
                if not isinstance(resolved, dict):
                    raise ValueError(f"schema reference with siblings is not an object: {ref}")
                resolved.update(dereference_schema(siblings, root, seen))
            return resolved
        return {key: dereference_schema(item, root, seen) for key, item in value.items()}
    if isinstance(value, list):
        return [dereference_schema(item, root, seen) for item in value]
    return value


def check_required_operations(paths: dict[str, Any]) -> None:
    csrf_ref = "#/components/parameters/CsrfToken"
    for (path, method), expected in REQUIRED_OPERATIONS.items():
        item = paths.get(path)
        if not isinstance(item, dict):
            raise ValueError(f"missing required path: {path}")
        operation = item.get(method)
        if not isinstance(operation, dict):
            raise ValueError(f"path {path} {method} must be an operation object")
        if operation.get("x-implementation-status") != "implemented":
            raise ValueError(f"path {path} {method} must be labeled implemented after Phase 3B")
        if operation.get("security") != expected["security"]:
            raise ValueError(f"path {path} {method} has unsafe or unexpected security")
        parameters = operation.get("parameters", [])
        has_csrf = any(
            isinstance(parameter, dict) and parameter.get("$ref") == csrf_ref
            for parameter in parameters
        )
        if has_csrf != expected["csrf"]:
            raise ValueError(f"path {path} {method} has incorrect CSRF declaration")


def check_security_components(document: dict[str, Any]) -> None:
    components = document.get("components")
    if not isinstance(components, dict):
        raise ValueError("OpenAPI components are missing")
    schemes = components.get("securitySchemes")
    browser = schemes.get("BrowserSession") if isinstance(schemes, dict) else None
    if not isinstance(browser, dict) or any(
        browser.get(key) != value
        for key, value in {"type": "apiKey", "in": "cookie", "name": "ap_session"}.items()
    ):
        raise ValueError("BrowserSession must be the opaque ap_session cookie scheme")
    parameters = components.get("parameters")
    csrf = parameters.get("CsrfToken") if isinstance(parameters, dict) else None
    if not isinstance(csrf, dict):
        raise ValueError("CsrfToken component is missing")
    csrf_schema = csrf.get("schema")
    if (
        csrf.get("name") != "X-CSRF-Token"
        or csrf.get("in") != "header"
        or csrf.get("required") is not True
        or not isinstance(csrf_schema, dict)
        or csrf_schema.get("type") != "string"
        or not isinstance(csrf_schema.get("minLength"), int)
        or csrf_schema["minLength"] < 16
    ):
        raise ValueError("CsrfToken must be a required X-CSRF-Token header of at least 16 characters")


def operation_response_schema(
    document: dict[str, Any], path: str, method: str, status: str
) -> Any:
    try:
        return document["paths"][path][method]["responses"][status]["content"][
            "application/json"
        ]["schema"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"fixture response schema missing for {path} {method} {status}") from exc


def absolute_uri(value: object) -> bool:
    if not isinstance(value, str) or not value or re.search(r"\s", value):
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def validate_fixture(document: dict[str, Any], name: str, fixture: Any | None = None) -> None:
    if fixture is None:
        fixture_path = FIXTURES / name
        if not fixture_path.is_file():
            raise ValueError(f"missing required fixture: {name}")
        fixture = load_json(fixture_path)
    try:
        path, method, status = REQUIRED_FIXTURES[name]
    except KeyError as exc:
        raise ValueError(f"fixture is not bound to an operation response: {name}") from exc
    schema = dereference_schema(operation_response_schema(document, path, method, status), document)
    format_checker = jsonschema.FormatChecker()

    @format_checker.checks("uri")
    def check_uri(value: object) -> bool:
        return absolute_uri(value)

    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=format_checker,
    )
    errors = sorted(validator.iter_errors(fixture), key=lambda error: list(error.path))
    if errors:
        path = ".".join(str(part) for part in errors[0].path) or "<root>"
        raise ValueError(f"fixture {name} invalid at {path}: {errors[0].message}")


def validate_document(document: dict[str, Any]) -> tuple[int, int, int, int]:
    if document.get("openapi") != "3.1.0":
        raise ValueError("OpenAPI version must be 3.1.0")
    validate(document)
    paths = document.get("paths", {})
    if not isinstance(paths, dict) or not paths:
        raise ValueError("OpenAPI paths are missing")
    check_security_components(document)
    check_required_operations(paths)
    refs = resolve_local_refs(document, document)
    schemas = sorted(SCHEMA_DIR.glob("*.schema.json"))
    for path in schemas:
        jsonschema.Draft7Validator.check_schema(load_json(path))
    incident_validator = jsonschema.Draft7Validator(load_json(SCHEMA_DIR / "incident.schema.json"))
    fleet = load_json(FIXTURES / "fleet-response.json")
    heartbeat = load_json(FIXTURES / "heartbeat-with-incidents.json")
    error = load_json(FIXTURES / "error-response.json")
    for item in fleet["agents"][0]["incidents"]:
        errors = sorted(incident_validator.iter_errors(item), key=lambda current: list(current.path))
        if errors:
            raise ValueError(f"fleet fixture invalid: {errors[0].message}")
    if not isinstance(heartbeat.get("incidents"), list) or len(heartbeat["incidents"]) > 50:
        raise ValueError("heartbeat fixture has invalid incidents")
    if not isinstance(error.get("error"), dict):
        raise ValueError("error fixture is invalid")
    for name in REQUIRED_FIXTURES:
        validate_fixture(document, name)
    return len(paths), refs, len(schemas), 3 + len(REQUIRED_FIXTURES)


def main() -> int:
    document = yaml.safe_load((CONTRACTS / "openapi.yaml").read_text(encoding="utf-8"))
    paths, refs, schemas, fixtures = validate_document(document)
    print(f"OpenAPI: {paths} paths; local refs: {refs}; JSON schemas: {schemas}; fixtures: {fixtures}")
    print("Contracts: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError, jsonschema.SchemaError) as exc:
        print(f"Contracts: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
