"""Subscription manager: what you pay for, when, how much, and whether it's worth it.

Statuses: trial → active → cancelling (cancelled, access until a date) → cancelled; paused; expired.
Amounts are stored in the subscription's own currency and converted to the home currency
(INR by default) for totals, using daily exchange rates with optional card forex markup.
"""
import json
import logging
import re
import urllib.request
from datetime import date, datetime, timedelta

from . import db

log = logging.getLogger("donna.subs")

CATEGORIES = ["entertainment", "music", "ai tools", "productivity", "cloud storage", "news & reading", "learning",
              "fitness & health", "food & delivery", "shopping & memberships", "gaming", "software & dev",
              "finance", "telecom & internet", "other"]
CYCLES = ["weekly", "monthly", "quarterly", "half-yearly", "yearly"]
PER = {"weekly": "week", "monthly": "month", "quarterly": "quarter", "half-yearly": "half-year", "yearly": "year"}
MONTHS_IN = {"weekly": 12 / 52, "monthly": 1, "quarterly": 3, "half-yearly": 6, "yearly": 12}
STATUSES = ["trial", "active", "paused", "cancelling", "cancelled", "expired"]
LIVE = ("trial", "active", "cancelling")  # still costing (or about to cost) money
FIELDS = {"name", "plan", "category", "amount", "currency", "cycle", "next_billing_date", "start_date", "status",
          "trial_end_date", "auto_renew", "payment_method", "billed_via", "account_email", "shared_with", "my_share",
          "manage_url", "notes", "value_rating", "last_used", "reminder_days", "cancel_effective_date", "cancel_reason",
          "cancel_checklist", "cancelled_at", "previous_amount", "cancel_guide", "emoji", "color"}

# Common services: category, an emoji and where to manage/cancel. Prices are deliberately not
# included: they change often and differ by plan, so they come from the user or their receipts.
CATALOG = [
    ("Netflix", "entertainment", "🎬", "https://www.netflix.com/account"),
    ("Amazon Prime", "shopping & memberships", "📦", "https://www.amazon.in/gp/primecentral"),
    ("JioHotstar", "entertainment", "⭐", "https://www.hotstar.com"),
    ("SonyLIV", "entertainment", "📺", "https://www.sonyliv.com"),
    ("ZEE5", "entertainment", "📺", "https://www.zee5.com"),
    ("YouTube Premium", "entertainment", "▶️", "https://www.youtube.com/paid_memberships"),
    ("Spotify", "music", "🎧", "https://www.spotify.com/account/"),
    ("Apple Music", "music", "🎵", "https://apps.apple.com/account/subscriptions"),
    ("Apple One", "entertainment", "🍎", "https://apps.apple.com/account/subscriptions"),
    ("iCloud+", "cloud storage", "☁️", "https://apps.apple.com/account/subscriptions"),
    ("Google One", "cloud storage", "☁️", "https://one.google.com/settings"),
    ("ChatGPT Plus", "ai tools", "🤖", "https://chatgpt.com"),
    ("Claude Pro", "ai tools", "✳️", "https://claude.ai/settings/billing"),
    ("Google AI Pro (Gemini)", "ai tools", "✨", "https://one.google.com/settings"),
    ("Perplexity Pro", "ai tools", "🔎", "https://www.perplexity.ai/settings/account"),
    ("GitHub Copilot", "software & dev", "🧑‍💻", "https://github.com/settings/billing"),
    ("Cursor", "software & dev", "⌨️", "https://www.cursor.com/settings"),
    ("Microsoft 365", "productivity", "🗂️", "https://account.microsoft.com/services"),
    ("Canva Pro", "productivity", "🎨", "https://www.canva.com/settings/billing-and-teams"),
    ("Adobe Creative Cloud", "productivity", "🅰️", "https://account.adobe.com/plans"),
    ("Notion", "productivity", "📝", "https://www.notion.so"),
    ("Dropbox", "cloud storage", "📁", "https://www.dropbox.com/account/plan"),
    ("LinkedIn Premium", "productivity", "💼", "https://www.linkedin.com/premium/manage/"),
    ("Kindle Unlimited", "news & reading", "📚", "https://www.amazon.in/kindle-dbs/ku/ku-central"),
    ("Audible", "news & reading", "🎧", "https://www.audible.in/account"),
    ("Times Prime", "shopping & memberships", "🎟️", "https://www.timesprime.com"),
    ("Swiggy One", "food & delivery", "🍔", ""),
    ("Zomato Gold", "food & delivery", "🍕", ""),
    ("Uber One", "shopping & memberships", "🚗", ""),
    ("cult.fit", "fitness & health", "💪", "https://www.cult.fit"),
    ("Duolingo Super", "learning", "🦉", ""),
    ("Coursera Plus", "learning", "🎓", "https://www.coursera.org/account-settings"),
    ("Xbox Game Pass", "gaming", "🎮", "https://account.microsoft.com/services"),
    ("PlayStation Plus", "gaming", "🎮", ""),
    ("Jio / Airtel / Vi plan", "telecom & internet", "📶", ""),
    ("Broadband", "telecom & internet", "🌐", ""),
]
CATALOG_BY_NAME = {c[0].lower(): c for c in CATALOG}


