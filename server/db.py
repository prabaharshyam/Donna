"""SQLite storage for Donna. One file, WAL mode, full-text search across everything."""
import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.environ.get("DONNA_DATA") or Path(__file__).resolve().parent.parent / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "donna.db"

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, emoji TEXT DEFAULT '', color TEXT DEFAULT '',
  group_name TEXT DEFAULT '', sort INTEGER DEFAULT 0, archived INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now','localtime')));

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
  title TEXT NOT NULL, note TEXT DEFAULT '', due_date TEXT, reminder_at TEXT, repeat TEXT DEFAULT '',
  important INTEGER DEFAULT 0, my_day TEXT, completed INTEGER DEFAULT 0, completed_at TEXT,
  tags TEXT DEFAULT '', sort INTEGER DEFAULT 0, reminder_sent INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT);

CREATE TABLE IF NOT EXISTS steps (
  id INTEGER PRIMARY KEY, task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
  title TEXT NOT NULL, done INTEGER DEFAULT 0, sort INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS journal (
  id INTEGER PRIMARY KEY, date TEXT UNIQUE NOT NULL, title TEXT DEFAULT '', body TEXT DEFAULT '',
  mood TEXT DEFAULT '', tags TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT);

CREATE TABLE IF NOT EXISTS ideas (
  id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  title TEXT DEFAULT '', body TEXT DEFAULT '', color TEXT DEFAULT '', pinned INTEGER DEFAULT 0,
  archived INTEGER DEFAULT 0, tags TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT);

CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY, category TEXT DEFAULT 'general', title TEXT NOT NULL, content TEXT DEFAULT '',
  tags TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT);

CREATE TABLE IF NOT EXISTS vault (
  id INTEGER PRIMARY KEY, category TEXT DEFAULT 'login', title TEXT NOT NULL, hint TEXT DEFAULT '',
  data BLOB NOT NULL, created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
  location TEXT DEFAULT '', description TEXT DEFAULT '', all_day INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now','localtime')));

CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY, title TEXT DEFAULT 'New conversation',
  created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY, conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL, content TEXT NOT NULL, meta TEXT DEFAULT '{}',
  created_at TEXT DEFAULT (datetime('now','localtime')));

CREATE TABLE IF NOT EXISTS sent_log (key TEXT PRIMARY KEY, sent_at TEXT DEFAULT (datetime('now','localtime')));

CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY, title TEXT, body TEXT, link TEXT DEFAULT '', seen INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now','localtime')));

CREATE TABLE IF NOT EXISTS people (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, relationship TEXT DEFAULT '', birthday TEXT DEFAULT '',
  email TEXT DEFAULT '', phone TEXT DEFAULT '', family TEXT DEFAULT '', notes TEXT DEFAULT '',
  contact_every_days INTEGER DEFAULT 0, last_contact TEXT,
  created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT);

