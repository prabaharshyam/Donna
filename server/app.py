"""Donna API server. Run: ./run.sh  (serves the web UI on http://localhost:8765)"""
import base64
import json
import logging
from datetime import date, timedelta
from pathlib import Path

import urllib.parse

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import agents, auth, backup, calendar_svc as cal, db, docs as D, inbox, life as L, llm, mailer, review, scheduler, secure, \
    services as S, telegram, timeparse, gamify, mentor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Donna", docs_url=None, redoc_url=None, openapi_url=None)


@app.on_event("startup")
def _startup():
    backup.apply_pending_restore()
    db.init()
    _cloud_bootstrap()
    tz = timeparse.apply_timezone()
    logging.getLogger("donna").info("Timezone: %s, local time now %s", tz, db.now())
    scheduler.start()
    telegram.start()


def _cloud_bootstrap():
    """Configuration from environment variables, for hosted deployments."""
    import os
    log = logging.getLogger("donna")
    pub = os.environ.get("DONNA_PUBLIC_URL", "").strip().rstrip("/")
    if pub and db.get_setting("public_url") != pub:
        db.set_setting("public_url", pub)
    pw = os.environ.get("DONNA_ADMIN_PASSWORD", "")
    if pw and not auth.enabled():
        auth.set_password(pw)
        log.info("App password set from DONNA_ADMIN_PASSWORD")
    if auth.CLOUD and not auth.enabled():
        log.warning("DONNA_CLOUD is on but no app password is set: every page will refuse access until DONNA_ADMIN_PASSWORD is provided")


PUBLIC_PATHS = {"/", "/manifest.webmanifest", "/sw.js", "/share", "/api/google/callback"}


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if not auth.allowed_host(request.headers.get("host", "")):
        return JSONResponse({"detail": "This host isn't allowed. Add it under Admin → Security → Allowed hosts (from this Mac)."}, 421)
    local = auth.is_local(request)
    is_api = path.startswith("/api/")
    # CSRF: browsers can't add custom headers cross-site without a CORS preflight, which we never allow.
    if is_api and request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-donna") != "1":
        return JSONResponse({"detail": "Forbidden"}, 403)
    public = path in PUBLIC_PATHS or path.startswith("/api/auth/") or path.startswith("/static/")
    if auth.enabled():
        if not public and not auth.valid_session(request.cookies.get(auth.COOKIE)):
            return JSONResponse({"detail": "Please sign in", "auth": True}, 401) if is_api else RedirectResponse("/")
    elif not local and not public:
        return JSONResponse({"detail": "Remote access is off until an app password is set (Admin → Login on the Mac, or DONNA_ADMIN_PASSWORD on a server)."}, 403)
    resp = await call_next(request)
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Permissions-Policy"] = "microphone=(self), camera=()"
    if request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https":
        resp.headers["Strict-Transport-Security"] = "max-age=31536000"
    return resp


@app.exception_handler(PermissionError)
def _perm(_req, exc):
    return JSONResponse({"detail": str(exc), "locked": True}, status_code=423)


