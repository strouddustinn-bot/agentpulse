"""Stripe-backed billing lifecycle and AgentPulse entitlement issuance."""

from __future__ import annotations

import secrets
from typing import Any, Dict, Optional

from .db import Db

_ACTIVE_STATUSES = frozenset({"active", "trialing"})
_PLAN_LIMITS = {"starter": 1, "pro": 5, "business": 1000}


def _get(value: Any, key: str, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


class StripeGateway:
    """Thin Stripe SDK adapter. Tests inject a deterministic fake gateway."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("STRIPE_SECRET_KEY is not configured")
        import stripe
        self._stripe = stripe
        self._api_key = api_key

    def construct_event(self, payload: bytes, signature: str, secret: str):
        return self._stripe.Webhook.construct_event(payload, signature, secret)

    def retrieve_checkout(self, session_id: str) -> Dict:
        session = self._stripe.checkout.Session.retrieve(
            session_id, api_key=self._api_key
        )
        details = _get(session, "customer_details") or {}
        payment_status = str(_get(session, "payment_status", ""))
        status = str(_get(session, "status", ""))
        return {
            "id": str(_get(session, "id", session_id)),
            "customer": str(_get(session, "customer", "")),
            "subscription": str(_get(session, "subscription", "")),
            "email": str(_get(details, "email", "")),
            "complete": status == "complete"
            and payment_status in ("paid", "no_payment_required"),
        }

    def retrieve_subscription(self, subscription_id: str) -> Dict:
        subscription = self._stripe.Subscription.retrieve(
            subscription_id,
            api_key=self._api_key,
            expand=["items.data.price.product"],
        )
        items = _get(_get(subscription, "items", {}), "data", []) or []
        item = items[0] if items else {}
        price = _get(item, "price", {}) or {}
        product = _get(price, "product", {}) or {}
        product_name = (_get(product, "name", "")
                        if not isinstance(product, str) else "")
        return {
            "id": str(_get(subscription, "id", subscription_id)),
            "customer": str(_get(subscription, "customer", "")),
            "status": str(_get(subscription, "status", "")),
            "price_id": str(_get(price, "id", "")),
            "product_name": str(product_name),
            "unit_amount": int(_get(price, "unit_amount", 0) or 0),
            "currency": str(_get(price, "currency", "")),
            "current_period_end": _get(subscription, "current_period_end"),
        }

    def create_portal(self, customer_id: str, return_url: str) -> str:
        session = self._stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
            api_key=self._api_key,
        )
        return str(_get(session, "url", ""))


class BillingService:
    def __init__(self, db: Db, gateway, webhook_secret: str,
                 public_base_url: str, price_plans: Optional[Dict[str, str]] = None):
        self.db = db
        self.gateway = gateway
        self.webhook_secret = webhook_secret
        self.public_base_url = public_base_url.rstrip("/")
        self.price_plans = {k: v for k, v in (price_plans or {}).items() if k}

    def _plan_for(self, subscription: Dict) -> tuple[str, int]:
        price_id = str(subscription.get("price_id", ""))
        if price_id in self.price_plans:
            plan = self.price_plans[price_id]
            return plan, _PLAN_LIMITS[plan]
        name = str(subscription.get("product_name", "")).lower()
        for plan in ("starter", "business", "pro"):
            if plan in name:
                return plan, _PLAN_LIMITS[plan]
        amount = int(subscription.get("unit_amount") or 0)
        currency = str(subscription.get("currency", "")).lower()
        if currency == "cad":
            by_amount = {2900: "starter", 9900: "pro", 29900: "business"}
            if amount in by_amount:
                plan = by_amount[amount]
                return plan, _PLAN_LIMITS[plan]
        raise ValueError("subscription price is not mapped to an AgentPulse plan")

    def _sync_subscription(self, subscription_id: str,
                           email: str = "",
                           status_override: Optional[str] = None) -> Dict:
        subscription = self.gateway.retrieve_subscription(subscription_id)
        customer_id = str(subscription.get("customer", ""))
        if not customer_id:
            raise ValueError("Stripe subscription has no customer")
        if email:
            self.db.upsert_billing_customer(customer_id, email)
        plan, limit = self._plan_for(subscription)
        self.db.upsert_subscription(
            str(subscription.get("id", subscription_id)), customer_id,
            status_override or str(subscription.get("status", "")),
            str(subscription.get("price_id", "")), plan, limit,
            subscription.get("current_period_end"),
        )
        return subscription

    def process_webhook(self, payload: bytes, signature: str) -> Dict:
        if not self.webhook_secret:
            raise ValueError("STRIPE_WEBHOOK_SECRET is not configured")
        event = self.gateway.construct_event(
            payload, signature, self.webhook_secret
        )
        event_id = str(_get(event, "id", ""))
        event_type = str(_get(event, "type", ""))
        if not event_id or not event_type:
            raise ValueError("invalid Stripe event envelope")
        if self.db.webhook_seen(event_id):
            return {"ok": True, "duplicate": True}
        data = _get(event, "data", {}) or {}
        obj = _get(data, "object", {}) or {}
        if event_type == "checkout.session.completed":
            customer_id = str(_get(obj, "customer", ""))
            subscription_id = str(_get(obj, "subscription", ""))
            details = _get(obj, "customer_details", {}) or {}
            email = str(_get(details, "email", "")).strip().lower()
            if not customer_id or not subscription_id or not email:
                raise ValueError("completed checkout is missing customer data")
            self.db.upsert_billing_customer(customer_id, email)
            self._sync_subscription(subscription_id, email=email)
        elif event_type.startswith("customer.subscription."):
            subscription_id = str(_get(obj, "id", ""))
            if subscription_id:
                self._sync_subscription(subscription_id)
        elif event_type in ("invoice.paid", "invoice.payment_failed"):
            subscription_id = str(_get(obj, "subscription", ""))
            if subscription_id:
                self._sync_subscription(
                    subscription_id,
                    status_override=("past_due"
                                     if event_type == "invoice.payment_failed"
                                     else None),
                )
        self.db.record_webhook(event_id, event_type)
        return {"ok": True, "duplicate": False}

    def claim_onboarding(self, session_id: str, email: str) -> Dict:
        session = self.gateway.retrieve_checkout(session_id)
        supplied_email = email.strip().lower()
        if not session.get("complete"):
            raise PermissionError("checkout is not complete")
        if supplied_email != str(session.get("email", "")).strip().lower():
            raise PermissionError("email does not match checkout")
        customer_id = str(session.get("customer", ""))
        subscription_id = str(session.get("subscription", ""))
        if not customer_id or not subscription_id:
            raise PermissionError("checkout has no subscription")
        self.db.upsert_billing_customer(customer_id, supplied_email)
        self._sync_subscription(subscription_id, email=supplied_email)
        subscription = self.db.subscription_for_customer(customer_id)
        if not subscription or subscription["status"] not in _ACTIVE_STATUSES:
            raise PermissionError("subscription is not active")
        raw_key = "ap_live_" + secrets.token_urlsafe(32)
        if not self.db.claim_and_issue_api_key(session_id, customer_id, raw_key):
            raise FileExistsError("checkout session was already claimed")
        config = {
            "enabled": True,
            "mode": "spoke",
            "hub_url": self.public_base_url,
            "secret": raw_key,
            "port": 8766,
            "bind": "127.0.0.1",
            "push_interval_seconds": 60,
        }
        return {
            "api_key": raw_key,
            "plan": subscription["plan"],
            "server_limit": subscription["server_limit"],
            "federation": config,
            "warning": "Save this API key now. It is stored only as a hash.",
        }

    def create_portal(self, raw_key: str) -> str:
        account = self.db.customer_for_api_key(raw_key)
        if not account or account.get("status") not in _ACTIVE_STATUSES:
            raise PermissionError("active subscription required")
        return self.gateway.create_portal(
            account["stripe_customer_id"], self.public_base_url + "/"
        )
