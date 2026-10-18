"""Donna as mentor: daily note, reflection feedback, goal game plans, milestone breakdowns.

Everything the model sees is pre-digested into plain, explicit facts (with "none" where data is
missing) so a small local model gives grounded, specific advice instead of generic platitudes.
"""
import json
import logging
import re
import threading
from datetime import date, datetime, timedelta

from . import db, gamify, life, llm

log = logging.getLogger("donna.mentor")
_generating = set()
_lock = threading.Lock()


def _skill(name):
    from .agents import skill
    return skill(name)


def _clean(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    return re.sub(r"\[System record[^\]]*\]", "", text).strip()


# ============================== facts ==============================
def _days_ago(ts):
    if not ts:
        return None
    return (date.today() - date.fromisoformat(ts[:10])).days


def goal_facts(g, reflections_n=3):
    lines = [f'GOAL "{g["title"]}"' + (f' (why it matters to them: {g["why"]})' if g.get("why") else " (they haven't written why it matters)")]
    if g.get("target_date"):
        dl = g["days_left"]
        lines.append(f"  Target date {g['target_date']} ({'OVERDUE by ' + str(-dl) + ' days' if dl < 0 else str(dl) + ' days left'}).")
    else:
        lines.append("  No target date set.")
    lines.append(f"  Progress {g['progress']}%: {g['done_count']} of {g['total_count']} milestones done." if g["milestones"]
                 else f"  Progress {g['progress']}%. No milestones yet.")
    if g["next_milestone"]:
        lines.append(f"  Current milestone: {g['next_milestone']}.")
    open_tasks = [t for t in g["tasks"] if not t["completed"]]
    if open_tasks:
        today = date.today().isoformat()
        lines.append("  Open tasks: " + "; ".join(
            t["title"] + (f" (OVERDUE, due {t['due_date']})" if t["due_date"] and t["due_date"] < today else f" (due {t['due_date']})" if t["due_date"] else "")
            for t in open_tasks[:5]) + ".")
    else:
        lines.append("  No open tasks: there is no defined next action.")
    week = (date.today() - timedelta(days=7)).isoformat()
    done7 = [t["title"] for t in g["tasks"] if t["completed"] and (t["completed_at"] or "") >= week]
    lines.append(f"  Tasks completed in the last 7 days: {len(done7)}" + (f" ({'; '.join(done7[:4])})." if done7 else "."))
    lp = _days_ago(g.get("last_progress"))
    lines.append(f"  Last completed task: {lp} days ago." if lp is not None else "  No task for this goal has ever been completed.")
    refs = life.reflections(g["id"], reflections_n)
    if refs:
        lines.append(f"  Reflection streak: {g['reflection_streak']} days. Recent reflections:")
        for r in refs:
            conf = f", feels {r['confidence']}/5 on track" if r["confidence"] else ""
            lines.append(f"   - {r['date']}{conf}: \"{r['text'][:260]}\"")
    else:
        lines.append("  They have never reflected on this goal.")
    return "\n".join(lines)


def overall_facts():
    now = datetime.now()
    today = date.today().isoformat()
    yday = (date.today() - timedelta(days=1)).isoformat()
    name = db.get_setting("user_name", "")
    g = gamify.summary()
    L = [f"Now: {now.strftime('%A %d %B %Y, %I:%M %p').replace(' 0', ' ')}." + (f" The user's name is {name}." if name else ""),
         f"Gamification: level {g['level']['level']} '{g['level']['title']}', {g['level']['xp']} XP, goal streak {g['streak']} days"
         f" (best {g['best_streak']}). {'Already active on goals today.' if g['active_today'] else 'No goal activity yet today.'}"]
    active = life.goals("active")
    if active:
        L.append(f"ACTIVE GOALS ({len(active)} of 3 slots):")
        for x in active:
            L.append(goal_facts(x, 2))
    else:
        L.append("ACTIVE GOALS: none. The user has no goals set.")
    achieved = db.row("SELECT COUNT(*) n FROM goals WHERE status='achieved'")["n"]
    if achieved:
        L.append(f"Goals achieved so far: {achieved}.")
    done_y = db.rows("SELECT title FROM tasks WHERE completed=1 AND substr(completed_at,1,10)=?", (yday,))
    done_t = db.rows("SELECT title FROM tasks WHERE completed=1 AND substr(completed_at,1,10)=?", (today,))
    L.append("Tasks completed yesterday: " + ("; ".join(t["title"] for t in done_y[:8]) if done_y else "none") + ".")
    if done_t:
        L.append("Completed so far today: " + "; ".join(t["title"] for t in done_t[:8]) + ".")
    due = db.rows("SELECT title, reminder_at FROM tasks WHERE completed=0 AND (due_date=? OR substr(reminder_at,1,10)=?)", (today, today))
    L.append("Due or reminders today: " + ("; ".join(t["title"] + (f" at {t['reminder_at'][11:16]}" if t["reminder_at"] else "") for t in due[:8]) if due else "none") + ".")
    overdue = db.rows("SELECT title, due_date FROM tasks WHERE completed=0 AND due_date<? ORDER BY due_date", (today,))
    L.append(f"Overdue tasks: {len(overdue)}" + (f" (oldest: {overdue[0]['title']}, due {overdue[0]['due_date']})." if overdue else "."))
    try:
        from . import calendar_svc as cal
        ev = [e for e in cal.list_events(today, today) if not e.get("all_day")]
        L.append("Calendar today: " + ("; ".join(f"{e['start'][11:16]} {e['title']}" for e in ev[:6]) if ev else "nothing scheduled") + ".")
    except Exception:
        pass
    js = db.rows("SELECT date, mood, body FROM journal WHERE length(body)>0 ORDER BY date DESC LIMIT 3")
    if js:
        L.append("Recent journal entries:")
        for j in js:
            L.append(f" - {j['date']}" + (f" (mood {j['mood']})" if j["mood"] else "") + f": \"{j['body'][:240]}\"")
    else:
        L.append("Journal: no recent entries.")
    ideas = db.rows("SELECT title, body FROM ideas WHERE created_at >= ? ORDER BY id DESC LIMIT 5", ((date.today() - timedelta(days=7)).isoformat(),))
    L.append("Ideas captured this week: " + ("; ".join((i["title"] or i["body"][:60]) for i in ideas) if ideas else "none") + ".")
    return "\n".join(L)


# ============================== daily note ==============================
def conversation_for(day=None):
    """One mentor conversation per day; the note is its first message, replies go through the goals agent."""
    day = day or date.today().isoformat()
    cur = db.get_setting("mentor_conv", {}) or {}
    if cur.get("date") == day and db.row("SELECT 1 FROM conversations WHERE id=?", (cur.get("id"),)):
        return cur["id"]
    cid = db.run("INSERT INTO conversations(title, updated_at) VALUES (?,?)",
                 (f"🎯 Mentor · {date.fromisoformat(day).strftime('%a %d %b')}", db.now()))
    db.set_setting("mentor_conv", {"date": day, "id": cid})
    return cid


def today_note():
    cur = db.get_setting("mentor_conv", {}) or {}
    if cur.get("date") != date.today().isoformat():
        return None
    r = db.row("SELECT * FROM messages WHERE conversation_id=? AND role='assistant' ORDER BY id LIMIT 1", (cur["id"],))
    return r


def generate_daily(force=False, notify=False):
    day = date.today().isoformat()
    with _lock:
        if day in _generating:
            return None
        if today_note() and not force:
            return today_note()
        _generating.add(day)
    try:
        facts = overall_facts()
        text = _clean(llm.complete([
            {"role": "system", "content": _skill("mentor") + "\n\n" + _skill("mentor_daily")},
            {"role": "user", "content": facts}], timeout=300))
        if not text:
            return None
        cid = conversation_for(day)
        if force:
            db.run("DELETE FROM messages WHERE conversation_id=?", (cid,))
        db.run("INSERT INTO messages(conversation_id, role, content, meta) VALUES (?,?,?,?)",
               (cid, "assistant", text, json.dumps({"agent": "goals", "trace": [], "kind": "mentor_note"})))
        db.run("UPDATE conversations SET updated_at=? WHERE id=?", (db.now(), cid))
        if notify:
            from . import services as S
            first = re.sub(r"[*_#>`]", "", text).split("\n")[0]
            S.notify("Donna's note for today", first[:220], "#/")
        return today_note()
    except Exception as e:
        log.warning("daily mentor note failed: %s", e)
        return None
    finally:
        _generating.discard(day)


def generate_daily_async(force=False, notify=False):
    threading.Thread(target=generate_daily, kwargs={"force": force, "notify": notify}, daemon=True).start()


def is_generating():
    return date.today().isoformat() in _generating


# ============================== reflection feedback ==============================
def reflect(gid, text, confidence=None):
    r, reward = life.reflection_save(gid, text, confidence)
    g = life.goal(gid)
    prompt = goal_facts(g, 6) + f"\n\nTODAY'S REFLECTION ({r['date']}" + (f", feels {confidence}/5 on track" if confidence else "") + f"):\n\"{text.strip()}\""
    try:
        reply = _clean(llm.complete([
            {"role": "system", "content": _skill("mentor") + "\n\n" + _skill("mentor_reflection") + "\n\nToday: " + datetime.now().strftime("%A %d %B %Y")},
            {"role": "user", "content": prompt}], timeout=300))
    except Exception as e:
        reply = f"(I couldn't think this through just now: {e}. Your reflection is saved.)"
    db.run("UPDATE goal_reflections SET mentor_reply=? WHERE id=?", (reply, r["id"]))
    r = db.row("SELECT * FROM goal_reflections WHERE id=?", (r["id"],))
    r["reward"] = reward
    return r


# ============================== plans ==============================
def _d(days):
    return (date.today() + timedelta(days=max(0, int(days or 0)))).isoformat()


def plan(gid):
    g = life.goal(gid)
    existing = [m["title"] + (" (done)" if m["done"] else "") for m in g["milestones"]]
    horizon = g["days_left"] if g.get("days_left") and g["days_left"] > 0 else 90
    schema = {"type": "object", "properties": {
        "strategy": {"type": "string"},
        "milestones": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "weeks_from_now": {"type": "integer"},
            "tasks": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string"}, "days_from_now": {"type": "integer"}}, "required": ["title"]}}},
            "required": ["title", "tasks"]}}},
        "required": ["strategy", "milestones"]}
    brief = (f'Goal: "{g["title"]}"\nWhy: {g["why"] or "not stated"}\nTime available: about {horizon} days'
             + (f" (target {g['target_date']})" if g.get("target_date") else " (no target date)")
             + ("\nExisting milestones (keep these, in order; add tasks to the next unfinished ones and add at most 2 new milestones only if something important is missing):\n- " + "\n- ".join(existing) if existing else "\nNo milestones yet.")
             + "\n\nRecent context:\n" + goal_facts(g, 3))
    out = json.loads(llm.complete([{"role": "system", "content": _skill("mentor") + "\n\n" + _skill("goal_plan")},
                                   {"role": "user", "content": brief}], fmt=schema, timeout=400))
    target = g.get("target_date")
    proposal = {"strategy": _clean(out.get("strategy", "")), "milestones": []}
    for m in out.get("milestones", [])[:8]:
        match = life.find_milestone(g, m.get("title", ""))
        due = _d(7 * int(m.get("weeks_from_now") or 0)) if m.get("weeks_from_now") else None
        if due and target and due > target:
            due = target
        proposal["milestones"].append({
            "title": match["title"] if match else m.get("title", "").strip(), "existing_id": match["id"] if match else None,
            "due_date": None if match else due,
            "tasks": [{"title": t["title"].strip(), "due_date": _d(t.get("days_from_now")) if t.get("days_from_now") is not None else None}
                      for t in m.get("tasks", [])[:6] if t.get("title", "").strip()]})
    return proposal


