"""Email worker — SMTP send with template rendering."""

from __future__ import annotations

import json
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger("nami_workers.email")

SMTP_HOST = os.environ.get("NAMI_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("NAMI_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("NAMI_SMTP_USER", "")
SMTP_PASS = os.environ.get("NAMI_SMTP_PASS", "")


def email_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Email worker: send, batch, templates."""
    action = payload.get("action", "send")

    if action == "send":
        return _send(payload)
    elif action == "batch":
        return _batch(payload)
    elif action == "templates":
        return _templates()
    else:
        return {"error": f"unknown action: {action}"}


def _send(payload: dict[str, Any]) -> dict[str, Any]:
    """Send a single email."""
    to = payload.get("to", "")
    subject = payload.get("subject", "Nami Notification")
    body = payload.get("body", "")
    html = payload.get("html", "")

    if not to:
        return {"error": "to address required"}
    if not SMTP_USER or not SMTP_PASS:
        return {"error": "SMTP credentials not configured (NAMI_SMTP_USER, NAMI_SMTP_PASS)"}

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = SMTP_USER
        msg["To"] = to
        msg["Subject"] = subject
        if body:
            msg.attach(MIMEText(body, "plain"))
        if html:
            msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        logger.info("Email sent to %s: %s", to, subject)
        return {"ok": True, "to": to, "subject": subject}
    except Exception as exc:
        logger.warning("Email send failed: %s", exc)
        return {"error": str(exc)}


def _batch(payload: dict[str, Any]) -> dict[str, Any]:
    """Send email to multiple recipients."""
    recipients = payload.get("recipients", [])
    subject = payload.get("subject", "Nami Notification")
    body = payload.get("body", "")
    html = payload.get("html", "")

    if not recipients:
        return {"error": "recipients list required"}

    results = []
    for addr in recipients:
        result = _send({"to": addr, "subject": subject, "body": body, "html": html})
        results.append(result)

    sent = sum(1 for r in results if r.get("ok"))
    return {"ok": True, "sent": sent, "total": len(recipients)}


def _templates() -> dict[str, Any]:
    """List available email templates."""
    return {
        "templates": [
            {"name": "welcome", "description": "Welcome email for new users"},
            {"name": "alert", "description": "Alert notification email"},
            {"name": "report", "description": "Daily/weekly report summary"},
        ]
    }
