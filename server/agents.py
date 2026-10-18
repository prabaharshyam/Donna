"""Donna's brain: a router + specialist agents.

Each agent = one skill file (server/skills/<agent>.md) + a small, focused tool set.
Small local models choose tools far more reliably from 5 options than from 25, so the
router picks the specialist first, then only that agent's tools are offered.
"""
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from . import calendar_svc as cal
from . import db, docs as D, life as L, llm, secure, services as S
from . import timeparse as TP
from . import subs as SUBS

SKILLS_DIR = Path(__file__).parent / "skills"
AGENTS = ["tasks", "calendar", "journal", "ideas", "memory", "people", "goals", "subscriptions", "renewals", "briefing", "general"]


def skill(name):
    p = SKILLS_DIR / f"{name}.md"
    return p.read_text().strip() if p.exists() else ""


# ============================== Tool implementations ==============================
def _p(name):
    p = S.find_project(name, create=True) if name else None
    return p["id"] if p else None


def _brief_task(t):
    out = {"id": t["id"], "title": t["title"]}
    for k in ("due_date", "reminder_at", "repeat", "project_name"):
        if t.get(k):
            out[k] = t[k]
    # Pre-written wording so the model never has to describe dates/times itself.
    if t.get("due_date"):
        out["due_say"] = TP.human(t["due_date"])
    if t.get("reminder_at"):
        out["reminder_say"] = TP.human(t["reminder_at"])
    if t.get("important"):
        out["important"] = True
    if t.get("completed"):
        out["done"] = True
    if t.get("steps"):
        out["steps"] = [s["title"] + (" ✓" if s["done"] else "") for s in t["steps"]]
    return out


import threading as _threading
_turn = _threading.local()  # the user's message for the current turn (used to sanity-check tool args)


