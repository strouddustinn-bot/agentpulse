| Capability | Completion criterion | What exists now | Status |
|---|---|---|---|
| Windows package boundary | Wheel/package imports, platform-neutral help/config validation, and automatic hostname resolution run on Windows; unsupported host operations fail closed | Candidate adds a `windows-latest` smoke job plus explicit lock/spool, service/process-check, and remediation refusal tests; native Windows monitoring, service lifecycle, and clean-host acceptance remain absent | 🟡 |
| Credential rotation/revocation | Account and agent credentials can be revoked/rotated without DB surgery | Schema has revocation fields; complete API/UX and proof are absent | 🟡 |
