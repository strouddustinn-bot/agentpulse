# Coralogix GitHub telemetry and webhook setup

## Purpose and scope

Two complementary paths use subsystem `agentpulse` for consistent filtering:

| Path | Data | Application |
| --- | --- | --- |
| [Actions exporter](../../.github/workflows/coralogix.yaml) | CI/CD logs, traces, and workflow metrics from completed runs, including failures and cancellations | `github-actions` |
| GitHub Contextual Data webhook | Repository events: pushes, pull requests, issues, releases, and optional workflow activity | `github-events` |

Use `github-events` for contextual events unless the organization intentionally
groups both paths into one application; in that case use `github-actions` for
both. Always use subsystem `agentpulse`. Webhook workflow events provide
context, not the detailed CI logs, traces, and metrics sent by the exporter.

These files prepare the integration; they do not prove ingestion is operational.
An administrator completes the external setup and validation below. This does
not replace the [Production Synthetic Watch](production-watch.md) or its alerts.

## Prerequisites

An administrator needs:

- Permission to create or manage Coralogix Contextual Data integrations.
- Repository-admin permission to add a GitHub webhook and manage Actions settings.
- A Coralogix Send-Your-Data API key for Contextual Data, and an appropriate
  Send-Your-Data key for Actions export. Prefer separate keys for independent rotation.
- The correct Coralogix account domain/region and its OTLP HTTP ingress endpoint.

Check for an existing integration or webhook before adding another. Reuse or
update it where appropriate to avoid duplicate ingestion.

## GitHub Actions setup

1. In repository **Settings > Secrets and variables > Actions**, configure:

   | Type | Name | Value |
   | --- | --- | --- |
   | Repository variable | `CORALOGIX_OTLP_ENDPOINT` | HTTPS OTLP HTTP base endpoint for the account's region |
   | Repository secret | `CORALOGIX_SEND_YOUR_DATA_API_KEY` | Send-Your-Data API key; never a plain variable |

2. Use a base endpoint only, without `/v1/logs`, `/v1/traces`, or `/v1/metrics`;
   the exporter appends these paths. Do not use the generated webhook URL here.
   Non-secret configuration notation (not a file to source or commit with real values):

   ```text
   CORALOGIX_OTLP_ENDPOINT=https://ingress.<your-coralogix-domain>:443
   CORALOGIX_SEND_YOUR_DATA_API_KEY=<store-as-a-GitHub-Actions-secret>
   ```

3. Through normal review, place `.github/workflows/coralogix.yaml` on the default
   branch, currently `master`. No existing CI workflow needs modification.
4. Confirm repository Actions policy allows `coralogix/OTLP-GitHubAction-Exporter@v3`.
   `GITHUB_TOKEN` is supplied automatically and has only `actions: read` here;
   no personal access token or write permission is needed.

The exporter reads run/job metadata and logs through GitHub's API. It does not
check out a pull-request head, restore its caches, execute its artifacts, or run
repository code. Its Docker action contains its own implementation, so checkout
is unnecessary. Metadata uses the triggering run, not the exporter run; custom
JSON values use `toJSON` to preserve quotes and other characters safely.

## Coralogix setup

1. In the correct Coralogix account/region, go to **Data Flow > Contextual Data**.
2. Choose **GitHub**.
3. Select **Add > Add new** (or manage the existing integration).
4. Give the integration a descriptive name, supply the Contextual Data
   Send-Your-Data API key, and set **App Name** to `github-events` (or
   `github-actions` under the shared-application policy above) and
   **Subsystem Name** to `agentpulse`.
5. Select **Generate URL**, then copy the generated ingestion URL and webhook secret.
6. Treat both generated values as sensitive configuration. Transfer them directly
   into GitHub's webhook form and retain them only in approved secret storage.

The Contextual Data URL and signing secret are separate from the Actions OTLP
endpoint and API-key secret. Do not substitute one for another.

## GitHub repository setup

1. Open `agentpulse` **Settings > Webhooks > Add webhook**.
2. Paste the generated Coralogix URL into **Payload URL**.
3. Set **Content type** to `application/json`.
4. Paste the generated webhook secret into **Secret**.
5. Enable **SSL verification**.
6. Choose **Let me select individual events**. Start with **Pushes**,
   **Pull requests**, **Issues**, and **Releases**. Add **Issue comments** only
   if useful to the team. Add **Workflow runs** or **Check runs** only if
   supported by the integration and useful for correlation.
7. Leave the webhook **Active** and select **Add webhook**.
8. Open **Recent Deliveries**, inspect the initial ping and an actual selected
   event, then confirm the contextual event in Coralogix.

Keep event selection minimal initially. Expand it only when the additional
events help incident correlation; avoid selecting all events by default.

## Security and privacy

- Never commit API keys, generated webhook URLs, or webhook secrets. Keep them
  out of logs, screenshots, issues, and support attachments. These docs may be public.
