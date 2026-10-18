"""Donna's language-model layer.

Two providers behind one interface used by agents, mentor, review, inbox and docs:
  * "claude" (default): Anthropic Claude API via the official SDK
  * "ollama": a local model through Ollama's HTTP API

Internally, conversations use a simple dict format:
  {"role": "system"|"user"|"assistant"|"tool", "content": str,
   "tool_calls": [...]  (assistant), "tool_call_id"/"tool_name" (tool), "images": [b64] (user)}
Each provider converts that to its own wire format.

The system prompt may contain VOLATILE_MARK: everything before it is stable (persona + skill)
and is prompt-cached on Claude; everything after it (time, retrieved notes) changes per request.
"""
import base64
import json
import time
import urllib.request
import uuid

from . import db, secure

VOLATILE_MARK = "\n\n[[VOLATILE]]\n\n"
CLAUDE_MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
# Server-side refusal fallback ("default" routing). Not available for Haiku.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-5", "claude-fable-5-1"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def provider():
    return db.get_setting("llm_provider", "claude")


def model():
    if provider() == "claude":
        return db.get_setting("claude_model", "claude-opus-5-5")
    return db.get_setting("ollama_model", "qwen3.5:4b")


# ============================== Claude ==============================
_client_cache = {}


def _claude():
    import anthropic
    key = secure.get_secret("anthropic_api_key")
    if key not in _client_cache:
        # With no saved key, the SDK resolves ANTHROPIC_API_KEY or an `ant auth login` profile.
        _client_cache.clear()
        _client_cache[key] = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    return _client_cache[key]


def _media_type(b64: str) -> str:
    head = base64.b64decode(b64[:32] + "=" * (-len(b64[:32]) % 4))
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head[:3] == b"GIF":
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _strict_schema(schema):
    """Structured outputs need additionalProperties: false on every object."""
    if isinstance(schema, dict):
        s = {k: _strict_schema(v) for k, v in schema.items()}
        if s.get("type") == "object":
            s.setdefault("additionalProperties", False)
        return s
    if isinstance(schema, list):
        return [_strict_schema(x) for x in schema]
    return schema


def _split_system(text):
    stable, _, volatile = text.partition(VOLATILE_MARK)
    blocks = [{"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}}]
    if volatile.strip():
        blocks.append({"type": "text", "text": volatile})
    return blocks


def _to_claude(messages):
    """Internal format → (system blocks, Claude messages)."""
    system, out = None, []
    for m in messages:
        role = m["role"]
        if role == "system":
            if system is None and not out:
                system = _split_system(m["content"])
            elif out and out[-1]["role"] == "user":
                out.append({"role": "system", "content": m["content"]})  # mid-conversation operator note
            else:
                out.append({"role": "user", "content": f"(Note from the Donna app) {m['content']}"})
        elif role == "assistant":
            if m.get("_claude_content") is not None:
                out.append({"role": "assistant", "content": m["_claude_content"]})  # unchanged, incl. thinking blocks
                continue
            blocks = [{"type": "text", "text": m["content"]}] if (m.get("content") or "").strip() else []
            for c in m.get("tool_calls") or []:
                args = c["function"].get("arguments") or {}
                blocks.append({"type": "tool_use", "id": c.get("id") or "toolu_" + uuid.uuid4().hex[:24],
                               "name": c["function"]["name"], "input": json.loads(args) if isinstance(args, str) else args})
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "(no reply)"}]})
        elif role == "tool":
            block = {"type": "tool_result", "tool_use_id": m.get("tool_call_id"), "content": m["content"]}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) and \
                    out[-1]["content"] and out[-1]["content"][0].get("type") == "tool_result":
                out[-1]["content"].append(block)  # all results for one turn go in a single user message
            else:
                out.append({"role": "user", "content": [block]})
        else:
            if m.get("images"):
                content = [{"type": "image", "source": {"type": "base64", "media_type": _media_type(b), "data": b}} for b in m["images"]]
                content.append({"type": "text", "text": m["content"]})
                out.append({"role": "user", "content": content})
            else:
                out.append({"role": "user", "content": m["content"]})
    if out and out[0]["role"] != "user":  # the API requires the conversation to open with a user turn
        out.insert(0, {"role": "user", "content": "(Earlier in this conversation)"})
    return system, out


