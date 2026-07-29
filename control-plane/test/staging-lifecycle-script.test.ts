// Vite inlines the shell artifact during transform; Workers tests cannot read
// outside the isolate's virtual filesystem at runtime.
// @ts-expect-error Vite raw imports are resolved by the test transform.
import script from "../../scripts/staging-commercial-lifecycle.sh?raw";
import { describe, expect, it } from "vitest";

describe("staging commercial lifecycle script", () => {
  it("uses prepare/prove exit semantics without secret argv/env continuation", () => {
    expect(script).toContain("mode required: prepare|prove");
    expect(script).toContain("prepare) prepare ;;");
    expect(script).toContain("prove) prove ;;");
    expect(script).toContain("EXIT_OWNER_ACTION=10");
    expect(script).toContain("AGENTPULSE_STAGING_LIFECYCLE INCOMPLETE");
    expect(script).toContain("AGENTPULSE_STAGING_LIFECYCLE PASS");
    expect(script).not.toContain("AP_CLAIM_NONCE");
  });

  it("protects capability material and validates staging checkout identity", () => {
    expect(script).toContain("umask 077");
    expect(script).toContain("chmod 700 \"$TMP_DIR\"");
    expect(script).toContain("chmod 600 \"$HANDOFF_FILE\"");
    expect(script).toContain("json_assert \"$LAST_BODY\" livemode=False");
    expect(script).toContain("session_id_assert \"$checkout_id\"");
    expect(script).toContain("url_assert_class \"$checkout_url\" checkout");
    expect(script).toContain('p.netloc == "billing.stripe.com" or p.netloc.endswith(".stripe.com")');
    expect(script).toContain("session_id=redacted");
    expect(script).not.toContain('echo "checkout=pass session_id=${checkout_id}');
  });

  it("proves required negative and replay checks before PASS", () => {
    expect(script).toContain("request POST /v1/onboarding/claim 409");
    expect(script).toContain("request POST /v1/billing/portal 403");
    expect(script).toContain("Origin: https://evil.example");
    expect(script).toContain("request POST /v1/agents/enroll 409");
    expect(script).toContain('json_get_file "$LAST_BODY" enrollment_token');
    expect(script).toContain('"agent_key":"agentpulse-staging-proof-agent"');
    expect(script).toContain('"local_policy_ceiling":"alert"');
    expect(script).toContain('"idempotency_key": "ap-proof-heartbeat-staging-lifecycle"');
    expect(script).toContain('a.get("agent_key") == "agentpulse-staging-proof-agent"');
    expect(script).toContain("request POST /v1/agents/heartbeat 202");
    expect(script).toContain("request POST /v1/agents/heartbeat 200");
    expect(script).toContain("request GET /v1/account 401");
    expect(script).toContain("request GET /v1/fleet 401");
  });
});
