"""Domain logic shared by the REST API and Donna's agents."""
import calendar as _cal
from datetime import date, datetime, timedelta

from . import db, secure

TASK_FIELDS = {"project_id", "title", "note", "due_date", "reminder_at", "repeat", "important",
               "my_day", "completed", "completed_at", "tags", "sort", "reminder_sent", "goal_id", "milestone_id"}


def today() -> str:
    return date.today().isoformat()


# ======================= Projects =======================
def projects(include_archived=False):
    sql = """SELECT p.*,
      (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.completed=0) AS open_tasks,
      (SELECT COUNT(*) FROM ideas i WHERE i.project_id=p.id AND i.archived=0) AS idea_count
      FROM projects p"""
    if not include_archived:
        sql += " WHERE archived=0"
    return db.rows(sql + " ORDER BY sort, id")


def find_project(name: str, create=False):
    if not name:
        return None
    p = db.row("SELECT * FROM projects WHERE lower(name)=lower(?)", (name.strip(),)) or \
        db.row("SELECT * FROM projects WHERE lower(name) LIKE lower(?)", (f"%{name.strip()}%",))
    if not p and create:
        pid = db.run("INSERT INTO projects(name, sort) VALUES (?, (SELECT COALESCE(MAX(sort),0)+1 FROM projects))",
                     (name.strip(),))
        p = db.row("SELECT * FROM projects WHERE id=?", (pid,))
    return p


# ======================= Tasks =======================
def _task_out(t):
    t["steps"] = db.rows("SELECT * FROM steps WHERE task_id=? ORDER BY sort, id", (t["id"],))
    return t


def list_tasks(view="all", project_id=None, q=None, include_completed=True):
    base = "SELECT t.*, p.name AS project_name, p.emoji AS project_emoji FROM tasks t LEFT JOIN projects p ON p.id=t.project_id"
    where, args = [], []
    td = today()
    if view == "myday":
        where.append("(t.my_day=? OR (t.due_date IS NOT NULL AND t.due_date<=? AND t.completed=0))")
        args += [td, td]
    elif view == "important":
        where.append("t.important=1")
    elif view == "planned":
        where.append("t.due_date IS NOT NULL")
    elif view == "completed":
        where.append("t.completed=1")
    elif view == "overdue":
        where.append("t.due_date < ? AND t.completed=0")
        args.append(td)
    elif view == "upcoming":
        where.append("t.due_date >= ? AND t.completed=0")
        args.append(td)
    elif view == "inbox":
        where.append("t.project_id IS NULL")
    if project_id:
        where.append("t.project_id=?")
        args.append(project_id)
    if q:
        where.append("(t.title LIKE ? OR t.note LIKE ? OR t.tags LIKE ?)")
        args += [f"%{q}%"] * 3
    if not include_completed and view != "completed":
        where.append("t.completed=0")
    sql = base + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY t.completed, t.sort, CASE WHEN t.due_date IS NULL THEN 1 ELSE 0 END, t.due_date, t.id DESC"
    return [_task_out(t) for t in db.rows(sql, args)]


def get_task(tid):
    t = db.row("SELECT t.*, p.name AS project_name FROM tasks t LEFT JOIN projects p ON p.id=t.project_id WHERE t.id=?", (tid,))
    return _task_out(t) if t else None


def create_task(title, project_id=None, **kw):
    fields = {k: v for k, v in kw.items() if k in TASK_FIELDS and v not in (None, "")}
    fields.update(title=title.strip(), project_id=project_id)
    cols = ", ".join(fields)
    tid = db.run(f"INSERT INTO tasks({cols}, updated_at) VALUES ({','.join('?' * len(fields))}, ?)",
                 (*fields.values(), db.now()))
    _index_task(tid)
    return get_task(tid)


def update_task(tid, fields: dict):
    if "reminder_at" in fields:
        fields["reminder_sent"] = 0
    if "completed" in fields:
        return complete_task(tid, bool(fields.pop("completed")), extra=fields)
    db.update("tasks", tid, fields, TASK_FIELDS)
    _index_task(tid)
    return get_task(tid)


def complete_task(tid, done=True, extra=None):
    t = get_task(tid)
    if not t:
        return None
    upd = dict(extra or {})
    upd.update(completed=1 if done else 0, completed_at=db.now() if done else None)
    db.update("tasks", tid, upd, TASK_FIELDS)
    # Microsoft To Do behaviour: completing a repeating task spawns the next occurrence.
    if done and t["repeat"] and not t["completed"]:
        nxt = next_occurrence(t["due_date"] or today(), t["repeat"])
        rem = None
        if t["reminder_at"]:
            rem = nxt + t["reminder_at"][10:]
        new = create_task(t["title"], t["project_id"], note=t["note"], due_date=nxt, reminder_at=rem,
                          repeat=t["repeat"], important=t["important"], tags=t["tags"])
        for s in t["steps"]:
            db.run("INSERT INTO steps(task_id,title,sort) VALUES (?,?,?)", (new["id"], s["title"], s["sort"]))
    _index_task(tid)
    out = get_task(tid)
    if done and not t["completed"]:
        from . import life
        reward = life.on_task_completed(out)
        if reward:
            out["reward"] = reward
    return out


