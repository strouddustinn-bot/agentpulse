# AgentPulse Stripe key handoff

The destination file already exists with mode `600`:

`/home/dstroud/API Keys chmod 600/agentpulse-stripe.env`

Never paste Stripe keys into chat, GitHub, source files, screenshots, or shell
command arguments.

## 1. Create the live restricted key

1. Open <https://dashboard.stripe.com/apikeys> and sign in.
2. Confirm you are in **live mode**. The page must not say **Test mode** or show
   a sandbox banner.
3. Click **Create restricted key**.
4. If Stripe asks how to configure it, choose **Start from zero** or
   **Customize permissions**.
5. Set **Key name** to `AgentPulse Fly production`.
6. Leave every permission at **None**, then set only:

   **Write**
   - Payment Links
   - Webhook Endpoints (sometimes shown under Workbench or Developers)
   - Billing Portal / Customer Portal / Billing Portal Configurations

   **Read**
   - Checkout Sessions
   - Customers
   - Subscriptions
   - Prices
   - Products
   - Invoices

   A **Write** permission already includes Read for that resource.
7. Do not grant access to balances, payouts, bank accounts, transfers, refunds,
   disputes, charges, files, issuing, treasury, tax registrations, or Connect.
8. Click **Create key**.
9. Complete Stripe's two-factor verification.
10. Click the new `rk_live_...` value to copy it. Stripe shows it only once.
11. In Stripe's note field enter:
    `Stored in local mode-600 AgentPulse secret file and Fly secrets`
12. Keep the Stripe tab open until the local save below is complete.

## 2. Strongly recommended: create the test restricted key

1. Open <https://dashboard.stripe.com/test/apikeys>.
2. Confirm **Test mode** or a Stripe sandbox is active.
3. Create another restricted key from zero named `AgentPulse Fly test`.
4. Give it the same permissions listed above.
5. Complete verification and copy the `rk_test_...` value.

This key lets the full checkout/webhook/entitlement/cancellation flow be tested
without a real charge.

## 3. Store both keys without exposing them in shell history

Open a terminal and paste this command block exactly:

```bash
read -rsp 'Paste LIVE rk_live_ key: ' LIVE; printf '\n'
read -rsp 'Paste TEST rk_test_ key (Enter to skip): ' TEST; printf '\n'
umask 077
{
  printf 'STRIPE_SECRET_KEY=%s\n' "$LIVE"
  if [ -n "$TEST" ]; then
    printf 'STRIPE_TEST_SECRET_KEY=%s\n' "$TEST"
  fi
} > "$HOME/API Keys chmod 600/agentpulse-stripe.env"
chmod 600 "$HOME/API Keys chmod 600/agentpulse-stripe.env"
unset LIVE TEST
stat -c 'saved=%n mode=%a bytes=%s' \
  "$HOME/API Keys chmod 600/agentpulse-stripe.env"
```

The terminal intentionally displays nothing while each key is pasted. Press
Enter after each key. The final line should show `mode=600` and a non-zero byte
count.

## 4. Return to Hermes

Reply only: `Stripe keys ready`

Do not include either key in the reply.

Hermes will then validate the keys without printing them, discover the exact
Product/Price/Payment Link IDs, register the signed webhook, save the webhook
secret to Fly, configure the customer portal, set all three Payment Links to
redirect to the verified onboarding page, deploy, run safe tests, and report
receipts.
