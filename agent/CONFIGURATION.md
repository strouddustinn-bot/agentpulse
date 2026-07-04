# AgentPulse Configuration Reference

The agent is configured with a single JSON file.
Start from `agentpulse.config.example.json` (production) or
`agentpulse.config.local.json` (local testing, no root needed).

---

## Top-level fields

| Field | Type | Default | Description |
|---|---|---|---|
| `hostname` | string | `"auto"` | Server label in notifications. `"auto"` reads the system hostname. |
| `interval_seconds` | int | `60` | How often the daemon runs a check cycle. |
| `state_file` | string | required | Path to the JSON file the agent uses to persist pending approvals and baseline data. Created on first run. |
| `log_file` | string | `""` | Optional. If set, the agent writes structured log lines here in addition to stdout. |

---

## `notify`

```json
"notify": {
  "type": "stdout",
  "webhook_url": ""
}
```

| Field | Values | Description |
|---|---|---|
| `type` | `"stdout"` · `"webhook"` | Where alerts are sent. `"stdout"` prints to the journal. `"webhook"` POSTs JSON to `webhook_url`. |
| `webhook_url` | URL string | Required when `type` is `"webhook"`; must be `http://` or `https://`. Discord/Slack webhook format is supported. |

---

## `baseline`

Statistical anomaly detection on top of threshold checks.

```json
"baseline": {
  "enabled": true,
  "min_samples": 20,
  "z_threshold": 3.0,
  "min_abs_deviation": 2.0
}
```

| Field | Type | Description |
|---|---|---|
| `enabled` | bool | Turn baseline learning on or off. |
| `min_samples` | int | Minimum observations before anomaly alerts fire. The agent stays quiet until it has seen enough data to know what "normal" looks like. |
| `z_threshold` | float | How many standard deviations from the mean counts as anomalous. 3.0 is conservative (few false positives). |
| `min_abs_deviation` | float | Suppresses alerts when the absolute deviation is small even if z-score is high. Avoids noise on very stable metrics. |

---

## `checks`

Each check has a `mode` field that controls how AgentPulse responds when a condition breaches threshold.

| Mode | Behavior |
|---|---|
| `"off"` | Check is disabled entirely. |
| `"alert"` | Default. Sends a notification; takes no action. |
| `"ask"` | Queues the fix for your approval. Run `agentpulse list-pending` + `agentpulse approve`. |
| `"auto"` | Runs the decision loop automatically (simulate → validate → execute → verify). Escalates if verify fails instead of retrying. |

---

### `checks.disk`

```json
"disk": {
  "mode": "alert",
  "threshold_percent": 90,
  "paths": ["/"],
  "cleanup_globs": ["/tmp/*", "/var/tmp/*"],
  "cleanup_older_than_days": 3
}
```

| Field | Type | Description |
|---|---|---|
| `threshold_percent` | int | Alert/act when a path's disk usage hits this percentage. |
| `paths` | string[] | Mount points to monitor. |
| `cleanup_globs` | string[] | Glob patterns of files the agent may delete. **Used only when mode is `ask` or `auto`.** Hard limits: never deletes directories, symlinks, files newer than `cleanup_older_than_days`, anything under system paths (`/bin`, `/etc`, `/usr`, etc.), or files that resolve outside the glob's base directory through a symlinked subdirectory. |
| `cleanup_older_than_days` | int | Files newer than this are never touched, regardless of the glob. |

**Example: auto-clean /var/log on a high-traffic server**
```json
"disk": {
  "mode": "auto",
  "threshold_percent": 85,
  "paths": ["/var"],
  "cleanup_globs": ["/var/log/nginx/*.gz", "/var/log/*.gz"],
  "cleanup_older_than_days": 7
}
```

---

### `checks.service`

```json
"service": {
  "mode": "alert",
  "services": ["nginx"]
}
```

| Field | Type | Description |
|---|---|---|
| `services` | string[] | systemd service names to monitor. Only services explicitly listed here can be restarted. |

**Example: auto-restart nginx + redis**
```json
"service": {
  "mode": "auto",
  "services": ["nginx", "redis"]
}
```

---

### `checks.process`

```json
"process": {
  "mode": "alert",
  "mem_percent_threshold": 85
}
```

| Field | Type | Description |
|---|---|---|
| `mem_percent_threshold` | float | Alert when a single process consumes this percentage of total system memory. |

**Safety note:** The process check **never auto-kills** in v1, even when `mode` is `"auto"`.
It flags the offender and queues it for your approval at most. This is intentional — automated process-kill is too dangerous for a first release.

---

## Minimal production config

```json
{
  "hostname": "web-01",
  "interval_seconds": 60,
  "state_file": "/var/lib/agentpulse/state.json",
  "log_file": "/var/log/agentpulse/agentpulse.log",
  "notify": {
    "type": "webhook",
    "webhook_url": "https://hooks.slack.com/services/your/webhook/url"
  },
  "baseline": {
    "enabled": true,
    "min_samples": 20,
    "z_threshold": 3.0,
    "min_abs_deviation": 2.0
  },
  "checks": {
    "disk": {
      "mode": "ask",
      "threshold_percent": 90,
      "paths": ["/"],
      "cleanup_globs": ["/tmp/*", "/var/tmp/*"],
      "cleanup_older_than_days": 3
    },
    "service": {
      "mode": "ask",
      "services": ["nginx"]
    },
    "process": {
      "mode": "alert",
      "mem_percent_threshold": 85
    }
  }
}
```

Validate before deploying:
```bash
agentpulse validate /etc/agentpulse/config.json
```
