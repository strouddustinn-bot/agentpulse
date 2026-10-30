#!/usr/bin/env python3
"""Read-only, bounded public website probe with redacted failure diagnostics."""
from __future__ import annotations

import http.client
import ssl
import time
import urllib.error
import urllib.request

URL = "https://agentpulse.ca/"
MARKER = b"Automatic recovery for the server incidents"
MAX_BODY_BYTES = 524288


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_response(response) -> str | None:
    if response.getcode() != 200:
        return f"expected HTTP 200, got {response.getcode()}"
    if response.geturl() != URL:
        return "response URL differs from canonical URL"
    body = response.read(MAX_BODY_BYTES + 1)
    if len(body) > MAX_BODY_BYTES:
        return "response exceeded the 512 KiB safety limit"
    if MARKER not in body:
        return "expected public product marker missing"
    return None


def probe(opener, *, attempts=3, delay=2, sleep=time.sleep, report=print) -> bool:
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            URL,
            headers={"Accept": "text/html", "User-Agent": "AgentPulse-production-watch/1"},
        )
        try:
            with opener.open(request, timeout=8) as response:
                error = check_response(response)
        except urllib.error.HTTPError as exc:
            # A real HTTP rejection is different from a transport failure.
            # Never print its body, headers, reason, or redirect destination.
            error = f"expected HTTP 200, got {exc.code}"
            exc.close()
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            error = f"transport failed: {type(exc).__name__}"
        if error is None:
            report(f"public_site=pass attempts_used={attempt}")
            return True
        report(f"public_site=blocked attempt={attempt}/{attempts}: {error}")
        if attempt < attempts:
            sleep(delay)
    return False


def main() -> int:
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        NoRedirectHandler(),
    )
    return 0 if probe(opener) else 1


if __name__ == "__main__":
    raise SystemExit(main())