# ============================== money ==============================
def home_currency():
    return (db.get_setting("home_currency", "INR") or "INR").upper()


def fx_rates():
    """{currency: value of 1 unit in home currency}."""
    r = db.get_setting("fx_rates", {}) or {}
    r[home_currency()] = 1.0
    return r


def refresh_fx(force=False):
    """Daily rates from a free public API (no key). Manual overrides in settings win."""
    last = db.get_setting("fx_updated", "")
    if not force and last and last[:10] == date.today().isoformat():
        return fx_rates()
    home = home_currency()
    try:
        with urllib.request.urlopen(f"https://open.er-api.com/v6/latest/{home}", timeout=10) as r:
            data = json.loads(r.read())
        if data.get("result") != "success":
            raise ValueError(data.get("error-type", "bad response"))
        rates = {cur: round(1 / v, 6) for cur, v in data["rates"].items() if v}
        manual = db.get_setting("fx_manual", {}) or {}
        rates.update({k.upper(): float(v) for k, v in manual.items() if v})
        db.set_setting("fx_rates", rates)
        db.set_setting("fx_updated", db.now())
    except Exception as e:
        log.warning("fx refresh failed: %s", e)
    return fx_rates()


def to_home(amount, currency):
    """Convert to home currency, including the card forex markup for foreign charges. None if unknown rate."""
    if amount is None:
        return None
    cur = (currency or home_currency()).upper()
    if cur == home_currency():
        return float(amount)
    rate = fx_rates().get(cur)
    if not rate:
        return None
    markup = float(db.get_setting("fx_markup_percent", 0) or 0)
    return float(amount) * rate * (1 + markup / 100)


def monthly_cost(s, mine=True):
    """Monthly equivalent in home currency (your share if `mine`)."""
    v = to_home(s.get("amount"), s.get("currency"))
    if v is None:
        return None
    v = v / MONTHS_IN.get(s.get("cycle") or "monthly", 1)
    if mine:
        v *= (s.get("my_share") if s.get("my_share") is not None else 100) / 100
    return v


def fmt_money(v, cur=None):
    if v is None:
        return "—"
    cur = (cur or home_currency()).upper()
    sym = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(cur, cur + " ")
    return f"{sym}{v:,.0f}" if v >= 100 else f"{sym}{v:,.2f}".rstrip("0").rstrip(".")


# ============================== dates ==============================
def advance(d: str, cycle: str) -> str:
    from .life import advance_date
    return advance_date(d, cycle if cycle in CYCLES else "monthly")


