"""Outgoing email. SMTP when configured, otherwise the message is printed to the API's log.

    DBINSIGHT_SMTP_HOST / _PORT / _USER / _PASSWORD / _FROM / _STARTTLS (default on, off for 1025) / _HELO

For local development, `docker compose up -d mailpit` and set DBINSIGHT_SMTP_HOST=localhost
DBINSIGHT_SMTP_PORT=1025: every message then appears at http://localhost:8025.
"""

import logging
import os
import smtplib
import ssl
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

log = logging.getLogger("dbinsight.mail")


class Mailer(Protocol):
    def send(self, to: str, subject: str, text: str, html: str | None = None) -> None: ...


@dataclass
class SmtpMailer:
    host: str
    port: int = 587
    user: str | None = None
    password: str | None = None
    sender: str = "DBInsight <no-reply@dbinsight.local>"
    starttls: bool = True
    # What we call ourselves in the SMTP greeting. If left to smtplib it asks the OS for this
    # machine's fully-qualified name, which can stall for ~35 s on macOS: a sign-up code would
    # arrive over half a minute late.
    helo: str = "localhost"

    def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self.sender, to, subject
        message.set_content(text)
        if html:
            message.add_alternative(html, subtype="html")
        context = ssl.create_default_context()
        connection = (
            smtplib.SMTP_SSL(
                self.host, self.port, local_hostname=self.helo, timeout=15, context=context
            )
            if self.port == 465
            else smtplib.SMTP(self.host, self.port, local_hostname=self.helo, timeout=15)
        )
        with connection as smtp:
            if self.port != 465 and self.starttls:
                smtp.starttls(context=context)
            if self.user:
                smtp.login(self.user, self.password or "")
            smtp.send_message(message)


class ConsoleMailer:
    """Development fallback: prints the message. Never used when SMTP is configured."""

    def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        bar = "=" * 64
        sys.stderr.write(
            f"\n{bar}\n[DBInsight mail, not sent: no SMTP configured]\nTo: {to}\nSubject: {subject}\n\n{text}\n{bar}\n"
        )
        sys.stderr.flush()


def mailer_from_env() -> Mailer:
    host = os.environ.get("DBINSIGHT_SMTP_HOST")
    if not host:
        return ConsoleMailer()
    port = int(os.environ.get("DBINSIGHT_SMTP_PORT", "587"))
    return SmtpMailer(
        host=host,
        port=port,
        user=os.environ.get("DBINSIGHT_SMTP_USER"),
        password=os.environ.get("DBINSIGHT_SMTP_PASSWORD"),
        sender=os.environ.get("DBINSIGHT_SMTP_FROM", "DBInsight <no-reply@dbinsight.local>"),
        starttls=os.environ.get("DBINSIGHT_SMTP_STARTTLS", "0" if port == 1025 else "1") == "1",
        helo=os.environ.get("DBINSIGHT_SMTP_HELO", "localhost"),
    )


# ---- messages ---------------------------------------------------------------------------------

_SHELL = """\
<div style="background:#f5f6f8;padding:32px 16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
  <div style="max-width:480px;margin:0 auto;background:#ffffff;border:1px solid #e5e8ee;border-radius:14px;padding:32px">
    <div style="font-size:16px;font-weight:600;color:#0f172a;margin-bottom:20px">DBInsight</div>
    {body}
    <p style="margin:28px 0 0;font-size:12px;color:#94a0b4">You received this because of activity on your DBInsight account. If that was not you, you can ignore this message.</p>
  </div>
</div>"""


def _code_box(code: str) -> str:
    spaced = f"{code[:3]} {code[3:]}"
    return (
        f'<div style="margin:20px 0;padding:16px;background:#eef0ff;border-radius:10px;text-align:center;'
        f'font-size:32px;letter-spacing:6px;font-weight:700;color:#3730a3;font-family:ui-monospace,Menlo,monospace">{spaced}</div>'
    )


def otp_message(purpose: str, code: str, minutes: int) -> tuple[str, str, str]:
    if purpose == "register":
        subject, headline, lead = (
            f"{code[:3]} {code[3:]} is your DBInsight verification code",
            "Verify your email",
            "Enter this code to finish creating your account.",
        )
    else:
        subject, headline, lead = (
            f"{code[:3]} {code[3:]} is your DBInsight password reset code",
            "Reset your password",
            "Enter this code to choose a new password.",
        )
    text = f"{headline}\n\n{lead}\n\n    {code[:3]} {code[3:]}\n\nThe code expires in {minutes} minutes and works once. If you did not request it, ignore this email; nobody can use it without access to your inbox."
    body = f'<h1 style="margin:0 0 8px;font-size:20px;color:#0f172a">{headline}</h1><p style="margin:0;color:#5b6577;font-size:14px;line-height:1.6">{lead}</p>{_code_box(code)}<p style="margin:0;color:#5b6577;font-size:13px">The code expires in {minutes} minutes and works once.</p>'
    return subject, text, _SHELL.format(body=body)


def already_registered_message() -> tuple[str, str, str]:
    text = "Someone tried to create a DBInsight account with this email address, but you already have one.\n\nSign in with your password, or use 'Forgot password' on the sign-in page to choose a new one.\n\nIf this was not you, you can ignore this email."
    body = '<h1 style="margin:0 0 8px;font-size:20px;color:#0f172a">You already have an account</h1><p style="margin:0;color:#5b6577;font-size:14px;line-height:1.6">Someone tried to create a DBInsight account with this email address. You can sign in with your password, or use <b>Forgot password</b> on the sign-in page to choose a new one.</p>'
    return "You already have a DBInsight account", text, _SHELL.format(body=body)


def password_changed_message() -> tuple[str, str, str]:
    text = "Your DBInsight password was just changed and you were signed out everywhere else.\n\nIf you did not do this, reset your password immediately from the sign-in page."
    body = '<h1 style="margin:0 0 8px;font-size:20px;color:#0f172a">Your password was changed</h1><p style="margin:0;color:#5b6577;font-size:14px;line-height:1.6">Your password was just changed and you were signed out of your other sessions. If you did not do this, reset your password right away from the sign-in page.</p>'
    return "Your DBInsight password was changed", text, _SHELL.format(body=body)
