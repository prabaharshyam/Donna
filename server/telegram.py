"""Telegram bot: talk to Donna from your phone and receive reminders there.

Uses long polling (outbound HTTPS only), so it works while Donna runs on your Mac with
no hosting or open ports. Only one paired chat is ever answered. Vault secrets are never
sent to Telegram.
"""
import html
import json
import logging
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request

from . import db, secure

log = logging.getLogger("donna.telegram")
_state = {"offset": 0, "ok": False, "error": "", "bot": ""}


def token():
    return secure.get_secret("telegram_token")


def _api(method, params=None, timeout=35):
    url = f"https://api.telegram.org/bot{token()}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=timeout) as r:
        out = json.loads(r.read())
    if not out.get("ok"):
        raise RuntimeError(out.get("description", "Telegram error"))
    return out["result"]


def pairing_code():
    code = db.get_setting("telegram_pair_code")
    if not code:
        code = f"{secrets.randbelow(900000) + 100000}"
        db.set_setting("telegram_pair_code", code)
    return code


def status():
    return {"configured": bool(token()), "paired": bool(db.get_setting("telegram_chat_id")),
            "bot": _state["bot"], "running": _state["ok"], "error": _state["error"], "code": pairing_code(),
            "notify": db.get_setting("telegram_notify", True)}


def _fmt(text: str) -> str:
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"(?<![*\w])\*(?!\s)(.+?)\*(?!\w)", r"<i>\1</i>", t)


def send(text, chat_id=None):
    chat_id = chat_id or db.get_setting("telegram_chat_id")
    if not (token() and chat_id):
        return
    try:
        _api("sendMessage", {"chat_id": chat_id, "text": _fmt(text)[:4000], "parse_mode": "HTML", "disable_web_page_preview": "true"}, 20)
    except Exception as e:
        log.warning("telegram send failed: %s", e)


def push(title, body=""):
    if db.get_setting("telegram_notify", True) and db.get_setting("telegram_chat_id"):
        threading.Thread(target=send, args=(f"🔔 **{title}**" + (f"\n{body}" if body else ""),), daemon=True).start()


def _conversation():
    cid = db.get_setting("telegram_conversation_id")
    if not cid or not db.row("SELECT 1 FROM conversations WHERE id=?", (cid,)):
        cid = db.run("INSERT INTO conversations(title, updated_at) VALUES (?,?)", ("📱 Telegram", db.now()))
        db.set_setting("telegram_conversation_id", cid)
    return cid


def _handle(msg):
    from . import agents
    chat_id = str(msg["chat"]["id"])
    text = (msg.get("text") or "").strip()
    paired = str(db.get_setting("telegram_chat_id") or "")
    if not paired:
        if text.startswith("/start") and text.split()[-1] == pairing_code():
            db.set_setting("telegram_chat_id", chat_id)
            db.set_setting("telegram_pair_code", "")
            send("Paired. I'm all yours. Send me tasks, ideas, journal notes or questions, and I'll send your reminders here.", chat_id)
        else:
            send("This Donna is private. Pair it from Admin → Phone & Telegram by sending /start followed by the pairing code.", chat_id)
        return
    if chat_id != paired:
        return  # silently ignore strangers
    if not text:
        send("I can only read text for now. Type it out and I'll handle it.", chat_id)
        return
    if text in ("/start", "/help"):
        send("Just talk to me: “remind me to call the bank at 4pm”, “idea: …”, “what's on today?”, “journal: today was…”.", chat_id)
        return
    cid = _conversation()
    _api("sendChatAction", {"chat_id": chat_id, "action": "typing"}, 10)
    final, meta = "", {}
    try:
        for ev in agents.run(cid, text):
            if ev["type"] == "final":
                final, meta = ev["text"], ev["meta"]
    except Exception as e:
        final = f"I couldn't think just now: {e}"
    if meta.get("vault_cards"):
        final += "\n\n🔒 Vault items are only shown inside the Donna app, never over Telegram."
    db.run("INSERT INTO messages(conversation_id, role, content) VALUES (?,?,?)", (cid, "user", text))
    db.run("INSERT INTO messages(conversation_id, role, content, meta) VALUES (?,?,?,?)", (cid, "assistant", final, json.dumps(meta)))
    db.run("UPDATE conversations SET updated_at=? WHERE id=?", (db.now(), cid))
    send(final or "Done.", chat_id)


def loop():
    while True:
        if not token():
            _state.update(ok=False, bot="")
            time.sleep(15)
            continue
        try:
            if not _state["bot"]:
                _state["bot"] = _api("getMe", timeout=15).get("username", "")
            updates = _api("getUpdates", {"timeout": 25, "offset": _state["offset"], "allowed_updates": '["message"]'}, 35)
            _state.update(ok=True, error="")
            for u in updates:
                _state["offset"] = u["update_id"] + 1
                if u.get("message"):
                    try:
                        _handle(u["message"])
                    except Exception as e:
                        log.exception("telegram handle failed: %s", e)
        except Exception as e:
            _state.update(ok=False, error=str(e)[:200], bot="")
            time.sleep(20)


def start():
    threading.Thread(target=loop, daemon=True, name="donna-telegram").start()