def _resolve_task(args):
    """Title first, id second: a hallucinated id must never hit the wrong task."""
    title = (args.get("title") or args.get("query") or "").strip()
    if title:
        t = db.row("SELECT * FROM tasks WHERE completed=0 AND lower(title)=lower(?) ORDER BY id DESC", (title,)) or \
            db.row("SELECT * FROM tasks WHERE completed=0 AND title LIKE ? ORDER BY id DESC", (f"%{title}%",))
        if t:
            return t
        words = [w for w in re.findall(r"\w+", title.lower()) if len(w) > 2]
        best, score = None, 0
        for c in db.rows("SELECT * FROM tasks WHERE completed=0 ORDER BY id DESC LIMIT 200"):
            s = sum(w in c["title"].lower() for w in words)
            if s > score:
                best, score = c, s
        if best and score >= max(1, (len(words) + 1) // 2):
            return best
        if args.get("task_id"):
            t = S.get_task(int(args["task_id"]))
            if t and any(w in t["title"].lower() for w in words):
                return t
        return None
    if args.get("task_id"):
        return S.get_task(int(args["task_id"]))
    return None


def _recent_tasks():
    return [{"id": r["id"], "title": r["title"]} for r in
            db.rows("SELECT id, title FROM tasks WHERE completed=0 ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 6")]


def t_list_tasks(view="myday", project=None):
    pid = None
    if project:
        p = S.find_project(project)
        if not p:
            return {"error": f"No list called '{project}'", "lists": [x["name"] for x in S.projects()]}
        pid = p["id"]
    tasks = S.list_tasks(view if view != "all" or not pid else "all", pid, include_completed=(view == "completed"))
    return {"view": view, "count": len(tasks), "tasks": [_brief_task(t) for t in tasks[:40]]}


def t_add_task(title, project=None, due_date=None, reminder_at=None, important=False, my_day=False,
               repeat=None, note=None, steps=None, goal=None):
    if reminder_at and not due_date:
        due_date = reminder_at[:10]
    # A repeat of a task created minutes ago is almost always a correction, not a new task.
    recent = db.row("""SELECT id FROM tasks WHERE completed=0 AND lower(title)=lower(?)
                       AND created_at >= datetime('now','localtime','-30 minutes') ORDER BY id DESC""", (title.strip(),))
    if recent:
        upd = {k: v for k, v in (("due_date", due_date), ("reminder_at", reminder_at), ("note", note)) if v}
        t = S.update_task(recent["id"], upd) if upd else S.get_task(recent["id"])
        return {"updated_existing_task": _brief_task(t), "note": "An identical task already existed, so it was updated instead of duplicated."}
    said = getattr(_turn, "text", None)
    if said is not None:  # star / My Day only when the user actually asked for it
        important = bool(re.search(r"\b(important|urgent|priority|asap|critical|star)\b|!", said, re.I))
        my_day = my_day and bool(re.search(r"\b(my day|today|focus)\b", said, re.I))
    g = L.find_goal(goal) if goal else None
    t = S.create_task(title, _p(project), due_date=due_date, reminder_at=reminder_at,
                      important=1 if important else 0, my_day=S.today() if my_day else None,
                      repeat=repeat if repeat in ("daily", "weekdays", "weekly", "monthly", "yearly") else None,
                      note=note, goal_id=g["id"] if g else None)
    for s in steps or []:
        S.add_step(t["id"], str(s))
    return {"created": _brief_task(S.get_task(t["id"]))}


def t_update_task(task_id=None, title=None, new_title=None, project=None, due_date=None, reminder_at=None,
                  important=None, my_day=None, note=None, repeat=None):
    t = _resolve_task({"task_id": task_id, "title": title})
    if not t:
        return {"error": "Task not found. Pass its current title exactly.", "recent_open_tasks": _recent_tasks()}
    f = {}
    said = getattr(_turn, "text", "") or ""
    if new_title and new_title.strip().lower() != t["title"].lower() and \
            re.search(r"\b(rename|call it|retitle|change the (title|name)|title (it|to)|name it)\b", said, re.I):
        f["title"] = new_title  # only rename when the user actually asked to
    if project:
        f["project_id"] = _p(project)
    for k, v in (("due_date", due_date), ("reminder_at", reminder_at), ("note", note), ("repeat", repeat)):
        if v is not None:
            f[k] = v
    if important is not None:
        f["important"] = 1 if important else 0
    if my_day is not None:
        f["my_day"] = S.today() if my_day else None
    return {"updated": _brief_task(S.update_task(t["id"], f))}


def t_complete_task(task_id=None, title=None):
    t = _resolve_task({"task_id": task_id, "title": title})
    if not t:
        return {"error": "Task not found. Call list_tasks to find the id."}
    done = S.complete_task(t["id"], True)
    out = {"completed": t["title"], "next_occurrence_created": bool(t.get("repeat"))}
    ready = (done.get("reward") or {}).get("milestone_ready")
    if ready:
        out["milestone_ready"] = f"All tasks under milestone '{ready['title']}' are done. Ask the user if the milestone itself is achieved."
    return out


def t_delete_task(task_id=None, title=None):
    t = _resolve_task({"task_id": task_id, "title": title})
    if not t:
        return {"error": "Task not found"}
    S.delete_task(t["id"])
    return {"deleted": t["title"]}


def t_list_projects():
    return {"lists": [{"name": p["name"], "open_tasks": p["open_tasks"], "ideas": p["idea_count"]} for p in S.projects()]}


def t_send_to_phone(message):
    from . import telegram
    if not db.get_setting("telegram_chat_id"):
        return {"error": "Telegram isn't paired yet. The user can pair it in Admin → Phone & Telegram."}
    telegram.send(message)
    return {"sent_to_telegram_now": message}


def _ev(e):
    out = {"id": e["id"], "source": e["source"], "title": e["title"], "start": e["start"], "end": e["end"]}
    if not e.get("all_day"):
        out["when_say"] = TP.human(e["start"]) + " to " + datetime.fromisoformat(e["end"]).strftime("%I:%M %p").lstrip("0")
    if e.get("all_day"):
        out["all_day"] = True
    if e.get("location"):
        out["location"] = e["location"]
    return out


def t_get_events(start_date=None, end_date=None):
    start_date = start_date or S.today()
    end_date = end_date if end_date and end_date[:10] >= start_date[:10] else start_date
    ev = cal.list_events(start_date[:10], end_date[:10])
    return {"from": start_date, "to": end_date, "count": len(ev), "events": [_ev(e) for e in ev],
            "google_connected": cal.google_connected()}


def t_create_event(title, start, end=None, location="", description="", all_day=False):
    start = start.replace(" ", "T")[:16]
    if end:
        end = end.replace(" ", "T")[:16]
    elif re.search(r"doctor|dentist|dr\.|clinic|hospital|salon|haircut|appointment|lunch|dinner|breakfast", title, re.I):
        end = (datetime.fromisoformat(start) + timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M")
    clashes = [e["title"] for e in cal.list_events(start[:10], start[:10])
               if not e.get("all_day") and e["start"] < (end or start) and e["end"] > start]
    e = cal.create_event(title, start, end, location, description, all_day)
    out = {"created": _ev({**e, "all_day": all_day}), "overlaps_with": clashes,
           "email_reminder_minutes_before": int(db.get_setting("event_reminder_min", 15))}
    if e.get("warning"):
        out["warning_tell_user"] = e["warning"]
    return out


def t_delete_event(event_id, source="local"):
    cal.delete_event(source, str(event_id))
    return {"deleted": event_id}


def t_find_free_time(date=None, duration_minutes=30):
    d = (date or S.today())[:10]
    return {"date": d, "duration_minutes": duration_minutes, "free_slots": cal.free_slots(d, int(duration_minutes))}


def t_write_journal(text, date=None, mood=None, title=None):
    d = (date or S.today())[:10]
    j = S.journal_save(d, body=text, mood=mood, title=title, append=True)
    return {"saved_to": d, "entry_length_words": len(j["body"].split()), "mood": j["mood"]}


def t_read_journal(date=None, start_date=None, end_date=None):
    if start_date:
        rows = db.rows("SELECT date, title, mood, body FROM journal WHERE date BETWEEN ? AND ? ORDER BY date",
                       (start_date[:10], (end_date or S.today())[:10]))
    else:
        rows = db.rows("SELECT date, title, mood, body FROM journal WHERE date=?", ((date or S.today())[:10],))
    for r in rows:
        r["body"] = r["body"][:1500]
    return {"entries": rows} if rows else {"entries": [], "note": "No journal entries for that period"}


def t_search_journal(query):
    hits = db.search(query, ["journal"], 6)
    out = []
    for h in hits:
        j = db.row("SELECT date, mood, body FROM journal WHERE id=?", (h["ref_id"],))
        if j:
            out.append({"date": j["date"], "mood": j["mood"], "excerpt": h["snip"]})
    return {"matches": out}


def t_add_idea(title, body="", project=None, tags=""):
    i = S.idea_save(title=title, body=body, project_id=_p(project), tags=tags)
    return {"saved_idea": {"id": i["id"], "title": i["title"], "project": project or "Unsorted"}}


def t_list_ideas(project=None, query=None):
    pid = None
    if project:
        p = S.find_project(project)
        pid = p["id"] if p else None
    items = S.ideas(pid, query)
    return {"count": len(items), "ideas": [{"id": i["id"], "title": i["title"], "body": i["body"][:300],
                                            "project": i["project_name"]} for i in items[:25]]}


def t_remember(title, content, category="general"):
    if category not in S.MEMORY_CATEGORIES:
        category = "general"
    existing = db.row("SELECT id FROM memories WHERE lower(title)=lower(?)", (title,))
    m = S.memory_save(existing["id"] if existing else None, category=category, title=title, content=content)
    return {"remembered": {"title": m["title"], "category": m["category"], "updated_existing": bool(existing)}}


def _hydrate(h):
    k, rid = h["kind"], h["ref_id"]
    if k == "memory":
        m = db.row("SELECT category, title, content FROM memories WHERE id=?", (rid,))
        return m and {"type": "memory", **m}
    if k == "journal":
        j = db.row("SELECT date FROM journal WHERE id=?", (rid,))
        return j and {"type": "journal", "date": j["date"], "excerpt": h["snip"]}
    if k == "idea":
        i = db.row("SELECT title, body FROM ideas WHERE id=?", (rid,))
        return i and {"type": "idea", "title": i["title"], "body": i["body"][:400]}
    if k == "task":
        t = db.row("SELECT title, due_date, completed FROM tasks WHERE id=?", (rid,))
        return t and {"type": "task", **t}
    if k == "event":
        e = db.row("SELECT title, start FROM events WHERE id=?", (rid,))
        return e and {"type": "event", **e}
    if k == "vault":
        v = db.row("SELECT id, category, title, hint FROM vault WHERE id=?", (rid,))
        return v and {"type": "vault_item", "title": v["title"], "category": v["category"], "hint": v["hint"],
                      "note": "secret; use vault_lookup to show it securely"}
    if k == "person":
        p = db.row("SELECT name, relationship, birthday, family, notes, last_contact FROM people WHERE id=?", (rid,))
        return p and {"type": "person", **{x: y for x, y in p.items() if y}}
    if k == "goal":
        g = db.row("SELECT title, why, target_date, status FROM goals WHERE id=?", (rid,))
        return g and {"type": "goal", **{x: y for x, y in g.items() if y}}
    if k == "renewal":
        r = db.row("SELECT title, category, due_date, amount, currency, cycle FROM renewals WHERE id=?", (rid,))
        return r and {"type": "renewal", **{x: y for x, y in r.items() if y not in (None, "")}}
    if k == "subscription":
        s = SUBS.get(rid)
        return s and {"type": "subscription", "name": s["name"], "status": s["status"],
                      "price": f"{SUBS.fmt_money(s['amount'], s['currency'])}/{s['cycle']}" if s["amount"] is not None else "unknown",
                      "next": s["next_billing_date"], "trial_end": s["trial_end_date"]}
    if k == "doc":
        c = db.row("SELECT c.text, d.title FROM doc_chunks c JOIN documents d ON d.id=c.doc_id WHERE c.id=?", (rid,))
        return c and {"type": "document", "title": c["title"], "excerpt": c["text"][:600]}
    return None


def t_recall(query):
    hits = [x for x in (_hydrate(h) for h in db.search(query, limit=8)) if x]
    return {"results": hits} if hits else {"results": [], "note": "Nothing stored about that yet."}


def t_vault_lookup(query, _ctx=None):
    hits = db.search(query, ["vault"], 5)
    if not hits:
        words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
        cand = db.rows("SELECT id, category, title, hint FROM vault")
        hits = [{"ref_id": v["id"]} for v in cand if any(w in (v["title"] + " " + v["category"]).lower() for w in words)][:5]
    items = [db.row("SELECT id, category, title, hint FROM vault WHERE id=?", (h["ref_id"],)) for h in hits]
    items = [i for i in items if i]
    if not items:
        return {"found": 0, "note": "No vault item matches. The user can add it in the Vault page."}
    if _ctx is not None:
        _ctx.setdefault("vault_cards", []).extend(i["id"] for i in items)
    return {"found": len(items), "items": [{"title": i["title"], "category": i["category"], "hint": i["hint"]} for i in items],
            "vault_locked": not secure.vault_unlocked(),
            "display": "Full details are shown to the user in a secure card below your reply. Never write secret values yourself."}


def t_get_briefing(date=None):
    d = (date or S.today())[:10]
    try:
        events = [_ev(e) for e in cal.list_events(d, d)]
    except Exception as e:
        events = [{"error": str(e)}]
    due = [_brief_task(t) for t in S.list_tasks("all", include_completed=False) if t["due_date"] == d]
    overdue = [_brief_task(t) for t in S.list_tasks("overdue")] if d == S.today() else []
    myday = [_brief_task(t) for t in S.list_tasks("myday", include_completed=False) if t["due_date"] != d and t["due_date"] is None]
    important = [_brief_task(t) for t in S.list_tasks("important", include_completed=False)][:5]
    j = S.journal_get(d)
    out = {"date": d, "events": events, "tasks_due": due, "overdue": overdue, "my_day": myday,
           "important": important, "journaled": bool(j and j["body"]), "journal_streak_days": S.journal_streak()}
    if d == S.today():
        out["birthdays"] = [{"name": p["name"], "in_days": p["birthday_in_days"], **({"turning": p["turning"]} if p["turning"] else {"age": "unknown, do not state an age"})}
                            for p in L.upcoming_birthdays(7)]
        out["renewals_due"] = [{"title": r["title"], "due_date": r["due_date"], "days_left": r["days_left"],
                                "amount": r["amount"], "currency": r["currency"]} for r in L.renewals(days_ahead=7)]
        out["reach_out"] = [{"name": p["name"], "days_since_contact": p["days_since_contact"]} for p in L.due_contacts()[:3]]
        out["inbox_commitments_pending"] = db.row("SELECT COUNT(*) n FROM inbox_items WHERE status='pending'")["n"]
        a = SUBS.analytics()
        out["subscriptions_due"] = [{"name": u["name"], "charges": SUBS.fmt_money(u["amount"], u["currency"]), "in_days": u["days"]}
                                    for u in a["upcoming"] if u["days"] <= 3 and u["status"] == "active"]
        out["trials_ending"] = [{"name": t["name"], "cancel_by": t["cancel_by"], "in_days": t["days"]} for t in a["trials"] if t["days"] is not None and t["days"] <= 7]
    return out


# ---------- people ----------
def _person_brief(p):
    keys = ("name", "relationship", "birthday", "next_birthday", "turning", "email", "phone", "family", "notes",
            "last_contact", "days_since_contact", "contact_every_days")
    out = {k: p[k] for k in keys if p.get(k) not in (None, "", 0)}
    if p.get("interactions"):
        out["recent_interactions"] = [f"{i['date']}: {i['note']}" for i in p["interactions"][:5]]
    return out


def t_find_person(name):
    p = L.find_person(name)
    if not p:
        matches = L.people(name)
        if matches:
            return {"matches": [_person_brief(L.person(m["id"])) for m in matches[:3]]}
        return {"found": False, "note": f"No one called {name} yet. Use save_person to add them."}
    return {"person": _person_brief(p)}


def t_save_person(name, relationship=None, birthday=None, email=None, phone=None, family=None, notes=None,
                  contact_every_days=None):
    p = L.find_person(name)
    f = {k: v for k, v in dict(relationship=relationship, birthday=birthday, email=email, phone=phone,
                                 contact_every_days=contact_every_days).items() if v not in (None, "")}
    if family:
        f["family"] = (p["family"] + "; " + family).strip("; ") if p and p["family"] and family not in p["family"] else family
    if notes:
        f["notes"] = (p["notes"] + "\n" + notes).strip() if p and p["notes"] and notes not in p["notes"] else notes
    if p:
        p = L.person_save(p["id"], **f)
        return {"updated": _person_brief(p)}
    return {"added": _person_brief(L.person_save(name=name.strip(), **f))}


def t_log_interaction(name, note="", date=None):
    p = L.find_person(name)
    if not p:
        p = L.person_save(name=name.strip())
    p = L.log_interaction(p["id"], note, date)
    return {"logged_for": p["name"], "date": (date or S.today())[:10]}


def t_people_to_contact():
    return {"overdue_to_reach_out": [{"name": p["name"], "relationship": p["relationship"],
                                      "days_since_contact": p["days_since_contact"], "every_days": p["contact_every_days"]} for p in L.due_contacts()],
            "birthdays_next_30_days": [{"name": p["name"], "date": p["next_birthday"], "in_days": p["birthday_in_days"],
                                        "turning": p["turning"]} for p in L.upcoming_birthdays(30)]}


# ---------- goals ----------
def _goal_brief(g):
    out = {"title": g["title"], "status": g["status"], "progress_percent": g["progress"],
           "milestones": [{"title": m["title"], "done": bool(m["done"]), "tasks": [t["title"] + (" ✓" if t["completed"] else "") for t in m["tasks"]][:6]}
                          for m in g["milestones"]],
           "reflection_streak_days": g["reflection_streak"], "reflected_today": g["reflected_today"]}
    if g.get("why"):
        out["why"] = g["why"]
    if g.get("target_date"):
        out["target_say"] = TP.human(g["target_date"])
        out["days_left"] = g["days_left"]
    if g["loose_tasks"]:
        out["other_tasks"] = [t["title"] + (" ✓" if t["completed"] else "") for t in g["loose_tasks"]][:6]
    return out


def t_list_goals(status="active"):
    status = {"done": "achieved", "paused": "active"}.get(status, status)
    gs = L.goals(status if status != "all" else None)
    return {"goals": [_goal_brief(g) for g in gs], "active_slots_used": L.active_count(), "max_active": L.MAX_ACTIVE_GOALS}


def _said_by_user(text_field, about=None):
    """True only if the words come from the user's message, and (when `about` is given) from the
    part of the message that talks about that goal, so one goal's reason isn't copied to another."""
    said = (getattr(_turn, "text", "") or "").lower()
    words = re.findall(r"[a-z0-9']{3,}", (text_field or "").lower())
    if not words:
        return False
    hit = lambda seg: sum(w in seg for w in words) / len(words) >= 0.6
    if about:
        keys = [w for w in re.findall(r"[a-z]{4,}", about.lower()) if w not in ("goal", "goals", "this", "year", "with", "become")]
        segs = [x for x in re.split(r"[,;.]|\band\b|\balso\b", said) if x.strip()]
        mine = [x for x in segs if any(k in x for k in keys)]
        if mine:
            # the reason must sit in this goal's clause (or the clause right after it)
            idx = [segs.index(x) for x in mine]
            near = " ".join(segs[i] + " " + (segs[i + 1] if i + 1 < len(segs) and not any(k in segs[i + 1] for k in keys) and
                                                not any(w in segs[i + 1] for w in ("read", "learn", "run", "save", "build", "lose", "write")) else "")
                            for i in idx)
            return hit(near)
    return hit(said)


def t_save_goal(title, why=None, target_date=None, area=None, milestones=None):
    if why and not _said_by_user(why, about=title):
        why = None  # small models love to invent (or copy) a "why"; only keep the user's own
    if target_date:
        target_date = TP.future_or_rolled(target_date)
    g = L.find_goal(title, active_only=True)
    f = {k: v for k, v in dict(why=why, target_date=target_date, area=area).items() if v}
    try:
        g = L.goal_save(g["id"], **f) if g else L.goal_save(title=title.strip(), **f)
    except L.GoalLimit as e:
        return {"error": str(e), "active_goals": [x["title"] for x in L.goals("active")]}
    existing = {m["title"].lower() for m in g["milestones"]}
    for m in milestones or []:
        if str(m).lower() not in existing:
            g = L.milestone_add(g["id"], str(m))
    return {"goal": _goal_brief(g), "slots_used": f"{L.active_count()}/3"}


def _goal_or_error(goal):
    g = L.find_goal(goal, active_only=True) or L.find_goal(goal)
    if not g:
        return None, {"error": f"No goal matching '{goal}'.", "active_goals": [x["title"] for x in L.goals("active")]}
    return g, None


def t_add_milestone(goal, title, due_date=None):
    g, err = _goal_or_error(goal)
    if err:
        return err
    return {"goal": _goal_brief(L.milestone_add(g["id"], title, due_date))}


def t_add_goal_task(goal, title, milestone=None, due_date=None, reminder_at=None):
    g, err = _goal_or_error(goal)
    if err:
        return err
    m = L.find_milestone(g, milestone) if milestone else next((x for x in g["milestones"] if not x["done"]), None)
    if m:
        t = L.milestone_task_add(m["id"], title.strip(), due_date, reminder_at)
    else:
        t = S.create_task(title.strip(), None, goal_id=g["id"], due_date=due_date or (reminder_at or "")[:10] or None, reminder_at=reminder_at)
    return {"created": _brief_task(S.get_task(t["id"])), "goal": g["title"], "milestone": m["title"] if m else None}


def t_complete_milestone(goal, milestone):
    g, err = _goal_or_error(goal)
    if err:
        return err
    m = L.find_milestone(g, milestone)
    if not m:
        return {"error": "Milestone not found", "milestones": [x["title"] for x in g["milestones"]]}
    g2, reward = L.milestone_set_done(m["id"], True)
    out = {"goal": _goal_brief(g2), "xp_earned": reward["xp"] if reward else 0}
    if g2["milestones"] and all(x["done"] for x in g2["milestones"]):
        out["note"] = "All milestones are done. Ask if they want to mark the goal achieved."
    return out


def t_achieve_goal(goal, note=""):
    g, err = _goal_or_error(goal)
    if err:
        return err
    g = L.goal_achieve(g["id"], note)
    return {"achieved": g["title"], "xp_earned": (g.get("reward") or {}).get("xp", 0),
            "tasks_completed": sum(t["completed"] for t in g["tasks"]), "reflections": g["reflection_count"], "slot_opened": True}


def t_let_go_goal(goal, note=""):
    g, err = _goal_or_error(goal)
    if err:
        return err
    L.goal_let_go(g["id"], note)
    return {"let_go": g["title"], "slot_opened": True, "note": "It stays in history and can be reactivated later."}


def t_reflect_on_goal(goal, text, confidence=None):
    g, err = _goal_or_error(goal)
    if err:
        return err
    from . import mentor
    r = mentor.reflect(g["id"], text, int(confidence) if confidence else None)
    # The dedicated mentor engine writes the reply; it's returned to the user verbatim.
    return {"saved_reflection_for": g["title"], "_final_reply": r["mentor_reply"]}


# ---------- renewals & documents ----------
def t_list_renewals(days_ahead=None):
    rs = L.renewals(days_ahead=int(days_ahead) if days_ahead else None)
    return {"monthly_subscription_spend": L.monthly_spend(),
            "items": [{"title": r["title"], "category": r["category"], "due_date": r["due_date"], "days_left": r["days_left"],
                       "amount": r["amount"], "currency": r["currency"], "cycle": r["cycle"]} for r in rs[:30]]}


def t_add_renewal(title, due_date, category="other", amount=None, currency=None, cycle=None, remind_days=None, notes=None):
    if category == "subscription":  # app/service subscriptions live in the Subscription manager
        return t_add_subscription(title, amount=amount, currency=currency, cycle=cycle or "monthly",
                                  next_billing_date=due_date, notes=notes)
    cat = category if category in L.RENEWAL_CATEGORIES else "other"
    if remind_days is None:
        remind_days = 30 if cat in ("document", "insurance") else 3 if cat in ("subscription", "bill") else 7
    existing = L.find_renewal(title)
    f = dict(title=title.strip(), due_date=due_date[:10], category=cat, amount=amount, currency=currency or "",
             cycle=cycle if cycle in ("weekly", "monthly", "quarterly", "half-yearly", "yearly") else "",
             remind_days=int(remind_days), notes=notes or "")
    r = L.renewal_save(existing["id"] if existing else None, **f)
    return {"saved": {k: r[k] for k in ("title", "due_date", "days_left", "category", "cycle", "remind_days")}, "updated_existing": bool(existing)}


def t_mark_renewed(title, new_due_date=None):
    r = L.find_renewal(title)
    if not r:
        return {"error": f"No renewal matching '{title}'"}
    r = L.renewal_done(r["id"], new_due_date)
    return {"title": r["title"], "status": r["status"], "next_due": r["due_date"] if r["status"] == "active" else None}


def t_search_documents(query):
    hits = D.search(query, 4)
    return {"results": hits} if hits else {"results": [], "note": "No uploaded document mentions that."}


# ---------- subscriptions ----------
def _sub_brief(s):
    out = {"name": s["name"], "status": s["status"], "category": s["category"]}
    if s["plan"]:
        out["plan"] = s["plan"]
    out["price"] = f"{SUBS.fmt_money(s['amount'], s['currency'])} per {SUBS.PER.get(s['cycle'], 'month')}" if s["amount"] is not None else "amount not set"
    if s["monthly_home"] is not None and s["currency"] != SUBS.home_currency():
        out["approx_monthly_home"] = SUBS.fmt_money(s["monthly_home"])
    if s["status"] == "trial" and s["trial_end_date"]:
        out["trial_ends_say"] = TP.human(s["trial_end_date"])
        out["cancel_by_say"] = TP.human(s["cancel_by"])
    elif s["next_billing_date"] and s["status"] in ("active", "cancelling"):
        out["next_charge_say" if s["status"] == "active" else "access_until_say"] = TP.human(s["next_billing_date"] if s["status"] == "active" else (s["cancel_effective_date"] or s["next_billing_date"]))
    for k in ("payment_method", "billed_via", "shared_with", "value_rating"):
        if s.get(k):
            out[k] = s[k]
    if s.get("unused_days") is not None:
        out["last_used_days_ago"] = s["unused_days"]
    pending = [k for k, v in s["checklist"].items() if not v]
    if s["status"] in ("cancelling", "cancelled") and pending:
        out["cancellation_steps_left"] = pending
    return out


def t_list_subscriptions(status="live"):
    status = status if status in ("live", "all", *SUBS.STATUSES) else "live"
    items = SUBS.subs(status)
    a = SUBS.analytics()
    return {"subscriptions": [_sub_brief(s) for s in items[:40]], "monthly_total": SUBS.fmt_money(a["monthly"]),
            "yearly_total": SUBS.fmt_money(a["yearly"])}


def t_add_subscription(name, amount=None, currency=None, cycle="monthly", next_billing_date=None, trial_end_date=None,
                       category=None, plan=None, payment_method=None, billed_via=None, shared_with=None,
                       my_share_percent=None, notes=None, start_date=None):
    existing = SUBS.find(name)
    f = {k: v for k, v in dict(amount=amount, currency=currency, cycle=cycle, next_billing_date=next_billing_date,
                                trial_end_date=trial_end_date, category=category, plan=plan, payment_method=payment_method,
                                billed_via=billed_via, shared_with=shared_with, my_share=my_share_percent, notes=notes,
                                start_date=start_date).items() if v not in (None, "")}
    if trial_end_date:
        f.update(status="trial", next_billing_date=trial_end_date)
    if existing and existing["status"] not in ("cancelled", "expired"):
        s = SUBS.save(existing["id"], **f)
        return {"updated_existing": _sub_brief(s)}
    s = SUBS.save(name=name.strip(), **f)
    out = {"added": _sub_brief(s)}
    if s["status"] == "trial":
        out["reminders"] = "Donna will remind the user 3 days before, 1 day before and on the morning of the cancel-by date."
    return out


def t_update_subscription(name, new_name=None, amount=None, currency=None, cycle=None, next_billing_date=None,
                          trial_end_date=None, category=None, plan=None, payment_method=None, billed_via=None,
                          shared_with=None, my_share_percent=None, value_rating=None, last_used=None, notes=None, status=None):
    s = SUBS.find(name)
    if not s:
        return {"error": f"No subscription called '{name}'.", "known": [x["name"] for x in SUBS.subs("all")][:30]}
    f = {k: v for k, v in dict(name=new_name, amount=amount, currency=currency, cycle=cycle, next_billing_date=next_billing_date,
                                trial_end_date=trial_end_date, category=category, plan=plan, payment_method=payment_method,
                                billed_via=billed_via, shared_with=shared_with, my_share=my_share_percent,
                                value_rating=value_rating, last_used=last_used, notes=notes,
                                status=status if status in ("active", "paused") else None).items() if v not in (None, "")}
    if amount not in (None, "") and s["amount"] is not None and float(amount) != s["amount"]:
        f["previous_amount"] = s["amount"]
    return {"updated": _sub_brief(SUBS.save(s["id"], **f))}


def t_cancel_subscription(name, effective_date=None, reason=None, already_cancelled_in_app=False):
    s = SUBS.find(name)
    if not s:
        return {"error": f"No subscription called '{name}'."}
    s = SUBS.cancel(s["id"], effective_date, reason or "")
    if already_cancelled_in_app:
        ck = s["checklist"]
        ck["service"] = True
        s = SUBS.save(s["id"], cancel_checklist=ck)
    out = {"cancelled": _sub_brief(s), "steps_left": [k for k, v in s["checklist"].items() if not v],
           "step_meanings": {"service": "cancel inside the app/website (or App Store/Play Store)",
                             "mandate": "revoke the UPI AutoPay / card e-mandate so no further debit happens",
                             "confirmation": "keep the cancellation confirmation email or screenshot"}}
    if s.get("manage_url"):
        out["manage_page"] = s["manage_url"]
    return out


def t_record_subscription_charge(name, amount=None, date=None, currency=None):
    s = SUBS.find(name)
    if not s:
        return {"error": f"No subscription called '{name}'. Add it first with add_subscription."}
    r = SUBS.record_charge(s["id"], amount, date, source="manual", currency=currency)
    s = SUBS.get(s["id"])
    out = {"logged": not r["duplicate"], "subscription": _sub_brief(s)}
    if r["price_change"]:
        out["price_change"] = f"{SUBS.fmt_money(r['price_change'][0], s['currency'])} → {SUBS.fmt_money(r['price_change'][1], s['currency'])}"
    return out


def t_subscription_spend():
    return {"facts": SUBS.facts(), "rule": "Use only these facts and money strings."}


def t_subscription_suggestions():
    from . import subs_email
    items = subs_email.suggestions()
    return {"found_in_email_waiting_for_review": [{"service": i["service"], "event": i["event"],
                                                   "amount": SUBS.fmt_money(i["amount"], i["currency"]) if i["amount"] else None,
                                                   "date": i["date"], "trial_end": i["trial_end"]} for i in items[:20]],
            "note": "The user accepts or dismisses these on the Subscriptions page."}


# ---------- review / inbox ----------
def t_week_review():
    from . import review
    return {"facts": review.facts(review.stats()), "rule": "Use only these facts. Where a fact says none/0/unknown, say so plainly."}


def t_inbox_commitments():
    items = db.rows("SELECT title, due_date, sender, subject FROM inbox_items WHERE status='pending' ORDER BY COALESCE(due_date,'9999') LIMIT 15")
    st = db.get_setting("inbox_status", {}) or {}
    return {"pending_suggestions": items, "last_scan": st.get("last_scan"),
            "note": "The user accepts or dismisses these on the Inbox page."}


# ============================== Tool schemas ==============================
def fn(name, desc, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props or {}, "required": required or []}}}


