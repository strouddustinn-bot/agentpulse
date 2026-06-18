# Contributing to AgentPulse

AgentPulse is a single-host Linux monitoring agent with hard safety invariants. PRs welcome.

## Before you start

```bash
git clone https://github.com/strouddustinn-bot/agentpulse
cd agentpulse/agent
python3 tools/run_tests.py   # all 66 tests should pass
```

## What we want

- Bug fixes (especially in `ouroboros.py`, `policy.py`, or `remediation.py`)
- New checks (follow the pattern in `checks.py` + add tests)
- Documentation improvements
- More test coverage (fuzz cases are especially welcome)
- Performance — keep it dependency-free and minimal

## What we won't merge in v1

- Multi-server federation or cloud sync (in development, not open)
- ML-learned baselines beyond the statistical model in `baseline.py`
- Process auto-kill (the process check is intentionally clamped to `ask` in v1)
- Anything that weakens the hard safety rules in `policy.py`

## How to add a check

1. Add the check function in `agentpulse/checks.py`; return `List[Observation]`
2. Wire it into `checks.gather()`
3. Add a new key to `agentpulse/config.py`
4. Add tests in `tests/test_checks.py`
5. Update `agent/CONFIGURATION.md` with the new config fields

## Safety rules are non-negotiable

The hard limits in `policy.py` — no system-path sweeps, no auto process-kill,
allowlisted services only — are enforced by the fuzz harness (`tests/test_fuzz.py`).
Any PR that weakens them will be declined without exception.

## PR checklist

- [ ] `python3 tools/run_tests.py` passes (all tests, including fuzz)
- [ ] New logic has matching tests
- [ ] Safety invariants are intact
- [ ] No new third-party dependencies added

## Reporting bugs

Open a GitHub issue. Include:
- Your OS and Python version
- The config you're using (redact any sensitive paths)
- The output of `agentpulse run-once --dry-run <config>`
