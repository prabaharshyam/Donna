"""Outgoing email over SMTP (works with Gmail App Passwords, Outlook, Zoho, iCloud...)."""
import html
import smtplib
import ssl
from email.message import EmailMessage

from . import db, secure


def configured():
    return bool(db.get_setting("smtp_host")) and bool(db.get_setting("notify_email"))


def _frame(title: str, inner_html: str) -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#f6f4f1;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1c1b1a">
<div style="max-width:560px;margin:32px auto;background:#fff;border:1px solid #ebe7e1;border-radius:14px;overflow:hidden">
  <div style="padding:22px 28px;border-bottom:1px solid #f0ece6">
    <div style="font-family:Georgia,serif;font-size:22px;letter-spacing:.2px">Donna</div>
    <div style="font-size:12px;color:#8a837a;margin-top:2px;text-transform:uppercase;letter-spacing:1.2px">{html.escape(title)}</div>
  </div>
  <div style="padding:24px 28px;font-size:15px;line-height:1.6">{inner_html}</div>
  <div style="padding:14px 28px;font-size:12px;color:#a39c92;border-top:1px solid #f0ece6">Sent by your Donna · <a style="color:#7a2e3a" href="{html.escape(db.get_setting('public_url', 'http://localhost:8765'))}">Open Donna</a></div>
</div></body></html>"""


def send(subject: str, inner_html: str, text: str = "", to: str = None):
    host = db.get_setting("smtp_host")
    if not host:
        raise RuntimeError("SMTP is not configured (Settings → Email)")
    port = int(db.get_setting("smtp_port", 587))
    user = db.get_setting("smtp_user", "")
    pw = secure.get_secret("smtp_password")
    sender = db.get_setting("smtp_from") or user
    to = to or db.get_setting("notify_email")
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, f"Donna <{sender}>", to
    msg.set_content(text or subject)
    msg.add_alternative(_frame(subject, inner_html), subtype="html")
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
            if user:
                s.login(user, pw)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls(context=ctx)
            if user:
                s.login(user, pw)
            s.send_message(msg)
