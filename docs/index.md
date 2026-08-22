---
layout: default
home: true
title: Automatic recovery for repeat server incidents
description: "Detect supported recurring server failures, run only approved recovery actions, verify the result, and escalate uncertainty instead of guessing."
---

<section class="hero section-pad">
  <div class="hero-copy reveal is-visible">
    <div class="eyebrow"><span class="live-dot"></span> BOUNDED SERVER RECOVERY</div>
    <h1>Automatic recovery for the server incidents <em>you already know how to fix.</em></h1>
    <p class="hero-lede">Turn recurring incidents into approved recovery playbooks. When the evidence matches, a permitted recovery can run. When it does not, the system stops and escalates.</p>
    <div class="hero-actions">
      <a class="button button-primary" href="https://app.agentpulse.ca/signup?plan=starter&source=home-hero"><span>Start with one host</span><span aria-hidden="true">↗</span></a>
      <a class="button button-quiet" href="#how-it-works"><span class="play-icon" aria-hidden="true">▶</span> See how it works</a>
    </div>
    <div class="hero-proof">
      <div><strong>Approved actions only</strong><span>No arbitrary remote shell.</span></div>
      <div><strong>Verified afterward</strong><span>A recovery is re-checked after action.</span></div>
      <div><strong>Fails closed</strong><span>Uncertainty goes to a human.</span></div>
    </div>
  </div>

  <div class="hero-visual reveal is-visible" aria-label="Bounded remediation decision visualization">
    <div class="visual-chrome">
      <span class="visual-label">ILLUSTRATIVE DECISION TRACE</span>
      <span class="visual-secure"><i></i> LOCAL POLICY ACTIVE</span>
    </div>
    <div class="incident-head">
      <div class="incident-icon"><span></span></div>
      <div><span>INCIDENT / SERVICE DOWN</span><strong>Approved service stopped</strong></div>
      <time>00:00:07</time>
    </div>
    <div class="trace">
      <div class="trace-line" aria-hidden="true"></div>
      <div class="trace-step complete"><span>01</span><div><strong>Detect</strong><small>Known condition matched</small></div><b>DONE</b></div>
      <div class="trace-step complete"><span>02</span><div><strong>Simulate</strong><small>Approved recovery selected</small></div><b>SAFE</b></div>
      <div class="trace-step active"><span>03</span><div><strong>Gate</strong><small>Local allowlist checked</small></div><b>PASS</b></div>
      <div class="trace-step pending"><span>04</span><div><strong>Act</strong><small>Bounded action only</small></div><b>NEXT</b></div>
      <div class="trace-step pending"><span>05</span><div><strong>Verify</strong><small>Re-check original failure</small></div><b>NEXT</b></div>
    </div>
    <div class="visual-footer"><span><i></i> Evidence recorded</span><span>NO ARBITRARY COMMANDS</span></div>
  </div>
</section>

<section class="trust-strip" aria-label="Product principles">
  <span>FOR OPERATORS WHO ALREADY KNOW THE FIRST FIX</span>
  <div><i></i> Linux</div><div><i></i> macOS</div><div><i></i> systemd</div><div><i></i> launchd</div><div><i></i> Generic webhooks</div>
</section>

<section id="how-it-works" class="thesis section-pad reveal">
  <div class="section-index">01 / HOW IT WORKS</div>
  <div class="thesis-grid">
    <h2>Observe → reason → simulate → gate → act → verify.</h2>
    <div>
      <p>Detect a supported recurring condition. Match it to a configured response. Simulate the proposed change. Check the host's local policy. Run only the permitted action. Verify the original condition afterward.</p>
      <p>If the evidence is weak, the action is unknown, policy denies it, or verification fails, recovery stops and the incident is escalated instead of entering an uncontrolled retry loop.</p>
    </div>
  </div>
</section>

<section class="system-section section-pad reveal">
  <div class="system-intro">
    <div class="section-index">02 / WHY IT IS DIFFERENT</div>
    <h2>Not “give an AI root access and hope.”</h2>
    <p>Host authority stays local. Cloud policy may narrow what is allowed, but cannot widen the host's local authority ceiling. Unknown actions fail closed.</p>
    <a class="text-link" href="features">Review the safety model <span>→</span></a>
  </div>
  <div class="system-map">
    <div class="map-orbit orbit-one" aria-hidden="true"></div>
    <div class="map-orbit orbit-two" aria-hidden="true"></div>
    <div class="map-node map-host"><span>HOST</span><strong>Local agent</strong><small>Detection · simulation · actions</small></div>
    <div class="map-node map-policy"><span>BOUNDARY</span><strong>Local allowlist</strong><small>Cannot be widened remotely</small></div>
    <div class="map-node map-cloud"><span>CONTROL PLANE</span><strong>Fleet evidence</strong><small>Policy can only reduce authority</small></div>
    <svg class="map-lines" viewBox="0 0 720 500" aria-hidden="true">
      <path d="M180 250 C 300 250, 305 120, 430 120" />
      <path d="M180 250 C 320 250, 390 365, 540 365" />
      <circle cx="180" cy="250" r="4"/><circle cx="430" cy="120" r="4"/><circle cx="540" cy="365" r="4"/>
    </svg>
    <div class="map-caption"><span>ALLOWLISTED</span><span>VERIFIED</span><span>RECORDED</span></div>
  </div>
