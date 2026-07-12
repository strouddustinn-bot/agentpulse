"""Billing control-plane tests: Stripe lifecycle, onboarding, and entitlements."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pulse_server.db import Db


class FakeStripeGateway:
    def __init__(self):
        self.event = None
        self.portal_customer = None
        self.checkout = {
            "id": "cs_live_1",
            "customer": "cus_1",
            "subscription": "sub_1",
            "email": "buyer@example.com",
            "complete": True,
        }
        self.subscription = {
            "id": "sub_1",
            "customer": "cus_1",
            "status": "active",
            "price_id": "price_pro",
            "product_name": "AgentPulse Pro",
            "unit_amount": 9900,
            "currency": "cad",
            "current_period_end": 1999999999,
        }

    def construct_event(self, payload, signature, secret):
        if signature != "valid-signature" or secret != "whsec_test":
            raise ValueError("invalid signature")
        return self.event or json.loads(payload)

    def retrieve_checkout(self, session_id):
        if session_id != self.checkout["id"]:
            raise ValueError("unknown checkout")
        return dict(self.checkout)

    def retrieve_subscription(self, subscription_id):
        if subscription_id != self.subscription["id"]:
            raise ValueError("unknown subscription")
        return dict(self.subscription)

    def create_portal(self, customer_id, return_url):
        self.portal_customer = customer_id
        return "https://billing.stripe.test/session/portal"


class TestBillingDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Db(os.path.join(self.tmp.name, "billing.db"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _active_customer(self, plan="starter", limit=1):
        self.db.upsert_billing_customer("cus_1", "buyer@example.com")
        self.db.upsert_subscription(
            "sub_1", "cus_1", "active", "price_1", plan, limit, 1999999999
        )
        self.db.issue_api_key("cus_1", "ap_live_testkey")

    def test_active_key_enforces_server_limit(self):
        self._active_customer()
        first = self.db.authorize_agent("ap_live_testkey", "node-1")
        self.assertTrue(first["allowed"])
        self.assertEqual(first["plan"], "starter")
        again = self.db.authorize_agent("ap_live_testkey", "node-1")
        self.assertTrue(again["allowed"])
        blocked = self.db.authorize_agent("ap_live_testkey", "node-2")
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["reason"], "server_limit_exceeded")

    def test_cancelled_subscription_revokes_access(self):
        self._active_customer()
        self.db.upsert_subscription(
            "sub_1", "cus_1", "canceled", "price_1", "starter", 1, 1999999999
        )
        result = self.db.authorize_agent("ap_live_testkey", "node-1")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "subscription_inactive")

    def test_webhook_event_ids_are_idempotent(self):
        self.assertFalse(self.db.webhook_seen("evt_1"))
        self.db.record_webhook("evt_1", "checkout.session.completed")
        self.assertTrue(self.db.webhook_seen("evt_1"))


class TestBillingApi(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from pulse_server.main import Settings, create_app

        self.tmp = tempfile.TemporaryDirectory()
        self.gateway = FakeStripeGateway()
        self.settings = Settings(
            state_file=os.path.join(self.tmp.name, "missing-state.json"),
            db_path=os.path.join(self.tmp.name, "pulse.db"),
            web_dist=os.path.join(self.tmp.name, "no-dist"),
            enable_background=False,
            stripe_secret_key="sk_live_test",
            stripe_webhook_secret="whsec_test",
            public_base_url="https://agentpulse-stroud.fly.dev",
        )
        self.app = create_app(self.settings, stripe_gateway=self.gateway)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def _checkout_event(self, event_id="evt_checkout_1"):
        return {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_live_1",
                "customer": "cus_1",
                "subscription": "sub_1",
                "customer_details": {"email": "buyer@example.com"},
            }},
        }

    def _post_event(self, event):
        self.gateway.event = event
        return self.client.post(
            "/api/stripe/webhook",
            content=json.dumps(event),
            headers={"Stripe-Signature": "valid-signature"},
        )

    def _activate_and_claim(self):
        response = self._post_event(self._checkout_event())
        self.assertEqual(response.status_code, 200)
        claim = self.client.post(
            "/api/onboarding/claim",
            json={"session_id": "cs_live_1", "email": "buyer@example.com"},
        )
        self.assertEqual(claim.status_code, 200)
        return claim.json()["api_key"]

    def test_webhook_rejects_bad_signature(self):
        response = self.client.post(
            "/api/stripe/webhook",
            content="{}",
            headers={"Stripe-Signature": "wrong"},
        )
        self.assertEqual(response.status_code, 400)

    def test_checkout_creates_subscription_and_is_idempotent(self):
        event = self._checkout_event()
        first = self._post_event(event)
        second = self._post_event(event)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["duplicate"])
        sub = self.app.state.db.subscription_for_customer("cus_1")
        self.assertEqual(sub["plan"], "pro")
        self.assertEqual(sub["server_limit"], 5)
        self.assertEqual(sub["status"], "active")

    def test_onboarding_issues_one_time_api_key(self):
        key = self._activate_and_claim()
        self.assertTrue(key.startswith("ap_live_"))
        duplicate = self.client.post(
            "/api/onboarding/claim",
            json={"session_id": "cs_live_1", "email": "buyer@example.com"},
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_onboarding_rejects_wrong_email(self):
        self._post_event(self._checkout_event())
        response = self.client.post(
            "/api/onboarding/claim",
            json={"session_id": "cs_live_1", "email": "attacker@example.com"},
        )
        self.assertEqual(response.status_code, 403)

    def test_customer_portal_requires_active_api_key(self):
        self.assertEqual(self.client.post("/api/billing/portal").status_code, 401)
        key = self._activate_and_claim()
        response = self.client.post(
            "/api/billing/portal",
            headers={"Authorization": "Bearer " + key},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["url"],
                         "https://billing.stripe.test/session/portal")
        self.assertEqual(self.gateway.portal_customer, "cus_1")

    def test_license_key_allows_heartbeat_and_enforces_pro_limit(self):
        key = self._activate_and_claim()
        for i in range(1, 6):
            response = self.client.post(
                "/fleet/heartbeat",
                json={"agent_id": "node-%d" % i, "hostname": "node-%d" % i,
                      "state": {}},
                headers={"Authorization": "Bearer " + key},
            )
            self.assertEqual(response.status_code, 200)
        blocked = self.client.post(
            "/fleet/heartbeat",
            json={"agent_id": "node-6", "hostname": "node-6", "state": {}},
            headers={"Authorization": "Bearer " + key},
        )
        self.assertEqual(blocked.status_code, 403)

    def test_failed_payment_disables_existing_key(self):
        key = self._activate_and_claim()
        # Stripe may emit invoice.payment_failed before Subscription.status
        # changes, so the event itself must fail closed immediately.
        self.gateway.subscription["status"] = "active"
        failed = {
            "id": "evt_failed_1",
            "type": "invoice.payment_failed",
            "data": {"object": {"subscription": "sub_1"}},
        }
        self.assertEqual(self._post_event(failed).status_code, 200)
        response = self.client.post(
            "/fleet/heartbeat",
            json={"agent_id": "node-1", "hostname": "node-1", "state": {}},
            headers={"Authorization": "Bearer " + key},
        )
        self.assertEqual(response.status_code, 402)


if __name__ == "__main__":
    unittest.main()