def apply_plan(gid, proposal):
    g = life.goal(gid)
    for m in proposal.get("milestones", []):
        mid = m.get("existing_id")
        if not mid:
            if not m.get("title"):
                continue
            life.milestone_add(gid, m["title"], m.get("due_date"))
            mid = db.row("SELECT id FROM milestones WHERE goal_id=? ORDER BY id DESC LIMIT 1", (gid,))["id"]
        have = {t["title"].lower() for t in db.rows("SELECT title FROM tasks WHERE milestone_id=?", (mid,))}
        for t in m.get("tasks", []):
            if t.get("title") and t["title"].lower() not in have:
                life.milestone_task_add(mid, t["title"], t.get("due_date"))
    if proposal.get("strategy"):
        life.goal_save(gid, mentor_plan=proposal["strategy"])
    reward = gamify.award("plan", gid, gid, g["title"])
    out = life.goal(gid)
    out["reward"] = reward
    return out


def breakdown(mid):
    m = db.row("SELECT * FROM milestones WHERE id=?", (mid,))
    g = life.goal(m["goal_id"])
    have = [t["title"] for t in db.rows("SELECT title FROM tasks WHERE milestone_id=?", (mid,))]
    schema = {"type": "object", "properties": {"tasks": {"type": "array", "items": {"type": "object", "properties": {
        "title": {"type": "string"}, "days_from_now": {"type": "integer"}}, "required": ["title"]}}}, "required": ["tasks"]}
    brief = (f'Goal: "{g["title"]}"\nMilestone to break down: "{m["title"]}"' + (f" (due {m['due_date']})" if m["due_date"] else "")
             + ("\nTasks already under it: " + "; ".join(have) if have else "\nNo tasks under it yet.")
             + "\nGive 3-6 concrete next tasks, each doable in one sitting (15-90 min), in order. days_from_now spaces them realistically.")
    out = json.loads(llm.complete([{"role": "system", "content": _skill("mentor") + "\n\n" + _skill("goal_plan")},
                                   {"role": "user", "content": brief}], fmt=schema, timeout=300))
    return [{"title": t["title"].strip(), "due_date": _d(t.get("days_from_now")) if t.get("days_from_now") is not None else None}
            for t in out.get("tasks", [])[:6] if t.get("title", "").strip() and t["title"].strip() not in have]