STR = {"type": "string"}
DATE = {"type": "string", "description": "YYYY-MM-DD"}
DT = {"type": "string", "description": "Local time YYYY-MM-DDTHH:MM"}
BOOL = {"type": "boolean"}
REPEAT = {"type": "string", "enum": ["daily", "weekdays", "weekly", "monthly", "yearly"]}

TOOLS = {
    "list_tasks": (t_list_tasks, fn("list_tasks", "List the user's to-dos.", {
        "view": {"type": "string", "enum": ["myday", "overdue", "upcoming", "important", "all", "completed"],
                 "description": "myday = today's focus + due today/overdue"},
        "project": {"type": "string", "description": "List/project name to filter by"}})),
    "add_task": (t_add_task, fn("add_task", "Create a to-do. Set reminder_at to email/notify the user at that time.", {
        "title": {"type": "string", "description": "Short imperative title, e.g. 'Call the bank'"},
        "project": {"type": "string", "description": "List/project name; created if missing"},
        "due_date": DATE, "reminder_at": DT,
        "important": {"type": "boolean", "description": "Only true if the user says important / urgent / priority"},
        "my_day": {"type": "boolean", "description": "Add to today's My Day"},
        "repeat": REPEAT, "note": STR,
        "steps": {"type": "array", "items": {"type": "string"}, "description": "Sub-steps"},
        "goal": {"type": "string", "description": "Goal this task moves forward, if the user names one"}}, ["title"])),
    "update_task": (t_update_task, fn("update_task", "Change an existing task (time, date, list, star…). Identify it by its CURRENT title.", {
        "title": {"type": "string", "description": "The task's current title, exactly as in the System record or list_tasks"},
        "task_id": {"type": "integer", "description": "Optional; only if shown in the System record"},
        "new_title": {"type": "string", "description": "Only if the user explicitly asks to rename it"}, "project": STR, "due_date": DATE, "reminder_at": DT, "important": BOOL, "my_day": BOOL,
        "note": STR, "repeat": REPEAT})),
    "complete_task": (t_complete_task, fn("complete_task", "Mark a task done. Identify by task_id or title.", {
        "task_id": {"type": "integer"}, "title": STR})),
    "delete_task": (t_delete_task, fn("delete_task", "Permanently delete a task (only after the user confirms).", {
        "task_id": {"type": "integer"}, "title": STR})),
    "list_projects": (t_list_projects, fn("list_projects", "List all lists/projects with counts.")),
    "get_events": (t_get_events, fn("get_events", "Get calendar events/appointments in a date range.", {
        "start_date": DATE, "end_date": {"type": "string", "description": "YYYY-MM-DD inclusive; omit for single day"}},
        ["start_date"])),
    "create_event": (t_create_event, fn("create_event", "Add an appointment or block time on the calendar.", {
        "title": STR, "start": DT, "end": {"type": "string", "description": "YYYY-MM-DDTHH:MM; default 30 min after start"},
        "location": STR, "description": STR, "all_day": BOOL}, ["title", "start"])),
    "delete_event": (t_delete_event, fn("delete_event", "Cancel a calendar event (only after the user confirms).", {
        "event_id": STR, "source": {"type": "string", "enum": ["google", "local"]}}, ["event_id", "source"])),
    "find_free_time": (t_find_free_time, fn("find_free_time", "Find open slots within working hours on a date.", {
        "date": DATE, "duration_minutes": {"type": "integer"}}, ["date"])),
    "write_journal": (t_write_journal, fn("write_journal", "Append text to the journal entry for a date.", {
        "text": {"type": "string", "description": "The entry, in the user's own voice (first person)"},
        "date": DATE, "mood": {"type": "string", "enum": ["great", "good", "okay", "low", "rough"]},
        "title": STR}, ["text"])),
    "read_journal": (t_read_journal, fn("read_journal", "Read journal entries for one date or a range.", {
        "date": DATE, "start_date": DATE, "end_date": DATE})),
    "search_journal": (t_search_journal, fn("search_journal", "Full-text search across all journal entries.", {
        "query": STR}, ["query"])),
    "add_idea": (t_add_idea, fn("add_idea", "Capture an idea into the Ideas board.", {
        "title": {"type": "string", "description": "Crisp headline for the idea"},
        "body": {"type": "string", "description": "The idea in the user's words, lightly cleaned up"},
        "project": STR, "tags": {"type": "string", "description": "comma separated"}}, ["title"])),
    "list_ideas": (t_list_ideas, fn("list_ideas", "List or search saved ideas.", {"project": STR, "query": STR})),
    "remember": (t_remember, fn("remember", "Store a fact about the user (not a password or card).", {
        "category": {"type": "string", "enum": S.MEMORY_CATEGORIES},
        "title": {"type": "string", "description": "What the fact is about, e.g. 'Shirt size'"},
        "content": {"type": "string", "description": "The fact itself"}}, ["title", "content"])),
    "recall": (t_recall, fn("recall", "Search everything the user has told Donna: memories, journal, ideas, tasks.", {
        "query": STR}, ["query"])),
    "vault_lookup": (t_vault_lookup, fn("vault_lookup", "Find a password, card, ID or account in the encrypted vault and show it securely.", {
        "query": STR}, ["query"])),
    "get_briefing": (t_get_briefing, fn("get_briefing", "Everything for a day: events, due/overdue tasks, My Day, birthdays, renewals, people to reach out to.", {
        "date": DATE})),
    # people
    "find_person": (t_find_person, fn("find_person", "Look up someone the user knows: relationship, birthday, family, notes, last contact.", {
        "name": {"type": "string", "description": "Name or relationship, e.g. 'Priya' or 'Mom'"}}, ["name"])),
    "save_person": (t_save_person, fn("save_person", "Add a person or update details about them. Notes/family are appended, not replaced.", {
        "name": STR, "relationship": {"type": "string", "description": "e.g. mother, friend, manager, client"},
        "birthday": {"type": "string", "description": "YYYY-MM-DD, or MM-DD if year unknown"},
        "email": STR, "phone": STR, "family": {"type": "string", "description": "Partner, kids' names, pets"},
        "notes": {"type": "string", "description": "Anything worth remembering about them"},
        "contact_every_days": {"type": "integer", "description": "Nudge the user if they haven't been in touch for this many days"}}, ["name"])),
    "log_interaction": (t_log_interaction, fn("log_interaction", "Record that the user talked to / met someone, with what was discussed.", {
        "name": STR, "note": {"type": "string", "description": "What you talked about, in a sentence"}, "date": DATE}, ["name"])),
    "people_to_contact": (t_people_to_contact, fn("people_to_contact", "Who the user is overdue to reach out to, and upcoming birthdays.")),
    # goals
    "list_goals": (t_list_goals, fn("list_goals", "List goals (max 3 active) with progress, milestones and their tasks.", {
        "status": {"type": "string", "enum": ["active", "achieved", "let_go", "all"]}})),
    "save_goal": (t_save_goal, fn("save_goal", "Create a goal (only 3 can be active) or update one, with optional milestones.", {
        "title": {"type": "string", "description": "Outcome-focused, e.g. 'Run a half marathon'"},
        "why": {"type": "string", "description": "ONLY a reason the user explicitly stated. Omit if they didn't say why."}, "target_date": DATE,
        "area": {"type": "string", "description": "health, career, money, relationships, learning, home, fun"},
        "milestones": {"type": "array", "items": {"type": "string"}, "description": "3-6 verifiable checkpoints"}}, ["title"])),
    "add_milestone": (t_add_milestone, fn("add_milestone", "Add a milestone to a goal.", {
        "goal": STR, "title": STR, "due_date": DATE}, ["goal", "title"])),
    "add_goal_task": (t_add_goal_task, fn("add_goal_task", "Add a small, concrete task under a goal's milestone (defaults to the current milestone).", {
        "goal": STR, "title": {"type": "string", "description": "Starts with a verb; one-sitting sized"},
        "milestone": {"type": "string", "description": "Milestone title; omit for the current one"},
        "due_date": DATE, "reminder_at": DT}, ["goal", "title"])),
    "complete_milestone": (t_complete_milestone, fn("complete_milestone", "Tick off a goal milestone.", {
        "goal": STR, "milestone": STR}, ["goal", "milestone"])),
    "achieve_goal": (t_achieve_goal, fn("achieve_goal", "Mark a goal achieved (moves to history, frees a slot).", {
        "goal": STR, "note": {"type": "string", "description": "Optional closing thought from the user"}}, ["goal"])),
    "let_go_goal": (t_let_go_goal, fn("let_go_goal", "Let go of a goal (moves to history, frees a slot). Confirm first.", {
        "goal": STR, "note": STR}, ["goal"])),
    "reflect_on_goal": (t_reflect_on_goal, fn("reflect_on_goal", "Save the user's daily reflection on a goal, then respond as their mentor.", {
        "goal": STR, "text": {"type": "string", "description": "The reflection in the user's own words"},
        "confidence": {"type": "integer", "description": "1-5 how on-track they feel, only if they expressed it"}}, ["goal", "text"])),
    # renewals & documents
    "list_renewals": (t_list_renewals, fn("list_renewals", "Subscriptions, bills, insurance and document expiries with due dates.", {
        "days_ahead": {"type": "integer", "description": "Only items due within this many days"}})),
    "add_renewal": (t_add_renewal, fn("add_renewal", "Track something that renews, is billed, or expires.", {
        "title": STR, "due_date": {"type": "string", "description": "Next due/expiry date YYYY-MM-DD"},
        "category": {"type": "string", "enum": L.RENEWAL_CATEGORIES}, "amount": {"type": "number"},
        "currency": {"type": "string", "description": "e.g. INR, USD"},
        "cycle": {"type": "string", "enum": ["weekly", "monthly", "quarterly", "half-yearly", "yearly"], "description": "Omit for one-off expiries"},
        "remind_days": {"type": "integer", "description": "Days before to remind"}, "notes": STR}, ["title", "due_date"])),
    "mark_renewed": (t_mark_renewed, fn("mark_renewed", "Mark a renewal/bill as paid or renewed; recurring ones roll to the next date.", {
        "title": STR, "new_due_date": DATE}, ["title"])),
    "search_documents": (t_search_documents, fn("search_documents", "Search the text of the user's uploaded documents (policies, warranties, tickets, contracts, statements).", {
        "query": STR}, ["query"])),
    # review / inbox
    "week_review": (t_week_review, fn("week_review", "Stats for this week: completed, slipped, moods, goals moved, people contacted, ideas.")),
    "inbox_commitments": (t_inbox_commitments, fn("inbox_commitments", "Commitments and requests Donna found in the user's email, awaiting review.")),
    "list_subscriptions": (t_list_subscriptions, fn("list_subscriptions", "The user's subscriptions with price, next charge / trial end and totals.", {
        "status": {"type": "string", "enum": ["live", "all", "trial", "active", "cancelling", "cancelled", "paused"], "description": "live = trials + active + cancelling (default)"}})),
    "add_subscription": (t_add_subscription, fn("add_subscription", "Add a subscription or free trial (updates it if it already exists).", {
        "name": {"type": "string", "description": "Service name, e.g. Netflix, ChatGPT Plus, iCloud+"},
        "amount": {"type": "number", "description": "Price per cycle (after the trial, for trials)"},
        "currency": {"type": "string", "description": "ISO code; INR unless stated"},
        "cycle": {"type": "string", "enum": SUBS.CYCLES}, "next_billing_date": DATE,
        "trial_end_date": {"type": "string", "description": "YYYY-MM-DD when the free trial ends (first charge)"},
        "category": {"type": "string", "enum": SUBS.CATEGORIES}, "plan": STR,
        "payment_method": {"type": "string", "description": "Label only, e.g. 'HDFC credit card' or 'UPI AutoPay (GPay)'"},
        "billed_via": {"type": "string", "description": "direct, App Store, Google Play, Amazon, or a telecom/card bundle"},
        "shared_with": STR, "my_share_percent": {"type": "number"}, "notes": STR, "start_date": DATE}, ["name"])),
    "update_subscription": (t_update_subscription, fn("update_subscription", "Change details of a subscription (price, dates, rating, last used…).", {
        "name": STR, "new_name": STR, "amount": {"type": "number"}, "currency": STR, "cycle": {"type": "string", "enum": SUBS.CYCLES},
        "next_billing_date": DATE, "trial_end_date": DATE, "category": {"type": "string", "enum": SUBS.CATEGORIES}, "plan": STR,
        "payment_method": STR, "billed_via": STR, "shared_with": STR, "my_share_percent": {"type": "number"},
        "value_rating": {"type": "integer", "description": "1-5 how worth it the user finds it"}, "last_used": DATE, "notes": STR,
        "status": {"type": "string", "enum": ["active", "paused"]}}, ["name"])),
    "cancel_subscription": (t_cancel_subscription, fn("cancel_subscription", "Mark a subscription as cancelled/cancelling and get the remaining cancellation steps.", {
        "name": STR, "effective_date": {"type": "string", "description": "YYYY-MM-DD access ends; default = end of the current period"},
        "reason": STR, "already_cancelled_in_app": {"type": "boolean"}}, ["name"])),
    "record_subscription_charge": (t_record_subscription_charge, fn("record_subscription_charge", "Log that a subscription charged the user.", {
        "name": STR, "amount": {"type": "number"}, "date": DATE, "currency": STR}, ["name"])),
    "subscription_spend": (t_subscription_spend, fn("subscription_spend", "Totals, every subscription's cost, trials, unused/low-value items, budget.")),
    "subscription_suggestions": (t_subscription_suggestions, fn("subscription_suggestions", "Subscriptions Donna detected in the user's email awaiting review.")),
    "send_to_phone": (t_send_to_phone, fn("send_to_phone", "Send a message to the user's phone via Telegram RIGHT NOW (only when they ask to send/push something now).", {
        "message": {"type": "string", "description": "Short message, e.g. 'Reminder: complete the Donna Bot by 11:59 PM today'"}}, ["message"])),
}