def _days(d):
    return (date.fromisoformat(d[:10]) - date.today()).days if d else None


def _out(s):
    s = dict(s)
    s["checklist"] = json.loads(s.get("cancel_checklist") or "{}")
    s["monthly_home"] = monthly_cost(s)
    s["monthly_home_full"] = monthly_cost(s, mine=False)
    s["days_to_billing"] = _days(s.get("next_billing_date"))
    s["days_to_trial_end"] = _days(s.get("trial_end_date"))
    s["cancel_by"] = (date.fromisoformat(s["trial_end_date"][:10]) - timedelta(days=1)).isoformat() if s.get("trial_end_date") else None
    s["unused_days"] = (-_days(s["last_used"])) if s.get("last_used") else None
    cat = CATALOG_BY_NAME.get((s.get("name") or "").lower())
    if not s.get("emoji"):
        s["emoji"] = cat[2] if cat else "💳"
    if not s.get("manage_url") and cat:
        s["manage_url"] = cat[3]
    return s


# ============================== CRUD ==============================
def subs(status=None):
    sql, args = "SELECT * FROM subscriptions", []
    if status == "live":
        sql += f" WHERE status IN ({','.join('?' * len(LIVE))})"
        args = list(LIVE)
    elif status and status != "all":
        sql += " WHERE status=?"
        args = [status]
    sql += " ORDER BY CASE status WHEN 'trial' THEN 0 WHEN 'active' THEN 1 WHEN 'cancelling' THEN 2 WHEN 'paused' THEN 3 ELSE 4 END, COALESCE(trial_end_date, next_billing_date, '9999'), name"
    return [_out(s) for s in db.rows(sql, args)]


def get(sid):
    s = db.row("SELECT * FROM subscriptions WHERE id=?", (sid,))
    if not s:
        return None
    s = _out(s)
    s["charges"] = db.rows("SELECT * FROM sub_charges WHERE sub_id=? ORDER BY date DESC, id DESC LIMIT 60", (sid,))
    for c in s["charges"]:
        c["home"] = to_home(c["amount"], c["currency"])
    return s


def find(name):
    if not name:
        return None
    n = name.strip().lower()
    s = db.row("SELECT * FROM subscriptions WHERE lower(name)=? ORDER BY status IN ('cancelled','expired'), id DESC", (n,))
    if not s:
        for cand in db.rows("SELECT * FROM subscriptions ORDER BY status IN ('cancelled','expired'), id DESC"):
            cn = cand["name"].lower()
            if n in cn or cn in n or (len(n.split()[0]) > 3 and n.split()[0] == cn.split()[0]):
                s = cand
                break
    return get(s["id"]) if s else None


def _clean(f):
    f = {k: v for k, v in f.items() if k in FIELDS}
    for k in ("amount", "my_share", "previous_amount"):
        if k in f and f[k] in ("", None):
            f[k] = None if k != "my_share" else 100
        elif k in f:
            f[k] = float(f[k])
    if "currency" in f and f["currency"]:
        f["currency"] = str(f["currency"]).upper()[:3]
    if "cycle" in f and f["cycle"] not in CYCLES:
        f["cycle"] = "monthly"
    if "category" in f and f["category"] not in CATEGORIES:
        f["category"] = "other"
    if isinstance(f.get("cancel_checklist"), dict):
        f["cancel_checklist"] = json.dumps(f["cancel_checklist"])
    for k in ("next_billing_date", "start_date", "trial_end_date", "last_used", "cancel_effective_date"):
        if k in f and not f[k]:
            f[k] = None
    return f


