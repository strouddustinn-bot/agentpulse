#!/usr/bin/env bash
set -euo pipefail
umask 077

EXIT_CONFIG=2
EXIT_ASSERT=3
EXIT_OWNER_ACTION=10

MODE="${1:-}"
if [[ -z "$MODE" && -n "${AP_STAGING_LIFECYCLE_MODE:-}" ]]; then
  MODE="$AP_STAGING_LIFECYCLE_MODE"
fi
if [[ -z "$MODE" ]]; then
  echo "FAIL config: mode required: prepare|prove" >&2
  exit 2
fi
API_BASE="${AP_STAGING_API_BASE:-https://staging-api.agentpulse.ca}"
APP_ORIGIN="${AP_STAGING_APP_ORIGIN:-https://staging-app.agentpulse.ca}"
PLAN="${AP_STAGING_PLAN:-starter}"
CLAIM_FILE="${AP_CLAIM_FILE:-}"
HANDOFF_FILE="${AP_CHECKOUT_HANDOFF_FILE:-}"
CURL_CONNECT_TIMEOUT="${AP_CURL_CONNECT_TIMEOUT:-5}"
CURL_MAX_TIME="${AP_CURL_MAX_TIME:-20}"
TMP_DIR=""
COOKIE_JAR=""
CSRF_FILE=""
AGENT_CREDENTIAL_FILE=""
IDEMPOTENCY_FILE=""
LAST_STATUS=""
LAST_BODY=""
LAST_HEADERS=""
LAST_RESPONSE_HEADERS=""
LAST_METHOD=""
LAST_PATH=""

