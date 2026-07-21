---
layout: default
home: true
title: AgentPulse — Safe first response for repeat server incidents
description: "AgentPulse detects repeat server incidents, applies only policy-approved fixes, verifies the result, and escalates when a fix does not hold."
---

<section class="hero section-pad">
  <div class="hero-copy reveal is-visible">
    <div class="eyebrow"><span class="live-dot"></span> Controlled beta · Alert-only by default</div>
    <h1>Your servers don’t need <em>another dashboard.</em></h1>
    <p class="hero-lede">They need a safer first responder. AgentPulse detects repeat host incidents, prepares a bounded fix, checks local policy, and proves whether the action worked.</p>
    <div class="hero-actions">
      <a class="button button-primary" href="signup#reserve"><span>Request a controlled pilot</span><span aria-hidden="true">↗</span></a>
      <a class="button button-quiet" href="features"><span class="play-icon" aria-hidden="true">▶</span> See the decision loop</a>
    </div>
    <div class="hero-proof">
      <div><strong>Local authority</strong><span>The host decides what is allowed.</span></div>
      <div><strong>Verified actions</strong><span>Every change is checked afterward.</span></div>
      <div><strong>No remote shell</strong><span>Known actions, not arbitrary commands.</span></div>
    </div>
  </div>

  <div class="hero-visual reveal is-visible" aria-label="AgentPulse remediation decision visualization">
    <div class="visual-chrome">
      <span class="visual-label">LIVE DECISION TRACE</span>
      <span class="visual-secure"><i></i> LOCAL POLICY ACTIVE</span>
    </div>
    <div class="incident-head">
      <div class="incident-icon"><span></span></div>
      <div><span>INCIDENT / DISK PRESSURE</span><strong>Cache volume at 91%</strong></div>
      <time>00:14:32</time>
    </div>
    <div class="trace">
      <div class="trace-line" aria-hidden="true"></div>
      <div class="trace-step complete"><span>01</span><div><strong>Observe</strong><small>Threshold crossed · 91.2%</small></div><b>DONE</b></div>
      <div class="trace-step complete"><span>02</span><div><strong>Simulate</strong><small>1.8 GB recoverable · 0 protected</small></div><b>SAFE</b></div>
      <div class="trace-step active"><span>03</span><div><strong>Gate</strong><small>Path allowlist + symlink boundary</small></div><b>PASS</b></div>
      <div class="trace-step pending"><span>04</span><div><strong>Act</strong><small>Awaiting approved mode</small></div><b>ASK</b></div>
      <div class="trace-step pending"><span>05</span><div><strong>Verify</strong><small>Re-check original condition</small></div><b>NEXT</b></div>
    </div>
    <div class="visual-footer"><span><i></i> Evidence recorded locally</span><span>POLICY / CACHE-CLEANUP-01</span></div>
  </div>
</section>

<section class="trust-strip" aria-label="Product principles">
  <span>BUILT FOR SMALL INFRASTRUCTURE TEAMS</span>
  <div><i></i> Linux</div><div><i></i> macOS</div><div><i></i> systemd</div><div><i></i> launchd</div><div><i></i> Generic webhooks</div>
</section>

<section class="thesis section-pad reveal">
  <div class="section-index">01 / THE PROBLEM</div>
  <div class="thesis-grid">
    <h2>Monitoring sees the fire.<br><span>AgentPulse handles the known first move.</span></h2>
    <div>
      <p>A full observability stack can show every spike, trace, and log line. It still leaves someone SSHing into a host to restart the same service or clear the same safe cache path.</p>
      <p>AgentPulse is deliberately narrower: repeat host incidents, explicit authority, deterministic safety gates, and verification after every attempted fix.</p>
    </div>
  </div>
</section>

<section class="system-section section-pad reveal">
  <div class="system-intro">
    <div class="section-index">02 / THE SYSTEM</div>
    <h2>Authority stays local.<br>Evidence travels.</h2>
    <p>Cloud policy can make the agent more restrictive. It cannot widen the authority configured on the host.</p>
    <a class="text-link" href="features">Explore the safety model <span>→</span></a>
  </div>
  <div class="system-map">
    <div class="map-orbit orbit-one" aria-hidden="true"></div>
    <div class="map-orbit orbit-two" aria-hidden="true"></div>
    <div class="map-node map-host"><span>HOST</span><strong>Local agent</strong><small>Checks · policy · actions</small></div>
    <div class="map-node map-policy"><span>BOUNDARY</span><strong>Local allowlist</strong><small>Cannot be widened remotely</small></div>
    <div class="map-node map-cloud"><span>CLOUD</span><strong>Fleet evidence</strong><small>Status · history · escalation</small></div>
    <svg class="map-lines" viewBox="0 0 720 500" aria-hidden="true">
      <path d="M180 250 C 300 250, 305 120, 430 120" />
      <path d="M180 250 C 320 250, 390 365, 540 365" />
      <circle cx="180" cy="250" r="4"/><circle cx="430" cy="120" r="4"/><circle cx="540" cy="365" r="4"/>
    </svg>
    <div class="map-caption"><span>OUTBOUND-ONLY</span><span>REDACTED</span><span>RETRY-BOUNDED</span></div>
  </div>