</section>

<section class="incidents section-pad reveal">
  <div class="section-index">03 / SUPPORTED REPEAT INCIDENTS</div>
  <div class="incidents-layout">
    <div class="incident-title">
      <h2>Start with the failures you are tired of fixing twice.</h2>
      <p>Known problem. Narrow response. Measurable outcome.</p>
    </div>
    <div class="incident-list">
      <article><span>01</span><div><h3>Crashed service</h3><p>Restart only an allowlisted systemd or launchd service, then confirm it is active.</p></div><b>Restart → verify</b></article>
      <article><span>02</span><div><h3>Disk pressure</h3><p>Clean only configured paths while refusing protected paths and symlink escapes, then re-check capacity.</p></div><b>Clean → re-check</b></article>
      <article><span>03</span><div><h3>Runaway process</h3><p>Identify and report the largest memory offender. The current release leaves process termination to a person.</p></div><b>Detect → report</b></article>
      <article><span>04</span><div><h3>Recovery did not hold</h3><p>Record failed verification and escalate once instead of retrying blindly.</p></div><b>Stop → escalate</b></article>
    </div>
  </div>
</section>

<section id="pricing" class="plans section-pad reveal">
  <div class="plans-copy">
    <div class="section-index">04 / PRICING</div>
    <h2>Pay for the host scope you actually run.</h2>
    <p>Current monthly pricing is preserved for this demand test. The point is to test whether the recovery model is worth paying for, not optimize pricing before there is buyer evidence.</p>
    <a class="button button-primary" href="https://app.agentpulse.ca/signup?plan=starter&source=home-pricing"><span>Start Starter checkout</span><span>↗</span></a>
    <small style="display:block;margin-top:14px;">Checkout is currently provided under the product name AgentPulse.</small>
  </div>
  <div class="plan-ledger">
    <div class="plan-row"><div><span>STARTER</span><strong>One host</strong></div><div><strong>C$29</strong><span>/ month CAD</span></div><p>1 host</p></div>
    <div class="plan-row featured"><div><span>PRO</span><strong>Small fleet</strong></div><div><strong>C$99</strong><span>/ month CAD</span></div><p>Up to 5 hosts</p></div>
    <div class="plan-row"><div><span>BUSINESS</span><strong>Managed small fleet</strong></div><div><strong>C$299</strong><span>/ month CAD</span></div><p>Up to 20 hosts · priority support · guided onboarding</p></div>
    <small>Supported incident classes and local policy still determine what may run automatically.</small>
  </div>
</section>

<section class="proof-section section-pad reveal">
  <div class="proof-card">
    <div class="proof-kicker">PRODUCT BOUNDARY</div>
    <h2>Confidence comes from what the system <em>refuses</em> to do.</h2>
    <div class="proof-grid">
      <div><span>×</span><p>No arbitrary browser-to-host command channel.</p></div>
      <div><span>×</span><p>No automatic process killing in the current release.</p></div>
      <div><span>×</span><p>No widening local authority from the cloud.</p></div>
      <div><span>×</span><p>No blind retries after verification fails.</p></div>
    </div>
  </div>
</section>

<section class="final-cta section-pad reveal">
  <div class="cta-glow" aria-hidden="true"></div>
  <div class="eyebrow">ONE REPEAT INCIDENT IS ENOUGH TO START</div>
  <h2>Stop being the remediation layer.</h2>
  <p>If you can name the failure and the first recovery step you already trust, that is the problem this product is built to test.</p>
  <div class="hero-actions centered">
    <a class="button button-primary" href="https://app.agentpulse.ca/signup?plan=starter&source=home-final"><span>Start with one host</span><span>↗</span></a>
    <a class="button button-quiet" href="mailto:support@agentpulse.ca">Ask a question</a>
  </div>
  <p style="margin-top:18px;font-size:0.82rem;opacity:0.72;">Checkout is currently provided under the product name AgentPulse.</p>
</section>