AGENT_TOOLS = {
    "tasks": ["list_tasks", "add_task", "update_task", "complete_task", "delete_task", "send_to_phone"],
    "calendar": ["get_events", "create_event", "find_free_time", "delete_event", "add_task", "update_task"],
    "journal": ["write_journal", "read_journal", "search_journal"],
    "ideas": ["add_idea", "list_ideas", "list_projects"],
    "memory": ["remember", "recall", "vault_lookup", "search_documents"],
    "people": ["find_person", "save_person", "log_interaction", "people_to_contact", "add_task"],
    "goals": ["list_goals", "save_goal", "add_goal_task", "complete_milestone", "reflect_on_goal", "achieve_goal", "let_go_goal", "add_milestone"],
    "subscriptions": ["list_subscriptions", "add_subscription", "update_subscription", "cancel_subscription",
                      "record_subscription_charge", "subscription_spend", "subscription_suggestions"],
    "renewals": ["list_renewals", "add_renewal", "mark_renewed", "search_documents"],
    "briefing": ["get_briefing", "get_events", "list_tasks", "week_review", "inbox_commitments"],
    "general": ["recall", "remember", "get_briefing", "search_documents", "send_to_phone"],
}

# ============================== Router ==============================
ROUTES = {
    "calendar": r"\b(calendar|meeting|meet|appointment|appt|schedule|reschedule|book(ing)?|block|event|free (time|slot)|busy|availability|available|call with|lunch with|dinner with|dentist|doctor|interview|flight)\b",
    "tasks": r"\b(task|tasks|to-?do|todos|remind me to|add .{1,40} to (my )?(list|tasks)|mark .* (done|complete)|completed?|pending|overdue|my day|checklist|errand)\b",
    "journal": r"\b(journal|diary|today was|yesterday was|i feel|i felt|feeling|log my day|reflect|mood|grateful|gratitude)\b",
    "ideas": r"\b(idea|ideas|brainstorm|jot|thought about|what if we|concept|pitch)\b",
    "memory": r"\b(remember|my .{0,20}(number|address|size|password|pin|card|passport|license|account|ifsc|email|phone|allerg)|what('s| is) my|prefer|preference|wish|wishlist|password|credit card|debit card|login|credentials|documents?|pdf|uploaded|warranty)\b",
    "people": r"\b(birthday|birthdays|catch ?up|caught up|spoke (to|with)|talked (to|with)|met (with|up)|haven'?t (talked|called|spoken|seen)|reach out|keep in touch|who should i (call|text|message)|people|contacts?|kids'? names?|who is)\b",
    "goals": r"\b(goal|goals|milestone|milestones|objective|resolution|progress on|working towards|reflection|mentor|motivat\w*|on track|achieved|achieve|level up|streak|xp)\b",
    "subscriptions": r"\b(subscri\w*|free trial|trial|autopay|auto-?pay|mandate|netflix|prime video|amazon prime|hotstar|jiohotstar|sonyliv|zee5|spotify|youtube premium|apple music|apple one|icloud\+?|google one|chatgpt|claude pro|gemini|perplexity|copilot|cursor|canva|adobe|notion|microsoft 365|office 365|linkedin premium|kindle unlimited|audible|swiggy one|zomato gold|uber one|cult\.?fit|duolingo|game pass|playstation plus|recurring|paying for)\b",
    "renewals": r"\b(renew|renewal|renewals|expire|expires|expiry|expiring|bill|bills|premium|insurance|emi|due for payment|recharge)\b",
    "briefing": r"\b(brief|briefing|my day look|agenda|what('s| is) on|plan my (day|week)|today look|morning|week ahead|what do i have|weekly review|review my week|my week go|inbox|commitments)\b",
}


