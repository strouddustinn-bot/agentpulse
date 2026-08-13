# Windows Agent Support Spike

> **For Hermes:** Use this plan to start Windows support as a separate platform slice, not as part of the current Tier 4 production launch track.

**Goal:** Add a scoped Windows agent MVP for AgentPulse, starting with alert-only support and a clear path to bounded remediation later.

**Architecture:** Keep the Worker/D1 control plane, dashboard, OpenAPI contracts, and policy model platform-neutral. Add Windows-specific adapters only where POSIX assumptions currently exist: service control, process/memory observation, file locking, filesystem safety rules, and packaging/install lifecycle. Start with read-only observation and import/install proof before any remediation or service management.

**Tech Stack:** Python agent package, pytest/unittest, Windows CI runner, packaging/build tooling, repository docs, and platform-specific service APIs (`sc.exe`/PowerShell or a bounded adapter layer).

---

## Why this is a separate slice

Windows support is not a one-line portability tweak. The current agent assumes POSIX behaviors in service management, locking, filesystem layout, and some process observation paths. Building Windows now is reasonable, but it should be treated as a standalone platform expansion so it does not block the ongoing Tier 4 production launch work.

## Proposed scope

### MVP target

- Alert-only Windows support first.
- No remediation on Windows until the observation and packaging path is proven.
- No change to the control plane contract unless Windows-specific behavior requires it.

### Out of scope for the first slice

- Production Windows installer branding and signing.
- Full remediation parity.
- Reusing POSIX service assumptions on Windows.
- Any change to launch gating for Linux/macOS rollout.

## Files likely to change

- `agent/agentpulse/checks.py`
- `agent/agentpulse/remediation.py`
- `agent/agentpulse/locking.py`
- `agent/agentpulse/spool.py`
- `agent/agentpulse/cli.py`
- `agent/tests/test_checks.py`
- `agent/tests/test_remediation.py`
- `agent/tests/test_locking.py`
- `agent/tests/test_spool.py`
- `pyproject.toml`
- `.github/workflows/*.yml`
- `docs/` (Windows support notes, install expectations, release boundary)

## Step-by-step plan

### Task 1: Map the Windows seams and define the adapter boundary

**Objective:** Identify exactly which host-OS behaviors need abstraction and where the current code already branches on Linux vs macOS.

**Files:**
- Read: `agent/agentpulse/checks.py`
- Read: `agent/agentpulse/remediation.py`
- Read: `agent/agentpulse/locking.py`
- Read: `agent/agentpulse/spool.py`
- Read: `agent/agentpulse/cli.py`
- Read: `scripts/install-agent.sh`
- Read: `scripts/uninstall-agent.sh`

**Deliverable:** A small adapter contract for Windows-specific behavior, with no code changes yet.

### Task 2: Add Windows-safe read-only observation first

**Objective:** Make the agent import and run on Windows for observation-only checks, without any remediation.

**Files:**
- Modify: `agent/agentpulse/checks.py`
- Modify: `agent/agentpulse/cli.py`
- Add tests under `agent/tests/`

**Behavior to prove:**
- Windows can report host state without `/proc`, `systemctl`, or `launchctl`.
- Unsupported remediation paths fail closed instead of trying POSIX calls.

### Task 3: Replace POSIX-only locking and path assumptions

**Objective:** Make state/credential/spool writes and lock behavior safe on Windows.

**Files:**
- Modify: `agent/agentpulse/locking.py`
- Modify: `agent/agentpulse/spool.py`
- Add platform tests for drive letters, UNC paths, and reparse/junction refusal rules

**Behavior to prove:**
- Locking has an equivalent stale/timeout story on Windows.
- Path safety refuses unsafe roots and path escapes on Windows.

### Task 4: Add bounded Windows service control only after observation is stable

**Objective:** Introduce a Windows service adapter only after read-only support is proven.

**Files:**
- Modify: `agent/agentpulse/remediation.py`
- Add a new Windows service adapter module if needed
- Add tests for restart/stop/start allowlist behavior

**Behavior to prove:**
- Service control is allowlisted and bounded.
- No arbitrary command execution path is introduced.

### Task 5: Add Windows packaging and CI coverage

