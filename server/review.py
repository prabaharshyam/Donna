"""Weekly review: what got done, what slipped, mood trends, goal progress, people, ideas."""
import html
import json
import re
import threading
from collections import Counter
from datetime import date, timedelta

from . import db, life, llm

_lock = threading.Lock()


def week_bounds(ref: date = None):
    ref = ref or date.today()
    start = ref - timedelta(days=ref.weekday())
    return start, start + timedelta(days=6)


def stats(ref: date = None):
    ws, we = week_bounds(ref)
    a, b = ws.isoformat(), we.isoformat()
    b_end = (we + timedelta(days=1)).isoformat()
    done = db.rows("SELECT t.title, p.name AS list FROM tasks t LEFT JOIN projects p ON p.id=t.project_id WHERE completed=1 AND completed_at>=? AND completed_at<? ORDER BY completed_at", (a, b_end))
    slipped = db.rows("SELECT title, due_date FROM tasks WHERE completed=0 AND due_date>=? AND due_date<=? AND due_date<?", (a, b, date.today().isoformat()))
    overdue = db.row("SELECT COUNT(*) n FROM tasks WHERE completed=0 AND due_date<?", (date.today().isoformat(),))["n"]
    created = db.row("SELECT COUNT(*) n FROM tasks WHERE created_at>=? AND created_at<?", (a, b_end))["n"]
    journal = db.rows("SELECT date, mood, length(body) AS chars FROM journal WHERE date BETWEEN ? AND ? AND length(body)>0 ORDER BY date", (a, b))
    moods = Counter(j["mood"] for j in journal if j["mood"])
    ideas = db.rows("SELECT title FROM ideas WHERE created_at>=? AND created_at<?", (a, b_end))
    contacted = db.rows("SELECT DISTINCT p.name FROM interactions i JOIN people p ON p.id=i.person_id WHERE i.date BETWEEN ? AND ?", (a, b))
    events = db.row("SELECT COUNT(*) n FROM events WHERE start>=? AND start<?", (a, b_end))["n"]
    goals = []
    for g in life.goals("active"):
        moved = db.row("SELECT COUNT(*) n FROM tasks WHERE goal_id=? AND completed=1 AND completed_at>=? AND completed_at<?", (g["id"], a, b_end))["n"]
        goals.append({"title": g["title"], "progress": g["progress"], "moved_this_week": moved, "target_date": g["target_date"]})
    return {
        "week": f"{ws.strftime('%d %b')} – {we.strftime('%d %b %Y')}", "week_start": a,
        "completed": [d["title"] for d in done][:40], "completed_count": len(done), "created_count": created,
        "slipped": [f"{s['title']} (due {s['due_date']})" for s in slipped][:15], "overdue_now": overdue,
        "journal_days": len(journal), "moods": dict(moods), "mood_by_day": {j["date"]: j["mood"] for j in journal if j["mood"]},
        "ideas_captured": [i["title"] for i in ideas][:15], "people_contacted": [c["name"] for c in contacted],
        "local_events": events, "goals": goals,
        "people_to_reach_out": [p["name"] for p in life.due_contacts()][:5],
        "birthdays_next_week": [f"{p['name']} ({date.fromisoformat(p['next_birthday']).strftime('%a %d %b')})" for p in life.upcoming_birthdays(10)],
        "renewals_next_2_weeks": [f"{r['title']} ({date.fromisoformat(r['due_date']).strftime('%a %d %b')})" for r in life.renewals(days_ahead=14)],
    }