FOLLOW_UP = re.compile(r"^(no\b|nope|actually|instead|change|make it|set (it|the)|move (it|that)|update|that'?s wrong|wrong|it'?s |its |today is|tomorrow is|i said|i meant|not |but |also|and |yes|yeah|ok|okay|sure|do it|send (it|the|that)|what about|how (could|can|is)|why)", re.I)


def route(text: str, prev_agent: str = None) -> str:
    t = text.lower()
    scores = {a: len(re.findall(p, t)) for a, p in ROUTES.items()}
    if re.search(r"remind me (about|of) .*\b(appointment|meeting|call)\b", t):
        scores["calendar"] += 2
    if re.search(r"\b(remind|reminder)\b", t) and not re.search(r"\b(meeting|appointment|event|calendar|book|block)\b", t):
        scores["tasks"] += 1
    best = max(scores, key=scores.get)
    ranked = sorted(scores.values(), reverse=True)
    # Corrections and short follow-ups belong to whoever handled the previous turn
    # (so "set it to 8am" can edit the task that agent just created).
    if prev_agent and prev_agent in AGENTS and prev_agent != "general" and (
            FOLLOW_UP.search(text.strip()) or (ranked[0] == 0 and len(text.split()) <= 14)):
        if ranked[0] == 0 or scores.get(prev_agent, 0) == ranked[0] or FOLLOW_UP.search(text.strip()):
            return prev_agent
    if scores[best] > 0 and ranked[0] > ranked[1]:
        return best
    try:
        out = llm.complete([
            {"role": "system", "content": skill("router")},
            {"role": "user", "content": text}],
            fmt={"type": "object", "properties": {"agent": {"type": "string", "enum": AGENTS}}, "required": ["agent"]},
            max_tokens=20, timeout=60, effort="low")
        a = json.loads(out).get("agent")
        return a if a in AGENTS else "general"
    except Exception:
        return best if scores[best] > 0 else "general"