- Rotate exposed credentials immediately, update both sides as needed, and
  remove exposed copies from logs/history through the incident process.
- Restrict event selection and assess whether issue/PR text, comments, commit
  messages, or author information contain sensitive data before enabling ingestion.
- Actions exports include workflow logs. Keep sensitive data out of source
  workflow logs; GitHub masking is not a substitute for that control.
- Preserve GitHub webhook signature verification with the generated shared
  secret (`X-Hub-Signature-256`) wherever applicable. Do not remove the secret
  or disable TLS/signature checks to work around delivery failures.
- Limit repository-settings and Coralogix integration access to the operators
  who need it. Apply appropriate telemetry access and retention controls.
- Keep exporter `GITHUB_DEBUG` disabled; HTTP debug output can reveal headers.
  Inspect errors without printing environment variables or authorization headers.

## Validation checklist

- [ ] Trigger or wait for a completed workflow, such as **Tests** or
  **Production Readiness**. Find **Export GitHub Actions telemetry to Coralogix**
  and confirm it exports the source run. Also inspect a failed or cancelled
  source run when one is available; no success-only filter is configured.
- [ ] In Coralogix, verify logs, traces, and metrics with `service.name=github`,
  `cx.application.name=github-actions`, and `cx.subsystem.name=agentpulse`.
  Match `github.repository`, `github.workflow.run.id`, and
  `github.workflow.run.url` to the source run.
- [ ] Use an authorized safe test event, such as a test-branch push or test PR.
  Do not alter a production release merely to test the webhook.
- [ ] Confirm the selected event has a successful 2xx delivery in GitHub
  **Recent Deliveries**; a successful ping alone is insufficient.
- [ ] Find that contextual event in Coralogix under the chosen application
  (`github-events` by default) and subsystem `agentpulse`. Match repository,
  event time, and commit or PR identity to the delivery.
- [ ] Confirm a completion from the exporter itself skips its export job;
  it must not produce repeated export jobs for itself.
- [ ] Verify no secrets appear in repository files, GitHub workflow logs, or
  shared delivery diagnostics. Record only run/delivery IDs, timestamps, and
  redacted outcomes as validation evidence.

## Troubleshooting

| Symptom | Check and action |
| --- | --- |
| Exporter never runs | The workflow must exist on the default branch (`master`), and another workflow must complete afterward. Check Actions policy and whether the source workflow ran at all. GitHub also limits `workflow_run` chains to three levels. |
| Recursive exports | Keep the workflow name and its job's exclusion string identical: `Export GitHub Actions telemetry to Coralogix`. A skipped export job for its own completion is expected. Do not remove the exclusion or add a second wildcard exporter. |
| Missing/invalid endpoint | Set repository variable `CORALOGIX_OTLP_ENDPOINT` to the account's HTTPS OTLP HTTP base URL. Check spelling, region, port, whitespace, and reachability from GitHub-hosted runners. Do not use a webhook URL or signal-specific path. |
| Missing/invalid key | Set Actions repository secret `CORALOGIX_SEND_YOUR_DATA_API_KEY` to an active Send-Your-Data key for the correct account. An environment-only secret is unavailable because this job declares no environment. |
| OTLP 401/403 or authorization failure | Confirm endpoint and key belong to the same account/region, the key permits ingestion, and it has not expired or been revoked. The workflow constructs `Authorization=Bearer ...`; do not paste the prefix into the secret. Never print the header while debugging. |
| Source-run log download fails | Verify `actions: read`, log retention, and source-run log availability. Runs cancelled before jobs start, or runs with deleted/expired logs, may contain little or no exportable data. Do not grant write access to fix a read failure. |
| Webhook timeout, non-2xx, or failed signature | Inspect GitHub delivery status and sanitized response details. Check generated URL/account, active integration, SSL verification, and the matching generated secret. For signature failures, correct the secret on both sides without disabling verification. Redeliver the failed event after repair and check for duplicates. |
| Successful delivery/export but no visible data | Check time range, account, and application/subsystem filters. Actions uses `github-actions`; contextual events use `github-events` unless deliberately shared. Both use `agentpulse`. Confirm the event was selected and inspect each signal, not just workflow success. |

## References

- [Coralogix GitHub Actions integration](https://www.coralogix.com/docs/integrations/ci/cd/github-actions/)
- [Exporter v3 source and configuration](https://github.com/coralogix/OTLP-GitHubAction-Exporter/tree/v3)
- [Coralogix GitHub Contextual Data integration](https://www.coralogix.com/docs/integrations/contextual-data/github-data-ingestion/)
- [Coralogix endpoints by region](https://coralogix.com/docs/integrations/coralogix-endpoints/)
- [GitHub workflow_run behavior and security](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
- [Validating GitHub webhook deliveries](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)
