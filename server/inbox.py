"""Inbox triage: read recent mail over IMAP (read-only, never marks anything as read),
find commitments and requests, and suggest them as tasks. All processing is local."""
import email
import email.policy
import imaplib
import json
import logging
import re
import threading
from datetime import date, datetime, timedelta
from email.utils import parseaddr, parsedate_to_datetime

from . import db, llm, secure

log = logging.getLogger("donna.inbox")
_lock = threading.Lock()
SKIP_SENDER = re.compile(r"no-?reply|do-?not-?reply|notifications?@|newsletter|mailer-daemon|updates@|news@|marketing|promo", re.I)
SENT_FOLDERS = ['"[Gmail]/Sent Mail"', '"[Google Mail]/Sent Mail"', "Sent", '"Sent Items"', '"Sent Messages"', "INBOX.Sent"]


def imap_host():
    h = db.get_setting("imap_host", "")
    if h:
        return h
    smtp = db.get_setting("smtp_host", "")
    return smtp.replace("smtp.", "imap.", 1) if smtp.startswith("smtp.") else smtp


def configured():
    return bool(imap_host() and db.get_setting("smtp_user") and secure.get_secret("smtp_password"))


def _status(**kw):
    s = db.get_setting("inbox_status", {}) or {}
    s.update(kw)
    db.set_setting("inbox_status", s)


def _body(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if not part:
        return ""
    try:
        txt = part.get_content()
    except Exception:
        txt = part.get_payload(decode=True).decode("utf8", "ignore")
    if part.get_content_type() == "text/html":
        txt = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", txt)
        txt = re.sub(r"<[^>]+>", " ", txt)
    # drop quoted replies so we only read the newest message
    txt = re.split(r"\n(?:On .{5,120}wrote:|-{2,}\s*Original Message|From: .+\nSent: )", txt)[0]
    txt = "\n".join(l for l in txt.splitlines() if not l.startswith(">"))
    return re.sub(r"\s+\n", "\n", re.sub(r"[ \t]+", " ", txt)).strip()[:2500]


def _extract(sender, subject, body, folder):
    from .agents import skill, time_context
    schema = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
        "title": {"type": "string"}, "due_date": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["title", "reason"]}}}, "required": ["items"]}
    who = "an email the USER SENT" if folder == "sent" else "an email the user RECEIVED"
    content = f"This is {who}.\nFrom/To: {sender}\nSubject: {subject}\n\n{body}"
    out = llm.complete([{"role": "system", "content": skill("inbox") + "\n\n" + time_context()},
                        {"role": "user", "content": content}], fmt=schema, timeout=180)
    items = json.loads(out).get("items", [])[:3]
    for it in items:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", it.get("due_date") or ""):
            it["due_date"] = None
        else:
            it["due_date"] = fix_weekday(it["due_date"], f"{it.get('reason', '')} {it.get('title', '')}")
    return [it for it in items if it.get("title", "").strip()]


_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def fix_weekday(due: str, text: str) -> str:
    """Small models miscount weekdays. If the text names a weekday ("by Friday") and the date
    isn't that weekday, snap to the next such day from today."""
    m = re.search(r"\b(" + "|".join(_DAYS) + r")\b", text.lower())
    if not m:
        return due
    want = _DAYS.index(m.group(1))
    d = date.fromisoformat(due)
    if d.weekday() == want:
        return due
    t = date.today()
    return (t + timedelta(days=(want - t.weekday()) % 7 or 7)).isoformat()