# ============================== Context ==============================
def time_context():
    now = datetime.now().astimezone()
    days = []
    for i in range(0, 8):
        d = date.today() + timedelta(days=i)
        label = "TODAY" if i == 0 else "TOMORROW" if i == 1 else ""
        days.append(f"{d.strftime('%A')} = {d.isoformat()}{' (' + label + ')' if label else ''}")
    off = now.strftime("%z")
    tzname = db.get_setting("timezone", TP.DEFAULT_TZ)
    part = "morning" if now.hour < 12 else "afternoon" if now.hour < 17 else "evening" if now.hour < 21 else "night"
    channels = []
    if db.get_setting("telegram_chat_id"):
        channels.append("Telegram")
    if db.get_setting("smtp_host") and db.get_setting("notify_email"):
        channels.append("email")
    channels.append("in-app notification")
    return (f"CURRENT DATE AND TIME: {now.strftime('%A %d %B %Y')}, {now.strftime('%I:%M %p').lstrip('0')} "
            f"({part}), timezone {tzname} (UTC{off[:3]}:{off[3:]}).\n"
            f"Today is {now.strftime('%A')}. Upcoming days: {'; '.join(days)}.\n"
            "AM = before noon, PM = after noon. 'Tonight' only ever means a PM time today.\n"
            f"Working hours: {db.get_setting('work_start', '09:00')}-{db.get_setting('work_end', '18:00')}.\n"
            f"Reminders are delivered automatically at the reminder time via: {', '.join(channels)}.")