def facts(s) -> str:
    """Plain sentences with explicit zeros, so a small model can't 'fill in' missing data."""
    L_ = [f"Week: {s['week']}."]
    L_.append(f"Tasks completed: {s['completed_count']}" + (f" ({'; '.join(s['completed'][:12])})." if s["completed"] else ". Nothing was completed."))
    L_.append(f"New tasks created: {s['created_count']}.")
    L_.append(f"Tasks that slipped past their due date this week: {len(s['slipped'])}" + (f" ({'; '.join(s['slipped'])})." if s["slipped"] else "."))
    L_.append(f"Total overdue right now: {s['overdue_now']}.")
    if s["journal_days"]:
        mood = ", ".join(f"{d}: {m}" for d, m in s["mood_by_day"].items()) or "no moods recorded"
        L_.append(f"Journal: wrote on {s['journal_days']} of 7 days. Moods by day: {mood}.")
    else:
        L_.append("Journal: NO entries this week, so mood is UNKNOWN. Do not describe mood or a streak.")
    L_.append(f"Ideas captured: {len(s['ideas_captured'])}" + (f" ({'; '.join(s['ideas_captured'])})." if s["ideas_captured"] else "."))
    L_.append("People the user caught up with: " + (", ".join(s["people_contacted"]) if s["people_contacted"] else "none logged") + ".")
    if s["goals"]:
        for g in s["goals"]:
            L_.append(f"Goal '{g['title']}': {g['progress']}% done, {g['moved_this_week']} linked tasks completed this week" +
                      (f", target {g['target_date']}" if g["target_date"] else "") + ".")
    else:
        L_.append("Goals: none set.")
    L_.append("Overdue to reach out to: " + (", ".join(s["people_to_reach_out"]) if s["people_to_reach_out"] else "nobody") + ".")
    L_.append("Birthdays in the next 10 days: " + (", ".join(s["birthdays_next_week"]) if s["birthdays_next_week"] else "none") + ".")
    L_.append("Renewals/bills due in the next 2 weeks: " + (", ".join(s["renewals_next_2_weeks"]) if s["renewals_next_2_weeks"] else "none") + ".")
    return "\n".join(L_)


def generate(ref: date = None, send_email=False):
    from .agents import skill
    with _lock:
        s = stats(ref)
        name = db.get_setting("user_name", "")
        try:
            narrative = llm.complete([{"role": "system", "content": skill("review") + (f"\nThe user's name is {name}." if name else "")},
                                      {"role": "user", "content": facts(s)}], timeout=300).strip()
            narrative = re.sub(r"<think>.*?</think>", "", narrative, flags=re.S).strip()
        except Exception as e:
            narrative = f"(Donna couldn't write the narrative: {e}). Here are the numbers."
        db.run("INSERT INTO reviews(week_start, stats, narrative) VALUES (?,?,?) ON CONFLICT(week_start) DO UPDATE SET stats=excluded.stats, narrative=excluded.narrative, created_at=datetime('now','localtime')",
               (s["week_start"], json.dumps(s), narrative))
        r = get(s["week_start"])
        if send_email:
            from . import mailer
            if mailer.configured():
                mailer.send(f"Your week in review · {s['week']}", md_html(narrative) + stats_html(s), narrative)
        return r


def get(week_start=None):
    r = db.row("SELECT * FROM reviews WHERE week_start=?", (week_start,)) if week_start else \
        db.row("SELECT * FROM reviews ORDER BY week_start DESC LIMIT 1")
    if r:
        r["stats"] = json.loads(r["stats"])
    return r


def history():
    return db.rows("SELECT id, week_start, created_at FROM reviews ORDER BY week_start DESC LIMIT 52")


_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_HEAD = re.compile(r"^#+\s*")


def md_html(s: str) -> str:
    out = []
    for block in re.split(r"\n\s*\n", html.escape(s)):
        lines = block.strip().splitlines()
        if lines and all(_BULLET.match(l) for l in lines):
            out.append("<ul>" + "".join("<li>" + _BULLET.sub("", l) + "</li>" for l in lines) + "</ul>")
        else:
            out.append("<p>" + "<br>".join(_HEAD.sub("", l) for l in lines) + "</p>")
    h = "".join(out)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)


def stats_html(s):
    tiles = [("Done", s["completed_count"]), ("Slipped", len(s["slipped"])), ("Journal days", s["journal_days"]), ("Ideas", len(s["ideas_captured"]))]
    return "<table style='width:100%;margin-top:18px;border-collapse:collapse'><tr>" + "".join(
        f"<td style='padding:10px;border:1px solid #eee;text-align:center'><div style='font-size:22px;font-family:Georgia,serif'>{v}</div><div style='font-size:11px;color:#8a837a;text-transform:uppercase'>{k}</div></td>"
        for k, v in tiles) + "</tr></table>"
