"""Optional email delivery for notifications.

In-app notifications (the bell icon) are always created by the task layer.
If SMTP_* settings are present, the same message is also emailed so people
who aren't logged in still hear about new work. Failures never break the
request that triggered them.
"""
import asyncio
import smtplib
from email.message import EmailMessage
from typing import Iterable, Set, Tuple

from app.config import settings
from app.logging_config import logger

_background: Set[asyncio.Task] = set()


def email_enabled() -> bool:
    return bool(settings.smtp_host and (settings.smtp_from or settings.smtp_user))


def _send_sync(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    footer = f"\n\nOpen the app: {settings.app_public_url}" if settings.app_public_url else ""
    msg.set_content(body + footer)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


async def _deliver(items: Iterable[Tuple[str, str, str]]) -> None:
    for to, subject, body in items:
        try:
            await asyncio.to_thread(_send_sync, to, subject, body)
        except Exception as exc:  # network / auth problems must not surface to users
            logger.warning(f"Email to {to} failed: {exc}")


def send_emails_in_background(items: Iterable[Tuple[str, str, str]]) -> None:
    items = list(items)
    if not items or not email_enabled():
        return
    task = asyncio.create_task(_deliver(items))
    _background.add(task)
    task.add_done_callback(_background.discard)