def user_context():
    name = db.get_setting("user_name", "")
    facts = db.rows("SELECT title, content FROM memories WHERE category IN ('profile','preference') ORDER BY updated_at DESC LIMIT 12")
    lines = [f"The user's name: {name}." if name else ""]
    if facts:
        lines.append("Known about the user: " + "; ".join(f"{f['title']}: {f['content'][:120]}" for f in facts))
    return "\n".join(l for l in lines if l)


def rag_context(text: str, agent: str):
    if agent not in ("memory", "general", "briefing", "ideas", "journal", "people", "goals", "renewals"):
        return ""
    hits = [x for x in (_hydrate(h) for h in db.search(text, limit=6)) if x]
    hits = [h for h in hits if h["type"] != "vault_item"] or []
    if not hits:
        return ""
    return "Possibly relevant notes from the user's records (use only if relevant):\n" + \
        "\n".join("- " + json.dumps(h, ensure_ascii=False) for h in hits)


def system_prompt(agent, text, mentor_chat=False):
    # Stable part first (persona + skills): prompt-cached on Claude. Everything after the mark changes per request.
    stable = [skill("donna"), skill(agent)]
    parts = [time_context(), TP.context_block(text), user_context(), rag_context(text, agent)]
    if agent == "goals":
        from . import mentor
        if mentor_chat:
            stable.append(skill("mentor"))
            parts.append("Mentor context (everything you know about their goals and recent life):\n" + mentor.overall_facts())
        else:
            gs = L.goals("active")
            parts.append("Mentor context:\n" + ("\n".join(mentor.goal_facts(g, 2) for g in gs) if gs else "No active goals yet."))
    extra = db.get_setting("custom_instructions", "")
    if extra:
        parts.append("Standing instructions from the user:\n" + extra)
    return "\n\n".join(p for p in stable if p) + llm.VOLATILE_MARK + "\n\n".join(p for p in parts if p)


# ============================== Agent loop ==============================
CLAIMS_ACTION = re.compile(
    r"\b(i'?ve|i have|i'?ll|i will|done|got it)\b[^.]{0,60}\b(added|updated|set|booked|scheduled|changed|moved|created|saved|marked|deleted|cancelled|canceled|sent|logged|tracked|remind)"
    r"|\b(added|updated|booked|scheduled|changed|moved|created|saved|sent|logged)\b[^.]{0,40}\b(task|reminder|event|appointment|list|calendar|telegram)", re.I)