def scan(days=None, limit=None):
    if not _lock.acquire(blocking=False):
        return {"running": True}
    found = 0
    try:
        if not configured():
            raise RuntimeError("Set up email (SMTP host, username and app password) in Admin first")
        days = days or int(db.get_setting("inbox_days", 2))
        limit = limit or int(db.get_setting("inbox_limit", 25))
        _status(running=True, started=db.now(), error="")
        M = imaplib.IMAP4_SSL(imap_host(), 993, timeout=30)
        M.login(db.get_setting("smtp_user"), secure.get_secret("smtp_password"))
        me = db.get_setting("smtp_user", "").lower()
        since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
        folders = [("INBOX", "inbox")]
        if db.get_setting("inbox_scan_sent", True):
            for f in SENT_FOLDERS:
                if M.select(f, readonly=True)[0] == "OK":
                    folders.append((f, "sent"))
                    break
        processed = 0
        for fname, kind in folders:
            if M.select(fname, readonly=True)[0] != "OK":
                continue
            _, data = M.search(None, f"(SINCE {since})")
            ids = data[0].split()[-limit:]
            for i in reversed(ids):
                _, md = M.fetch(i, "(BODY.PEEK[])")
                raw = next((x[1] for x in md if isinstance(x, tuple)), None)
                if not raw:
                    continue
                msg = email.message_from_bytes(raw, policy=email.policy.default)
                mid = (msg.get("Message-ID") or f"{fname}:{i.decode()}").strip()
                key = "inbox:" + mid
                if db.row("SELECT 1 FROM sent_log WHERE key=?", (key,)):
                    continue
                mark = lambda: db.run("INSERT OR IGNORE INTO sent_log(key) VALUES (?)", (key,))
                if kind == "inbox" and db.get_setting("subs_email_watch", True):
                    try:  # receipts/trials often come from no-reply senders, so check before the skip filter
                        from . import subs_email
                        subs_email.handle_message(msg, mid)
                    except Exception as e:
                        log.warning("subscription check failed: %s", e)
                sender = str(msg.get("To" if kind == "sent" else "From") or "")
                addr = parseaddr(sender)[1].lower()
                if kind == "inbox" and (msg.get("List-Unsubscribe") or msg.get("Precedence") in ("bulk", "list") or SKIP_SENDER.search(addr) or addr == me):
                    mark()
                    continue
                body = _body(msg)
                if len(body) < 20:
                    mark()
                    continue
                subject = str(msg.get("Subject") or "")
                try:
                    received = parsedate_to_datetime(msg.get("Date")).astimezone().strftime("%Y-%m-%dT%H:%M")
                except Exception:
                    received = ""
                processed += 1
                _status(progress=f"Reading {processed}: {subject[:60]}")
                for it in _extract(sender, subject, body, kind):
                    db.run("INSERT INTO inbox_items(msg_id, folder, sender, subject, received, title, due_date, reason) VALUES (?,?,?,?,?,?,?,?)",
                           (mid, kind, sender[:200], subject[:300], received, it["title"][:200], it.get("due_date"), it.get("reason", "")[:300]))
                    found += 1
                mark()  # only after a successful read, so an Ollama hiccup doesn't lose the email
        M.logout()
        _status(running=False, last_scan=db.now(), last_found=found, last_read=processed, progress="")
        if found:
            from . import services
            services.notify(f"{found} new {'commitment' if found == 1 else 'commitments'} found in your email", "Review them in Inbox", "#/inbox")
        return {"found": found, "read": processed}
    except Exception as e:
        log.warning("inbox scan failed: %s", e)
        _status(running=False, error=str(e)[:300], progress="")
        raise
    finally:
        _lock.release()


def scan_async():
    threading.Thread(target=lambda: _safe_scan(), daemon=True).start()


def _safe_scan():
    try:
        scan()
    except Exception:
        pass


def items(status="pending"):
    return db.rows("SELECT * FROM inbox_items WHERE status=? ORDER BY COALESCE(due_date,'9999'), id DESC LIMIT 200", (status,))


def accept(iid, project_id=None, title=None, due_date=None):
    from . import services as S
    it = db.row("SELECT * FROM inbox_items WHERE id=?", (iid,))
    note = f"From email: “{it['subject']}” ({it['sender']})\n{it['reason']}"
    t = S.create_task(title or it["title"], project_id, due_date=due_date or it["due_date"], note=note,
                      reminder_at=((due_date or it["due_date"]) + "T09:00") if (due_date or it["due_date"]) else None)
    db.run("UPDATE inbox_items SET status='accepted', task_id=? WHERE id=?", (t["id"], iid))
    return t


def dismiss(iid):
    db.run("UPDATE inbox_items SET status='dismissed' WHERE id=?", (iid,))


def due_for_scan():
    if not db.get_setting("inbox_enabled", False) or not configured():
        return False
    last = (db.get_setting("inbox_status", {}) or {}).get("last_scan")
    hours = float(db.get_setting("inbox_interval_hours", 3))
    return not last or datetime.now() - datetime.fromisoformat(last) >= timedelta(hours=hours)