@app.exception_handler(ValueError)
def _val(_req, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(RuntimeError)
def _rt(_req, exc):
    return JSONResponse({"detail": str(exc)}, status_code=502)


def _404(x):
    if not x:
        raise HTTPException(404, "Not found")
    return x


# ---------------- Bootstrap / search ----------------
@app.get("/api/bootstrap")
def bootstrap():
    return {
        "user_name": db.get_setting("user_name", ""), "projects": S.projects(), "counts": S.task_counts(),
        "vault": {"configured": secure.vault_configured(), "unlocked": secure.vault_unlocked()},
        "google": {"configured": cal.google_configured(), "connected": cal.google_connected(),
                   "account": db.get_setting("google_account", "")},
        "email": mailer.configured(), "streak": S.journal_streak(), "theme": db.get_setting("theme", "system"),
        "onboarded": bool(db.get_setting("onboarded", False)),
        "inbox_pending": db.row("SELECT COUNT(*) n FROM inbox_items WHERE status='pending'")["n"],
        "renewals_soon": len(L.renewals(days_ahead=7)), "birthdays_soon": len(L.upcoming_birthdays(7)),
        "telegram": bool(db.get_setting("telegram_chat_id")), "auth": auth.enabled(),
    }


@app.get("/api/search")
def search(q: str):
    return [x for x in (agents._hydrate(h) for h in db.search(q, limit=20)) if x] if q else []


# ---------------- Projects ----------------
@app.get("/api/projects")
def projects():
    return S.projects()


@app.post("/api/projects")
def project_create(b: dict = Body(...)):
    pid = db.run("INSERT INTO projects(name, emoji, color, sort) VALUES (?,?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM projects))",
                 (b["name"].strip(), b.get("emoji", ""), b.get("color", "")))
    return db.row("SELECT * FROM projects WHERE id=?", (pid,))


@app.patch("/api/projects/{pid}")
def project_update(pid: int, b: dict = Body(...)):
    db.update("projects", pid, b, {"name", "emoji", "color", "group_name", "sort", "archived"})
    return db.row("SELECT * FROM projects WHERE id=?", (pid,))


@app.delete("/api/projects/{pid}")
def project_delete(pid: int):
    for t in db.rows("SELECT id FROM tasks WHERE project_id=?", (pid,)):
        db.unindex("task", t["id"])
    db.run("DELETE FROM projects WHERE id=?", (pid,))
    return {"ok": True}


# ---------------- Tasks ----------------
@app.get("/api/tasks")
def tasks(view: str = "all", project_id: int = None, q: str = None):
    return S.list_tasks(view, project_id, q)


@app.get("/api/tasks/counts")
def task_counts():
    return {"counts": S.task_counts(), "projects": S.projects()}


@app.get("/api/tasks/{tid}")
def task_get(tid: int):
    return _404(S.get_task(tid))


@app.post("/api/tasks")
def task_create(b: dict = Body(...)):
    title = b.pop("title", "").strip()
    if not title:
        raise HTTPException(400, "Title required")
    return S.create_task(title, b.pop("project_id", None), **b)


@app.patch("/api/tasks/{tid}")
def task_update(tid: int, b: dict = Body(...)):
    _404(S.get_task(tid))
    return S.update_task(tid, b)


@app.delete("/api/tasks/{tid}")
def task_delete(tid: int):
    S.delete_task(tid)
    return {"ok": True}


@app.post("/api/tasks/{tid}/steps")
def step_add(tid: int, b: dict = Body(...)):
    return S.add_step(tid, b["title"])


@app.patch("/api/steps/{sid}")
def step_update(sid: int, b: dict = Body(...)):
    db.update("steps", sid, b, {"title", "done", "sort"})
    return S.get_task(db.row("SELECT task_id FROM steps WHERE id=?", (sid,))["task_id"])


@app.delete("/api/steps/{sid}")
def step_delete(sid: int):
    s = _404(db.row("SELECT task_id FROM steps WHERE id=?", (sid,)))
    db.run("DELETE FROM steps WHERE id=?", (sid,))
    return S.get_task(s["task_id"])


# ---------------- Journal ----------------
@app.get("/api/journal")
def journal_list(q: str = None):
    return {"entries": S.journal_list(365, q), "streak": S.journal_streak()}


@app.get("/api/journal/{d}")
def journal_get(d: str):
    return S.journal_get(d) or {"date": d, "title": "", "body": "", "mood": "", "tags": ""}


@app.put("/api/journal/{d}")
def journal_put(d: str, b: dict = Body(...)):
    return S.journal_save(d, b.get("body"), b.get("title"), b.get("mood"), b.get("tags"))


@app.delete("/api/journal/{d}")
def journal_delete(d: str):
    j = S.journal_get(d)
    if j:
        db.run("DELETE FROM journal WHERE id=?", (j["id"],))
        db.unindex("journal", j["id"])
    return {"ok": True}


# ---------------- Ideas ----------------
@app.get("/api/ideas")
def ideas(project_id: int = None, q: str = None, archived: bool = False):
    return S.ideas(project_id, q, archived)


@app.post("/api/ideas")
def idea_create(b: dict = Body(...)):
    return S.idea_save(**b)


@app.patch("/api/ideas/{iid}")
def idea_update(iid: int, b: dict = Body(...)):
    return S.idea_save(iid, **b)


@app.delete("/api/ideas/{iid}")
def idea_delete(iid: int):
    S.idea_delete(iid)
    return {"ok": True}


@app.post("/api/ideas/{iid}/to-task")
def idea_to_task(iid: int):
    i = _404(db.row("SELECT * FROM ideas WHERE id=?", (iid,)))
    return S.create_task(i["title"] or i["body"][:80], i["project_id"], note=i["body"])


# ---------------- Memories ----------------
@app.get("/api/memories")
def memories(category: str = None, q: str = None):
    return {"items": S.memories(category, q), "categories": S.MEMORY_CATEGORIES}


@app.post("/api/memories")
def memory_create(b: dict = Body(...)):
    return S.memory_save(**b)


@app.patch("/api/memories/{mid}")
def memory_update(mid: int, b: dict = Body(...)):
    return S.memory_save(mid, **b)


@app.delete("/api/memories/{mid}")
def memory_delete(mid: int):
    S.memory_delete(mid)
    return {"ok": True}


# ---------------- Vault ----------------
@app.get("/api/vault/status")
def vault_status():
    return {"configured": secure.vault_configured(), "unlocked": secure.vault_unlocked(),
            "autolock_min": db.get_setting("vault_autolock_min", 15)}


@app.post("/api/vault/setup")
def vault_setup(b: dict = Body(...)):
    secure.vault_setup(b["password"])
    return vault_status()


@app.post("/api/vault/unlock")
def vault_unlock(b: dict = Body(...)):
    if not secure.vault_unlock(b.get("password", "")):
        raise HTTPException(401, "Wrong master password")
    return vault_status()


@app.post("/api/vault/lock")
def vault_lock():
    secure.vault_lock()
    return vault_status()


@app.get("/api/vault")
def vault_list():
    return {"items": S.vault_list(), "unlocked": secure.vault_unlocked()}


@app.get("/api/vault/{vid}")
def vault_get(vid: int):
    return _404(S.vault_get(vid))


@app.get("/api/vault-cards")
def vault_cards(ids: str):
    out = []
    for i in [int(x) for x in ids.split(",") if x.strip().isdigit()]:
        v = db.row("SELECT id, category, title, hint FROM vault WHERE id=?", (i,))
        if v:
            out.append(v)
    return {"items": out, "unlocked": secure.vault_unlocked()}


@app.post("/api/vault")
def vault_create(b: dict = Body(...)):
    return S.vault_save(None, b.get("category", "login"), b["title"], b.get("data", {}))


@app.patch("/api/vault/{vid}")
def vault_update(vid: int, b: dict = Body(...)):
    return S.vault_save(vid, b.get("category", "login"), b["title"], b.get("data", {}))


@app.delete("/api/vault/{vid}")
def vault_delete(vid: int):
    if not secure.vault_unlocked():
        raise PermissionError("Unlock the vault to delete items")
    S.vault_delete(vid)
    return {"ok": True}


# ---------------- Calendar ----------------
@app.get("/api/events")
def events(start: str = None, end: str = None):
    start = start or date.today().isoformat()
    end = end or (date.fromisoformat(start) + timedelta(days=13)).isoformat()
    return {"events": cal.list_events(start, end), "google": cal.google_connected()}


@app.post("/api/events")
def event_create(b: dict = Body(...)):
    return cal.create_event(b["title"], b["start"], b.get("end"), b.get("location", ""), b.get("description", ""),
                            bool(b.get("all_day")), b.get("target"))


@app.delete("/api/events/{source}/{eid}")
def event_delete(source: str, eid: str):
    cal.delete_event(source, eid)
    return {"ok": True}


@app.get("/api/free")
def free(d: str, duration: int = 30):
    return cal.free_slots(d, duration)


@app.get("/api/google/auth")
def google_auth():
    if not cal.google_configured():
        raise HTTPException(400, "Add your Google OAuth client ID and secret in Settings first")
    return RedirectResponse(cal.auth_url())


@app.get("/api/google/callback")
def google_callback(code: str = None, state: str = None, error: str = None):
    if error or not code:
        return RedirectResponse(f"/#/settings?google=error&msg={error or 'cancelled'}")
    try:
        cal.finish_oauth(code, state)
    except Exception as e:
        return RedirectResponse(f"/#/settings?google=error&msg={str(e)[:120]}")
    return RedirectResponse("/#/settings?google=connected")


@app.post("/api/google/disconnect")
def google_disconnect():
    cal.disconnect()
    return {"ok": True}


# ---------------- Chat ----------------
@app.get("/api/conversations")
def conversations():
    return db.rows("SELECT * FROM conversations ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 100")


@app.post("/api/conversations")
def conversation_create():
    cid = db.run("INSERT INTO conversations(updated_at) VALUES (?)", (db.now(),))
    return db.row("SELECT * FROM conversations WHERE id=?", (cid,))


@app.get("/api/conversations/{cid}")
def conversation_messages(cid: int):
    msgs = db.rows("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (cid,))
    for m in msgs:
        m["meta"] = json.loads(m["meta"] or "{}")
    return msgs


@app.delete("/api/conversations/{cid}")
def conversation_delete(cid: int):
    db.run("DELETE FROM conversations WHERE id=?", (cid,))
    return {"ok": True}


@app.post("/api/chat")
def chat(b: dict = Body(...)):
    text = (b.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Empty message")
    cid = b.get("conversation_id")
    if not cid:
        cid = db.run("INSERT INTO conversations(title, updated_at) VALUES (?,?)", (text[:60], db.now()))
    conv = _404(db.row("SELECT * FROM conversations WHERE id=?", (cid,)))
    if conv["title"] == "New conversation":
        db.run("UPDATE conversations SET title=? WHERE id=?", (text[:60], cid))

    def gen():
        yield json.dumps({"type": "conversation", "id": cid}) + "\n"
        final, meta = "", {}
        try:
            for ev in agents.run(cid, text, b.get("agent")):
                if ev["type"] == "final":
                    final, meta = ev["text"], ev["meta"]
                yield json.dumps(ev, default=str) + "\n"
        except Exception as e:
            logging.exception("chat failed")
            final = f"I couldn't think just now: {e}"
            yield json.dumps({"type": "error", "text": final}) + "\n"
        db.run("INSERT INTO messages(conversation_id, role, content) VALUES (?,?,?)", (cid, "user", text))
        db.run("INSERT INTO messages(conversation_id, role, content, meta) VALUES (?,?,?,?)",
               (cid, "assistant", final, json.dumps(meta)))
        db.run("UPDATE conversations SET updated_at=? WHERE id=?", (db.now(), cid))
        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------------- Notifications ----------------
@app.get("/api/notifications")
def notifications(unseen: bool = False):
    sql = "SELECT * FROM notifications" + (" WHERE seen=0" if unseen else "") + " ORDER BY id DESC LIMIT 30"
    return db.rows(sql)


@app.post("/api/notifications/seen")
def notifications_seen():
    db.run("UPDATE notifications SET seen=1 WHERE seen=0")
    return {"ok": True}


# ---------------- Settings / admin ----------------
PUBLIC_SETTINGS = {
    "user_name": "", "notify_email": "", "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_from": "",
    "email_enabled": True, "briefing_enabled": True, "briefing_time": "07:30", "journal_nudge_time": "21:00",
    "event_reminder_min": 15, "default_event_minutes": 30, "work_start": "09:00", "work_end": "18:00",
    "llm_provider": "claude", "claude_model": "claude-opus-5-5", "claude_effort": "medium",
    "ollama_url": "http://localhost:11434", "ollama_model": "qwen3.5:4b", "llm_temperature": 0.4, "llm_num_ctx": 8192,
    "llm_think": False, "google_client_id": "", "google_calendar_id": "primary", "public_url": "http://localhost:8765",
    "vault_autolock_min": 15, "custom_instructions": "", "theme": "system", "onboarded": False,
    "imap_host": "", "inbox_enabled": False, "inbox_interval_hours": 3, "inbox_days": 2, "inbox_scan_sent": True,
    "review_enabled": True, "review_day": 6, "review_time": "18:00", "prep_enabled": True, "prep_lead_min": 30,
    "prep_ai": True, "birthday_remind_days": 7, "nudge_weekday": 5, "telegram_notify": True, "allowed_hosts": "",
    "timezone": "Asia/Kolkata", "mentor_enabled": True, "reflection_nudge_time": "20:30",
}
SECRET_SETTINGS = {"smtp_password", "google_client_secret", "telegram_token", "anthropic_api_key"}


@app.get("/api/settings")
def settings_get():
    out = {k: db.get_setting(k, v) for k, v in PUBLIC_SETTINGS.items()}
    out["secrets"] = {k: bool(secure.get_secret(k)) for k in SECRET_SETTINGS}
    out["google_redirect_uri"] = cal.redirect_uri()
    out["google_connected"] = cal.google_connected()
    out["google_account"] = db.get_setting("google_account", "")
    return out


@app.put("/api/settings")
def settings_put(b: dict = Body(...)):
    for k, v in b.items():
        if k in PUBLIC_SETTINGS:
            db.set_setting(k, v)
        elif k in SECRET_SETTINGS and v:
            secure.set_secret(k, v)
    if {"llm_provider", "claude_model", "anthropic_api_key", "ollama_url", "ollama_model"} & b.keys():
        llm.reset_status()
    if b.get("timezone"):
        timeparse.apply_timezone(b["timezone"])
    if b.get("telegram_token"):
        db.set_setting("telegram_chat_id", "")
        telegram._state.update(bot="", offset=0)
    return settings_get()


@app.post("/api/settings/test-email")
def test_email():
    mailer.send("Donna is connected", "<p>Email reminders are working. I'll take it from here.</p>", "Email works.")
    return {"ok": True}


@app.get("/api/ai/status")
@app.get("/api/ollama/status")
def ollama_status():
    return llm.status()


@app.get("/api/briefing")
def briefing():
    inner, data = scheduler.briefing_html()
    return {"html": inner, "data": data}


@app.post("/api/briefing/send")
def briefing_send():
    inner, _ = scheduler.briefing_html()
    mailer.send(f"Your day: {date.today().strftime('%a %d %b')}", inner)
    return {"ok": True}


@app.get("/api/skills")
def skills():
    return [{"name": p.stem, "content": p.read_text()} for p in sorted(agents.SKILLS_DIR.glob("*.md"))]


@app.put("/api/skills/{name}")
def skill_put(name: str, b: dict = Body(...)):
    p = agents.SKILLS_DIR / f"{name}.md"
    if not p.exists():
        raise HTTPException(404, "Unknown skill")
    p.write_text(b["content"])
    return {"ok": True}


@app.get("/api/backup/full")
def backup_full(request: Request):
    _require_admin(request)
    return Response(backup.build_zip(), media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename=donna-full-backup-{date.today()}.zip"})


@app.post("/api/backup/restore")
async def backup_restore(request: Request, file: UploadFile = File(...)):
    _require_admin(request)
    backup.stage_restore(await file.read())
    backup.restart_soon()
    return {"ok": True, "restarting": True}


@app.get("/api/export")
def export():
    data = {t: db.rows(f"SELECT * FROM {t}") for t in
            ("projects", "tasks", "steps", "journal", "ideas", "memories", "events", "conversations", "messages")}
    data["vault_encrypted"] = [{**v, "data": base64.b64encode(v["data"]).decode()} for v in db.rows("SELECT * FROM vault")]
    return JSONResponse(data, headers={"Content-Disposition": f"attachment; filename=donna-backup-{date.today()}.json"})


# ---------------- People ----------------
@app.get("/api/people")
def people(q: str = None):
    return {"items": L.people(q), "due": [p["id"] for p in L.due_contacts()],
            "birthdays": [p["id"] for p in L.upcoming_birthdays(30)]}


@app.get("/api/people/{pid}")
def person_get(pid: int):
    return _404(L.person(pid))


@app.post("/api/people")
def person_create(b: dict = Body(...)):
    if not (b.get("name") or "").strip():
        raise HTTPException(400, "Name required")
    return L.person_save(**b)


@app.patch("/api/people/{pid}")
def person_update(pid: int, b: dict = Body(...)):
    return L.person_save(pid, **b)


@app.delete("/api/people/{pid}")
def person_delete(pid: int):
    L.person_delete(pid)
    return {"ok": True}


@app.post("/api/people/{pid}/interactions")
def interaction_add(pid: int, b: dict = Body(...)):
    return L.log_interaction(pid, b.get("note", ""), b.get("date"))


@app.delete("/api/interactions/{iid}")
def interaction_delete(iid: int):
    i = _404(db.row("SELECT person_id FROM interactions WHERE id=?", (iid,)))
    db.run("DELETE FROM interactions WHERE id=?", (iid,))
    last = db.row("SELECT MAX(date) d FROM interactions WHERE person_id=?", (i["person_id"],))["d"]
    db.run("UPDATE people SET last_contact=? WHERE id=?", (last, i["person_id"]))
    return L.person(i["person_id"])


# ---------------- Goals (3 active slots) ----------------
@app.exception_handler(L.GoalLimit)
def _goal_limit(_req, exc):
    return JSONResponse({"detail": str(exc), "goal_limit": True}, status_code=409)


@app.get("/api/goals")
def goals(status: str = None):
    return L.goals(status)


@app.get("/api/goals/board")
def goals_board():
    return {"active": L.goals("active"), "history": L.goals("achieved") + L.goals("let_go"),
            "max": L.MAX_ACTIVE_GOALS, "game": gamify.summary()}


@app.get("/api/goals/{gid}")
def goal_get(gid: int):
    g = _404(L.goal(gid))
    g["reflections"] = L.reflections(gid)
    return g


@app.post("/api/goals")
def goal_create(b: dict = Body(...)):
    ms = b.pop("milestones", [])
    b.pop("status", None)
    g = L.goal_save(**b)
    for m in ms:
        g = L.milestone_add(g["id"], m)
    return g


@app.patch("/api/goals/{gid}")
def goal_update(gid: int, b: dict = Body(...)):
    b.pop("status", None)  # status changes go through achieve / let-go / reactivate
    return L.goal_save(gid, **b)


@app.post("/api/goals/{gid}/achieve")
def goal_achieve(gid: int, b: dict = Body(default={})):
    return L.goal_achieve(gid, (b or {}).get("note", ""))


@app.post("/api/goals/{gid}/let-go")
def goal_let_go(gid: int, b: dict = Body(default={})):
    return L.goal_let_go(gid, (b or {}).get("note", ""))


@app.post("/api/goals/{gid}/reactivate")
def goal_reactivate(gid: int):
    return L.goal_reactivate(gid)


@app.delete("/api/goals/{gid}")
def goal_delete(gid: int):
    L.goal_delete(gid)
    return {"ok": True}


@app.post("/api/goals/{gid}/milestones")
def milestone_create(gid: int, b: dict = Body(...)):
    return L.milestone_add(gid, b["title"], b.get("due_date"))


@app.patch("/api/milestones/{mid}")
def milestone_update(mid: int, b: dict = Body(...)):
    m = _404(db.row("SELECT goal_id FROM milestones WHERE id=?", (mid,)))
    reward = None
    if "done" in b:
        _, reward = L.milestone_set_done(mid, bool(b.pop("done")))
    if b:
        db.update("milestones", mid, b, {"title", "due_date", "sort"})
    g = L.goal_save(m["goal_id"])
    g["reward"] = reward
    return g


@app.delete("/api/milestones/{mid}")
def milestone_delete(mid: int):
    m = _404(db.row("SELECT goal_id FROM milestones WHERE id=?", (mid,)))
    db.run("UPDATE tasks SET milestone_id=NULL WHERE milestone_id=?", (mid,))
    db.run("DELETE FROM milestones WHERE id=?", (mid,))
    return L.goal_save(m["goal_id"])


@app.post("/api/milestones/{mid}/tasks")
def milestone_task(mid: int, b: dict = Body(...)):
    _404(db.row("SELECT 1 FROM milestones WHERE id=?", (mid,)))
    return L.milestone_task_add(mid, b["title"], b.get("due_date"), b.get("reminder_at"))


@app.post("/api/milestones/{mid}/breakdown")
def milestone_breakdown(mid: int):
    _404(db.row("SELECT 1 FROM milestones WHERE id=?", (mid,)))
    return {"tasks": mentor.breakdown(mid)}


@app.post("/api/goals/{gid}/plan")
def goal_plan(gid: int):
    _404(L.goal(gid))
    return mentor.plan(gid)


@app.post("/api/goals/{gid}/plan/apply")
def goal_plan_apply(gid: int, b: dict = Body(...)):
    return mentor.apply_plan(gid, b)


@app.post("/api/goals/{gid}/reflections")
def goal_reflect(gid: int, b: dict = Body(...)):
    if not (b.get("text") or "").strip():
        raise HTTPException(400, "Write a few words first")
    c = b.get("confidence")
    return mentor.reflect(gid, b["text"], int(c) if c else None)


@app.get("/api/game")
def game():
    return gamify.summary()


# ---------------- Mentor (daily note on Today) ----------------
@app.get("/api/mentor/today")
def mentor_today():
    note = mentor.today_note()
    enabled = db.get_setting("mentor_enabled", True)
    if enabled and not note and not mentor.is_generating():
        mentor.generate_daily_async()
    cid = (db.get_setting("mentor_conv", {}) or {}).get("id") if note else None
    msgs = []
    if cid:
        msgs = db.rows("SELECT id, role, content, meta FROM messages WHERE conversation_id=? ORDER BY id", (cid,))
        for m in msgs:
            m["meta"] = json.loads(m["meta"] or "{}")
    return {"enabled": enabled, "generating": mentor.is_generating(), "conversation_id": cid, "messages": msgs,
            "goals": [{"id": g["id"], "title": g["title"], "progress": g["progress"], "reflected_today": g["reflected_today"]} for g in L.goals("active")],
            "game": gamify.summary()}


@app.post("/api/mentor/regenerate")
def mentor_regenerate():
    mentor.generate_daily_async(force=True)
    return {"generating": True}


# ---------------- Renewals ----------------
@app.get("/api/renewals")
def renewals(status: str = "active"):
    return {"items": L.renewals(status), "monthly": L.monthly_spend(), "categories": L.RENEWAL_CATEGORIES}


@app.post("/api/renewals")
def renewal_create(b: dict = Body(...)):
    return L.renewal_save(**b)


@app.patch("/api/renewals/{rid}")
def renewal_update(rid: int, b: dict = Body(...)):
    return L.renewal_save(rid, **b)


@app.post("/api/renewals/{rid}/done")
def renewal_done(rid: int, b: dict = Body(default={})):
    return _404(L.renewal_done(rid, (b or {}).get("new_due_date")))


@app.delete("/api/renewals/{rid}")
def renewal_delete(rid: int):
    L.renewal_delete(rid)
    return {"ok": True}


# ---------------- Documents ----------------
@app.get("/api/documents")
def documents():
    return D.documents()


@app.post("/api/documents")
async def document_upload(file: UploadFile = File(...)):
    data = await file.read()
    return D.save_upload(file.filename or "document", data, file.content_type or "")


@app.get("/api/documents/{did}/file")
def document_file(did: int):
    d = _404(db.row("SELECT * FROM documents WHERE id=?", (did,)))
    return FileResponse(D.DOC_DIR / d["stored_name"], filename=d["filename"], content_disposition_type="inline")


@app.get("/api/documents/{did}/text")
def document_text(did: int):
    return {"text": "\n\n".join(c["text"] for c in db.rows("SELECT text FROM doc_chunks WHERE doc_id=? ORDER BY idx", (did,)))}


@app.patch("/api/documents/{did}")
def document_update(did: int, b: dict = Body(...)):
    if "title" in b:
        db.run("UPDATE documents SET title=? WHERE id=?", (b["title"], did))
    return db.row("SELECT * FROM documents WHERE id=?", (did,))


@app.post("/api/documents/{did}/reprocess")
def document_reprocess(did: int):
    import threading
    db.run("UPDATE documents SET status='processing', error='' WHERE id=?", (did,))
    threading.Thread(target=D.process, args=(did,), daemon=True).start()
    return {"ok": True}


@app.delete("/api/documents/{did}")
def document_delete(did: int):
    D.delete(did)
    return {"ok": True}


# ---------------- Inbox triage ----------------
@app.get("/api/inbox")
def inbox_list(status: str = "pending"):
    return {"items": inbox.items(status), "status": db.get_setting("inbox_status", {}) or {},
            "configured": inbox.configured(), "enabled": db.get_setting("inbox_enabled", False), "imap_host": inbox.imap_host()}


@app.post("/api/inbox/scan")
def inbox_scan():
    if not inbox.configured():
        raise HTTPException(400, "Set up email (SMTP host, username and app password) in Admin first")
    inbox.scan_async()
    return {"started": True}


@app.post("/api/inbox/{iid}/accept")
def inbox_accept(iid: int, b: dict = Body(default={})):
    b = b or {}
    return inbox.accept(iid, b.get("project_id"), b.get("title"), b.get("due_date"))


@app.post("/api/inbox/{iid}/dismiss")
def inbox_dismiss(iid: int):
    inbox.dismiss(iid)
    return {"ok": True}


# ---------------- Weekly review & meeting prep ----------------
@app.get("/api/review")
def review_get(week: str = None):
    return {"review": review.get(week), "history": review.history(), "live": review.stats()}


@app.post("/api/review/generate")
def review_generate(b: dict = Body(default={})):
    return review.generate(send_email=bool((b or {}).get("email")))


@app.post("/api/prep")
def prep(b: dict = Body(...), ai: bool = False):
    p = L.meeting_prep(b)
    p["talking_points"] = L.talking_points(p) if ai and L.prep_has_substance(p) else ""
    return p


# ---------------- Telegram ----------------
@app.get("/api/telegram")
def telegram_status():
    return telegram.status()


@app.post("/api/telegram/unpair")
def telegram_unpair():
    db.set_setting("telegram_chat_id", "")
    return telegram.status()


@app.post("/api/telegram/test")
def telegram_test():
    if not db.get_setting("telegram_chat_id"):
        raise HTTPException(400, "Pair your Telegram first")
    telegram.send("👋 **Donna here.** Reminders will arrive in this chat.")
    return {"ok": True}


# ---------------- Auth ----------------
def _secure_cookie(request: Request):
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


@app.get("/api/auth/status")
def auth_status(request: Request):
    return {"enabled": auth.enabled(), "totp": auth.totp_enabled(),
            "signed_in": (not auth.enabled()) or auth.valid_session(request.cookies.get(auth.COOKIE)),
            "sessions": auth.session_count() if auth.enabled() else 0}


@app.post("/api/auth/login")
def auth_login(request: Request, b: dict = Body(...)):
    ip = request.client.host if request.client else "?"
    wait = auth.throttled(ip)
    if wait:
        raise HTTPException(429, f"Too many attempts. Try again in {wait}s")
    ok = auth.check_password(b.get("password", "")) and (not auth.totp_enabled() or auth.totp_verify(b.get("code", "")))
    if not ok:
        auth.record_fail(ip)
        raise HTTPException(401, "Wrong password" + (" or code" if auth.totp_enabled() else ""))
    auth.record_ok(ip)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, auth.create_session(request.headers.get("user-agent", "")), max_age=auth.SESSION_DAYS * 86400,
                    httponly=True, samesite="lax", secure=_secure_cookie(request))
    return resp


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    auth.end_session(request.cookies.get(auth.COOKIE))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE)
    return resp


def _require_admin(request: Request):
    """Changing security needs a signed-in session, or (before a password exists) this Mac."""
    if auth.enabled():
        if not auth.valid_session(request.cookies.get(auth.COOKIE)):
            raise HTTPException(401, "Please sign in")
    elif not auth.is_local(request):
        raise HTTPException(403, "Set the app password from this Mac")


@app.post("/api/auth/password")
def auth_password(request: Request, b: dict = Body(...)):
    _require_admin(request)
    if auth.enabled() and not auth.check_password(b.get("current", "")):
        raise HTTPException(401, "Current password is wrong")
    auth.set_password(b["password"])
    auth.end_all()
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, auth.create_session(request.headers.get("user-agent", "")), max_age=auth.SESSION_DAYS * 86400,
                    httponly=True, samesite="lax", secure=_secure_cookie(request))
    return resp


@app.post("/api/auth/disable")
def auth_disable(request: Request, b: dict = Body(...)):
    _require_admin(request)
    if not auth.check_password(b.get("current", "")):
        raise HTTPException(401, "Password is wrong")
    auth.disable()
    return {"ok": True}


@app.post("/api/auth/totp/begin")
def totp_begin(request: Request):
    _require_admin(request)
    if not auth.enabled():
        raise HTTPException(400, "Set an app password first")
    return auth.totp_begin()


@app.post("/api/auth/totp/confirm")
def totp_confirm(request: Request, b: dict = Body(...)):
    _require_admin(request)
    auth.totp_confirm(b.get("code", ""))
    return {"ok": True}


@app.post("/api/auth/totp/disable")
def totp_disable(request: Request, b: dict = Body(...)):
    _require_admin(request)
    if not auth.check_password(b.get("current", "")):
        raise HTTPException(401, "Password is wrong")
    auth.totp_disable()
    return {"ok": True}


@app.post("/api/auth/sessions/end")
def sessions_end(request: Request):
    _require_admin(request)
    auth.end_all()
    return {"ok": True}


# ---------------- PWA ----------------
@app.get("/manifest.webmanifest")
def manifest():
    return JSONResponse({
        "name": "Donna", "short_name": "Donna", "start_url": "/", "display": "standalone", "scope": "/",
        "background_color": "#F6F4F0", "theme_color": "#7A2E3A", "description": "Your private personal assistant",
        "icons": [{"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}],
        "share_target": {"action": "/share", "method": "GET", "params": {"title": "title", "text": "text", "url": "url"}},
        "shortcuts": [{"name": "Ask Donna", "url": "/#/chat"}, {"name": "New idea", "url": "/#/ideas"}, {"name": "Journal", "url": "/#/journal"}],
    }, media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(WEB / "sw.js", media_type="application/javascript", headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.get("/share")
def share(title: str = "", text: str = "", url: str = ""):
    content = " ".join(x for x in (title, text, url) if x).strip()
    return RedirectResponse("/#/chat?ask=" + urllib.parse.quote("Save this: " + content if content else ""))


# ---------------- Web UI ----------------
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})
