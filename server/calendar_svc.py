"""Calendar: Google Calendar (OAuth2, no SDK needed) with a local fallback calendar.

If Google is connected, events are read from and written to Google. Local events are always
merged in, so appointments you add before connecting Google still show up.
All times are local, formatted 'YYYY-MM-DDTHH:MM'.
"""
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from . import db, secure

SCOPES = "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.readonly"
API = "https://www.googleapis.com/calendar/v3"
_oauth_state = {}


def redirect_uri():
    return db.get_setting("public_url", "http://localhost:8765").rstrip("/") + "/api/google/callback"


def tz():
    return datetime.now().astimezone().tzinfo


def _to_rfc(local: str) -> str:
    return datetime.fromisoformat(local).replace(tzinfo=tz()).isoformat()


def _from_rfc(v: str) -> str:
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(tz()).strftime("%Y-%m-%dT%H:%M")


# ---------------- OAuth ----------------
def google_configured():
    return bool(db.get_setting("google_client_id")) and bool(secure.get_secret("google_client_secret"))


class GoogleDisconnected(RuntimeError):
    pass


TESTING_DAYS = 7  # Google expires refresh tokens after 7 days while the OAuth app is in "Testing"


def google_connected():
    return bool(secure.get_secret("google_refresh_token"))


def _mark_disconnected(reason):
    """Google revoked/expired our access: forget the dead tokens and tell the user once."""
    from . import services as S
    for k in ("google_refresh_token", "google_access_token", "google_access_expiry"):
        db.run("DELETE FROM settings WHERE key=?", (k,))
    first = not db.get_setting("google_needs_reconnect")
    db.set_setting("google_needs_reconnect", {"at": db.now(), "reason": str(reason)[:200]})
    if first:
        url = db.get_setting("public_url", "http://localhost:8765").rstrip("/") + "/#/settings?s=google"
        S.notify("🔌 Google Calendar disconnected",
                 f"Google ended Donna's access (it does this every {TESTING_DAYS} days for apps in Testing). Reconnect in 20 seconds: {url}",
                 "#/settings?s=google")


def _explain(msg):
    if "has not been used in project" in msg or "is disabled" in msg or "accessNotConfigured" in msg:
        import re as _re
        m = _re.search(r"project (\d+)", msg)
        url = "https://console.cloud.google.com/apis/library/calendar-json.googleapis.com" + (f"?project={m.group(1)}" if m else "")
        return f"The Google Calendar API is turned off in your Google Cloud project. Enable it here, wait a minute, then reload: {url}"
    return msg[:300]


def status():
    connected_at = db.get_setting("google_connected_at", "")
    out = {"configured": google_configured(), "connected": google_connected(),
           "needs_reconnect": bool(db.get_setting("google_needs_reconnect")), "account": db.get_setting("google_account", ""),
           "connected_at": connected_at, "testing_mode": bool(db.get_setting("google_testing_mode", True)),
           "error": (db.get_setting("google_last_error") or {}).get("message", "")}
    if out["connected"] and connected_at and out["testing_mode"]:
        age = (datetime.now() - datetime.fromisoformat(connected_at)).total_seconds() / 86400
        out["days_left"] = max(0, round(TESTING_DAYS - age, 1))
    return out


def health_check():
    """Force a token refresh so an expired connection is noticed even when nobody opens the calendar."""
    if not google_connected():
        return status()
    db.set_setting("google_access_expiry", 0)
    try:
        _access_token()
    except GoogleDisconnected:
        pass
    except Exception:
        pass  # offline etc.: try again next time
    return status()


def auth_url():
    state = secrets.token_urlsafe(16)
    _oauth_state[state] = time.time()
    q = urllib.parse.urlencode({
        "client_id": db.get_setting("google_client_id"), "redirect_uri": redirect_uri(),
        "response_type": "code", "scope": SCOPES, "access_type": "offline", "prompt": "consent", "state": state})
    return "https://accounts.google.com/o/oauth2/v2/auth?" + q


