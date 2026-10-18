"""Find subscriptions in email: receipts, trials, renewals, price changes, failed payments and
RBI e-mandate pre-debit notifications (Indian banks must notify before every auto-debit).

Known subscriptions are updated automatically (a payment is logged, a date or price updated).
New subscriptions become suggestions the user confirms on the Subscriptions page.
"""
import email
import email.policy
import imaplib
import json
import logging
import re
import threading
from datetime import date, timedelta
from email.utils import parseaddr

from . import db, llm, secure, services as S, subs

log = logging.getLogger("donna.subs_email")
_lock = threading.Lock()

HINT = re.compile(r"subscri|receipt|invoice|payment|paid|trial|renew|membership|billing|bill\b|debit|mandate|autopay|"
                  r"auto-pay|e-?nach|standing instruction|your plan|charged|price (change|increase|update)|premium|"
                  r"plus\b|pro\b|upgrade|cancel", re.I)
SUBJECT_TERMS = ["subscription", "receipt", "invoice", "trial", "renewal", "renew", "membership", "billing",
                 "payment", "debit", "mandate", "autopay"]
EVENTS = ["trial_started", "charged", "upcoming_charge", "price_change", "payment_failed", "cancelled", "not_subscription"]


def looks_relevant(subject, sender=""):
    return bool(HINT.search(subject or "")) or bool(re.search(r"billing|payments?@|receipts?@|invoice", sender or "", re.I))


def extract(sender, subject, body, received=""):
    from .agents import skill
    schema = {"type": "object", "properties": {
        "event": {"type": "string", "enum": EVENTS},
        "service": {"type": "string"}, "plan": {"type": "string"},
        "amount": {"type": "number"}, "currency": {"type": "string"},
        "date": {"type": "string"}, "next_date": {"type": "string"}, "trial_end": {"type": "string"},
        "cycle": {"type": "string", "enum": subs.CYCLES + ["unknown"]},
        "evidence": {"type": "string"}},
        "required": ["event", "service", "evidence"]}
    content = f"Received: {received}\nFrom: {sender}\nSubject: {subject}\n\n{body[:3500]}"
    out = json.loads(llm.complete([{"role": "system", "content": skill("subscription_email") + f"\n\nToday: {date.today().isoformat()}"},
                                   {"role": "user", "content": content}], fmt=schema, effort="low", timeout=120))
    for k in ("date", "next_date", "trial_end"):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", out.get(k) or ""):
            out[k] = None
    if out.get("cycle") == "unknown":
        out["cycle"] = None
    if out.get("currency"):
        out["currency"] = out["currency"].upper()[:3]
    return out


