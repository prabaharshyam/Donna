"""People, goals, renewals and meeting prep."""
import calendar as _cal
import json
import re
from datetime import date, timedelta

from . import db

# ============================== People ==============================
PERSON_FIELDS = {"name", "relationship", "birthday", "email", "phone", "family", "notes", "contact_every_days", "last_contact"}


def next_birthday(bday: str):
    """bday: 'YYYY-MM-DD' or 'MM-DD'. Returns (date, turning_age or None)."""
    if not bday:
        return None, None
    m = re.match(r"^(?:(\d{4})-)?(\d{1,2})-(\d{1,2})$", bday.strip())
    if not m:
        return None, None
    y, mo, d = (int(m.group(1)) if m.group(1) else None), int(m.group(2)), int(m.group(3))
    t = date.today()
    for yr in (t.year, t.year + 1):
        try:
            nb = date(yr, mo, min(d, _cal.monthrange(yr, mo)[1]))
        except ValueError:
            continue
        if nb >= t:
            return nb, (yr - y if y else None)
    return None, None


def _person_out(p):
    nb, age = next_birthday(p.get("birthday"))
    p["next_birthday"] = nb.isoformat() if nb else None
    p["birthday_in_days"] = (nb - date.today()).days if nb else None
    p["turning"] = age
    p["days_since_contact"] = (date.today() - date.fromisoformat(p["last_contact"][:10])).days if p.get("last_contact") else None
    p["contact_due"] = bool(p.get("contact_every_days")) and (
        p["days_since_contact"] is None or p["days_since_contact"] >= p["contact_every_days"])
    return p


def people(q=None):
    sql, args = "SELECT * FROM people", []
    if q:
        sql += " WHERE name LIKE ? OR relationship LIKE ? OR notes LIKE ? OR family LIKE ?"
        args = [f"%{q}%"] * 4
    return [_person_out(p) for p in db.rows(sql + " ORDER BY name", args)]


def person(pid):
    p = db.row("SELECT * FROM people WHERE id=?", (pid,))
    if not p:
        return None
    p = _person_out(p)
    p["interactions"] = db.rows("SELECT * FROM interactions WHERE person_id=? ORDER BY date DESC, id DESC LIMIT 50", (pid,))
    return p


def find_person(name):
    if not name:
        return None
    n = name.strip()
    p = db.row("SELECT * FROM people WHERE lower(name)=lower(?)", (n,)) or \
        db.row("SELECT * FROM people WHERE lower(name) LIKE lower(?) ORDER BY length(name)", (f"{n}%",)) or \
        db.row("SELECT * FROM people WHERE lower(name) LIKE lower(?) OR lower(relationship)=lower(?) ORDER BY length(name)", (f"%{n}%", n))
    return person(p["id"]) if p else None


def person_save(pid=None, **f):
    f = {k: v for k, v in f.items() if k in PERSON_FIELDS}
    if pid:
        db.update("people", pid, f, PERSON_FIELDS)
    else:
        f["updated_at"] = db.now()
        pid = db.run(f"INSERT INTO people({', '.join(f)}) VALUES ({','.join('?' * len(f))})", tuple(f.values()))
    p = person(pid)
    db.index("person", pid, p["name"], f"{p['relationship']} {p['family']} {p['notes']} {p['email']}")
    return p


def person_delete(pid):
    db.run("DELETE FROM people WHERE id=?", (pid,))
    db.unindex("person", pid)


def log_interaction(pid, note="", d=None):
    d = (d or date.today().isoformat())[:10]
    db.run("INSERT INTO interactions(person_id, date, note) VALUES (?,?,?)", (pid, d, note))
    cur = db.row("SELECT last_contact FROM people WHERE id=?", (pid,))
    if not cur["last_contact"] or cur["last_contact"] < d:
        db.run("UPDATE people SET last_contact=?, updated_at=? WHERE id=?", (d, db.now(), pid))
    return person(pid)


