# AgentPulse Tier 1 / Phase 1C acceptance evidence

**Acceptance date:** 2026-07-20
**Published baseline:** `v0.2.0-beta.1` (`0.2.0b1`)
**Repaired candidate:** local, unpublished `0.2.0b2` fixture
**Decision:** repaired source accepted on disposable Debian/systemd; published beta rejected; replacement immutable release still required.

## Evidence boundary

The published `v0.2.0-beta.1` wheel, source archive, and `SHA256SUMS` were downloaded from the GitHub Release and passed checksum verification. Clean-host testing then reproduced defects in that immutable artifact. It must not be described as containing the repairs below.

A wheel built from the repaired source was used only as an upgrade and lifecycle fixture. It was not published or presented as an official release.

Candidate fixture SHA-256:

```text
7ae77aae95274768fa2caa48899f268ec5bb41a19b1b2323cb1d37f0d89b7939  agentpulse-0.2.0b2-py3-none-any.whl
```

## Published-beta defects reproduced

- The active control-plane heartbeat path did not durably spool outage evidence.
- Queued check-in evidence was not automatically replayed by the runtime.
- Enrollment tokens could be exposed through process arguments.
- Installer dry-run failure was warning-only.
- Smoke-test warnings could be reported with success status.
- Upgrade and rollback did not fully enforce the requested resulting version.
- Non-purge uninstall backed up obsolete paths and initially used a predictable temporary destination.
- Declining purge did not stop destructive deletion.
- State writes were permissive and used a predictable temporary filename.
- Real Python 3.11 delivery exposed an invalid positional `urllib.request.urlopen` timeout call.

## Repaired-source verification

Local verification at the accepted source tree:

- Agent suite: `193 passed, 0 failed`.
- Packaging/lifecycle suite: `20 passed, 0 failed`.
- Ruff: passed.
- Agent config schema validation: passed.
- Lifecycle shell syntax: passed.
- Git whitespace/diff validation: passed.
- Final review fixes preserve the current event during credential-recovery
  replay and contain a missing check-in credential without stopping the local
  safety cycle. The synthetic fixture was rebuilt and both canonical disposable
  host runners passed again after those changes.

Focused disposable-host control-plane recovery:

- Four events were present after the outage window.
- The recovered endpoint received replayed heartbeats.
- The backlog drained from four events to zero.
- No Python `TypeError` occurred after the urllib timeout fix.
- The sandbox was destroyed after the run.

## Broad disposable-host acceptance

The broad acceptance runner passed:

- immutable beta-1 download and checksum verification;
- exact installed version verification;
- alert-only configuration and dry-run;
- package, config, directory, and service invariants;
- process restart recovery;
- outage spooling, redaction, restart persistence, and explicit replay;
- non-purge uninstall and preserved configuration/state;
- reinstall with preserved configuration;
- purge removal.

Receipt name: `agentpulse-gate1-latest.json`
Receipt result: `OVERALL=PASS`
Sandbox cleanup: confirmed.

## Real-systemd lifecycle acceptance

The real-systemd runner passed with fail-fast remote commands and independent assertions:

- published beta-1 installation and service activation;
- alert-only runtime and secure files;
- reproduction of beta-1's missing control-plane outage spool;
- upgrade to the checksummed local `0.2.0b2` candidate;
- durable, redacted control-plane spooling during outage;
- process-locked, storage-bounded strict-FIFO replay after endpoint recovery;
- credential-recovery propagation and permanent-response quarantine;
- fail-closed post-start service liveness verification;
- backlog drain to zero;
- preserved config/state through upgrade;
- rollback to beta-1 with preserved config/state;
- secure `mktemp` non-purge backup;
- uninstall, reinstall, and final purge.

Receipt name: `agentpulse-gate1-systemd-latest.json`
Receipt result: `OVERALL=PASS`
Sandbox cleanup: confirmed.

## Remaining release gate

Tier 1 is not publicly complete yet. The accepted source must be committed and packaged as a new immutable prerelease, recommended `v0.2.0-beta.2`. The exact published wheel and checksums must then repeat the clean-host acceptance run. Public self-serve installation remains closed until that exact-artifact run passes.