cleanup() {
  if [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT HUP INT TERM

fail_config() { echo "FAIL config: $*" >&2; exit "$EXIT_CONFIG"; }
fail_assert() { echo "FAIL assertion: $*" >&2; exit "$EXIT_ASSERT"; }

init_tmp() {
  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/agentpulse-staging-lifecycle.XXXXXX")"
  chmod 700 "$TMP_DIR"
  COOKIE_JAR="$TMP_DIR/cookies.jar"
  CSRF_FILE="$TMP_DIR/csrf"
  AGENT_CREDENTIAL_FILE="$TMP_DIR/agent-credential"
  IDEMPOTENCY_FILE="$TMP_DIR/idempotency-key"
  : > "$COOKIE_JAR"
  : > "$CSRF_FILE"
  : > "$AGENT_CREDENTIAL_FILE"
  : > "$IDEMPOTENCY_FILE"
  chmod 600 "$COOKIE_JAR" "$CSRF_FILE" "$AGENT_CREDENTIAL_FILE" "$IDEMPOTENCY_FILE"
}

redact_url_origin() {
  python3 - "$1" <<'PY'
from urllib.parse import urlsplit
import sys
p = urlsplit(sys.argv[1])
print(f"{p.scheme}://{p.netloc}")
PY
}

validate_origin_url() {
  python3 - "$1" <<'PY'
from urllib.parse import urlsplit
import sys
u = sys.argv[1]
p = urlsplit(u)
if p.scheme not in ("http", "https") or p.username or p.password or p.path not in ("", "/") or p.query or p.fragment or not p.hostname:
    raise SystemExit(1)
if p.hostname not in ("localhost", "127.0.0.1", "staging-api.agentpulse.ca"):
    raise SystemExit(1)
if p.hostname in ("localhost", "127.0.0.1") and p.scheme != "http":
    raise SystemExit(1)
if p.hostname == "staging-api.agentpulse.ca" and p.scheme != "https":
    raise SystemExit(1)
PY
}

json_get_file() {
  python3 - "$1" "$2" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for key in sys.argv[2].split('.'):
    if key == "len()":
        value = len(value)
    elif isinstance(value, list):
        value = value[int(key)]
    else:
        value = value[key]
print(value)
PY
}

json_assert() {
  python3 - "$1" "$2" <<'PY'
import json, sys
path, expr = sys.argv[2].split("=", 1)
value = json.load(open(sys.argv[1], encoding="utf-8"))
for key in path.split('.'):
    if key == "len()":
        value = len(value)
    elif isinstance(value, list):
        value = value[int(key)]
    else:
        value = value[key]
if str(value) != expr:
    raise SystemExit(f"expected {path}={expr}, got {value}")
PY
}

url_assert_class() {
  python3 - "$1" "$2" <<'PY'
from urllib.parse import urlsplit
import sys
url, kind = sys.argv[1], sys.argv[2]
p = urlsplit(url)
if p.scheme != "https" or p.username or p.password or not p.netloc:
    raise SystemExit(1)
if kind == "checkout" and not (p.netloc == "checkout.stripe.com" and p.path.startswith("/c/")):
    raise SystemExit(1)
if kind == "portal" and not (p.netloc == "billing.stripe.com" or p.netloc.endswith(".stripe.com")):
    raise SystemExit(1)
PY
}

session_id_assert() {
  python3 - "$1" <<'PY'
import re, sys
if not re.match(r"^cs_test_[A-Za-z0-9_]+$", sys.argv[1]):
    raise SystemExit(1)
PY
}

request() {
  local method="$1" path="$2" expected="$3" body_file="${4:-}" header_file="${5:-}"
  LAST_METHOD="$method"
  LAST_PATH="$path"
  LAST_STATUS="$TMP_DIR/status"
  LAST_BODY="$TMP_DIR/body-${method//[^A-Za-z0-9]/_}-${path//[^A-Za-z0-9]/_}"
  LAST_HEADERS="$TMP_DIR/headers-${method//[^A-Za-z0-9]/_}-${path//[^A-Za-z0-9]/_}"
  LAST_RESPONSE_HEADERS="$TMP_DIR/response-headers-${method//[^A-Za-z0-9]/_}-${path//[^A-Za-z0-9]/_}"
  : > "$LAST_HEADERS"
  chmod 600 "$LAST_HEADERS"
  if [[ -n "$header_file" ]]; then cat "$header_file" >> "$LAST_HEADERS"; fi
  local args=(--silent --show-error --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" --request "$method" "${API_BASE}${path}" --cookie "$COOKIE_JAR" --cookie-jar "$COOKIE_JAR" --dump-header "$LAST_RESPONSE_HEADERS" --output "$LAST_BODY" --write-out '%{http_code}' --header "Accept: application/json")
  if [[ -s "$LAST_HEADERS" ]]; then args+=(--header "@$LAST_HEADERS"); fi
  if [[ -n "$body_file" ]]; then args+=(--header "Content-Type: application/json" --data-binary "@$body_file"); fi
  if ! curl "${args[@]}" > "$LAST_STATUS"; then
    echo "FAIL ${method} ${path}: transport" >&2
    exit "$EXIT_ASSERT"
  fi
  local status
  status="$(cat "$LAST_STATUS")"
  if [[ "$status" != "$expected" ]]; then
    echo "FAIL ${method} ${path}: expected HTTP ${expected}, got ${status}" >&2
    exit "$EXIT_ASSERT"
  fi
}

write_json_body() {
  local file="$1" content="$2"
  printf '%s' "$content" > "$file"
  chmod 600 "$file"
}

write_csrf_header() {
  local file="$1" origin="${2:-$APP_ORIGIN}"
  {
    printf 'Origin: %s\n' "$origin"
    printf 'X-CSRF-Token: %s\n' "$(cat "$CSRF_FILE")"
  } > "$file"
  chmod 600 "$file"
}

write_origin_header() {
  local file="$1" origin="$2"
  printf 'Origin: %s\n' "$origin" > "$file"
  chmod 600 "$file"
}

require_mode600_file() {
  local file="$1" label="$2"
  [[ -n "$file" ]] || fail_config "$label file path is required"
  [[ -f "$file" ]] || fail_config "$label file does not exist"
  local mode
  mode="$(python3 - "$file" <<'PY'
import os, stat, sys
print(oct(stat.S_IMODE(os.stat(sys.argv[1]).st_mode)))
PY
)"
  [[ "$mode" == "0o600" ]] || fail_config "$label file must be mode 600, got $mode"
}

prepare() {
  validate_origin_url "$API_BASE" || fail_config "unexpected AP_STAGING_API_BASE"
  case "$PLAN" in starter|pro|business) ;; *) fail_config "AP_STAGING_PLAN must be starter, pro, or business" ;; esac
  init_tmp
  if [[ -z "$HANDOFF_FILE" ]]; then
    HANDOFF_FILE="$(pwd)/agentpulse-staging-checkout-handoff.txt"
  fi
  [[ ! -e "$HANDOFF_FILE" ]] || fail_config "handoff file already exists: $HANDOFF_FILE"

  echo "AgentPulse staging lifecycle prepare"
  echo "api_base=$(redact_url_origin "$API_BASE")"
  echo "mode=test-only no-real-payment"

  request GET /health 200
  json_assert "$LAST_BODY" ok=True || fail_assert "health ok missing"
  json_get_file "$LAST_BODY" environment >/dev/null || fail_assert "health environment missing"

  local checkout_body="$TMP_DIR/checkout.json"
  write_json_body "$checkout_body" "{\"plan\":\"${PLAN}\"}"
  request POST /v1/billing/checkout 201 "$checkout_body"
  json_assert "$LAST_BODY" livemode=False || fail_assert "checkout livemode must be false"
  local checkout_id checkout_url expires_at
  checkout_id="$(json_get_file "$LAST_BODY" checkout_session_id)"
  session_id_assert "$checkout_id" || fail_assert "checkout_session_id is not cs_test_*"
  checkout_url="$(json_get_file "$LAST_BODY" checkout_url)"
  url_assert_class "$checkout_url" checkout || fail_assert "checkout_url is not a Stripe Checkout URL"
  expires_at="$(json_get_file "$LAST_BODY" expires_at)"

  {
    echo "AgentPulse staging Checkout operator handoff"
    echo "WARNING: Stripe test mode only. Use Stripe test payment details only; do not enter a real card."
    echo "checkout_url=${checkout_url}"
    echo "checkout_session_id=${checkout_id}"
    echo "livemode=false"
    echo "expires_at=${expires_at}"
    echo "After payment, provide claim material to prove via a mode-600 file or protected stdin/FD only."
  } > "$HANDOFF_FILE"
  chmod 600 "$HANDOFF_FILE"

  echo "checkout=pass session_id=redacted livemode=false url_origin=$(redact_url_origin "$checkout_url") handoff_file=${HANDOFF_FILE}"
  echo "AGENTPULSE_STAGING_LIFECYCLE INCOMPLETE owner_action_required=true"
  exit "$EXIT_OWNER_ACTION"
}