</section>

<section class="autonomy section-pad reveal">
  <div class="section-index">03 / CONTROL</div>
  <div class="autonomy-head">
    <h2>Not “autonomous” or “manual.”<br><span>Exactly as much authority as each check deserves.</span></h2>
    <p>Promote one low-risk action without giving every incident the same permission.</p>
  </div>
  <div class="mode-rail">
    <div class="mode"><span>01</span><strong>Off</strong><p>Do not run this check.</p></div>
    <div class="mode"><span>02</span><strong>Alert</strong><p>Detect and notify. Change nothing.</p><b>DEFAULT</b></div>
    <div class="mode mode-active"><span>03</span><strong>Ask</strong><p>Prepare the fix. Wait for approval.</p><b>REVIEW</b></div>
    <div class="mode"><span>04</span><strong>Auto</strong><p>Run an allowlisted fix, then verify.</p><b>OPT-IN</b></div>
  </div>
</section>

<section class="incidents section-pad reveal">
  <div class="section-index">04 / REPEAT INCIDENTS</div>
  <div class="incidents-layout">
    <div class="incident-title">
      <h2>Built for the incidents you’re tired of fixing twice.</h2>
      <p>Known problem. Narrow response. Measurable outcome.</p>
    </div>
    <div class="incident-list">
      <article><span>01</span><div><h3>Disk pressure</h3><p>Clean only configured paths. Refuse system paths, directories, and symlink escapes.</p></div><b>Clean → re-check</b></article>
      <article><span>02</span><div><h3>Crashed service</h3><p>Restart only an allowlisted systemd or launchd service, then confirm it is active.</p></div><b>Restart → verify</b></article>
      <article><span>03</span><div><h3>Runaway process</h3><p>Identify the largest memory offender and preserve the termination decision for a person.</p></div><b>Detect → report</b></article>
      <article><span>04</span><div><h3>Fix did not hold</h3><p>Record failed verification and escalate instead of entering a destructive retry loop.</p></div><b>Stop → escalate</b></article>
    </div>
  </div>
</section>

<section class="proof-section section-pad reveal">
  <div class="proof-card">
    <div class="proof-kicker">PRODUCT BOUNDARY</div>
    <h2>The confidence comes from what AgentPulse <em>refuses</em> to do.</h2>
    <div class="proof-grid">
      <div><span>×</span><p>No arbitrary browser-to-host command channel.</p></div>
      <div><span>×</span><p>No automatic process killing in the current release.</p></div>
      <div><span>×</span><p>No widening local authority from the cloud.</p></div>
      <div><span>×</span><p>No blind retries after verification fails.</p></div>
    </div>
    <a class="text-link" href="install">Review the current release boundary <span>→</span></a>
  </div>
</section>

<section class="plans section-pad reveal">
  <div class="plans-copy">
    <div class="section-index">05 / FOUNDING BETA</div>
    <h2>Start with one host.<br>Earn the next permission.</h2>
    <p>Every pilot begins on one approved non-critical host in alert-only mode. Multi-host plans remain founding reservations until the full paid lifecycle is ready.</p>
    <a class="button button-primary" href="signup#reserve"><span>Request beta access</span><span>↗</span></a>
  </div>
  <div class="plan-ledger">
    <div class="plan-row"><div><span>STARTER</span><strong>Controlled pilot</strong></div><div><strong>C$29</strong><span>/ month CAD</span></div><p>One host · alert-only first</p></div>
    <div class="plan-row featured"><div><span>PRO · FOUNDING</span><strong>Small fleet</strong></div><div><strong>C$99</strong><span>/ month CAD</span></div><p>Up to 5 hosts when fleet access ships</p></div>
    <div class="plan-row"><div><span>BUSINESS · FOUNDING</span><strong>Agreed fleet</strong></div><div><strong>C$299</strong><span>/ month CAD</span></div><p>Finite host limit confirmed before billing</p></div>
    <small>Reservations are free. No charge until the matching service is ready and you choose to activate.</small>
  </div>
</section>

<section class="final-cta section-pad reveal">
  <div class="cta-glow" aria-hidden="true"></div>
  <div class="eyebrow">ONE REPEAT INCIDENT IS ENOUGH TO START</div>
  <h2>Stop being the remediation layer.</h2>
  <p>Tell us the host type, stack, and incident you keep fixing. No credentials. No server addresses. Just enough to confirm fit.</p>
  <div class="hero-actions centered">
    <a class="button button-primary" href="signup#reserve"><span>Request a controlled pilot</span><span>↗</span></a>
    <a class="button button-quiet" href="mailto:support@agentpulse.ca">support@agentpulse.ca</a>
  </div>
</section>