CREATE TABLE IF NOT EXISTS interactions (
  id INTEGER PRIMARY KEY, person_id INTEGER REFERENCES people(id) ON DELETE CASCADE,
  date TEXT NOT NULL, note TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime')));

CREATE TABLE IF NOT EXISTS goals (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, why TEXT DEFAULT '', area TEXT DEFAULT '', target_date TEXT,
  status TEXT DEFAULT 'active', created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT);

CREATE TABLE IF NOT EXISTS milestones (
  id INTEGER PRIMARY KEY, goal_id INTEGER REFERENCES goals(id) ON DELETE CASCADE,
  title TEXT NOT NULL, done INTEGER DEFAULT 0, due_date TEXT, sort INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS renewals (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT DEFAULT 'subscription', amount REAL,
  currency TEXT DEFAULT '', due_date TEXT NOT NULL, cycle TEXT DEFAULT '', remind_days INTEGER DEFAULT 7,
  notes TEXT DEFAULT '', doc_id INTEGER, status TEXT DEFAULT 'active',
  created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, filename TEXT, stored_name TEXT, mime TEXT, size INTEGER,
  summary TEXT DEFAULT '', dates TEXT DEFAULT '[]', status TEXT DEFAULT 'processing', error TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now','localtime')));

CREATE TABLE IF NOT EXISTS doc_chunks (
  id INTEGER PRIMARY KEY, doc_id INTEGER REFERENCES documents(id) ON DELETE CASCADE, idx INTEGER, text TEXT);

CREATE TABLE IF NOT EXISTS inbox_items (
  id INTEGER PRIMARY KEY, msg_id TEXT, folder TEXT DEFAULT 'inbox', sender TEXT DEFAULT '', subject TEXT DEFAULT '',
  received TEXT DEFAULT '', title TEXT NOT NULL, due_date TEXT, reason TEXT DEFAULT '', status TEXT DEFAULT 'pending',
  task_id INTEGER, created_at TEXT DEFAULT (datetime('now','localtime')));

CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY, week_start TEXT UNIQUE, stats TEXT, narrative TEXT,
  created_at TEXT DEFAULT (datetime('now','localtime')));

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, created_at TEXT DEFAULT (datetime('now','localtime')), expires TEXT, agent TEXT DEFAULT '');

CREATE TABLE IF NOT EXISTS goal_reflections (
  id INTEGER PRIMARY KEY, goal_id INTEGER REFERENCES goals(id) ON DELETE CASCADE, date TEXT NOT NULL,
  text TEXT NOT NULL, confidence INTEGER, mentor_reply TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now','localtime')), UNIQUE(goal_id, date));

CREATE TABLE IF NOT EXISTS xp_log (
  id INTEGER PRIMARY KEY, key TEXT UNIQUE, goal_id INTEGER, kind TEXT, points INTEGER, note TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now','localtime')));

CREATE TABLE IF NOT EXISTS mentor_messages (
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now','localtime')));

CREATE VIRTUAL TABLE IF NOT EXISTS search_idx USING fts5(kind, ref_id UNINDEXED, title, body, tokenize='porter unicode61');
"""


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(DB_PATH, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        _local.conn = c
    return c


def init():
    c = conn()
    c.executescript(SCHEMA)
    def add_col(table, col, ddl):
        if col not in {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    add_col("tasks", "goal_id", "INTEGER REFERENCES goals(id) ON DELETE SET NULL")
    add_col("tasks", "milestone_id", "INTEGER REFERENCES milestones(id) ON DELETE SET NULL")
    add_col("goals", "mentor_plan", "TEXT DEFAULT ''")
    add_col("goals", "achieved_at", "TEXT")
    add_col("goals", "closing_note", "TEXT DEFAULT ''")
    add_col("milestones", "done_at", "TEXT")
    # v3 goal statuses: active / achieved / let_go  (older builds used done / paused)
    c.execute("UPDATE goals SET status='achieved', achieved_at=COALESCE(achieved_at, updated_at) WHERE status='done'")
    c.execute("UPDATE goals SET status='active' WHERE status='paused'")
    if not c.execute("SELECT 1 FROM projects LIMIT 1").fetchone():
        c.executemany("INSERT INTO projects(name, emoji, sort) VALUES (?,?,?)",
                      [("Personal", "🏠", 0), ("Work", "💼", 1)])
    c.commit()


def now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def rows(sql, args=()):
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def row(sql, args=()):
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def run(sql, args=()):
    c = conn()
    cur = c.execute(sql, args)
    c.commit()
    return cur.lastrowid


def update(table: str, id_: int, fields: dict, allowed: set):
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    if "updated_at" in _columns(table):
        fields["updated_at"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    run(f"UPDATE {table} SET {cols} WHERE id=?", (*fields.values(), id_))


_colcache = {}


def _columns(table):
    if table not in _colcache:
        _colcache[table] = {r["name"] for r in rows(f"PRAGMA table_info({table})")}
    return _colcache[table]


# ---------- settings ----------
def get_setting(key, default=None):
    r = row("SELECT value FROM settings WHERE key=?", (key,))
    return json.loads(r["value"]) if r else default


def set_setting(key, value):
    run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)))


# ---------- search index ----------
def index(kind: str, ref_id: int, title: str, body: str):
    c = conn()
    c.execute("DELETE FROM search_idx WHERE kind=? AND ref_id=?", (kind, ref_id))
    c.execute("INSERT INTO search_idx(kind, ref_id, title, body) VALUES (?,?,?,?)",
              (kind, ref_id, title or "", body or ""))
    c.commit()


def unindex(kind: str, ref_id: int):
    run("DELETE FROM search_idx WHERE kind=? AND ref_id=?", (kind, ref_id))


def search(query: str, kinds=None, limit=8):
    """BM25 full-text search. Falls back to OR-matching words so loose questions still hit."""
    words = [w for w in "".join(ch if ch.isalnum() else " " for ch in query.lower()).split()
             if len(w) > 2 and w not in _STOP]
    if not words:
        return []
    fts = " OR ".join(f'"{w}"*' for w in words)
    sql = "SELECT kind, ref_id, title, snippet(search_idx, 3, '', '', ' … ', 24) AS snip, bm25(search_idx) AS score FROM search_idx WHERE search_idx MATCH ?"
    args = [fts]
    if kinds:
        sql += f" AND kind IN ({','.join('?' * len(kinds))})"
        args += list(kinds)
    sql += " ORDER BY score LIMIT ?"
    args.append(limit)
    try:
        return rows(sql, args)
    except sqlite3.OperationalError:
        return []


_STOP = set("""the and for with what whats when where who how my me is are was were you your our of to in on at
a an it its this that these those do does did can could would should please tell show give find about from
have has had any all get got i im id ive be been being there their them they we us not no yes just also
donna""".split())
