"""Notifications. Multi-channel: stdout, webhook, email, Telegram.

All channels are stdlib-only. A failed channel falls back to stdout; a broken
notification chain never crashes the agent.
"""

from __future__ import annotations

import json
import smtplib
import ssl
import urllib.error
import urllib.request
from email.mime.text import MIMEText
from typing import List

from .config import NotifyChannel, NotifyConfig


class _StdoutChannel:
    def send(self, title: str, body: str) -> bool:
        print(f"[AgentPulse] {title}\n{body}", flush=True)
        return True


class _WebhookChannel:
    def __init__(self, ch: NotifyChannel, opener=None):
        self.url = ch.webhook_url
        self._opener = opener or urllib.request.urlopen

    def send(self, title: str, body: str) -> bool:
        payload = json.dumps({"text": f"[AgentPulse] {title}\n{body}"}).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(req, timeout=10) as resp:
                return 200 <= getattr(resp, "status", 200) < 300
        except (urllib.error.URLError, OSError) as exc:
            print(f"[AgentPulse] {title}\n{body}\n(webhook failed: {exc})", flush=True)
            return False


class _EmailChannel:
    def __init__(self, ch: NotifyChannel):
        self.smtp_host = ch.smtp_host
        self.smtp_port = ch.smtp_port
        self.smtp_user = ch.smtp_user
        self.smtp_password = ch.smtp_password
        self.from_address = ch.from_address
        self.to_addresses = list(ch.to_addresses)
        self.use_tls = ch.use_tls

    def send(self, title: str, body: str) -> bool:
        if not self.smtp_host or not self.to_addresses:
            return False
        msg = MIMEText(f"{title}\n\n{body}", "plain", "utf-8")
        msg["Subject"] = f"[AgentPulse] {title}"
        msg["From"] = self.from_address
        msg["To"] = ", ".join(self.to_addresses)
        try:
            if self.use_tls:
                ctx = ssl.create_default_context()
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as s:
                    s.starttls(context=ctx)
                    if self.smtp_user:
                        s.login(self.smtp_user, self.smtp_password)
                    s.sendmail(self.from_address, self.to_addresses, msg.as_string())
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as s:
                    if self.smtp_user:
                        s.login(self.smtp_user, self.smtp_password)
                    s.sendmail(self.from_address, self.to_addresses, msg.as_string())
            return True
        except (smtplib.SMTPException, OSError) as exc:
            print(f"[AgentPulse] {title}\n{body}\n(email failed: {exc})", flush=True)
            return False


class _TelegramChannel:
    _API = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, ch: NotifyChannel, opener=None):
        self.bot_token = ch.bot_token
        self.chat_id = ch.chat_id
        self._opener = opener or urllib.request.urlopen

    def send(self, title: str, body: str) -> bool:
        if not self.bot_token or not self.chat_id:
            return False
        text = f"*[AgentPulse]* {title}\n{body}"
        payload = json.dumps({
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }).encode("utf-8")
        url = self._API.format(token=self.bot_token)
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return bool(data.get("ok"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            print(f"[AgentPulse] {title}\n{body}\n(telegram failed: {exc})", flush=True)
            return False


def _build_channel(ch: NotifyChannel, opener=None):
    if ch.type == "webhook":
        return _WebhookChannel(ch, opener=opener)
    if ch.type == "email":
        return _EmailChannel(ch)
    if ch.type == "telegram":
        return _TelegramChannel(ch, opener=opener)
    return _StdoutChannel()


class Notifier:
    def __init__(self, cfg: NotifyConfig, opener=None):
        self._channels = [_build_channel(ch, opener=opener) for ch in cfg.channels]

    def send(self, title: str, body: str) -> bool:
        results = [ch.send(title, body) for ch in self._channels]
        return any(results)
