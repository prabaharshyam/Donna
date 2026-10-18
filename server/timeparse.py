"""Deterministic date/time understanding.

Small local models are unreliable at calendar arithmetic ("Thursday night" → Wednesday, "8am" →
"tonight"). So Python resolves every date/time phrase in the user's message to an exact local
datetime, tells the model the answers, and corrects tool arguments that disagree.
"""
import os
import re
import time
from datetime import date, datetime, timedelta

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY_ABBR = {d[:3]: i for i, d in enumerate(DAYS)} | {"tues": 1, "thur": 3, "thurs": 3}
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
PART_OF_DAY = {"morning": "09:00", "afternoon": "14:00", "evening": "18:00", "night": "21:00", "tonight": "21:00",
               "noon": "12:00", "midday": "12:00", "midnight": "23:59", "eod": "17:00", "end of day": "17:00", "lunch": "13:00"}

DEFAULT_TZ = "Asia/Kolkata"


def apply_timezone(tz: str = None):
    """Pin the whole process to the user's timezone (IST by default) so every datetime.now()
    is correct even when Donna is hosted on a server in another zone."""
    from . import db
    tz = tz or db.get_setting("timezone", DEFAULT_TZ) or DEFAULT_TZ
    os.environ["TZ"] = tz
    time.tzset()
    return tz


# ------------------------------------------------------------------ parsing
_WD = r"(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(?:day|nesday|sday|rsday|urday)?"
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
_TIME = r"(?<![\d/:.-])(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)|(?<![\d/.-])([01]?\d|2[0-3]):([0-5]\d)(?!\s*(?:am|pm))"
DATE_PATTERNS = [
    ("day after tomorrow", r"\bday after tomorrow\b"),
    ("tomorrow", r"\b(?:tomorrow|tmrw|tmr|tomo)\b"),
    ("today", r"\b(?:today|tonight|this (?:morning|afternoon|evening))\b"),
    ("yesterday", r"\byesterday\b"),
    ("in_days", r"\bin (\d{1,3}) days?\b"),
    ("next_week", r"\bnext week\b"),
    ("weekday", rf"\b(next |this |coming |on )?({_WD})\b"),
    ("dmy", r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b"),
    ("iso", r"\b(20\d{2})-(\d{2})-(\d{2})\b"),
    ("d_mon", rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MON})(?:,?\s+(20\d{{2}}))?\b"),
    ("mon_d", rf"\b({_MON})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(20\d{{2}}))?\b"),
]


def _weekday_index(word):
    w = word.lower()
    for i, d in enumerate(DAYS):
        if w.startswith(d[:3]):
            return i
    return None


def _month(word):
    return MONTHS.get(word.lower()[:3])


def _future_date(month, day, year=None):
    t = date.today()
    try:
        if year:
            return date(int(year) + (2000 if int(year) < 100 else 0), month, day)
        d = date(t.year, month, day)
        return d if d >= t - timedelta(days=1) else date(t.year + 1, month, day)
    except ValueError:
        return None


def future_or_rolled(d: str) -> str:
    """Goal/target dates must be in the future: 'by March' said in October means next March."""
    try:
        x = date.fromisoformat(d[:10])
    except ValueError:
        return d
    while x < date.today():
        try:
            x = x.replace(year=x.year + 1)
        except ValueError:
            x = x.replace(year=x.year + 1, day=28)
    return x.isoformat()


def _end_of_month(y, m):
    import calendar
    return date(y, m, calendar.monthrange(y, m)[1])


def _find_dates(text):
    t = date.today()
    out = []
    # "by March", "in June", "end of December": last day of the next such month
    for m in re.finditer(rf"\b(?:by|in|before|until|till|end of)\s+({_MON})(?!\s*\d{{1,2}}\b)(?:\s+(20\d{{2}}))?\b", text, re.I):
        mo = _month(m.group(1))
        if not mo:
            continue
        y = int(m.group(2)) if m.group(2) else (t.year if mo >= t.month else t.year + 1)
        out.append((m.start(), m.end(), m.group(0), _end_of_month(y, mo)))
    for m in re.finditer(r"\b(?:this year|end of (?:the )?year|by year[- ]end)\b", text, re.I):
        out.append((m.start(), m.end(), m.group(0), date(t.year, 12, 31)))
    for kind, pat in DATE_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            d = None
            if kind == "today":
                d = t
            elif kind == "tomorrow":
                d = t + timedelta(days=1)
            elif kind == "day after tomorrow":
                d = t + timedelta(days=2)
            elif kind == "yesterday":
                d = t - timedelta(days=1)
            elif kind == "in_days":
                d = t + timedelta(days=int(m.group(1)))
            elif kind == "next_week":
                d = t + timedelta(days=7 - t.weekday())  # next Monday
            elif kind == "weekday":
                wi = _weekday_index(m.group(2))
                if wi is None:
                    continue
                ahead = (wi - t.weekday()) % 7
                prefix = (m.group(1) or "").strip().lower()
                if prefix == "next" and ahead == 0:
                    ahead = 7
                d = t + timedelta(days=ahead)
            elif kind == "iso":
                try:
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except ValueError:
                    continue
            elif kind == "dmy":  # Indian format: DD/MM[/YYYY]
                dd, mm = int(m.group(1)), int(m.group(2))
                if not (1 <= mm <= 12 and 1 <= dd <= 31):
                    continue
                d = _future_date(mm, dd, m.group(3))
            elif kind == "d_mon":
                mo = _month(m.group(2))
                d = mo and _future_date(mo, int(m.group(1)), m.group(3))
            elif kind == "mon_d":
                mo = _month(m.group(1))
                d = mo and _future_date(mo, int(m.group(2)), m.group(3))
            if d and not any(s <= m.start() < e for s, e, *_ in out):
                out.append((m.start(), m.end(), m.group(0), d))
    return sorted(out)