def upcoming_birthdays(days=7):
    return sorted([p for p in people() if p["birthday_in_days"] is not None and p["birthday_in_days"] <= days],
                  key=lambda p: p["birthday_in_days"])


def due_contacts():
    return sorted([p for p in people() if p["contact_due"]], key=lambda p: -(p["days_since_contact"] or 9999))


# ============================== Goals ==============================
# Three active goals at a time. Achieved / let-go goals live on in history.
GOAL_FIELDS = {"title", "why", "area", "target_date", "status", "mentor_plan", "achieved_at", "closing_note"}
MAX_ACTIVE_GOALS = 3


class GoalLimit(ValueError):
    pass


def active_count(exclude=None):
    return db.row("SELECT COUNT(*) n FROM goals WHERE status='active' AND id!=?", (exclude or 0,))["n"]


def _goal_out(g):
    from . import gamify
    ms = db.rows("SELECT * FROM milestones WHERE goal_id=? ORDER BY sort, id", (g["id"],))
    tasks = db.rows("SELECT id, title, completed, due_date, reminder_at, milestone_id, completed_at FROM tasks WHERE goal_id=? "
                    "ORDER BY completed, COALESCE(due_date,'9999'), id", (g["id"],))
    by_ms = {}
    for t in tasks:
        by_ms.setdefault(t["milestone_id"], []).append(t)
    parts = []
    for m in ms:
        m["tasks"] = by_ms.get(m["id"], [])
        m["tasks_done"] = sum(t["completed"] for t in m["tasks"])
        m["progress"] = 100 if m["done"] else (round(100 * m["tasks_done"] / len(m["tasks"])) if m["tasks"] else 0)
        parts.append(m["progress"] / 100)
    g["milestones"] = ms
    g["loose_tasks"] = [t for t in tasks if not t["milestone_id"] or t["milestone_id"] not in {m["id"] for m in ms}]
    g["tasks"] = tasks
    if parts:
        g["progress"] = round(100 * sum(parts) / len(parts))
    elif tasks:
        g["progress"] = round(100 * sum(t["completed"] for t in tasks) / len(tasks))
    else:
        g["progress"] = 100 if g["status"] == "achieved" else 0
    g["done_count"] = sum(m["done"] for m in ms) if ms else sum(t["completed"] for t in tasks)
    g["total_count"] = len(ms) if ms else len(tasks)
    g["next_milestone"] = next((m["title"] for m in ms if not m["done"]), None)
    nxt_task = next((t for t in tasks if not t["completed"]), None)
    g["next_task"] = nxt_task["title"] if nxt_task else None
    g["xp"] = gamify.goal_xp(g["id"])
    g["reflection_streak"] = gamify.reflection_streak(g["id"])
    today_ref = db.row("SELECT id FROM goal_reflections WHERE goal_id=? AND date=?", (g["id"], date.today().isoformat()))
    g["reflected_today"] = bool(today_ref)
    g["reflection_count"] = db.row("SELECT COUNT(*) n FROM goal_reflections WHERE goal_id=?", (g["id"],))["n"]
    g["days_left"] = (date.fromisoformat(g["target_date"][:10]) - date.today()).days if g.get("target_date") else None
    last = db.row("SELECT MAX(completed_at) AS last FROM tasks WHERE goal_id=? AND completed=1", (g["id"],))
    g["last_progress"] = last["last"] if last else None
    return g


def goals(status=None):
    sql, args = "SELECT * FROM goals", []
    if status:
        sql += " WHERE status=?"
        args.append(status)
    sql += " ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'achieved' THEN 1 ELSE 2 END, COALESCE(achieved_at, target_date, '9999') DESC, id"
    return [_goal_out(g) for g in db.rows(sql, args)]


def goal(gid):
    g = db.row("SELECT * FROM goals WHERE id=?", (gid,))
    return _goal_out(g) if g else None


