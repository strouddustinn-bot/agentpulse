---
layout: default
title: Join the AgentPulse Paid Beta
---

<!--
  ========================================================================
  DUSTINN — ONE-LINE GO-LIVE FOR REAL PAYMENT
  ------------------------------------------------------------------------
  To turn on real checkout, paste your Stripe Payment Link below, replacing
  the placeholder in the `href` of the "checkout-cta" button (search the
  page for STRIPE_PAYMENT_LINK).

  To turn on a real backed lead form instead of (or alongside) checkout,
  paste a Tally / Google Form embed URL into the iframe `src` below
  (search for LEAD_FORM_EMBED) and delete the surrounding comment markers.

  Until you do either, the page still works: the button and the form
  section both fall back to a structured email capture, which is better
  than a bare mailto because it pre-fills every field we need.
  ========================================================================
-->

# Join the paid beta

AgentPulse is onboarding a small group of founders and small teams who run
1–10 Linux servers and want monitoring that can safely remediate repeat
incidents — disk pressure, crashed services, runaway processes — instead of
just paging you about them.

<p>
  <!-- STRIPE_PAYMENT_LINK: replace the href below with your Stripe Payment Link to enable checkout -->
  <a id="checkout-cta"
     class="btn"
     href="mailto:support@agentpulse.dustinnstroud.com?subject=AgentPulse%20Pro%20Beta%20-%20reserve%20my%20slot&body=I%20want%20the%20Pro%20Beta%20(%2499%2Fmo%2C%20up%20to%205%20servers).%0A%0AName%3A%0ACompany%2Fproduct%3A%0A%23%20of%20Linux%20servers%3A%0AHosting%20provider%20(Hetzner%2FDO%2FLinode%2FVultr%2FAWS)%3A%0AStack%20(web%20server%2C%20process%20manager%2C%20db)%3A%0AThe%20recurring%20incident%20I%20want%20gone%3A%0APreferred%20start%20mode%3A%20alert-only%20%2F%20ask-first%20%2F%20auto-fix"
     style="display:inline-block;padding:14px 26px;background:#0b5fff;color:#fff;border-radius:8px;text-decoration:none;font-weight:700;font-size:1.05em;">
     Reserve your Pro Beta slot — $99/mo
  </a>
</p>

<p style="font-size:0.95em;color:#555;margin-top:-6px;">
  Up to 5 servers · hands-on onboarding for the first server ·
  <strong>30-day guarantee:</strong> if it doesn't catch or reduce one repeat
  incident, the next month is free.
</p>

<p style="font-size:0.9em;">
  Running one server, or a whole team? <a href="pricing">See all plans</a> —
  Starter ($29/mo) and Business Beta ($299/mo) are on the pricing page.
</p>

---

## Reserve your slot

<!--
  LEAD_FORM_EMBED — to use a real backed form (Tally, Google Forms, Typeform):
  1. Build a form with the fields listed under "What to include" below.
  2. Paste its embed URL into the iframe src.
  3. Delete this comment and the two "FORM-FALLBACK" comment lines to reveal the iframe.

  <iframe src="LEAD_FORM_EMBED"
          width="100%" height="720" frameborder="0"
          title="AgentPulse Paid Beta signup"></iframe>
-->

<!-- FORM-FALLBACK START (delete this block once the iframe above is live) -->
The fastest way in tonight: hit the button above, or send the details below to
[support@agentpulse.dustinnstroud.com](mailto:support@agentpulse.dustinnstroud.com?subject=AgentPulse%20paid%20beta%20request).
We reply within a few hours during the launch window with your recommended
first-server setup and the payment link for your plan.
<!-- FORM-FALLBACK END -->

### What to include

- Number of Linux servers you want to monitor.
- Hosting provider (Hetzner, DigitalOcean, Linode, Vultr, AWS Lightsail/EC2).
- Your stack: web server, process manager (PM2/systemd), database.
- The incident that keeps repeating.
- Whether you want to start alert-only, ask-first, or auto-fix.
- Your preferred plan: Starter, Pro Beta, or Business Beta.

## What happens after you sign up

1. **Within a few hours (launch window):** we reply with your recommended
   first-server setup and the safest starting policies.
2. **Day 0:** install the agent on one non-critical server in alert-only mode.
3. **Day 1–3:** we review the first real alerts together and identify your top
   repeat incident classes.
4. **When you're ready:** promote one safe action to ask-first, then to
   auto-fix only after you've seen it behave.

The first server always starts in **alert-only mode**. You only promote an
action to automatic once you'd be comfortable running it over SSH yourself.
Every policy is visible, reversible, and scoped to the server it runs on.

## Good first beta fit

- You run 1–10 Linux servers for a real app or client workload.
- You already have alerts, but still SSH in to fix the same things.
- You can name one recurring issue you want reduced: disk pressure, crashed
  services, runaway processes, or similar.
- You're willing to start with one server and review policies before any
  automation is enabled.

For urgent setup, email
[support@agentpulse.dustinnstroud.com](mailto:support@agentpulse.dustinnstroud.com).