def _token_request(params):
    params.update(client_id=db.get_setting("google_client_id"), client_secret=secure.get_secret("google_client_secret"))
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=urllib.parse.urlencode(params).encode())
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def finish_oauth(code, state):
    if state not in _oauth_state:
        raise ValueError("Invalid OAuth state; please try connecting again")
    _oauth_state.pop(state, None)
    tok = _token_request({"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri()})
    if tok.get("refresh_token"):
        secure.set_secret("google_refresh_token", tok["refresh_token"])
    _store_access(tok)
    db.set_setting("google_connected_at", db.now())
    db.run("DELETE FROM settings WHERE key='google_needs_reconnect'")
    try:
        info = _api("GET", "/users/me/calendarList/primary")
        db.set_setting("google_account", info.get("id", ""))
    except Exception:
        pass


def _store_access(tok):
    secure.set_secret("google_access_token", tok["access_token"])
    db.set_setting("google_access_expiry", time.time() + int(tok.get("expires_in", 3600)) - 60)


def disconnect():
    for k in ("google_refresh_token", "google_access_token", "google_access_expiry", "google_account", "google_connected_at", "google_needs_reconnect"):
        db.run("DELETE FROM settings WHERE key=?", (k,))


def _access_token():
    if time.time() > float(db.get_setting("google_access_expiry", 0)):
        try:
            tok = _token_request({"refresh_token": secure.get_secret("google_refresh_token"), "grant_type": "refresh_token"})
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="ignore")
            if e.code in (400, 401) and ("invalid_grant" in body or "unauthorized" in body.lower()):
                _mark_disconnected("invalid_grant")
                raise GoogleDisconnected("Google Calendar is disconnected. Reconnect it in Admin → Google Calendar.")
            raise RuntimeError(f"Google sign-in error {e.code}: {body[:200]}")
        _store_access(tok)
    return secure.get_secret("google_access_token")


def _api(method, path, params=None, body=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + _access_token(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 401:  # access revoked by the user or by Google
            _mark_disconnected("401 from Calendar API")
            raise GoogleDisconnected("Google Calendar is disconnected. Reconnect it in Admin → Google Calendar.")
        raise RuntimeError(f"Google Calendar error {e.code}: {e.read().decode()[:300]}")


def calendar_id():
    return db.get_setting("google_calendar_id", "primary") or "primary"


# ---------------- Unified API ----------------
def list_events(start: str, end: str):
    """start/end: 'YYYY-MM-DD'. end is inclusive."""
    end_excl = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    out = []
    for e in db.rows("SELECT * FROM events WHERE start < ? AND end >= ? ORDER BY start", (end_excl, start)):
        out.append({**e, "id": str(e["id"]), "source": "local", "link": ""})
    res = {}
    if google_connected():
        try:
            res = _api("GET", f"/calendars/{urllib.parse.quote(calendar_id())}/events", {
                "timeMin": _to_rfc(start + "T00:00"), "timeMax": _to_rfc(end_excl + "T00:00"),
                "singleEvents": "true", "orderBy": "startTime", "maxResults": 250})
        except GoogleDisconnected:
            res = {}  # keep working with Donna's own calendar; the user has been told to reconnect
        except RuntimeError as e:
            res = {}  # e.g. Calendar API disabled: show Donna's own events and explain in the UI
            db.set_setting("google_last_error", {"at": db.now(), "message": _explain(str(e))})
        else:
            db.run("DELETE FROM settings WHERE key='google_last_error'")
    if res:
        for g in res.get("items", []):
            if g.get("status") == "cancelled":
                continue
            s, e_ = g.get("start", {}), g.get("end", {})
            all_day = "date" in s
            out.append({
                "id": g["id"], "source": "google", "title": g.get("summary", "(No title)"),
                "start": s["date"] + "T00:00" if all_day else _from_rfc(s["dateTime"]),
                "end": e_["date"] + "T00:00" if all_day else _from_rfc(e_["dateTime"]),
                "all_day": 1 if all_day else 0, "location": g.get("location", ""),
                "description": g.get("description", ""), "link": g.get("htmlLink", ""),
                "attendees": [a.get("email") for a in g.get("attendees", [])][:10]})
    out.sort(key=lambda e: e["start"])
    return out


def create_event(title, start, end=None, location="", description="", all_day=False, target=None):
    if not end:
        end = (datetime.fromisoformat(start) + timedelta(minutes=int(db.get_setting("default_event_minutes", 30)))).strftime("%Y-%m-%dT%H:%M")
    target = target or ("google" if google_connected() else "local")
    if target == "google":
        body = {"summary": title, "location": location, "description": description}
        if all_day:
            body["start"] = {"date": start[:10]}
            body["end"] = {"date": (date.fromisoformat(end[:10]) + timedelta(days=1)).isoformat()}
        else:
            body["start"] = {"dateTime": _to_rfc(start)}
            body["end"] = {"dateTime": _to_rfc(end)}
        lead = int(db.get_setting("event_reminder_min", 15))
        body["reminders"] = {"useDefault": False, "overrides": [{"method": "popup", "minutes": lead}]}
        try:
            g = _api("POST", f"/calendars/{urllib.parse.quote(calendar_id())}/events", body=body)
            return {"id": g["id"], "source": "google", "title": title, "start": start, "end": end, "link": g.get("htmlLink", "")}
        except GoogleDisconnected:
            local = create_event(title, start, end, location, description, all_day, target="local")
            local["warning"] = "Google Calendar is disconnected, so this was saved in Donna's own calendar. Reconnect Google in Admin."
            return local
    eid = db.run("INSERT INTO events(title,start,end,location,description,all_day) VALUES (?,?,?,?,?,?)",
                 (title, start, end, location, description, 1 if all_day else 0))
    db.index("event", eid, title, f"{start} {location} {description}")
    return {"id": str(eid), "source": "local", "title": title, "start": start, "end": end, "link": ""}


def delete_event(source, eid):
    if source == "google":
        _api("DELETE", f"/calendars/{urllib.parse.quote(calendar_id())}/events/{urllib.parse.quote(eid)}")
    else:
        db.run("DELETE FROM events WHERE id=?", (int(eid),))
        db.unindex("event", int(eid))


def free_slots(day: str, duration_min=30, day_start=None, day_end=None):
    day_start = day_start or db.get_setting("work_start", "09:00")
    day_end = day_end or db.get_setting("work_end", "18:00")
    events = [e for e in list_events(day, day) if not e.get("all_day")]
    cursor = datetime.fromisoformat(f"{day}T{day_start}")
    limit = datetime.fromisoformat(f"{day}T{day_end}")
    if day == date.today().isoformat():
        now = datetime.now().replace(second=0, microsecond=0)
        now += timedelta(minutes=(15 - now.minute % 15) % 15)
        cursor = max(cursor, now)
    slots = []
    for e in events:
        s, en = datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])
        if s - cursor >= timedelta(minutes=duration_min):
            slots.append((cursor, min(s, limit)))
        cursor = max(cursor, en)
    if limit - cursor >= timedelta(minutes=duration_min):
        slots.append((cursor, limit))
    return [{"start": a.strftime("%Y-%m-%dT%H:%M"), "end": b.strftime("%Y-%m-%dT%H:%M")} for a, b in slots if b > a]