def find_goal(title, active_only=False):
    if not title:
        return None
    cond = " AND status='active'" if active_only else ""
    g = db.row(f"SELECT id FROM goals WHERE lower(title)=lower(?){cond}", (title,)) or \
        db.row(f"SELECT id FROM goals WHERE title LIKE ?{cond} ORDER BY status='active' DESC, id DESC", (f"%{title}%",))
    if not g:
        words = [w for w in re.findall(r"\w+", title.lower()) if len(w) > 3]
        for cand in db.rows("SELECT id, title FROM goals WHERE status='active'"):
            if words and sum(w in cand["title"].lower() for w in words) >= max(1, len(words) // 2):
                g = cand
                break
    if not g and not active_only:
        act = db.rows("SELECT id FROM goals WHERE status='active'")
        if len(act) == 1 and re.search(r"\b(my goal|the goal|it)\b", title.lower()):
            g = act[0]
    return goal(g["id"]) if g else None


def goal_save(gid=None, **f):
    f = {k: v for k, v in f.items() if k in GOAL_FIELDS}
    if not gid or f.get("status") == "active":
        if active_count(exclude=gid) >= MAX_ACTIVE_GOALS and (not gid or db.row("SELECT status FROM goals WHERE id=?", (gid,))["status"] != "active"):
            raise GoalLimit("You already have 3 active goals. Achieve one or let one go to open a slot.")
    if gid:
        db.update("goals", gid, f, GOAL_FIELDS)
    else:
        f.setdefault("status", "active")
        f["updated_at"] = db.now()
        gid = db.run(f"INSERT INTO goals({', '.join(f)}) VALUES ({','.join('?' * len(f))})", tuple(f.values()))
    g = goal(gid)
    db.index("goal", gid, g["title"], f"{g['why']} {g['area']} {' '.join(m['title'] for m in g['milestones'])}")
    return g


def goal_achieve(gid, note=""):
    from . import gamify
    g = goal_save(gid, status="achieved", achieved_at=db.now(), closing_note=note or "")
    g["reward"] = gamify.award("goal", gid, gid, g["title"])
    return g


def goal_let_go(gid, note=""):
    return goal_save(gid, status="let_go", achieved_at=db.now(), closing_note=note or "")


def goal_reactivate(gid):
    return goal_save(gid, status="active", achieved_at=None)


def goal_delete(gid):
    db.run("UPDATE tasks SET goal_id=NULL, milestone_id=NULL WHERE goal_id=?", (gid,))
    db.run("DELETE FROM goals WHERE id=?", (gid,))
    db.unindex("goal", gid)


def milestone_add(gid, title, due_date=None):
    db.run("INSERT INTO milestones(goal_id, title, due_date, sort) VALUES (?,?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM milestones WHERE goal_id=?))",
           (gid, title, due_date, gid))
    return goal_save(gid)


def milestone_set_done(mid, done=True):
    from . import gamify
    m = db.row("SELECT * FROM milestones WHERE id=?", (mid,))
    if not m:
        return None, None
    db.run("UPDATE milestones SET done=?, done_at=? WHERE id=?", (1 if done else 0, db.now() if done else None, mid))
    reward = gamify.award("milestone", mid, m["goal_id"], m["title"]) if done else None
    return goal_save(m["goal_id"]), reward


def milestone_task_add(mid, title, due_date=None, reminder_at=None):
    from . import services as S
    m = db.row("SELECT * FROM milestones WHERE id=?", (mid,))
    t = S.create_task(title, None, goal_id=m["goal_id"], milestone_id=mid, due_date=due_date or (reminder_at or "")[:10] or None,
                      reminder_at=reminder_at, note=f"Milestone: {m['title']}")
    return t


def find_milestone(g, text):
    if not text or not g:
        return None
    t = text.lower()
    exact = next((m for m in g["milestones"] if m["title"].lower() == t), None)
    if exact:
        return exact
    part = next((m for m in g["milestones"] if t in m["title"].lower() or m["title"].lower() in t), None)
    if part:
        return part
    words = [w for w in re.findall(r"\w+", t) if len(w) > 3]
    scored = sorted(((sum(w in m["title"].lower() for w in words), m) for m in g["milestones"]), key=lambda x: -x[0])
    return scored[0][1] if scored and scored[0][0] >= max(1, len(words) // 2) else None


def on_task_completed(task):
    """Called by services when any task is completed: XP, and when a milestone's last task is done,
    ask the user whether the milestone itself is achieved (tasks done ≠ outcome reached)."""
    from . import gamify
    if not task.get("goal_id"):
        return None
    reward = gamify.award("task", task["id"], task["goal_id"], task["title"])
    if task.get("milestone_id"):
        left = db.row("SELECT COUNT(*) n FROM tasks WHERE milestone_id=? AND completed=0", (task["milestone_id"],))["n"]
        m = db.row("SELECT id, title, done FROM milestones WHERE id=?", (task["milestone_id"],))
        if left == 0 and m and not m["done"]:
            reward = reward or {"xp": 0, "kind": "task", "line": "All tasks here are done."}
            reward["milestone_ready"] = {"id": m["id"], "title": m["title"]}
    return reward


# ---------- reflections ----------
def reflections(gid, limit=60):
    return db.rows("SELECT * FROM goal_reflections WHERE goal_id=? ORDER BY date DESC, id DESC LIMIT ?", (gid, limit))


def reflection_save(gid, text, confidence=None, d=None):
    from . import gamify
    d = (d or date.today().isoformat())[:10]
    db.run("""INSERT INTO goal_reflections(goal_id, date, text, confidence) VALUES (?,?,?,?)
              ON CONFLICT(goal_id, date) DO UPDATE SET text=excluded.text, confidence=excluded.confidence, mentor_reply=''""",
           (gid, d, text.strip(), confidence))
    r = db.row("SELECT * FROM goal_reflections WHERE goal_id=? AND date=?", (gid, d))
    db.index("reflection", r["id"], f"Goal reflection {d}", text)
    reward = gamify.award("reflection", f"{gid}:{d}", gid, text[:80])
    return r, reward


# ============================== Renewals ==============================
RENEWAL_FIELDS = {"title", "category", "amount", "currency", "due_date", "cycle", "remind_days", "notes", "doc_id", "status"}
RENEWAL_CATEGORIES = ["subscription", "bill", "insurance", "document", "membership", "tax", "other"]


def _ren_out(r):
    r["days_left"] = (date.fromisoformat(r["due_date"][:10]) - date.today()).days
    return r


def renewals(status="active", days_ahead=None):
    rs = [_ren_out(r) for r in db.rows("SELECT * FROM renewals WHERE status=? ORDER BY due_date", (status,))]
    if days_ahead is not None:
        rs = [r for r in rs if r["days_left"] <= days_ahead]
    return rs


def find_renewal(title):
    r = db.row("SELECT * FROM renewals WHERE status='active' AND lower(title)=lower(?)", (title,)) or \
        db.row("SELECT * FROM renewals WHERE status='active' AND title LIKE ? ORDER BY due_date", (f"%{title}%",))
    return _ren_out(r) if r else None


def renewal_save(rid=None, **f):
    f = {k: v for k, v in f.items() if k in RENEWAL_FIELDS}
    if f.get("amount") in ("", None):
        f.pop("amount", None)
    if rid:
        db.update("renewals", rid, f, RENEWAL_FIELDS)
    else:
        f["updated_at"] = db.now()
        rid = db.run(f"INSERT INTO renewals({', '.join(f)}) VALUES ({','.join('?' * len(f))})", tuple(f.values()))
    r = _ren_out(db.row("SELECT * FROM renewals WHERE id=?", (rid,)))
    db.index("renewal", rid, r["title"], f"{r['category']} due {r['due_date']} {r['cycle']} {r['notes']}")
    return r


def advance_date(d: str, cycle: str) -> str:
    x = date.fromisoformat(d[:10])
    months = {"monthly": 1, "quarterly": 3, "half-yearly": 6, "yearly": 12}.get(cycle)
    if cycle == "weekly":
        return (x + timedelta(weeks=1)).isoformat()
    if not months:
        return d
    m = x.month - 1 + months
    y = x.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(x.day, _cal.monthrange(y, m)[1])).isoformat()


def renewal_done(rid, new_due=None):
    """Mark paid/renewed. Recurring items roll forward; one-offs are archived."""
    r = db.row("SELECT * FROM renewals WHERE id=?", (rid,))
    if not r:
        return None
    if new_due:
        return renewal_save(rid, due_date=new_due)
    if r["cycle"]:
        nd = r["due_date"]
        while nd <= date.today().isoformat() or nd == r["due_date"]:
            nd = advance_date(nd, r["cycle"])
        return renewal_save(rid, due_date=nd)
    return renewal_save(rid, status="done")


def renewal_delete(rid):
    db.run("DELETE FROM renewals WHERE id=?", (rid,))
    db.unindex("renewal", rid)


def monthly_spend():
    factor = {"weekly": 52 / 12, "monthly": 1, "quarterly": 1 / 3, "half-yearly": 1 / 6, "yearly": 1 / 12}
    out = {}
    for r in db.rows("SELECT amount, currency, cycle FROM renewals WHERE status='active' AND amount IS NOT NULL AND cycle!=''"):
        cur = r["currency"] or ""
        out[cur] = out.get(cur, 0) + r["amount"] * factor.get(r["cycle"], 0)
    return {k: round(v, 2) for k, v in out.items()}


# ============================== Meeting prep ==============================
def _people_in(text: str, attendees=None):
    text_l = (text or "").lower()
    emails = {a.lower() for a in (attendees or []) if a}
    found = []
    for p in db.rows("SELECT * FROM people"):
        first = p["name"].split()[0].lower()
        if (p["email"] and p["email"].lower() in emails) or re.search(rf"\b{re.escape(p['name'].lower())}\b", text_l) or \
                (len(first) > 2 and re.search(rf"\b{re.escape(first)}\b", text_l)):
            found.append(person(p["id"]))
    return found


def meeting_prep(event: dict):
    from .agents import _hydrate
    text = f"{event.get('title', '')} {event.get('description', '')}"
    ppl = _people_in(text, event.get("attendees"))
    query = re.sub(r"\b(call|meeting|sync|with|catch ?up|1:1|chat|weekly|daily|standup)\b", " ", event.get("title", ""), flags=re.I)
    query = " ".join([query] + [p["name"] for p in ppl])
    related = [x for x in (_hydrate(h) for h in db.search(query, ["task", "idea", "memory", "journal", "doc", "goal"], 8)) if x]
    open_tasks = [t for t in related if t.get("type") == "task" and not t.get("completed")]
    return {
        "event": {k: event.get(k) for k in ("title", "start", "end", "location", "description", "attendees", "link")},
        "people": [{"name": p["name"], "relationship": p["relationship"], "family": p["family"], "notes": p["notes"],
                    "last_contact": p["last_contact"], "last_note": (p["interactions"][0]["note"] if p["interactions"] else ""),
                    "birthday_in_days": p["birthday_in_days"]} for p in ppl],
        "open_tasks": open_tasks,
        "related": [r for r in related if r.get("type") != "task"][:6],
    }


def prep_has_substance(prep):
    return bool(prep["people"] or prep["open_tasks"] or prep["related"] or prep["event"].get("description"))


def talking_points(prep) -> str:
    from . import llm
    from .agents import skill
    try:
        return llm.complete([{"role": "system", "content": skill("prep")},
                             {"role": "user", "content": json.dumps(prep, ensure_ascii=False, default=str)}],
                            max_tokens=260, timeout=120).strip()
    except Exception:
        return ""
