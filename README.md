# Donna: your personal assistant

## Run it
```bash
./run.sh
```
Open http://localhost:8765. Ollama must be running. Everything (data, AI, vault) stays on this Mac.

## What's inside
| Area | What it does |
|---|---|
| **Today** | Greeting, read-aloud briefing, "Talk to Donna" voice mode, schedule, My Day, birthdays/renewals/reach-outs |
| **Ask Donna** | Chat with a router + 9 specialist agents. Mic input, read-aloud replies, hands-free conversation |
| **Inbox** | Reads recent email over IMAP (read-only, incl. Sent) and suggests commitments as tasks |
| **To Do** | Microsoft To Do model: My Day, Important, Planned, lists, steps, reminders, repeat, notes, link to goals |
| **Calendar** | Week view, Google Calendar sync, meeting **prep packs** (people, open promises, talking points) |
| **Goals** | Goals → milestones → linked tasks, with progress |
| **Ideas** | Keep-style board |
| **Journal** | Daily entries, moods, streaks |
| **Weekly review** | Every Sunday evening (configurable): wins, slips, moods, goals, people, next week's 3 priorities. Emailed |
| **People** | Birthdays, families, notes, catch-up timeline, keep-in-touch cadence + nudges |
| **Renewals** | Subscriptions, bills, insurance, document expiries; alerts; monthly spend |
| **Documents** | Upload PDF/Word/text/photos; text is extracted (photos via Qwen vision), searchable, and key dates are detected |
| **Memory / Vault** | Personal facts (RAG) / AES-256 encrypted secrets |
| **Admin** | Every setting, Telegram pairing, voice, login + 2FA, hosting guide, editable agent skills |

## Agents & skills (`server/skills/*.md`)
Agents: `tasks` · `calendar` · `journal` · `ideas` · `memory` · `people` · `goals` · `renewals` · `briefing` · `general`, plus `router`.
Background skills: `inbox` (commitment extraction), `review` (weekly review), `prep` (talking points), `documents` (summary + dates).
Each agent sees only its own 3–6 tools. Data handed to the model is pre-digested into explicit facts ("no journal entries, mood unknown") so a small local model can't fill gaps with inventions.

## Phone
* **Telegram** (works with no hosting): Admin → Phone & Telegram. Create a bot with @BotFather, paste the token, send `/start <code>` to pair. Chat with Donna and receive reminders there. Vault secrets are never sent to Telegram.
* **Install as an app (PWA)**: once Donna is reachable from your phone, Safari → Share → Add to Home Screen.

## Security
* Without an app password, Donna only answers requests from this Mac.
* Admin → Login & hosting: app password (scrypt), optional TOTP 2FA, 30-day HttpOnly sessions, login rate limiting.
* Every write request needs an `X-Donna` header (CSRF defence); unknown `Host` headers are rejected (DNS-rebinding defence).
* To reach Donna from anywhere: set password + 2FA, then `cloudflared tunnel --url http://localhost:8765` (or a named tunnel on your domain), and set Admin → Data → App URL.

## Files
```
server/app.py          REST API, security middleware, streaming chat
server/agents.py       router, tools, agent loop
server/skills/         agent instructions (markdown, editable in Admin)
server/services.py     tasks / journal / ideas / memory / vault
server/life.py         people, goals, renewals, meeting prep
server/docs.py         document upload, extraction, chunking
server/inbox.py        IMAP triage
server/review.py       weekly review
server/telegram.py     Telegram bot (long polling)
server/auth.py         login, 2FA, sessions
server/scheduler.py    reminders, prep, renewals, birthdays, review, inbox scans
server/calendar_svc.py Google Calendar + local calendar
web/                   UI (vanilla JS, no build step) + PWA service worker
data/                  your database, documents, app key. Back this up; never commit it
```
Set `DONNA_DATA=/some/dir` to run a separate instance (e.g. for testing).