def delete_task(tid):
    db.run("DELETE FROM tasks WHERE id=?", (tid,))
    db.unindex("task", tid)


def next_occurrence(from_date: str, repeat: str) -> str:
    d = date.fromisoformat(from_date[:10])
    if repeat == "daily":
        d += timedelta(days=1)
    elif repeat == "weekdays":
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
    elif repeat == "weekly":
        d += timedelta(weeks=1)
    elif repeat == "monthly":
        m = d.month % 12 + 1
        y = d.year + (d.month // 12)
        d = d.replace(year=y, month=m, day=min(d.day, _cal.monthrange(y, m)[1]))
    elif repeat == "yearly":
        try:
            d = d.replace(year=d.year + 1)
        except ValueError:
            d = d.replace(year=d.year + 1, day=28)
    return d.isoformat()


def _index_task(tid):
    t = db.row("SELECT * FROM tasks WHERE id=?", (tid,))
    if t:
        status = "done" if t["completed"] else "open"
        db.index("task", tid, t["title"], f"{t['note']} due {t['due_date'] or ''} {status} {t['tags']}")


def add_step(task_id, title):
    db.run("INSERT INTO steps(task_id,title,sort) VALUES (?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM steps WHERE task_id=?))",
           (task_id, title, task_id))
    return get_task(task_id)


def task_counts():
    td = today()
    q = lambda sql, a=(): db.row(sql, a)["n"]
    return {
        "myday": q("SELECT COUNT(*) n FROM tasks WHERE completed=0 AND (my_day=? OR (due_date IS NOT NULL AND due_date<=?))", (td, td)),
        "important": q("SELECT COUNT(*) n FROM tasks WHERE completed=0 AND important=1"),
        "planned": q("SELECT COUNT(*) n FROM tasks WHERE completed=0 AND due_date IS NOT NULL"),
        "all": q("SELECT COUNT(*) n FROM tasks WHERE completed=0"),
        "inbox": q("SELECT COUNT(*) n FROM tasks WHERE completed=0 AND project_id IS NULL"),
        "overdue": q("SELECT COUNT(*) n FROM tasks WHERE completed=0 AND due_date<?", (td,)),
    }


# ======================= Journal =======================
def journal_get(d):
    return db.row("SELECT * FROM journal WHERE date=?", (d,))


def journal_save(d, body=None, title=None, mood=None, tags=None, append=False):
    cur = journal_get(d)
    if cur:
        fields = {}
        if body is not None:
            fields["body"] = (cur["body"].rstrip() + "\n\n" + body).strip() if append and cur["body"] else body
        for k, v in (("title", title), ("mood", mood), ("tags", tags)):
            if v is not None:
                fields[k] = v
        db.update("journal", cur["id"], fields, {"body", "title", "mood", "tags"})
        jid = cur["id"]
    else:
        jid = db.run("INSERT INTO journal(date,title,body,mood,tags,updated_at) VALUES (?,?,?,?,?,?)",
                     (d, title or "", body or "", mood or "", tags or "", db.now()))
    j = db.row("SELECT * FROM journal WHERE id=?", (jid,))
    db.index("journal", jid, f"Journal {j['date']} {j['title']}", f"{j['body']} mood {j['mood']} {j['tags']}")
    return j


def journal_list(limit=60, q=None):
    if q:
        return db.rows("SELECT * FROM journal WHERE body LIKE ? OR title LIKE ? OR tags LIKE ? ORDER BY date DESC LIMIT ?",
                       (f"%{q}%", f"%{q}%", f"%{q}%", limit))
    return db.rows("SELECT * FROM journal ORDER BY date DESC LIMIT ?", (limit,))


def journal_streak():
    dates = {r["date"] for r in db.rows("SELECT date FROM journal WHERE length(body)>0")}
    d, n = date.today(), 0
    if d.isoformat() not in dates:
        d -= timedelta(days=1)
    while d.isoformat() in dates:
        n += 1
        d -= timedelta(days=1)
    return n


# ======================= Ideas =======================
IDEA_FIELDS = {"project_id", "title", "body", "color", "pinned", "archived", "tags"}


def ideas(project_id=None, q=None, archived=False):
    sql = "SELECT i.*, p.name AS project_name, p.emoji AS project_emoji FROM ideas i LEFT JOIN projects p ON p.id=i.project_id WHERE i.archived=?"
    args = [1 if archived else 0]
    if project_id:
        sql += " AND i.project_id=?"
        args.append(project_id)
    if q:
        sql += " AND (i.title LIKE ? OR i.body LIKE ? OR i.tags LIKE ?)"
        args += [f"%{q}%"] * 3
    return db.rows(sql + " ORDER BY i.pinned DESC, COALESCE(i.updated_at, i.created_at) DESC", args)


def idea_save(iid=None, **fields):
    if iid:
        db.update("ideas", iid, fields, IDEA_FIELDS)
    else:
        f = {k: v for k, v in fields.items() if k in IDEA_FIELDS}
        f["updated_at"] = db.now()
        iid = db.run(f"INSERT INTO ideas({', '.join(f)}) VALUES ({','.join('?' * len(f))})", tuple(f.values()))
    i = db.row("SELECT * FROM ideas WHERE id=?", (iid,))
    db.index("idea", iid, i["title"], f"{i['body']} {i['tags']}")
    return i


def idea_delete(iid):
    db.run("DELETE FROM ideas WHERE id=?", (iid,))
    db.unindex("idea", iid)


# ======================= Memory (personal knowledge) =======================
MEMORY_CATEGORIES = ["profile", "preference", "goal", "wish", "person", "health", "finance", "travel", "work", "general"]


def memories(category=None, q=None):
    sql, args = "SELECT * FROM memories WHERE 1=1", []
    if category:
        sql += " AND category=?"
        args.append(category)
    if q:
        sql += " AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
        args += [f"%{q}%"] * 3
    return db.rows(sql + " ORDER BY category, COALESCE(updated_at, created_at) DESC", args)


def memory_save(mid=None, **fields):
    allowed = {"category", "title", "content", "tags"}
    if mid:
        db.update("memories", mid, fields, allowed)
    else:
        f = {k: v for k, v in fields.items() if k in allowed}
        f["updated_at"] = db.now()
        mid = db.run(f"INSERT INTO memories({', '.join(f)}) VALUES ({','.join('?' * len(f))})", tuple(f.values()))
    m = db.row("SELECT * FROM memories WHERE id=?", (mid,))
    db.index("memory", mid, m["title"], f"{m['category']} {m['content']} {m['tags']}")
    return m


def memory_delete(mid):
    db.run("DELETE FROM memories WHERE id=?", (mid,))
    db.unindex("memory", mid)


# ======================= Vault =======================
VAULT_CATEGORIES = ["card", "login", "identity", "bank", "note"]


def _mask(cat, data):
    """A safe one-liner Donna (and the list view) may see without decrypting secrets."""
    if cat == "card" and data.get("number"):
        return f"•••• {str(data['number']).replace(' ', '')[-4:]}"
    if cat == "login" and data.get("username"):
        return data["username"]
    if cat == "bank" and data.get("account_number"):
        return f"A/C •••• {str(data['account_number'])[-4:]}"
    if cat == "identity" and data.get("number"):
        return f"•••• {str(data['number'])[-4:]}"
    return ""


def vault_list():
    return db.rows("SELECT id, category, title, hint, created_at, updated_at FROM vault ORDER BY category, title")


def vault_get(vid):
    v = db.row("SELECT * FROM vault WHERE id=?", (vid,))
    if not v:
        return None
    v["data"] = secure.decrypt_item(v["data"])
    return v


def vault_save(vid=None, category="login", title="", data=None):
    blob = secure.encrypt_item(data or {})
    hint = _mask(category, data or {})
    if vid:
        db.run("UPDATE vault SET category=?, title=?, hint=?, data=?, updated_at=? WHERE id=?",
               (category, title, hint, blob, db.now(), vid))
    else:
        vid = db.run("INSERT INTO vault(category,title,hint,data,updated_at) VALUES (?,?,?,?,?)",
                     (category, title, hint, blob, db.now()))
    # Only the title + category are searchable. Secret values never enter the index.
    db.index("vault", vid, title, f"{category} {hint}")
    return {"id": vid, "category": category, "title": title, "hint": hint}


def vault_delete(vid):
    db.run("DELETE FROM vault WHERE id=?", (vid,))
    db.unindex("vault", vid)


# ======================= Notifications =======================
def notify(title, body="", link=""):
    db.run("INSERT INTO notifications(title, body, link) VALUES (?,?,?)", (title, body, link))
    try:
        from . import telegram
        telegram.push(title, body)
    except Exception:
        pass