def _to_claude_tools(tools):
    out = []
    for t in tools or []:
        f = t["function"]
        out.append({"name": f["name"], "description": f.get("description", ""), "input_schema": f["parameters"],
                    "eager_input_streaming": True})
    return out


def _claude_params(messages, tools=None, effort=None, max_tokens=16000):
    system, msgs = _to_claude(messages)
    mdl = model()
    p = {"model": mdl, "max_tokens": max_tokens, "messages": msgs,
         "output_config": {"effort": effort or db.get_setting("claude_effort", "medium")},
         "cache_control": {"type": "ephemeral"}}
    if system:
        p["system"] = system
    if tools:
        p["tools"] = _to_claude_tools(tools)
    if mdl in FALLBACK_MODELS:
        p["betas"] = [FALLBACK_BETA]
        p["fallbacks"] = "default"
    return p


def _friendly(e):
    import anthropic
    if isinstance(e, anthropic.AuthenticationError):
        return RuntimeError("Claude API key is missing or invalid. Add it in Admin → AI model.")
    if isinstance(e, anthropic.PermissionDeniedError):
        return RuntimeError("This API key can't use the selected Claude model. Check Admin → AI model.")
    if isinstance(e, anthropic.NotFoundError):
        return RuntimeError(f"Claude model '{model()}' wasn't found. Pick another in Admin → AI model.")
    if isinstance(e, anthropic.RateLimitError):
        return RuntimeError("Claude is rate-limiting requests right now. Try again in a minute.")
    if isinstance(e, anthropic.APIStatusError):
        return RuntimeError(f"Claude API error {e.status_code}: {getattr(e, 'message', e)}")
    if isinstance(e, anthropic.APIConnectionError):
        return RuntimeError("Can't reach the Claude API. Check your internet connection.")
    return e


REFUSAL_TEXT = "I can't help with that one. Try asking a different way."


def _claude_chat_stream(messages, tools):
    import anthropic
    params = _claude_params(messages, tools)
    for attempt in range(2):
        text = []
        try:
            with _claude().beta.messages.stream(**params) as stream:
                for event in stream:
                    if event.type == "text":
                        text.append(event.text)
                        yield "token", event.text
                final = stream.get_final_message()
            break
        except ValueError:
            # Eager tool-input streaming produced JSON the SDK couldn't parse: retry once buffered.
            if attempt:
                raise
            for t in params.get("tools", []):
                t.pop("eager_input_streaming", None)
            yield "reset", None
        except anthropic.APIError as e:
            raise _friendly(e)
    if final.stop_reason == "refusal":
        yield "message", {"role": "assistant", "content": REFUSAL_TEXT}
        return
    calls = [b for b in final.content if b.type == "tool_use"]
    out = {"role": "assistant", "content": "".join(b.text for b in final.content if b.type == "text"),
           "_claude_content": final.content}
    if calls and final.stop_reason != "max_tokens":  # a truncated tool input must never run
        out["tool_calls"] = [{"id": b.id, "function": {"name": b.name, "arguments": b.input if isinstance(b.input, dict) else {}}}
                             for b in calls]
    yield "message", out


def _claude_complete(messages, fmt=None, effort=None):
    import anthropic
    params = _claude_params(messages, effort=effort)
    if fmt:
        params["output_config"]["format"] = {"type": "json_schema", "schema": _strict_schema(fmt)}
    try:
        resp = _claude().beta.messages.create(**params)
    except anthropic.APIError as e:
        raise _friendly(e)
    if resp.stop_reason == "refusal":
        if fmt:
            raise RuntimeError("Claude declined this request")
        return REFUSAL_TEXT
    return "".join(b.text for b in resp.content if b.type == "text")


_status_cache = {"at": 0, "value": None}


