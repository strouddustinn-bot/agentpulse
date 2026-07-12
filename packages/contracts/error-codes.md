# AgentPulse Error Codes

All error codes are scoped to the component that emits them. Format: `<COMPONENT>_<NUMERIC_CODE>`.

## Agent (1xxx)

| Code | HTTP | Message | Resolution |
|------|------|---------|-----------|
| `AGENT_1000` | 400 | Invalid check-in payload | Agent sent malformed JSON or missing required fields |
| `AGENT_1001` | 400 | Signature verification failed | HMAC mismatch — check shared secret |
| `AGENT_1002` | 400 | Sequence number regression | Agent replayed an old sequence; must monotonically increase |
| `AGENT_1003` | 401 | Enrollment token expired | Token TTL exceeded; re-enroll via dashboard |
| `AGENT_1004` | 403 | Agent not enrolled | Agent must enroll before sending check-ins |
| `AGENT_1005` | 409 | Duplicate enrollment attempt | Agent already enrolled with this host_id |
| `AGENT_1006` | 422 | Unsupported check type | Agent does not support this check type; upgrade agent |
| `AGENT_1007` | 422 | Check configuration invalid | Check config failed schema validation |
| `AGENT_1008` | 429 | Rate limit exceeded | Check-in interval too short; increase interval |
| `AGENT_1009` | 503 | Backend unreachable | Network issue; agent queues locally and retries |

## Backend (2xxx)

| Code | HTTP | Message | Resolution |
|------|------|---------|-----------|
| `BACKEND_2000` | 500 | Internal server error | Internal failure; check backend logs |
| `BACKEND_2001` | 503 | Database unavailable | Check database connectivity and health |
| `BACKEND_2002` | 409 | Conflict | Resource already exists |
| `BACKEND_2003` | 404 | Resource not found | Check the requested ID is correct |
| `BACKEND_2004` | 422 | Validation error | Request body failed schema validation |
| `BACKEND_2005` | 429 | Rate limit exceeded | Back off and retry after retry_after seconds |

## Control Plane (3xxx)

| Code | HTTP | Message | Resolution |
|------|------|---------|-----------|
| `CP_3000` | 400 | Malformed request | Request body is not valid JSON |
| `CP_3001` | 401 | Authentication failed | Check API key or HMAC signature |
| `CP_3002` | 403 | Forbidden | Actor lacks permission for this operation |
| `CP_3003` | 404 | Tenant not found | Organization does not exist |
| `CP_3004` | 409 | Resource conflict | ID already exists (enrollment, etc.) |
| `CP_3005` | 422 | Contract version unsupported | Upgrade agent or backend to a supported contract version |

## Remediation (4xxx)

| Code | HTTP | Message | Resolution |
|------|------|---------|-----------|
| `REM_4000` | 409 | Idempotency key reused | This action has already been executed |
| `REM_4001` | 409 | Remediation already in progress | Wait for the current action to complete |
| `REM_4002` | 404 | Remediation target not found | Service or container does not exist |
| `REM_4003` | 403 | Action blocked by policy | Remediation risk level exceeds policy ceiling |
| `REM_4004` | 409 | Cooldown period active | Wait for cooldown to expire before retrying |
| `REM_4005` | 408 | Remediation timeout | Action took too long; increase timeout or check target |
| `REM_4006` | 422 | Preconditions not met | Required conditions for this action are not satisfied |
| `REM_4007` | 503 | Rollback unavailable | Rollback is not supported for this action type |

## Worker (5xxx)

| Code | HTTP | Message | Resolution |
|------|------|---------|-----------|
| `WORKER_5000` | 500 | Job execution failed | Check worker logs for the specific job |
| `WORKER_5001` | 429 | Job queue full | System under load; back off |
| `WORKER_5002` | 503 | Dependency unavailable | A required service (DB, queue) is down |

## Dashboard (6xxx)

| Code | HTTP | Message | Resolution |
|------|------|---------|-----------|
| `DASH_6000` | 401 | Authentication required | Log in or provide valid session token |
| `DASH_6001` | 403 | Insufficient permissions | Contact org admin to grant access |
| `DASH_6002` | 404 | Server not found | Agent may have been uninstalled |
| `DASH_6003` | 409 | Conflict | Resource already exists |
| `DASH_6004` | 422 | Invalid configuration | Check configuration values against schema |
