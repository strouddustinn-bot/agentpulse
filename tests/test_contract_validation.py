from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate-contracts.py"
SPEC = importlib.util.spec_from_file_location("validate_contracts", MODULE_PATH)
assert SPEC and SPEC.loader
validate_contracts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_contracts)


class ContractValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(
            (ROOT / "packages" / "contracts" / "openapi.yaml").read_text(encoding="utf-8")
        )

    def test_rejects_null_required_operation(self) -> None:
        document = copy.deepcopy(self.document)
        document["paths"]["/v1/billing/checkout"]["post"] = None
        with self.assertRaises(OpenAPIValidationError):
            validate_contracts.validate_document(document)

    def test_rejects_missing_session_security(self) -> None:
        document = copy.deepcopy(self.document)
        document["paths"]["/v1/account"]["get"]["security"] = []
        with self.assertRaisesRegex(ValueError, "security"):
            validate_contracts.check_required_operations(document["paths"])

    def test_rejects_missing_csrf_parameter(self) -> None:
        document = copy.deepcopy(self.document)
        document["paths"]["/v1/billing/portal"]["post"]["parameters"] = []
        with self.assertRaisesRegex(ValueError, "CSRF"):
            validate_contracts.check_required_operations(document["paths"])

    def test_rejects_weakened_browser_session_and_csrf_components(self) -> None:
        mutations = (
            (
                "browser header",
                lambda document: document["components"]["securitySchemes"][
                    "BrowserSession"
                ].update({"in": "header", "name": "Authorization"}),
            ),
            (
                "optional csrf",
                lambda document: document["components"]["parameters"]["CsrfToken"].update(
                    {"in": "query", "required": False}
                ),
            ),
            (
                "short csrf",
                lambda document: document["components"]["parameters"]["CsrfToken"][
                    "schema"
                ].update({"minLength": 0}),
            ),
        )
        for name, mutate in mutations:
            with self.subTest(name=name):
                document = copy.deepcopy(self.document)
                mutate(document)
                with self.assertRaises(ValueError):
                    validate_contracts.validate_document(document)

    def test_rejects_fixture_response_rebinding_and_invalid_uri(self) -> None:
        document = copy.deepcopy(self.document)
        document["paths"]["/v1/billing/checkout"]["post"]["responses"]["201"][
            "content"
        ]["application/json"]["schema"] = {
            "$ref": "#/components/schemas/BillingPortalResponse"
        }
        with self.assertRaisesRegex(ValueError, "checkout-response"):
            validate_contracts.validate_document(document)
        with self.assertRaisesRegex(ValueError, "checkout_url"):
            validate_contracts.validate_fixture(
                self.document,
                "checkout-response.json",
                {"checkout_url": "not a uri", "expires_at": 1784144000},
            )

    def test_rejects_wrong_fixture_types_and_nested_enums(self) -> None:
        with self.assertRaisesRegex(ValueError, "checkout_url"):
            validate_contracts.validate_fixture(
                self.document,
                "checkout-response.json",
                {"checkout_url": 7, "expires_at": "never"},
            )
        invalid_claim = {
            "csrf_token": "csrf_00000000000000000000000000000000",
            "account": {
                "tenant_id": "00000000-0000-4000-8000-000000000001",
                "email": "owner@example.com",
                "plan": "unlimited",
                "entitlement_status": "active",
                "agent_limit": 5,
            },
        }
        with self.assertRaisesRegex(ValueError, "account.plan"):
            validate_contracts.validate_fixture(
                self.document,
                "claim-response.json",
                invalid_claim,
            )


if __name__ == "__main__":
    unittest.main()
