"""Background loop: task reminders, appointment reminders, daily briefing, evening journal nudge."""
import html
import logging
import threading
import time
from datetime import date, datetime, timedelta

from . import calendar_svc as cal
from . import db, mailer, services as S

log = logging.getLogger("donna.scheduler")


def _once(key) -> bool:
    """True the first time a key is seen; makes every reminder idempotent."""
    if db.row("SELECT 1 FROM sent_log WHERE key=?", (key,)):
        return False
    db.run("INSERT INTO sent_log(key) VALUES (?)", (key,))
    return True


def _fmt(dt: str):
    d = datetime.fromisoformat(dt)
    return d.strftime("%a %d %b, %I:%M %p").replace(" 0", " ")


def _email(subject, inner, text=""):
    if db.get_setting("email_enabled", True) and mailer.configured():
        try:
            mailer.send(subject, inner, text)
        except Exception as e:
            log.warning("email failed: %s", e)
            S.notify("Email delivery failed", str(e)[:200], "#/settings")


def task_reminders():
    for t in db.rows("SELECT * FROM tasks WHERE completed=0 AND reminder_sent=0 AND reminder_at IS NOT NULL AND reminder_at<=?",
                     (db.now(),)):
        db.run("UPDATE tasks SET reminder_sent=1 WHERE id=?", (t["id"],))
        if t["reminder_at"] < (datetime.now() - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M"):
            continue  # stale (app was off), don't spam
        S.notify(f"Reminder: {t['title']}", t["note"][:140], f"#/tasks?task={t['id']}")
        due = f"<div style='color:#8a837a;font-size:13px'>Due {html.escape(t['due_date'])}</div>" if t["due_date"] else ""
        note = f"<p style='color:#57524b'>{html.escape(t['note'])}</p>" if t["note"] else ""
        _email(f"Reminder: {t['title']}",
               f"<div style='font-size:18px;font-weight:600'>{html.escape(t['title'])}</div>{due}{note}"
               "<p style='color:#8a837a;font-size:13px;margin-top:18px'>Mark it done in Donna when you're finished.</p>",
               t["title"])


def event_reminders():
    lead = int(db.get_setting("event_reminder_min", 15))
    now = datetime.now()
    try:
        events = cal.list_events(date.today().isoformat(), (date.today() + timedelta(days=1)).isoformat())
    except Exception as e:
        log.warning("calendar fetch failed: %s", e)
        return
    for e in events:
        if e.get("all_day"):
            continue
        start = datetime.fromisoformat(e["start"])
        if now <= start <= now + timedelta(minutes=lead) and _once(f"evt:{e['source']}:{e['id']}:{e['start']}"):
            mins = max(1, int((start - now).total_seconds() // 60))
            S.notify(f"In {mins} min: {e['title']}", _fmt(e["start"]) + (f" · {e['location']}" if e.get("location") else ""), "#/calendar")
            loc = f"<div>📍 {html.escape(e['location'])}</div>" if e.get("location") else ""
            link = f"<p><a style='color:#7a2e3a' href='{html.escape(e['link'])}'>Open in Google Calendar</a></p>" if e.get("link") else ""
            _email(f"In {mins} min: {e['title']}",
                   f"<div style='font-size:18px;font-weight:600'>{html.escape(e['title'])}</div>"
                   f"<div style='color:#57524b'>{_fmt(e['start'])} – {datetime.fromisoformat(e['end']).strftime('%I:%M %p').lstrip('0')}</div>{loc}{link}",
                   e["title"])


def briefing_html(d=None):
    from .agents import t_get_briefing
    b = t_get_briefing(d)
    sec = []

    def block(title, items):
        if items:
            sec.append(f"<div style='margin:18px 0 6px;font-size:12px;letter-spacing:1.2px;text-transform:uppercase;color:#8a837a'>{title}</div>"
                       + "".join(f"<div style='padding:7px 0;border-bottom:1px solid #f3efe9'>{i}</div>" for i in items))

    block("Schedule", [f"<b>{datetime.fromisoformat(e['start']).strftime('%I:%M %p').lstrip('0') if not e.get('all_day') else 'All day'}</b> · {html.escape(e['title'])}"
                       for e in b["events"] if "error" not in e])
    block("Overdue", [f"{html.escape(t['title'])} <span style='color:#b0413e'>· due {t.get('due_date')}</span>" for t in b["overdue"]])
    block("Due today", [html.escape(t["title"]) for t in b["tasks_due"]])
    block("My Day", [html.escape(t["title"]) for t in b["my_day"]])
    block("Important", [f"★ {html.escape(t['title'])}" for t in b["important"]])
    block("Birthdays", [f"🎂 {html.escape(p['name'])} · {'today' if p['in_days'] == 0 else 'in ' + str(p['in_days']) + ' days'}{' (turning ' + str(p['turning']) + ')' if p.get('turning') else ''}" for p in b.get("birthdays", [])])
    block("Renewals & bills", [f"{html.escape(r['title'])} · {'due today' if r['days_left'] == 0 else ('overdue' if r['days_left'] < 0 else 'in ' + str(r['days_left']) + ' days')}" for r in b.get("renewals_due", [])])
    block("Reach out", [f"{html.escape(p['name'])} · {str(p['days_since_contact']) + ' days since you spoke' if p['days_since_contact'] is not None else 'not logged yet'}" for p in b.get("reach_out", [])])
    if b.get("inbox_commitments_pending"):
        block("From your email", [f"{b['inbox_commitments_pending']} commitments waiting in Inbox"])
    name = db.get_setting("user_name", "")
    intro = f"Good morning{', ' + html.escape(name) if name else ''}. Here's your {datetime.now().strftime('%A')}."
    try:
        from . import mentor
        from .review import md_html
        note = mentor.today_note()
        if note:
            intro += ("<div style='margin:16px 0;padding:14px 16px;background:#f7efef;border-left:3px solid #7a2e3a;border-radius:8px'>"
                      f"<div style='font-size:11px;letter-spacing:1.2px;text-transform:uppercase;color:#7a2e3a;margin-bottom:6px'>Donna's note</div>{md_html(note['content'])}</div>")
    except Exception:
        pass
    if not sec:
        sec.append("<p>Nothing scheduled and nothing due. A clean slate.</p>")
    return f"<p style='font-size:16px'>{intro}</p>" + "".join(sec), b


def daily_briefing():
    if not db.get_setting("briefing_enabled", True):
        return
    at = db.get_setting("briefing_time", "07:30")
    if datetime.now().strftime("%H:%M") < at:
        return
    if db.get_setting("mentor_enabled", True):
        from . import mentor
        waited = datetime.now() - datetime.combine(date.today(), datetime.strptime(at, "%H:%M").time())
        if not mentor.today_note() and waited < timedelta(minutes=5):
            return  # give Donna's note a few minutes so it can lead the briefing email
    if not _once(f"brief:{date.today().isoformat()}"):
        return
    inner, b = briefing_html()
    n = len(b["events"]) + len(b["tasks_due"]) + len(b["overdue"])
    S.notify("Your daily briefing is ready", f"{len(b['events'])} events · {len(b['tasks_due']) + len(b['overdue'])} tasks need you", "#/")
    _email(f"Your day: {datetime.now().strftime('%a %d %b')} · {n} things", inner)


def journal_nudge():
    at = db.get_setting("journal_nudge_time", "21:00")
    if not at or datetime.now().strftime("%H:%M") < at:
        return
    j = S.journal_get(date.today().isoformat())
    if (not j or not j["body"]) and _once(f"jnudge:{date.today().isoformat()}"):
        S.notify("How was today?", "Two lines in your journal before bed?", "#/journal")


_bg = {}


def _background(name, fn):
    """Run slow (LLM) jobs off the main loop so reminders stay punctual."""
    t = _bg.get(name)
    if t and t.is_alive():
        return
    _bg[name] = threading.Thread(target=fn, daemon=True, name=f"donna-{name}")
    _bg[name].start()


def meeting_prep():
    if not db.get_setting("prep_enabled", True):
        return
    from . import life
    lead = int(db.get_setting("prep_lead_min", 30))
    now = datetime.now()
    try:
        events = cal.list_events(date.today().isoformat(), (date.today() + timedelta(days=1)).isoformat())
    except Exception:
        return
    todo = []
    for e in events:
        if e.get("all_day"):
            continue
        start = datetime.fromisoformat(e["start"])
        if now < start <= now + timedelta(minutes=lead):
            key = f"prep:{e['source']}:{e['id']}:{e['start']}"
            if not db.row("SELECT 1 FROM sent_log WHERE key=?", (key,)):
                todo.append((key, e))
    if not todo:
        return

    def work():
        for key, e in todo:
            if not _once(key):
                continue
            prep = life.meeting_prep(e)
            if not life.prep_has_substance(prep):
                continue
            points = life.talking_points(prep) if db.get_setting("prep_ai", True) else ""
            from .review import md_html
            sec = []
            if points:
                sec.append(md_html(points))
            for p in prep["people"]:
                bits = [x for x in (p.get("relationship"), p.get("family"), p.get("notes")) if x]
                last = f"<div style='color:#8a837a;font-size:13px'>Last spoke {p['last_contact']}: {html.escape(p['last_note'])}</div>" if p.get("last_contact") else ""
                sec.append(f"<div style='margin:12px 0'><b>{html.escape(p['name'])}</b><div style='color:#57524b'>{html.escape(' · '.join(bits))}</div>{last}</div>")
            if prep["open_tasks"]:
                sec.append("<div style='margin-top:12px;font-size:12px;letter-spacing:1px;text-transform:uppercase;color:#8a837a'>Open items</div>" +
                           "".join(f"<div>☐ {html.escape(t['title'])}</div>" for t in prep["open_tasks"]))
            S.notify(f"Prep: {e['title']}", (points.replace("\n", " ")[:180] if points else "Your prep pack is ready"), "#/calendar")
            _email(f"Prep: {e['title']} at {datetime.fromisoformat(e['start']).strftime('%I:%M %p').lstrip('0')}",
                   f"<div style='font-size:18px;font-weight:600'>{html.escape(e['title'])}</div><div style='color:#57524b;margin-bottom:10px'>{_fmt(e['start'])}</div>" + "".join(sec))

    _background("prep", work)


def renewal_alerts():
    from . import life
    for r in life.renewals():
        dl = r["days_left"]
        if r["category"] == "subscription" and r["cycle"] and dl < 0:
            life.renewal_done(r["id"])  # subscriptions renew themselves; roll the date forward
            continue
        # Alert stages, each sent once per due date: first heads-up, the day before, the day, and once if overdue.
        stage = ("overdue" if -14 <= dl < 0 else "due" if dl == 0 else "tomorrow" if dl == 1
                 else "soon" if dl <= r["remind_days"] else None)
        if not stage or not _once(f"ren:{r['id']}:{r['due_date']}:{stage}"):
            continue
        amt = f" · {r['currency']} {r['amount']:g}".replace("  ", " ") if r["amount"] else ""
        when = {"due": "due today", "tomorrow": "due tomorrow", "overdue": f"overdue by {-dl} days"}.get(stage, f"due in {dl} {'day' if dl == 1 else 'days'} ({r['due_date']})")
        S.notify(f"{r['title']} {when}", f"{r['category'].title()}{amt}", "#/renewals")
        _email(f"{r['title']} is {when}",
               f"<div style='font-size:18px;font-weight:600'>{html.escape(r['title'])}</div><div style='color:#57524b'>{html.escape(r['category'].title())}{html.escape(amt)} · {when}</div>"
               f"{'<p>' + html.escape(r['notes']) + '</p>' if r['notes'] else ''}<p style='color:#8a837a;font-size:13px'>Mark it renewed in Donna once it's handled.</p>")


def people_nudges():
    from . import life
    if datetime.now().strftime("%H:%M") < db.get_setting("briefing_time", "07:30"):
        return
    ahead = int(db.get_setting("birthday_remind_days", 7))
    for p in life.upcoming_birthdays(ahead):
        d = p["birthday_in_days"]
        if d in (0, 1, ahead) and _once(f"bday:{p['id']}:{p['next_birthday']}:{d}"):
            turning = f" (turning {p['turning']})" if p["turning"] else ""
            when = "today" if d == 0 else "tomorrow" if d == 1 else f"in {d} days"
            S.notify(f"🎂 {p['name']}'s birthday is {when}{turning}", "Send a wish" if d == 0 else "Plan a gift or message", "#/people")
            _email(f"{p['name']}'s birthday is {when}{turning}",
                   f"<p>🎂 <b>{html.escape(p['name'])}</b>'s birthday is {when}{html.escape(turning)}.</p>" +
                   (f"<p style='color:#57524b'>{html.escape(p['family'])}</p>" if p["family"] else "") +
                   (f"<p style='color:#57524b'>{html.escape(p['notes'][:300])}</p>" if p["notes"] else ""))
    if datetime.now().weekday() == int(db.get_setting("nudge_weekday", 5)):
        due = life.due_contacts()[:3]
        if due and _once(f"reach:{date.today().isocalendar()[1]}"):
            names = ", ".join(p["name"] for p in due)
            S.notify("Time to reach out", f"You haven't been in touch with {names} for a while.", "#/people")


def weekly_review():
    if not db.get_setting("review_enabled", True):
        return
    if datetime.now().weekday() != int(db.get_setting("review_day", 6)) or datetime.now().strftime("%H:%M") < db.get_setting("review_time", "18:00"):
        return
    if not _once(f"review:{date.today().isoformat()}"):
        return

    def work():
        from . import review
        review.generate(send_email=True)
        S.notify("Your weekly review is ready", "What you did, what slipped, and next week's priorities", "#/review")

    _background("review", work)


def mentor_note():
    """Donna's daily mentor note, written at briefing time and pushed to phone."""
    if not db.get_setting("mentor_enabled", True):
        return
    if datetime.now().strftime("%H:%M") < db.get_setting("briefing_time", "07:30"):
        return
    if not _once(f"mentor:{date.today().isoformat()}"):
        return
    from . import mentor
    if mentor.today_note():
        return
    _background("mentor", lambda: mentor.generate_daily(notify=True))


def reflection_nudge():
    at = db.get_setting("reflection_nudge_time", "20:30")
    if not at or datetime.now().strftime("%H:%M") < at:
        return
    from . import life
    pending = [g for g in life.goals("active") if not g["reflected_today"]]
    if pending and _once(f"reflectnudge:{date.today().isoformat()}"):
        streaky = max(pending, key=lambda g: g["reflection_streak"])
        extra = f" Your {streaky['reflection_streak']}-day streak on “{streaky['title']}” is on the line." if streaky["reflection_streak"] >= 2 else ""
        names = ", ".join(f"“{g['title']}”" for g in pending)
        S.notify("Two minutes with your goals?", f"Reflect on {names}.{extra}", f"#/goals/{pending[0]['id']}")


def inbox_scan():
    from . import inbox
    if inbox.due_for_scan():
        _background("inbox", inbox._safe_scan)


def loop():
    while True:
        for job in (task_reminders, event_reminders, daily_briefing, journal_nudge, meeting_prep, renewal_alerts,
                    people_nudges, weekly_review, inbox_scan, mentor_note, reflection_nudge):
            try:
                job()
            except Exception as e:
                log.exception("scheduler job %s failed: %s", job.__name__, e)
        time.sleep(30)


def start():
    threading.Thread(target=loop, daemon=True, name="donna-scheduler").start()