def save(sid=None, **f):
    f = _clean(f)
    if not sid:
        cat = CATALOG_BY_NAME.get((f.get("name") or "").lower())
        if cat:
            f.setdefault("category", cat[1])
            f.setdefault("emoji", cat[2])
            f.setdefault("manage_url", cat[3])
        f.setdefault("currency", home_currency())
        f.setdefault("start_date", date.today().isoformat())
        if f.get("trial_end_date") and not f.get("status"):
            f["status"] = "trial"
        if f.get("status") == "trial" and f.get("trial_end_date"):
            f.setdefault("next_billing_date", f["trial_end_date"])
        f["updated_at"] = db.now()
        sid = db.run(f"INSERT INTO subscriptions({', '.join(f)}) VALUES ({','.join('?' * len(f))})", tuple(f.values()))
    else:
        db.update("subscriptions", sid, f, FIELDS)
    s = get(sid)
    db.index("subscription", sid, s["name"], f"{s['plan']} {s['category']} {s['status']} {s['payment_method']} {s['notes']} subscription")
    return s


def delete(sid):
    db.run("DELETE FROM subscriptions WHERE id=?", (sid,))
    db.unindex("subscription", sid)


# ============================== events ==============================
def record_charge(sid, amount=None, d=None, source="manual", note="", currency=None):
    """Log a payment. Rolls the next billing date forward and detects price changes.
    Returns {"charge_id", "price_change": (old, new) | None, "duplicate": bool}."""
    s = get(sid)
    d = (d or date.today().isoformat())[:10]
    amount = s["amount"] if amount in (None, "") else float(amount)
    currency = (currency or s["currency"] or home_currency()).upper()
    dup = db.row("SELECT id FROM sub_charges WHERE sub_id=? AND ABS(julianday(date)-julianday(?))<=3 AND ABS(COALESCE(amount,0)-?)<0.01",
                  (sid, d, amount or 0))
    if dup:
        return {"charge_id": dup["id"], "price_change": None, "duplicate": True}
    cid = db.run("INSERT INTO sub_charges(sub_id, date, amount, currency, source, note) VALUES (?,?,?,?,?,?)",
                 (sid, d, amount, currency, source, note))
    upd, change = {}, None
    if (amount is not None and s["amount"] is not None and currency == (s["currency"] or "").upper()
            and source in ("manual", "email") and abs(amount - s["amount"]) > max(0.01 * s["amount"], 0.5)):
        change = (s["amount"], amount)
        upd.update(previous_amount=s["amount"], amount=amount)
    if s["amount"] is None and amount is not None:
        upd["amount"] = amount
    nb = s["next_billing_date"]
    if nb and d >= (date.fromisoformat(nb) - timedelta(days=5)).isoformat():
        nb = advance(nb, s["cycle"])  # this payment covers the period due on nb (even if paid a few days early)
        while nb <= d:
            nb = advance(nb, s["cycle"])
        upd["next_billing_date"] = nb
    elif not nb:
        upd["next_billing_date"] = advance(d, s["cycle"])
    if s["status"] == "trial":
        upd["status"] = "active"
    if upd:
        save(sid, **upd)
    return {"charge_id": cid, "price_change": change, "duplicate": False}


def cancel(sid, effective_date=None, reason=""):
    s = get(sid)
    eff = effective_date or (s["trial_end_date"] if s["status"] == "trial" else s["next_billing_date"])
    future = bool(eff) and eff > date.today().isoformat()
    via = f"{s['payment_method']} {s['billed_via']}".lower()
    checklist = {"service": False, "confirmation": False}
    if re.search(r"upi|autopay|card|credit|debit|mandate|e-?nach|si\b|standing", via) or not via.strip():
        checklist["mandate"] = False
    return save(sid, status="cancelling" if future else "cancelled", auto_renew=0, cancel_effective_date=eff,
                cancel_reason=reason or "", cancelled_at=db.now(), cancel_checklist=checklist)


def reactivate(sid):
    s = get(sid)
    nb = s["next_billing_date"] or date.today().isoformat()
    while nb < date.today().isoformat():
        nb = advance(nb, s["cycle"])
    return save(sid, status="active", auto_renew=1, cancel_effective_date=None, cancelled_at=None, next_billing_date=nb)


