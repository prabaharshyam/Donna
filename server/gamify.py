"""Gamification: XP, levels, streaks, badges and Donna's celebration lines.

XP is keyed per item (e.g. "task:42"), so ticking/unticking a task can't farm points.
"""
import random
from datetime import date, timedelta

from . import db

POINTS = {"task": 10, "milestone": 50, "reflection": 15, "goal": 300, "plan": 20}

LEVELS = [  # (xp needed, title)
    (0, "Associate"), (150, "Senior Associate"), (400, "Junior Partner"), (800, "Senior Partner"),
    (1400, "Managing Partner"), (2200, "Name Partner"), (3500, "Legend"),
]

LINES = {
    "task": [
        "That's how it's done.", "One step closer. Keep moving.", "Momentum is a decision. You just made it.",
        "Small wins compound. That one counted.", "Done is a habit. You're building it.",
        "See? You didn't need motivation. You needed to start.", "Another brick. The wall is going up.",
    ],
    "milestone": [
        "Milestone down. Now you know you can.", "That wasn't luck. That was you.",
        "Look back for one second. Then look forward. Next one.", "Checkpoint cleared. Most people never get here.",
        "This is the part where it starts getting real.",
    ],
    "goal": [
        "You did it. I never doubted you. Not once.", "Goal achieved. Remember this feeling. Then go bigger.",
        "Winners aren't people who never fail. They're people who never quit. Case closed.",
    ],
    "reflection": [
        "Honest reflection is a superpower. Noted.", "Thinking about it is how you get better at it.",
        "Showing up to reflect is half the game.",
    ],
    "plan": ["A goal without a plan is a wish. Now it's a plan."],
}


def award(kind: str, ref, goal_id=None, note=""):
    """Grant XP once per (kind, ref). Returns a reward dict, or None if already granted."""
    key = f"{kind}:{ref}"
    if db.row("SELECT 1 FROM xp_log WHERE key=?", (key,)):
        return None
    before = total_xp()
    pts = POINTS.get(kind, 0)
    db.run("INSERT INTO xp_log(key, goal_id, kind, points, note) VALUES (?,?,?,?,?)", (key, goal_id, kind, pts, note[:200]))
    after = before + pts
    lb, la = level_for(before), level_for(after)
    return {"xp": pts, "total": after, "kind": kind, "line": random.choice(LINES.get(kind, LINES["task"])),
            "level_up": la["title"] if la["level"] > lb["level"] else None, "level": la}


def total_xp():
    return db.row("SELECT COALESCE(SUM(points),0) n FROM xp_log")["n"]


def goal_xp(goal_id):
    return db.row("SELECT COALESCE(SUM(points),0) n FROM xp_log WHERE goal_id=?", (goal_id,))["n"]


def level_for(xp):
    idx = max(i for i, (need, _) in enumerate(LEVELS) if xp >= need)
    need, title = LEVELS[idx]
    nxt = LEVELS[idx + 1] if idx + 1 < len(LEVELS) else None
    return {"level": idx + 1, "title": title, "xp": xp, "floor": need,
            "next_at": nxt[0] if nxt else None, "next_title": nxt[1] if nxt else None,
            "pct": round(100 * (xp - need) / (nxt[0] - need)) if nxt else 100}


def active_days():
    """Days with goal activity: a reflection or a completed goal task/milestone."""
    rows = db.rows("""SELECT date AS d FROM goal_reflections
                      UNION SELECT substr(completed_at,1,10) FROM tasks WHERE goal_id IS NOT NULL AND completed=1 AND completed_at IS NOT NULL
                      UNION SELECT substr(done_at,1,10) FROM milestones WHERE done=1 AND done_at IS NOT NULL""")
    return {r["d"] for r in rows if r["d"]}


def streak(days=None):
    days = days if days is not None else active_days()
    d, n = date.today(), 0
    if d.isoformat() not in days:
        d -= timedelta(days=1)  # today isn't over yet; yesterday keeps the streak alive
    while d.isoformat() in days:
        n += 1
        d -= timedelta(days=1)
    return n


def reflection_streak(goal_id):
    days = {r["date"] for r in db.rows("SELECT date FROM goal_reflections WHERE goal_id=?", (goal_id,))}
    return streak(days)


def best_streak(days):
    best = cur = 0
    prev = None
    for d in sorted(days):
        cur = cur + 1 if prev and (date.fromisoformat(d) - date.fromisoformat(prev)).days == 1 else 1
        best, prev = max(best, cur), d
    return best


def badges():
    q = lambda sql: db.row(sql)["n"]
    days = active_days()
    best = best_streak(days)
    defs = [
        ("first_step", "First step", "Completed your first goal task", q("SELECT COUNT(*) n FROM tasks WHERE goal_id IS NOT NULL AND completed=1") >= 1),
        ("mirror", "Honest mirror", "Wrote your first goal reflection", q("SELECT COUNT(*) n FROM goal_reflections") >= 1),
        ("milestone", "Milestone maker", "Cleared your first milestone", q("SELECT COUNT(*) n FROM milestones WHERE done=1") >= 1),
        ("streak7", "On fire", "7-day goal streak", best >= 7),
        ("streak30", "Unstoppable", "30-day goal streak", best >= 30),
        ("closer", "The closer", "Achieved a goal", q("SELECT COUNT(*) n FROM goals WHERE status='achieved'") >= 1),
        ("hattrick", "Hat-trick", "Achieved 3 goals", q("SELECT COUNT(*) n FROM goals WHERE status='achieved'") >= 3),
        ("reflect30", "Self-aware", "30 reflections written", q("SELECT COUNT(*) n FROM goal_reflections") >= 30),
    ]
    return [{"id": i, "name": n, "desc": d, "earned": bool(e)} for i, n, d, e in defs]


def summary():
    xp = total_xp()
    days = active_days()
    return {"level": level_for(xp), "streak": streak(days), "best_streak": best_streak(days), "badges": badges(),
            "active_today": date.today().isoformat() in days}