def apply(ev, msg_id="", sender="", subject="", received=""):
    """Act on one extracted event. Returns a short description of what happened (or None)."""
    if not ev or ev.get("event") == "not_subscription" or not (ev.get("service") or "").strip():
        return None
    if db.row("SELECT 1 FROM sub_suggestions WHERE msg_id=? AND lower(service)=lower(?)", (msg_id, ev["service"])):
        return None  # this email was already handled
    sub = subs.find(ev["service"])
    event = ev["event"]
    row = dict(msg_id=msg_id, service=ev["service"].strip()[:80], event=event, amount=ev.get("amount"),
               currency=ev.get("currency"), date=ev.get("date") or (received or "")[:10] or None,
               next_date=ev.get("next_date"), trial_end=ev.get("trial_end"), cycle=ev.get("cycle"),
               plan=(ev.get("plan") or "")[:80], sender=sender[:200], subject=subject[:300], evidence=(ev.get("evidence") or "")[:300])

    def store(status, sub_id=None):
        row.update(status=status, sub_id=sub_id)
        db.run(f"INSERT INTO sub_suggestions({', '.join(row)}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))

    if not sub or sub["status"] in ("cancelled", "expired") and event in ("trial_started",):
        if event in ("trial_started", "charged", "upcoming_charge", "price_change"):
            store("pending")
            what = "free trial" if event == "trial_started" else "subscription"
            S.notify(f"New {what} found: {row['service']}",
                     (subs.fmt_money(row["amount"], row["currency"]) + " · " if row["amount"] else "") + "Review it in Subscriptions", "#/subscriptions")
            return f"suggested {row['service']}"
        store("dismissed")
        return None

    sid, done = sub["id"], None
    if event == "charged":
        r = subs.record_charge(sid, row["amount"], row["date"], source="email", note=subject[:120], currency=row["currency"])
        if r["price_change"]:
            old, new = r["price_change"]
            S.notify(f"{sub['name']} price changed", f"{subs.fmt_money(old, sub['currency'])} → {subs.fmt_money(new, sub['currency'])}", "#/subscriptions")
        if row["next_date"]:
            subs.save(sid, next_billing_date=row["next_date"])
        done = "logged a payment" if not r["duplicate"] else "payment already logged"
    elif event == "upcoming_charge":
        upd = {}
        if row["next_date"] or row["date"]:
            upd["next_billing_date"] = row["next_date"] or row["date"]
        if row["amount"] and sub["amount"] and abs(row["amount"] - sub["amount"]) > 0.01 * sub["amount"]:
            upd.update(previous_amount=sub["amount"], amount=row["amount"])
            S.notify(f"{sub['name']} will charge a different amount",
                     f"{subs.fmt_money(sub['amount'], sub['currency'])} → {subs.fmt_money(row['amount'], row['currency'] or sub['currency'])}", "#/subscriptions")
        if upd:
            subs.save(sid, **upd)
        done = "updated the next charge"
    elif event == "price_change":
        if row["amount"]:
            subs.save(sid, previous_amount=sub["amount"], amount=row["amount"])
        S.notify(f"{sub['name']} is changing its price", row["evidence"][:160], "#/subscriptions")
        done = "recorded a price change"
    elif event == "payment_failed":
        S.notify(f"⚠️ {sub['name']} payment failed", "Update your payment method to avoid losing access.", "#/subscriptions")
        done = "flagged a failed payment"
    elif event == "cancelled":
        if sub["status"] not in ("cancelling", "cancelled"):
            subs.cancel(sid, row["next_date"] or row["date"])
        s2 = subs.get(sid)
        ck = s2["checklist"]
        ck.update(service=True, confirmation=True)
        subs.save(sid, cancel_checklist=ck)
        done = "confirmed the cancellation"
    elif event == "trial_started":
        if row["trial_end"]:
            subs.save(sid, status="trial", trial_end_date=row["trial_end"], next_billing_date=row["trial_end"])
        done = "updated the trial"
    store("applied", sid)
    return f"{sub['name']}: {done}" if done else None


def accept(suggestion_id, overrides=None):
    sg = db.row("SELECT * FROM sub_suggestions WHERE id=?", (suggestion_id,))
    o = overrides or {}
    f = dict(name=o.get("name") or sg["service"], plan=o.get("plan", sg["plan"]), amount=o.get("amount", sg["amount"]),
             currency=o.get("currency") or sg["currency"] or subs.home_currency(), cycle=o.get("cycle") or sg["cycle"] or "monthly",
             payment_method=o.get("payment_method", ""), category=o.get("category"))
    if sg["event"] == "trial_started" and sg["trial_end"]:
        f.update(status="trial", trial_end_date=sg["trial_end"], next_billing_date=sg["trial_end"])
    else:
        f["next_billing_date"] = sg["next_date"] or (subs.advance(sg["date"], f["cycle"]) if sg["date"] else None)
    s = subs.save(**{k: v for k, v in f.items() if v is not None})
    if sg["event"] == "charged" and sg["date"]:
        db.run("INSERT INTO sub_charges(sub_id, date, amount, currency, source, note) VALUES (?,?,?,?,?,?)",
               (s["id"], sg["date"], sg["amount"], f["currency"], "email", sg["subject"][:120]))
    db.run("UPDATE sub_suggestions SET status='accepted', sub_id=? WHERE id=?", (s["id"], suggestion_id))
    # other pending suggestions for the same service are now known
    db.run("UPDATE sub_suggestions SET status='merged', sub_id=? WHERE status='pending' AND lower(service)=lower(?) AND id!=?",
           (s["id"], sg["service"], suggestion_id))
    return subs.get(s["id"])


def dismiss(suggestion_id):
    db.run("UPDATE sub_suggestions SET status='dismissed' WHERE id=?", (suggestion_id,))


def suggestions(status="pending"):
    return db.rows("SELECT * FROM sub_suggestions WHERE status=? ORDER BY id DESC LIMIT 100", (status,))


# ============================== scanning ==============================
def handle_message(msg, mid):
    """Used by the inbox triage scan and the dedicated subscription scan."""
    key = "subemail:" + mid
    if db.row("SELECT 1 FROM sent_log WHERE key=?", (key,)):
        return None
    from .inbox import _body
    sender = str(msg.get("From") or "")
    subject = str(msg.get("Subject") or "")
    if not looks_relevant(subject, parseaddr(sender)[1]):
        db.run("INSERT OR IGNORE INTO sent_log(key) VALUES (?)", (key,))
        return None
    body = _body(msg)
    try:
        from email.utils import parsedate_to_datetime
        received = parsedate_to_datetime(msg.get("Date")).astimezone().strftime("%Y-%m-%d")
    except Exception:
        received = ""
    ev = extract(sender, subject, body, received)
    result = apply(ev, mid, sender, subject, received)
    db.run("INSERT OR IGNORE INTO sent_log(key) VALUES (?)", (key,))
    return result


def _status(**kw):
    s = db.get_setting("subscan_status", {}) or {}
    s.update(kw)
    db.set_setting("subscan_status", s)


def scan(days=120, limit=150):
    """Search recent mail for subscription-looking messages (read-only; nothing is marked read)."""
    from .inbox import configured, imap_host
    if not _lock.acquire(blocking=False):
        return {"running": True}
    found = []
    try:
        if not configured():
            raise RuntimeError("Set up email (SMTP host, username and app password) in Admin first")
        _status(running=True, started=db.now(), error="", progress="Connecting…")
        M = imaplib.IMAP4_SSL(imap_host(), 993, timeout=30)
        M.login(db.get_setting("smtp_user"), secure.get_secret("smtp_password"))
        M.select("INBOX", readonly=True)
        since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
        crit = f'SUBJECT "{SUBJECT_TERMS[0]}"'
        for t in SUBJECT_TERMS[1:]:
            crit = f'OR SUBJECT "{t}" {crit}'  # IMAP OR is prefix/binary: OR a (OR b (OR c d))
        typ, data = M.search(None, f"SINCE {since} {crit}")
        ids = data[0].split()[-limit:] if typ == "OK" else []
        for n, i in enumerate(reversed(ids), 1):
            _, md = M.fetch(i, "(BODY.PEEK[])")
            raw = next((x[1] for x in md if isinstance(x, tuple)), None)
            if not raw:
                continue
            msg = email.message_from_bytes(raw, policy=email.policy.default)
            mid = (msg.get("Message-ID") or f"INBOX:{i.decode()}").strip()
            _status(progress=f"Reading {n}/{len(ids)}: {str(msg.get('Subject') or '')[:60]}")
            try:
                r = handle_message(msg, mid)
                if r:
                    found.append(r)
            except Exception as e:
                log.warning("subscription email failed: %s", e)
        M.logout()
        _status(running=False, last_scan=db.now(), last_read=len(ids), last_found=len(found), progress="", days=days)
        return {"read": len(ids), "found": found}
    except Exception as e:
        _status(running=False, error=str(e)[:300], progress="")
        raise
    finally:
        _lock.release()


def scan_async(days=120):
    def go():
        try:
            scan(days)
        except Exception:
            pass
    threading.Thread(target=go, daemon=True).start()