def mark_used(sid, d=None):
    return save(sid, last_used=(d or date.today().isoformat())[:10])


# ============================== analytics ==============================
def analytics():
    live = subs("live")
    home = home_currency()
    paying = [s for s in live if s["status"] != "trial"]
    monthly = sum(s["monthly_home"] or 0 for s in paying)
    unconverted = sorted({s["currency"] for s in live if s["amount"] is not None and s["monthly_home"] is None})

    def group(key):
        out = {}
        for s in paying:
            k = (s.get(key) or "").strip() or "Not set"
            out[k] = out.get(k, 0) + (s["monthly_home"] or 0)
        return sorted(({"name": k, "monthly": round(v, 2)} for k, v in out.items()), key=lambda x: -x["monthly"])

    trend = []
    start = (date.today().replace(day=1) - timedelta(days=330)).replace(day=1)
    rows = db.rows("SELECT c.date, c.amount, c.currency, s.my_share FROM sub_charges c JOIN subscriptions s ON s.id=c.sub_id WHERE c.date>=?",
                   (start.isoformat(),))
    buckets = {}
    for r in rows:
        v = to_home(r["amount"], r["currency"])
        if v is not None:
            buckets[r["date"][:7]] = buckets.get(r["date"][:7], 0) + v * (r["my_share"] or 100) / 100
    m = start
    for _ in range(12):
        key = m.strftime("%Y-%m")
        trend.append({"month": key, "label": m.strftime("%b"), "total": round(buckets.get(key, 0), 2)})
        m = (m + timedelta(days=32)).replace(day=1)

    today = date.today()
    upcoming = sorted([s for s in live if s["status"] in ("active", "trial") and s["days_to_billing"] is not None and 0 <= s["days_to_billing"] <= 30],
                      key=lambda s: s["days_to_billing"])
    trials = sorted([s for s in live if s["status"] == "trial"], key=lambda s: s["days_to_trial_end"] if s["days_to_trial_end"] is not None else 999)
    waste = []
    for s in paying:
        why = []
        if s.get("value_rating") and s["value_rating"] <= 2:
            why.append(f"you rated it {s['value_rating']}/5")
        if s.get("unused_days") is not None and s["unused_days"] >= 45:
            why.append(f"not used in {s['unused_days']} days")
        if why:
            waste.append({"id": s["id"], "name": s["name"], "monthly": s["monthly_home"], "why": ", ".join(why)})
    budget = float(db.get_setting("subs_budget", 0) or 0)
    return {
        "home_currency": home, "monthly": round(monthly, 2), "yearly": round(monthly * 12, 2),
        "daily": round(monthly * 12 / 365, 2),
        "counts": {st: sum(1 for s in subs() if s["status"] == st) for st in STATUSES},
        "by_category": group("category"), "by_payment": group("payment_method"), "by_billed_via": group("billed_via"),
        "trend": trend, "upcoming": [{"id": s["id"], "name": s["name"], "emoji": s["emoji"], "date": s["next_billing_date"],
                                      "days": s["days_to_billing"], "amount": s["amount"], "currency": s["currency"],
                                      "status": s["status"]} for s in upcoming],
        "trials": [{"id": s["id"], "name": s["name"], "emoji": s["emoji"], "trial_end": s["trial_end_date"],
                    "days": s["days_to_trial_end"], "cancel_by": s["cancel_by"], "amount": s["amount"], "currency": s["currency"]}
                   for s in trials],
        "waste": waste, "waste_monthly": round(sum(w["monthly"] or 0 for w in waste), 2),
        "price_changes": [{"id": s["id"], "name": s["name"], "from": s["previous_amount"], "to": s["amount"], "currency": s["currency"]}
                          for s in live if s.get("previous_amount")],
        "cancelling_open": [{"id": s["id"], "name": s["name"], "pending": [k for k, v in s["checklist"].items() if not v]}
                            for s in subs() if s["status"] in ("cancelling", "cancelled") and any(not v for v in s["checklist"].values())],
        "budget": budget, "over_budget": bool(budget) and monthly > budget,
        "unconverted_currencies": unconverted, "fx_updated": db.get_setting("fx_updated", ""),
        "fx_markup_percent": float(db.get_setting("fx_markup_percent", 0) or 0),
        "suggestions_pending": db.row("SELECT COUNT(*) n FROM sub_suggestions WHERE status='pending'")["n"],
        "as_of": today.isoformat(),
    }