def _dates_in(text):
    return any(d > date.today() for *_, d in _find_dates(text))


def _find_times(text):
    out = []
    for m in re.finditer(_TIME, text, re.I):
        if m.group(3):
            h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower().replace(".", "")
            if not (1 <= h <= 12 and mi < 60):
                continue
            h = (0 if h == 12 else h) + (12 if ap == "pm" else 0)
        else:
            h, mi = int(m.group(4)), int(m.group(5))
        out.append((m.start(), m.end(), m.group(0), f"{h:02d}:{mi:02d}"))
    # bare "at 7" → use part-of-day words to decide am/pm
    for m in re.finditer(r"\bat (\d{1,2})(?![\d:.]|\s*(?:am|pm|a\.m|p\.m|%|days?|min|hours?))\b", text, re.I):
        h = int(m.group(1))
        if not 1 <= h <= 12 or any(s <= m.start(1) < e for s, e, *_ in out):
            continue
        low = text.lower()
        if re.search(r"\b(night|tonight|evening|pm)\b", low) and h < 12:
            h += 12
        elif re.search(r"\b(afternoon)\b", low) and h < 7:
            h += 12
        elif not re.search(r"\b(morning|am)\b", low) and (h <= 6 or (h < 12 and not _dates_in(text) and datetime.now().hour >= h)):
            h += 12  # "at 5" with no cue means 5 PM; "at 7" said after 7 AM today means 7 PM
        out.append((m.start(), m.end(), m.group(0), f"{h % 24:02d}:00"))
    if not out:
        for word, hm in PART_OF_DAY.items():
            m = re.search(rf"\b{word}\b", text, re.I)
            if m:
                out.append((m.start(), m.end(), m.group(0), hm))
                break
    return sorted(out)


_FACT = re.compile(rf"\b(?:today|tomorrow|yesterday)\s+(?:is|was)\s+(?:a\s+)?{_WD}\b|\bit'?s\s+{_WD}(?:\s+today)?\b"
                   r"|\b(?:how|why)\b[^?]{0,50}?\b(?:could|can|is|would|did|does|come)\b[^?]*\??", re.I)


def fix_wording(reply: str, saved_values) -> str:
    """Make the reply's times agree with what was actually saved (AM/PM flips, 'tonight' for a morning time)."""
    saved = set()
    for v in saved_values:
        m = re.match(r"^\d{4}-\d{2}-\d{2}T(\d{2}):(\d{2})", str(v or ""))
        if m:
            saved.add((int(m.group(1)), int(m.group(2))))
    if not saved:
        return reply

    def repl(m):
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).upper().replace(".", "")
        h24 = (0 if h == 12 else h) + (12 if ap.startswith("P") else 0)
        if (h24, mi) in saved:
            return m.group(0)
        flipped = (h24 + 12) % 24
        if (flipped, mi) in saved:
            return f"{h}:{mi:02d} {'AM' if flipped < 12 else 'PM'}"
        return m.group(0)

    reply = re.sub(r"\b(\d{1,2})(?::(\d{2}))?\s*([AaPp]\.?[Mm]\.?)", repl, reply)
    if all(h < 12 for h, _ in saved):
        reply = re.sub(r"\btonight\b", "this morning", reply, flags=re.I)
    return reply


def is_fact_only(text: str) -> bool:
    """True for messages that only state a fact or question the previous reply
    ("today is Wednesday", "how could 8am be tonight? it's AM"). These are not edit requests."""
    rest = _FACT.sub(" ", text)
    if rest == text:
        return False
    rest = re.sub(r"\bit'?s\s+(?:am|pm|morning|evening|night)\b|[?.!,]", " ", rest, flags=re.I)
    return len(re.findall(r"[a-z]{2,}", rest.lower())) <= 2


