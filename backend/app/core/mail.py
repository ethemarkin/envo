"""Outgoing e-mail over SMTP.

Sending runs in a worker thread so the event loop is not blocked. Tests and
development without SMTP replace `deliver` (see tests/conftest.py).
"""

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger("envo.mail")


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    text: str


def _send_smtp(mail: Mail) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = mail.to
    msg["Subject"] = mail.subject
    msg.set_content(mail.text)
    with smtplib.SMTP(s.smtp_host or "", s.smtp_port, timeout=15) as smtp:
        if s.smtp_starttls:
            smtp.starttls()
        if s.smtp_username:
            smtp.login(s.smtp_username, s.smtp_password or "")
        smtp.send_message(msg)


async def deliver(mail: Mail) -> bool:
    """Send a message. Returns False (and logs without the body, which may
    contain a secret link) if SMTP is not configured or sending fails."""
    if not get_settings().smtp_enabled:
        return False
    try:
        await asyncio.to_thread(_send_smtp, mail)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        log.warning("sending %r to %s failed: %s", mail.subject, mail.to, exc)
        return False