def facts():
    """Plain-language summary for the AI (audit, briefing, chat)."""
    a = analytics()
    L = [f"Home currency {a['home_currency']}. Subscriptions costing money: {sum(a['counts'][k] for k in ('active', 'cancelling'))}, "
         f"trials: {a['counts']['trial']}. Total ≈ {fmt_money(a['monthly'])}/month ≈ {fmt_money(a['yearly'])}/year (user's share)."]
    if a["budget"]:
        L.append(f"Monthly budget {fmt_money(a['budget'])}: {'OVER budget' if a['over_budget'] else 'within budget'}.")
    for s in subs("live") + subs("paused"):
        bits = [f"{s['name']}" + (f" ({s['plan']})" if s["plan"] else ""), s["status"], s["category"],
                f"{fmt_money(s['amount'], s['currency'])}/{PER[s['cycle']]}" if s["amount"] is not None else "amount unknown"]
        if s["monthly_home"] is not None and (s["currency"] or "") != a["home_currency"]:
            bits.append(f"≈ {fmt_money(s['monthly_home'])}/month")
        if s["status"] == "trial":
            bits.append(f"trial ends {s['trial_end_date']} (cancel by {s['cancel_by']})")
        elif s["next_billing_date"]:
            bits.append(f"next charge {s['next_billing_date']}")
        if s["payment_method"]:
            bits.append(f"paid via {s['payment_method']}")
        if s["billed_via"]:
            bits.append(f"billed through {s['billed_via']}")
        if s["shared_with"]:
            bits.append(f"shared with {s['shared_with']} (user pays {s['my_share']:.0f}%)")
        if s.get("value_rating"):
            bits.append(f"value {s['value_rating']}/5")
        if s.get("unused_days") is not None:
            bits.append(f"last used {s['unused_days']} days ago")
        if s.get("previous_amount"):
            bits.append(f"price changed from {fmt_money(s['previous_amount'], s['currency'])}")
        L.append("- " + ", ".join(bits))
    if a["waste"]:
        L.append("Low value / unused: " + "; ".join(f"{w['name']} ({w['why']})" for w in a["waste"]))
    if a["unconverted_currencies"]:
        L.append("No exchange rate for: " + ", ".join(a["unconverted_currencies"]) + " (excluded from totals).")
    return "\n".join(L)


# ============================== AI helpers ==============================
def audit():
    from . import llm
    from .agents import skill
    text = llm.complete([{"role": "system", "content": skill("subscription_audit")},
                         {"role": "user", "content": f"Today: {date.today().isoformat()}\n\n" + facts()}], timeout=240)
    db.set_setting("subs_last_audit", {"at": db.now(), "text": text})
    return text


def cancel_guide(sid):
    from . import llm
    from .agents import skill
    s = get(sid)
    prompt = (f"Service: {s['name']}" + (f" ({s['plan']})" if s["plan"] else "") +
              f"\nBilled through: {s['billed_via'] or 'unknown'}\nPayment method: {s['payment_method'] or 'unknown'}"
              f"\nManage page on file: {s['manage_url'] or 'none'}\nCountry: India")
    text = llm.complete([{"role": "system", "content": skill("subscription_cancel")}, {"role": "user", "content": prompt}], timeout=180)
    save(sid, cancel_guide=text)
    return text