def resolve(text: str):
    """Returns {"items": [...], "date": iso|None, "time": "HH:MM"|None, "datetime": iso|None}.
    date/time are only set when the message contains exactly one of them (unambiguous).
    Statements of fact ("today is Wednesday") and questions about earlier replies are not instructions."""
    text = _FACT.sub(" ", text)
    rel = re.search(r"\bin (\d{1,3}|an?|half an?) (minutes?|mins?|hours?|hrs?)\b", text, re.I)
    if rel:
        n = {"a": 1, "an": 1}.get(rel.group(1).lower(), None)
        n = 0.5 if rel.group(1).lower().startswith("half") else (n or int(rel.group(1)))
        delta = timedelta(minutes=n) if rel.group(2).lower().startswith("m") else timedelta(hours=n)
        at = (datetime.now() + delta).strftime("%Y-%m-%dT%H:%M")
        return {"items": [{"phrase": rel.group(0), "date": at[:10], "time": at[11:]}], "date": at[:10], "time": at[11:], "datetime": at}
    dates, times = _find_dates(text), _find_times(text)
    items = []
    for s, e, phrase, d in dates:
        tm = next((t for t in times if 0 <= t[0] - e <= 25 or 0 <= s - t[1] <= 12), None)
        items.append({"phrase": phrase + (f" {tm[2]}" if tm else ""), "date": d.isoformat(), "time": tm[3] if tm else None})
    used = {t[0] for t in times if any(i["time"] == t[3] for i in items)}
    for s, e, phrase, hm in times:
        if s not in used:
            items.append({"phrase": phrase, "date": None, "time": hm})
    uniq_dates = sorted({i["date"] for i in items if i["date"]})
    uniq_times = sorted({i["time"] for i in items if i["time"]})
    out = {"items": items, "date": uniq_dates[0] if len(uniq_dates) == 1 else None,
           "time": uniq_times[0] if len(uniq_times) == 1 else None}
    # When the time is attached to one specific date phrase, that pairing wins.
    paired = [i for i in items if i["date"] and i["time"]]
    if len(paired) == 1:
        out["datetime"] = f"{paired[0]['date']}T{paired[0]['time']}"
    elif out["date"] and out["time"]:
        out["datetime"] = f"{out['date']}T{out['time']}"
    else:
        out["datetime"] = None
    return out


# ------------------------------------------------------------------ human wording
def human(value: str) -> str:
    """'2026-10-15T21:00' → 'Tomorrow (Thu 15 Oct) at 9:00 PM'. Dates alone omit the time."""
    if not value:
        return ""
    has_time = len(value) > 10
    dt = datetime.fromisoformat(value[:16]) if has_time else datetime.fromisoformat(value[:10] + "T00:00")
    d, t = dt.date(), date.today()
    diff = (d - t).days
    label = dt.strftime("%a %d %b") + ("" if d.year == t.year else dt.strftime(" %Y"))
    rel = {0: "Today", 1: "Tomorrow", -1: "Yesterday"}.get(diff)
    day = f"{rel} ({label})" if rel else label
    if not has_time:
        return day
    clock = dt.strftime("%I:%M %p").lstrip("0")
    s = f"{day} at {clock}"
    if dt < datetime.now():
        s += " (this time has ALREADY PASSED)"
    return s


def context_block(text: str) -> str:
    r = resolve(text)
    if not r["items"]:
        return ""
    lines = []
    for i in r["items"]:
        if i["date"] and i["time"]:
            v = f"{i['date']}T{i['time']} = {human(i['date'] + 'T' + i['time'])}"
        elif i["date"]:
            v = f"{i['date']} = {human(i['date'])}"
        else:
            v = f"time {i['time']} ({datetime.strptime(i['time'], '%H:%M').strftime('%I:%M %p').lstrip('0')}); the date is not stated in this message"
        lines.append(f'- "{i["phrase"]}" → {v}')
    return ("Date/time phrases in the user's latest message, ALREADY RESOLVED by the system. Use these exact values "
            "in tool arguments; do not recalculate:\n" + "\n".join(lines))


# ------------------------------------------------------------------ argument correction
DATETIME_ARGS = {"reminder_at", "start"}
DATE_ARGS = {"due_date", "date", "start_date", "target_date"}


def correct_args(args: dict, text: str):
    """Fix tool arguments that contradict what the user literally said. Returns (args, changes)."""
    r = resolve(text)
    changes = []
    if not r["items"]:
        return args, changes
    args = dict(args)
    for k in DATETIME_ARGS & args.keys():
        v = str(args[k] or "").replace(" ", "T")[:16]
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$", v):
            if r["datetime"]:
                args[k], _ = r["datetime"], changes.append(f"{k}: {v!r} → {r['datetime']}")
            continue
        new = v
        if r["datetime"]:
            new = r["datetime"]
        else:
            if r["date"]:
                new = r["date"] + new[10:]
            if r["time"]:
                new = new[:11] + r["time"]
        if new != v:
            args[k] = new
            changes.append(f"{k}: {v} → {new}")
    for k in DATE_ARGS & args.keys():
        v = str(args[k] or "")[:10]
        want = r["date"] or (r["datetime"] or "")[:10] or None
        # due date follows the reminder when the user gave a single date
        if want and v and v != want:
            args[k] = want
            changes.append(f"{k}: {v} → {want}")
    if "reminder_at" in args and "due_date" in args and args["reminder_at"] and args["due_date"] and \
            str(args["reminder_at"])[:10] > str(args["due_date"])[:10]:
        args["due_date"] = str(args["reminder_at"])[:10]
    return args, changes