MUTATING = {"add_subscription", "update_subscription", "cancel_subscription", "record_subscription_charge", "add_goal_task", "achieve_goal", "let_go_goal", "reflect_on_goal", "add_task", "update_task", "complete_task", "delete_task", "create_event", "delete_event", "write_journal",
            "add_idea", "remember", "save_person", "log_interaction", "save_goal", "add_milestone", "complete_milestone",
            "add_renewal", "mark_renewed", "send_to_phone"}


def _summarise_result(name, result):
    """Compact record of what a tool did, replayed in later turns so the model knows the real state."""
    if "error" in result:
        return f"{name} failed: {result['error']}"
    for key in ("created", "updated", "updated_existing_task"):
        t = result.get(key)
        if isinstance(t, dict) and "id" in t:
            bits = [f"task #{t['id']} '{t['title']}'"]
            if t.get("reminder_say"):
                bits.append(f"reminder {t['reminder_say']}")
            elif t.get("due_say"):
                bits.append(f"due {t['due_say']}")
            return f"{name}: " + ", ".join(bits)
    for key in ("added", "updated", "updated_existing", "cancelled", "subscription"):
        sub = result.get(key)
        if isinstance(sub, dict) and "name" in sub and "status" in sub:
            bits = [f"{key} subscription '{sub['name']}'", sub.get("price", ""), sub["status"]]
            for k in ("payment_method", "billed_via", "shared_with", "next_charge_say", "trial_ends_say", "cancel_by_say", "access_until_say"):
                if sub.get(k):
                    bits.append(f"{k.replace('_say', '').replace('_', ' ')}: {sub[k]}")
            if result.get("price_change"):
                bits.append(f"price change {result['price_change']}")
            return f"{name}: " + ", ".join(b for b in bits if b)
    if "created" in result and isinstance(result["created"], dict):
        e = result["created"]
        return f"{name}: '{e.get('title')}' {e.get('when_say', e.get('start', ''))}"
    s = json.dumps(result, ensure_ascii=False, default=str)
    return f"{name}: {s[:300]}"


def run(conversation_id: int, text: str, agent: str = None):
    """Generator of event dicts streamed to the UI."""
    hist_rows = db.rows("SELECT role, content, meta FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 8", (conversation_id,))[::-1]
    prev_agent = None
    for h in reversed(hist_rows):
        if h["role"] == "assistant":
            prev_agent = json.loads(h["meta"] or "{}").get("agent")
            break
    mentor_chat = (db.get_setting("mentor_conv", {}) or {}).get("id") == conversation_id
    if mentor_chat and agent not in AGENTS:
        agent = "goals"
    agent = agent if agent in AGENTS else route(text, prev_agent)
    yield {"type": "agent", "agent": agent}
    from . import gamify
    xp_before = gamify.total_xp()
    messages = [{"role": "system", "content": system_prompt(agent, text, mentor_chat)}]
    for h in hist_rows:
        content = h["content"]
        if h["role"] == "assistant":
            done = json.loads(h["meta"] or "{}").get("trace") or []
            actions = [x.get("summary") or x["tool"] for x in done]
            content += "\n[System record of what was actually done in this turn: " + ("; ".join(actions) if actions else "NOTHING (no tool was called, nothing was changed)") + "]"
        messages.append({"role": h["role"], "content": content})
    messages.append({"role": "user", "content": text})
    tools = [TOOLS[n][1] for n in AGENT_TOOLS[agent]]
    allowed = set(AGENT_TOOLS[agent])
    ctx, trace, final = {}, [], ""
    nudged = False
    direct_reply = None
    _turn.text = text
    fact_only = TP.is_fact_only(text)
    if fact_only:
        messages.append({"role": "system", "content":
                         "The user's latest message only states a fact or questions your previous reply. Do NOT change any data. "
                         "Check the System record of earlier turns, then answer honestly in at most 2 short sentences: "
                         "acknowledge any wrong wording you used before and state what is actually saved."})

    for _ in range(6):
        msg = None
        for kind, val in llm.chat_stream(messages, tools):
            if kind == "token":
                yield {"type": "token", "text": val}
            elif kind == "reset":
                yield {"type": "reset"}
            else:
                msg = val
        messages.append(msg)
        if not msg.get("tool_calls"):
            final = msg["content"]
            # Guard: the model claimed to change something but called no tool this turn.
            if not trace and CLAIMS_ACTION.search(final or ""):  # claimed an action without calling any tool at all
                if not nudged and not fact_only:
                    nudged = True
                    messages.append({"role": "user", "content":
                                     "(Automatic check from the Donna app) You did not call any tool, so NOTHING was changed. "
                                     "If I asked for something to be added, changed or sent, call the correct tool now "
                                     "(update_task with the task's current title to change an existing task). "
                                     "If nothing needs changing, answer without claiming you did anything."})
                    yield {"type": "reset"}
                    continue
                if fact_only:
                    break  # explanation of current state is expected here
                # Still claiming an action that never happened: never let a false confirmation through.
                final = ("I haven't actually changed anything yet. Tell me exactly what you'd like "
                         "(for example \"set the reminder for 8:07 AM today\") and I'll do it.")
            break
        for call in msg["tool_calls"]:
            name = call["function"]["name"]
            args = call["function"].get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            # Dates/times the user literally said beat the model's arithmetic.
            if name in ("add_task", "add_goal_task", "save_goal", "update_task", "create_event", "get_events", "find_free_time", "write_journal", "read_journal"):
                args, fixes = TP.correct_args(args, text)
            else:
                fixes = []
            yield {"type": "tool", "name": name, "args": args}
            if name not in allowed:
                result = {"error": f"Tool {name} not available here"}
            elif fact_only and name in MUTATING:
                result = {"error": "Not executed: the user only stated a fact / asked about your last reply. Change nothing; "
                                   "explain what is actually saved using the System record."}
            else:
                try:
                    f = TOOLS[name][0]
                    result = f(**args, _ctx=ctx) if name == "vault_lookup" else f(**args)
                except TypeError as e:
                    result = {"error": f"Bad arguments: {e}"}
                except Exception as e:
                    result = {"error": str(e)}
            if fixes and "error" not in result:
                result["system_note"] = "Dates were set exactly as the user said. Describe times ONLY using the *_say fields."
            trace.append({"tool": name, "args": args, "ok": "error" not in result, "summary": _summarise_result(name, result)})
            yield {"type": "tool_result", "name": name, "ok": "error" not in result}
            if result.get("_final_reply"):
                direct_reply = result.pop("_final_reply")
            messages.append({"role": "tool", "tool_name": name, "tool_call_id": call.get("id"),
                             "content": json.dumps(result, ensure_ascii=False, default=str)})
        yield {"type": "reset"}  # UI clears any pre-tool chatter before the next round
        if direct_reply:
            final = direct_reply  # a specialist engine already wrote the answer (e.g. mentor feedback)
            break
    else:
        final = final or "I've done what I can on that. Take a look and tell me if anything needs adjusting."

    final = re.sub(r"<think>.*?</think>", "", final, flags=re.S)
    final = re.sub(r"\[System record[^\]]*\]", "", final).strip()
    saved_times = [a.get(k) for t in trace if t["ok"] for a in [t["args"]] for k in ("reminder_at", "start", "end")]
    if not saved_times and fact_only:
        saved_times = re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", json.dumps(
            [db.row("SELECT reminder_at FROM tasks WHERE COALESCE(updated_at, created_at) >= datetime('now','localtime','-2 hours') ORDER BY id DESC")]))
    if llm.provider() != "claude":  # crutch for small local models; Claude words times correctly
        final = TP.fix_wording(final, saved_times)
    gained = gamify.total_xp() - xp_before
    if gained > 0:
        lvl = gamify.level_for(gamify.total_xp())
        before_lvl = gamify.level_for(xp_before)
        yield {"type": "reward", "xp": gained, "level": lvl, "level_up": lvl["title"] if lvl["level"] > before_lvl["level"] else None}
    meta = {"agent": agent, "trace": trace}
    if gained > 0:
        meta["xp"] = gained
    if ctx.get("vault_cards"):
        meta["vault_cards"] = list(dict.fromkeys(ctx["vault_cards"]))
        yield {"type": "vault_cards", "ids": meta["vault_cards"]}
    yield {"type": "final", "text": final, "meta": meta}