def _claude_status():
    import anthropic
    if time.time() - _status_cache["at"] < 120 and _status_cache["value"]:
        return _status_cache["value"]
    try:
        info = _claude().models.retrieve(model())
        v = {"ok": True, "provider": "claude", "model": model(), "model_installed": True,
             "display_name": getattr(info, "display_name", model()), "models": CLAUDE_MODELS}
    except anthropic.APIError as e:
        v = {"ok": False, "provider": "claude", "model": model(), "model_installed": False, "models": CLAUDE_MODELS,
             "error": str(_friendly(e))}
    except Exception as e:  # e.g. no credentials at all
        v = {"ok": False, "provider": "claude", "model": model(), "model_installed": False, "models": CLAUDE_MODELS,
             "error": "Add your Claude API key in Admin → AI model." if "api_key" in str(e).lower() or "auth" in str(e).lower() else str(e)}
    _status_cache.update(at=time.time(), value=v)
    return v


def reset_status():
    _status_cache.update(at=0, value=None)
    _client_cache.clear()


# ============================== Ollama ==============================
def ollama_url():
    return db.get_setting("ollama_url", "http://localhost:11434").rstrip("/")


def _post(path, payload, timeout=300):
    req = urllib.request.Request(ollama_url() + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def _ollama_messages(messages):
    out = []
    for m in messages:
        m = {k: v for k, v in m.items() if not k.startswith("_") and k != "tool_call_id"}
        if m["role"] == "system":
            m["content"] = m["content"].replace(VOLATILE_MARK, "\n\n")
        out.append(m)
    return out


def _ollama_options():
    return {"temperature": float(db.get_setting("llm_temperature", 0.4)), "num_ctx": int(db.get_setting("llm_num_ctx", 8192))}


def _ollama_chat_stream(messages, tools):
    payload = {"model": model(), "messages": _ollama_messages(messages), "stream": True,
               "think": bool(db.get_setting("llm_think", False)), "keep_alive": "30m", "options": _ollama_options()}
    if tools:
        payload["tools"] = tools
    content, tool_calls = [], []
    try:
        r = _post("/api/chat", payload)
    except Exception as e:
        raise RuntimeError(f"Can't reach Ollama ({e}). Is it running?")
    with r:
        for line in r:
            if not line.strip():
                continue
            chunk = json.loads(line)
            if chunk.get("error"):
                raise RuntimeError(chunk["error"])
            msg = chunk.get("message", {})
            if msg.get("content"):
                content.append(msg["content"])
                yield "token", msg["content"]
            if msg.get("tool_calls"):
                tool_calls.extend(msg["tool_calls"])
            if chunk.get("done"):
                break
    out = {"role": "assistant", "content": "".join(content)}
    if tool_calls:
        for c in tool_calls:
            c.setdefault("id", "call_" + uuid.uuid4().hex[:12])
        out["tool_calls"] = tool_calls
    yield "message", out


def _ollama_complete(messages, fmt=None, max_tokens=None, timeout=120):
    payload = {"model": model(), "messages": _ollama_messages(messages), "stream": False, "think": False, "keep_alive": "30m",
               "options": {**_ollama_options(), **({"num_predict": max_tokens} if max_tokens else {})}}
    if fmt:
        payload["format"] = fmt
    with _post("/api/chat", payload, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


def _ollama_status():
    try:
        with urllib.request.urlopen(ollama_url() + "/api/tags", timeout=3) as r:
            models = [m["name"] for m in json.loads(r.read()).get("models", [])]
        return {"ok": True, "provider": "ollama", "models": models, "model": model(), "model_installed": model() in models}
    except Exception as e:
        return {"ok": False, "provider": "ollama", "error": str(e), "models": [], "model": model()}


# ============================== Public interface ==============================
def chat_stream(messages, tools=None):
    """Yields ("token", str), optionally ("reset", None), and finally ("message", assistant_dict)."""
    if provider() == "claude":
        yield from _claude_chat_stream(messages, tools)
    else:
        yield from _ollama_chat_stream(messages, tools)


def complete(messages, fmt=None, max_tokens=None, timeout=120, effort=None):
    """One-shot completion. fmt = JSON schema for structured output. effort only applies to Claude."""
    if provider() == "claude":
        return _claude_complete(messages, fmt, effort)
    return _ollama_complete(messages, fmt, max_tokens, timeout)


def status():
    return _claude_status() if provider() == "claude" else _ollama_status()