read_claim_nonce() {
  if [[ -n "$CLAIM_FILE" ]]; then
    require_mode600_file "$CLAIM_FILE" "claim"
    python3 - "$CLAIM_FILE" <<'PY'
import json, sys
raw = open(sys.argv[1], encoding="utf-8").read().strip()
try:
    value = json.loads(raw).get("claim_nonce", raw)
except Exception:
    value = raw
if not isinstance(value, str) or len(value) < 16:
    raise SystemExit(1)
print(value)
PY
  else
    if [[ -t 0 ]]; then fail_config "prove requires AP_CLAIM_FILE mode-600 file or protected stdin"; fi
    python3 - <<'PY'
import json, sys
raw = sys.stdin.read().strip()
try:
    value = json.loads(raw).get("claim_nonce", raw)
except Exception:
    value = raw
if not isinstance(value, str) or len(value) < 16:
    raise SystemExit(1)
print(value)
PY
  fi
}

prove() {
  validate_origin_url "$API_BASE" || fail_config "unexpected AP_STAGING_API_BASE"
  init_tmp
  local claim_nonce
  claim_nonce="$(read_claim_nonce)" || fail_config "invalid claim material"

  echo "AgentPulse staging lifecycle prove"
  echo "api_base=$(redact_url_origin "$API_BASE")"
  echo "mode=test-only no-real-payment"

  request GET /health 200
  json_assert "$LAST_BODY" ok=True || fail_assert "health ok missing"

  local claim_body="$TMP_DIR/claim.json" origin_header="$TMP_DIR/origin.header"
  printf '%s' "$claim_nonce" | python3 -c 'import json, sys; print(json.dumps({"claim_nonce": sys.stdin.read()}))' > "$claim_body"
  chmod 600 "$claim_body"
  write_origin_header "$origin_header" "$APP_ORIGIN"
  request POST /v1/onboarding/claim 200 "$claim_body" "$origin_header"
  json_get_file "$LAST_BODY" csrf_token > "$CSRF_FILE"
  chmod 600 "$CSRF_FILE"
  json_assert "$LAST_BODY" account.entitlement_status=active || json_assert "$LAST_BODY" account.entitlement_status=grace || fail_assert "claim account entitlement not hosted-ok"
  local plan host_limit
  plan="$(json_get_file "$LAST_BODY" account.plan)"
  host_limit="$(json_get_file "$LAST_BODY" account.agent_limit)"
  echo "claim=pass csrf=redacted cookie=redacted plan=${plan} host_limit=${host_limit}"

  request POST /v1/onboarding/claim 409 "$claim_body" "$origin_header"
  echo "claim_replay=pass status=409"

  request GET /v1/account 200
  json_assert "$LAST_BODY" plan="$plan" || fail_assert "account plan mismatch"
  echo "account=pass plan=${plan} host_limit=${host_limit}"

  local empty_body="$TMP_DIR/empty.json" bad_header="$TMP_DIR/bad.header" csrf_header="$TMP_DIR/csrf.header"
  write_json_body "$empty_body" "{}"
  write_origin_header "$bad_header" "$APP_ORIGIN"
  request POST /v1/billing/portal 403 "$empty_body" "$bad_header"
  printf 'Origin: https://evil.example\nX-CSRF-Token: %s\n' "$(cat "$CSRF_FILE")" > "$bad_header"
  chmod 600 "$bad_header"
  request POST /v1/billing/portal 403 "$empty_body" "$bad_header"
  write_csrf_header "$csrf_header"
  request POST /v1/billing/portal 200 "$empty_body" "$csrf_header"
  local portal_url
  portal_url="$(json_get_file "$LAST_BODY" portal_url)"
  url_assert_class "$portal_url" portal || fail_assert "portal_url is not Stripe-hosted"
  echo "portal=pass url=redacted"

  local enroll_body="$TMP_DIR/enrollment-token.json"
  write_json_body "$enroll_body" '{"ttl_seconds":300}'
  request POST /v1/browser/enrollment-tokens 201 "$enroll_body" "$csrf_header"
  local enrollment_token
  enrollment_token="$(json_get_file "$LAST_BODY" enrollment_token)"
  echo "browser_enrollment_token=pass token=redacted"

  local enroll_agent_body="$TMP_DIR/agent-enroll.json" enrollment_header="$TMP_DIR/enrollment.header"
  write_json_body "$enroll_agent_body" '{"agent_key":"agentpulse-staging-proof-agent","hostname":"agentpulse-staging-proof-host","local_policy_ceiling":"alert"}'
  printf 'Authorization: Bearer %s\n' "$enrollment_token" > "$enrollment_header"
  chmod 600 "$enrollment_header"
  request POST /v1/agents/enroll 201 "$enroll_agent_body" "$enrollment_header"
  json_get_file "$LAST_BODY" agent_credential > "$AGENT_CREDENTIAL_FILE"
  chmod 600 "$AGENT_CREDENTIAL_FILE"
  request POST /v1/agents/enroll 409 "$enroll_agent_body" "$enrollment_header"
  echo "agent_enrollment=pass credential=redacted replay_status=409"

  local heartbeat_body="$TMP_DIR/heartbeat.json" agent_header="$TMP_DIR/agent.header"
  printf 'ap-proof-heartbeat-staging-lifecycle' > "$IDEMPOTENCY_FILE"
  write_json_body "$heartbeat_body" "$(python3 - <<'PY'
import json
print(json.dumps({
  "agent_id": "agentpulse-staging-proof-agent",
  "idempotency_key": "ap-proof-heartbeat-staging-lifecycle",
  "hostname": "agentpulse-staging-proof-host",
  "observed_at": 1784144000,
  "policy_mode": "alert",
  "summary": {"observations": 1, "breaches": 0, "actions": 0, "queued": 0, "alerts": 0, "anomalies": 0, "escalations": 0, "blocked": 0},
  "incidents": []
}))
PY
)"
  {
    printf 'Authorization: Bearer %s\n' "$(cat "$AGENT_CREDENTIAL_FILE")"
    printf 'Idempotency-Key: %s\n' "$(cat "$IDEMPOTENCY_FILE")"
  } > "$agent_header"
  chmod 600 "$agent_header"
  request POST /v1/agents/heartbeat 202 "$heartbeat_body" "$agent_header"
  request POST /v1/agents/heartbeat 200 "$heartbeat_body" "$agent_header"
  echo "heartbeat=pass first_status=202 duplicate_status=200"

  request GET /v1/fleet 200
  python3 - "$LAST_BODY" <<'PY' || fail_assert "synthetic agent missing from fleet"
import json, sys
body = json.load(open(sys.argv[1], encoding="utf-8"))
agents = body.get("agents", [])
if not any(a.get("agent_key") == "agentpulse-staging-proof-agent" and a.get("hostname") == "agentpulse-staging-proof-host" for a in agents):
    raise SystemExit(1)
PY
  echo "fleet=pass contains_synthetic_agent=true"

  request DELETE /v1/session 204 "" "$csrf_header"
  request GET /v1/account 401
  request GET /v1/fleet 401
  echo "logout=pass post_logout_account=401 post_logout_fleet=401"
  echo "AGENTPULSE_STAGING_LIFECYCLE PASS plan=${plan} entitlement_hosted_ok=true host_limit=${host_limit} checkout_created=false secrets_redacted=true"
}

case "$MODE" in
  prepare) prepare ;;
  prove) prove ;;
  *) fail_config "mode must be prepare or prove" ;;
esac