**Objective:** Prove install/import/smoke coverage on a Windows runner.

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/*.yml`
- Add Windows-specific packaging and smoke tests

**Behavior to prove:**
- Windows wheel install/import passes.
- A CLI smoke test runs on Windows.
- Unit tests cover the new adapter boundaries.

### Task 6: Document the support boundary

**Objective:** Tell users exactly what Windows does and does not support.

**Files:**
- Update: `agent/README.md`
- Update: `ARCHITECTURE.md`
- Update: `docs/` Windows support note or release note

**Behavior to prove:**
- Docs state Windows as a bounded platform expansion, not full parity until verified.

## Validation

Minimum checks before calling the spike successful:

1. Existing Linux/macOS tests remain green.
2. New Windows-focused unit tests pass.
3. Windows CI job can install and import the package.
4. Any Windows-specific command or path support fails closed when unsupported.
5. The plan remains separate from Tier 4 production launch work.

## Risks and tradeoffs

- Windows support may expose hidden POSIX assumptions in locking and path handling.
- Service management is the biggest divergence from Linux/macOS.
- If we try to do full parity immediately, the spike will sprawl and delay launch.

## Recommended execution order

1. Read the seams.
2. Implement observation-only Windows support.
3. Add Windows tests and CI.
4. Expand into bounded service control.
5. Leave remediation parity for a later slice.

## 2026-08-01 — Hermes — Windows integration checkpoint

**Outcome:** Added a narrow uncommitted Windows package/CLI smoke slice. Package imports no longer fail solely because `fcntl` is absent; `LockManager` and `Spool` now raise `UnsupportedPlatformError` before filesystem work when POSIX locking is unavailable. CI installs the wheel on `windows-latest`, imports the boundary modules, and runs `--help` plus config validation as independently gated steps. Agent docs explicitly state that monitoring, service control, remediation, and Windows lifecycle installation remain unsupported.

**Files touched:** `.github/workflows/test.yml`, `agent/README.md`, `agent/agentpulse/locking.py`, `agent/agentpulse/spool.py`, `agent/agentpulse/platform_support.py`, `agent/tests/test_windows_compat.py`, `tests/test_packaging.py`.

**Verification:** RED tests reproduced the `fcntl` import failure and workflow exit-code masking risk; final agent suite 195/195, packaging 24/24, Ruff clean, workflow YAML/step contract PASS, `git diff --check` PASS, and independent exact-slice review PASS with no security or logic findings.

**Remaining gates:** The Windows GitHub runner has not executed this uncommitted workflow. Functional Windows monitoring still requires platform observation adapters plus Windows-safe locking/state/spool permissions; service control/remediation and installer lifecycle remain later fail-closed slices. Windows is non-blocking for Tier 4 launch.

## 2026-08-01 — Hermes — Windows process fail-closed checkpoint

**Outcome:** Advanced the existing uncommitted Windows candidate with one TDD-sized safety fix. On Windows, the `/proc`-based process check now emits one explicit breached/unsupported observation without invoking a command or probing POSIX process state; it can no longer return an empty result that looks healthy. Updated the agent README and finished-product matrix to the verified 200-test count.

**Files touched in this checkpoint:** `agent/agentpulse/checks.py`, `agent/tests/test_checks.py`, `agent/README.md`, `docs/planning/AGENTPULSE-FINISHED-PRODUCT-MATRIX.md`.

**Verification:** RED was 199 passed / 1 failed before implementation; GREEN was `make agent-test` 200/200, `make packaging-test` 24/24 plus launchd XML and shell syntax PASS, pinned Ruff 0.4.10 PASS via isolated `uvx`, `git diff --check` PASS, and a self-cleaning ad-hoc changed-behavior probe PASS with unchanged pre/post hashes. The host is Linux, so the uncommitted `windows-latest` workflow has not produced native Windows evidence.

**Next autonomous slice:** Run the frozen candidate on GitHub `windows-latest`; after native package/CLI smoke is green, implement a read-only Windows process-memory adapter with injected platform APIs and adversarial unit tests. Keep remediation, Windows Service lifecycle, installer/signing, and support claims closed until their separate gates pass.

## 2026-08-01 — Hermes — Windows hostname portability checkpoint

**Outcome:** Removed one additional POSIX-only runtime assumption from the uncommitted Windows candidate. Automatic host identity now uses cross-platform `socket.gethostname()` instead of `os.uname()`, with a regression that deletes `os.uname` to simulate the Windows API surface. The `windows-latest` smoke candidate now exercises automatic hostname resolution as its own native command step.

**Files touched in this checkpoint:** `agent/agentpulse/config.py`, `agent/tests/test_config.py`, `.github/workflows/test.yml`, `tests/test_packaging.py`, `agent/README.md`, `docs/planning/AGENTPULSE-FINISHED-PRODUCT-MATRIX.md`.

**Verification:** TDD RED was 200 passed / 1 failed on missing `os.uname`; GREEN was `make agent-test` 201/201, `make packaging-test` 24/24 plus launchd XML and shell syntax PASS, pinned Ruff 0.4.10 PASS via isolated `uvx`, `git diff --check` PASS, and a self-cleaning ad-hoc changed-behavior probe PASS with unchanged changed-path hashes. The host is Linux, so the uncommitted `windows-latest` workflow still has no native Windows execution receipt.

**Next autonomous slice:** Preserve the frozen candidate until it can run on GitHub `windows-latest`. After that native smoke is green, implement the planned read-only Windows process-memory adapter; do not advance remediation, Windows Service control, installer/signing, or support claims before their separate gates.

