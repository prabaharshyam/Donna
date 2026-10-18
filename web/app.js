/* Donna — single-file SPA, no build step. */
"use strict";

// ============================== Utilities ==============================
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

const HDR = { "X-Donna": "1" };
async function api(method, url, body) {
  const isForm = body instanceof FormData;
  const res = await fetch(url, { method, headers: body && !isForm ? { ...HDR, "Content-Type": "application/json" } : HDR, body: body ? (isForm ? body : JSON.stringify(body)) : undefined });
  let data = null;
  try { data = await res.json(); } catch { /* empty */ }
  if (res.status === 401 && data && data.auth) showLogin();
  if (!res.ok) {
    const err = new Error((data && data.detail) || res.statusText);
    err.status = res.status;
    err.locked = data && data.locked;
    throw err;
  }
  return data;
}
const GET = (u) => api("GET", u), POST = (u, b) => api("POST", u, b || {}), PATCH = (u, b) => api("PATCH", u, b), PUT = (u, b) => api("PUT", u, b), DEL = (u) => api("DELETE", u);

const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  sparkle: '<path d="M12 3l1.9 5.6 5.6 1.9-5.6 1.9L12 18l-1.9-5.6-5.6-1.9 5.6-1.9z"/><path d="M19 3v4M17 5h4"/>',
  check: '<rect x="3" y="3" width="18" height="18" rx="5"/><path d="m8 12 3 3 5-6"/>',
  tick: '<path d="M20 6 9 17l-5-5"/>',
  calendar: '<rect x="3" y="4.5" width="18" height="16.5" rx="3"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/>',
  bulb: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.6.5 1.1 1.3 1.1 2.2h5c0-.9.5-1.7 1.1-2.2A6 6 0 0 0 12 3z"/>',
  book: '<path d="M4 19.5V5a2 2 0 0 1 2-2h14v15H6a2 2 0 0 0-2 2zm0 0A2 2 0 0 0 6 22h14"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  lock: '<rect x="4" y="10.5" width="16" height="10.5" rx="2.5"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/>',
  unlock: '<rect x="4" y="10.5" width="16" height="10.5" rx="2.5"/><path d="M8 10.5V7a4 4 0 0 1 7.8-1.2"/>',
  settings: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9z"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  repeat: '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  up: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  pin: '<path d="M12 17v5M9 10.8V4h6v6.8l3 3.2v2H6v-2z"/>',
  archive: '<rect x="2" y="3" width="20" height="5" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8M10 12h4"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  chevL: '<path d="m15 18-6-6 6-6"/>', chevR: '<path d="m9 18 6-6-6-6"/>', chevD: '<path d="m6 9 6 6 6-6"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  eyeOff: '<path d="M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.4-1.6M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  mail: '<rect x="2" y="4" width="20" height="16" rx="3"/><path d="m2 7 10 6 10-6"/>',
  cpu: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v4M15 1v4M9 19v4M15 19v4M1 9h4M1 15h4M19 9h4M19 15h4"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  card: '<rect x="2" y="5" width="20" height="14" rx="3"/><path d="M2 10h20M6 15h4"/>',
  key: '<circle cx="7.5" cy="15.5" r="4.5"/><path d="m10.7 12.3 9.3-9.3M17 6l3 3M14 9l2 2"/>',
  bank: '<path d="M3 21h18M5 21V10M19 21V10M9 21V10M15 21V10M2 10l10-7 10 7z"/>',
  id: '<rect x="2" y="4" width="20" height="16" rx="3"/><circle cx="8.5" cy="11" r="2.5"/><path d="M5 16.5a3.5 3.5 0 0 1 7 0M15 9h4M15 13h4"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  color: '<circle cx="12" cy="12" r="9"/><circle cx="8" cy="10" r="1"/><circle cx="12" cy="7.5" r="1"/><circle cx="16" cy="10" r="1"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  chart: '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 6-6"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18.5 20a6.5 6.5 0 0 0-3-5.5"/>',
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4"/>',
  play: '<path d="M7 4.5v15l12-7.5z" fill="currentColor"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>',
  volume: '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/>',
  gift: '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13M5 12v9h14v-9M12 8S10.5 3 8 3.5 7 8 12 8zm0 0s1.5-5 4-4.5S17 8 12 8z"/>',
  upload: '<path d="M12 15V3M7 8l5-5 5 5M4 21h16"/>',
  phone: '<rect x="6" y="2" width="12" height="20" rx="3"/><path d="M11 18h2"/>',
  flag: '<path d="M4 22V4M4 4h12l-2 4 2 4H4"/>',
};
const icon = (n, cls = "") => `<svg class="i ${cls}" viewBox="0 0 24 24">${ICONS[n] || ""}</svg>`;
const hydrateIcons = (root = document) => $$("[data-icon]", root).forEach((e) => { e.outerHTML = icon(e.dataset.icon); });

// ---------- dates ----------
const pad = (n) => String(n).padStart(2, "0");
const isoDate = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const isoDT = (d) => `${isoDate(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const parseD = (s) => (s.length <= 10 ? new Date(s + "T00:00") : new Date(s));
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const TODAY = () => isoDate();
const fmtTime = (s) => parseD(s).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
const fmtDate = (s, opts = { weekday: "short", day: "numeric", month: "short" }) => parseD(s).toLocaleDateString(undefined, opts);
function relDay(s) {
  if (!s) return "";
  const d = s.slice(0, 10), t = TODAY();
  if (d === t) return "Today";
  if (d === isoDate(addDays(new Date(), 1))) return "Tomorrow";
  if (d === isoDate(addDays(new Date(), -1))) return "Yesterday";
  const diff = (parseD(d) - parseD(t)) / 864e5;
  if (diff > 0 && diff < 7) return parseD(d).toLocaleDateString(undefined, { weekday: "long" });
  return fmtDate(d);
}
const greeting = () => { const h = new Date().getHours(); return h < 5 ? "Burning the midnight oil" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };

// ---------- markdown (tiny, safe) ----------
function md(src) {
  const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*(?!\s)(.+?)\*(?!\*)/g, "$1<i>$2</i>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const lines = esc(src || "").split("\n");
  let out = "", list = null, para = [];
  const flushP = () => { if (para.length) { out += `<p>${inline(para.join("<br>"))}</p>`; para = []; } };
  const flushL = () => { if (list) { out += `</${list}>`; list = null; } };
  for (const line of lines) {
    let m;
    if ((m = line.match(/^\s*[-*•]\s+(.*)/))) { flushP(); if (list !== "ul") { flushL(); out += "<ul>"; list = "ul"; } out += `<li>${inline(m[1])}</li>`; }
    else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { flushP(); if (list !== "ol") { flushL(); out += "<ol>"; list = "ol"; } out += `<li>${inline(m[1])}</li>`; }
    else if (!line.trim()) { flushP(); flushL(); }
    else if ((m = line.match(/^#{1,4}\s+(.*)/))) { flushP(); flushL(); out += `<p><b>${inline(m[1])}</b></p>`; }
    else { flushL(); para.push(line); }
  }
  flushP(); flushL();
  return out;
}

// ---------- toasts / modals ----------
function toast(msg, opts = {}) {
  const el = document.createElement("div");
  el.className = "toast" + (opts.error ? " err" : "");
  el.innerHTML = opts.title ? `<div><b>${esc(opts.title)}</b>${esc(msg)}</div>` : esc(msg);
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), opts.ms || 3500);
}
const fail = (e) => toast(e.message || String(e), { error: true });

function modal({ title, body, foot = "", size = "", onMount }) {
  const root = $("#modalRoot");
  const wrap = document.createElement("div");
  wrap.className = "overlay";
  wrap.innerHTML = `<div class="modal ${size}"><div class="modal-head"><h3>${esc(title)}</h3><button class="icon-btn" data-close>${icon("x")}</button></div>
    <div class="modal-body">${body}</div>${foot ? `<div class="modal-foot">${foot}</div>` : ""}</div>`;
  const close = () => { wrap.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  wrap.addEventListener("mousedown", (e) => { if (e.target === wrap) close(); });
  $$("[data-close]", wrap).forEach((b) => b.addEventListener("click", close));
  document.addEventListener("keydown", onKey);
  root.appendChild(wrap);
  const m = $(".modal", wrap);
  onMount && onMount(m, close);
  const first = $("input:not([type=hidden]),textarea", m);
  first && setTimeout(() => first.focus(), 30);
  return { el: m, close };
}
function confirmBox(text, okLabel = "Delete") {
  return new Promise((resolve) => {
    modal({
      title: "Are you sure?", body: `<p style="margin:0;color:var(--ink-2)">${esc(text)}</p>`,
      foot: `<button class="btn ghost" data-close>Cancel</button><button class="btn accent" id="cfOk">${esc(okLabel)}</button>`,
      onMount: (m, close) => { $("#cfOk", m).onclick = () => { close(); resolve(true); }; $$("[data-close]", m).forEach((b) => b.addEventListener("click", () => resolve(false))); },
    });
  });
}
const formData = (root) => Object.fromEntries($$("[name]", root).map((i) => [i.name, i.type === "checkbox" ? i.checked : i.value]));

// ============================== State & boot ==============================
const state = { boot: null, pendingAsk: null, chat: { cid: null }, tasks: { selected: null, showDone: true }, cal: { weekStart: null }, journal: { date: TODAY(), month: null }, ideas: { projectId: null, archived: false, q: "", color: "" }, notifSeen: new Set() };

function applyTheme(t) {
  const dark = t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyTheme(state.boot?.theme || "system"));

async function refreshBoot() {
  state.boot = await GET("/api/bootstrap");
  const b = state.boot;
  $("#navTaskCount").textContent = b.counts.myday || "";
  $("#navInbox").textContent = b.inbox_pending || "";
  $("#navPeople").innerHTML = b.birthdays_soon ? icon("gift") : "";
  $("#navRenewals").textContent = b.renewals_soon || "";
  $("#navSubs").textContent = b.subs_alerts || "";
  $("#navVault").innerHTML = b.vault.configured ? (b.vault.unlocked ? icon("unlock") : "") : "";
  $("#statusLine").innerHTML = `
    <span title="AI model"><i id="aiDot"></i>AI</span>
    <span title="Google Calendar"><i class="${b.google.connected ? "on" : ""}"></i>Calendar</span>
    <span title="Email reminders"><i class="${b.email ? "on" : ""}"></i>Email</span>`;
  GET("/api/ai/status").then((s) => { state.ai = s; const d = $("#aiDot"); if (d) { d.className = s.ok && s.model_installed ? "on" : "off"; d.parentElement.title = s.ok ? `AI: ${s.display_name || s.model}` : (s.error || "AI not connected"); } }).catch(() => {});
  applyTheme(b.theme);
  return b;
}

// ============================== Router ==============================
const VIEWS = {};
function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const [path, qs] = h.split("?");
  const parts = path.split("/").filter(Boolean);
  return { route: parts[0] || "", parts, params: new URLSearchParams(qs || "") };
}
async function render() {
  const r = parseHash();
  $$("#nav a, .foot-link").forEach((a) => a.classList.toggle("active", a.dataset.route === r.route));
  $("#sidebar").classList.remove("open");
  const main = $("#main");
  const view = VIEWS[r.route] || VIEWS[""];
  try { await view(main, r); } catch (e) { console.error(e); main.innerHTML = `<div class="page"><div class="empty big"><h3>Something went wrong</h3><p>${esc(e.message)}</p></div></div>`; }
}
window.addEventListener("hashchange", render);
const go = (h) => { if (location.hash === h) render(); else location.hash = h; };
function askDonna(text) { state.pendingAsk = text; state.chat.cid = null; go("#/chat"); }

// ============================== TODAY ==============================
VIEWS[""] = async (el) => {
  const [brief, myday, ideas, jr] = await Promise.all([GET("/api/briefing"), GET("/api/tasks?view=myday"), GET("/api/ideas"), GET(`/api/journal/${TODAY()}`)]);
  const b = brief.data, name = state.boot.user_name;
  const open = myday.filter((t) => !t.completed);
  const events = b.events.filter((e) => !e.error);
  const now = isoDT(new Date());
  let nowPlaced = false;
  const agenda = events.map((e) => {
    let line = "";
    if (!nowPlaced && !e.all_day && e.start > now) { nowPlaced = true; line = `<div class="now-line">NOW</div>`; }
    return line + `<div class="agenda-item ${e.source} ${!e.all_day && e.end < now ? "past" : ""}"><div class="time">${e.all_day ? "All day" : fmtTime(e.start)}</div><div class="bar"></div><div><div class="t">${esc(e.title)}</div><div class="m">${e.all_day ? "" : fmtTime(e.start) + " – " + fmtTime(e.end)}${e.location ? " · " + esc(e.location) : ""}</div></div></div>`;
  }).join("");
  const summary = [events.length ? `${events.length} ${events.length === 1 ? "event" : "events"}` : "a clear calendar", open.length ? `${open.length} ${open.length === 1 ? "task" : "tasks"} in focus` : "nothing pressing"].join(" and ");
  el.innerHTML = `<div class="page">
    <div class="hero">
      <div class="eyebrow">${new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</div>
      <h1>${greeting()}${name ? `, <em>${esc(name)}</em>` : ""}.</h1>
      <div class="muted" style="margin-top:8px;font-size:15px">You have ${summary}${b.overdue.length ? `, and <b style="color:var(--warn)">${b.overdue.length} overdue</b>` : ""}.</div>
      <form class="ask-bar" id="askForm">${icon("sparkle")}<input id="askInput" placeholder="Tell Donna anything: “Remind me to call the bank at 4pm”, “Block Friday morning for the pitch”…" autocomplete="off"><button type="button" class="icon-btn mic" id="askMic" title="Speak">${icon("mic")}</button><button class="btn primary">Ask</button></form>
      <div class="suggest">${["Brief me on today", "What's overdue?", "Block 2 hours tomorrow for deep work", "What did I write in my journal this week?"].map((s) => `<button class="chip btnlike" data-ask="${esc(s)}">${esc(s)}</button>`).join("")}</div>
    </div>
    <div class="card mentor-card" id="mentorCard"></div>
    <div class="card voice-card"><button class="play" id="playBrief" title="Play briefing">${icon("play")}</button>
      <div style="flex:1"><b>Your briefing, read aloud</b><span class="muted" style="font-size:13px">About a minute. Then tap the mic and talk back: “add pick up dry cleaning”, “move the dentist to 5”.</span></div>
      <button class="btn sm" id="talkBtn">${icon("mic")}Talk to Donna</button></div>
    ${(b.birthdays?.length || b.renewals_due?.length || b.reach_out?.length || b.trials_ending?.length || b.subscriptions_due?.length) ? `<div class="card" style="margin-bottom:16px"><div class="card-head">${icon("gift")}<h3>Coming up</h3></div><div class="card-body" style="display:flex;flex-wrap:wrap;gap:8px">
      ${(b.birthdays || []).map((p) => `<a class="chip accent" href="#/people">🎂 ${esc(p.name)} · ${p.in_days === 0 ? "today" : p.in_days === 1 ? "tomorrow" : "in " + p.in_days + " days"}${p.turning ? " · turning " + p.turning : ""}</a>`).join("")}
      ${(b.trials_ending || []).map((t) => `<a class="chip ${t.in_days <= 2 ? "warn" : "accent"}" href="#/subscriptions">⏳ ${esc(t.name)} trial · cancel by ${fmtDate(t.cancel_by)}</a>`).join("")}
      ${(b.subscriptions_due || []).map((x) => `<a class="chip" href="#/subscriptions">${icon("card")}${esc(x.name)} ${esc(x.charges)} · ${x.in_days === 0 ? "today" : "in " + x.in_days + "d"}</a>`).join("")}
      ${(b.renewals_due || []).map((r) => `<a class="chip ${r.days_left < 0 ? "warn" : ""}" href="#/renewals">${icon("refresh")}${esc(r.title)} · ${r.days_left < 0 ? "overdue" : r.days_left === 0 ? "due today" : "in " + r.days_left + "d"}</a>`).join("")}
      ${(b.reach_out || []).map((p) => `<a class="chip" href="#/people">${icon("users")}Reach out to ${esc(p.name)}</a>`).join("")}
      ${b.inbox_commitments_pending ? `<a class="chip accent" href="#/inbox">${icon("mail")}${b.inbox_commitments_pending} from your email</a>` : ""}</div></div>` : ""}
    <div class="stat-row">
      <div class="card stat"><div class="eyebrow">Events today</div><div class="n">${events.length}</div></div>
      <div class="card stat"><div class="eyebrow">In focus</div><div class="n">${open.length}</div></div>
      <div class="card stat"><div class="eyebrow">Overdue</div><div class="n" style="${b.overdue.length ? "color:var(--warn)" : ""}">${b.overdue.length}</div></div>
      <div class="card stat"><div class="eyebrow">Journal streak</div><div class="n">${b.journal_streak_days}<small>${b.journal_streak_days === 1 ? "day" : "days"}</small></div></div>
    </div>
    <div class="grid">
      <div class="card col-7"><div class="card-head">${icon("calendar")}<h3>Schedule</h3><a class="more" href="#/calendar">Calendar →</a></div>
        <div class="card-body">${agenda || `<div class="empty">Nothing on the calendar today. ${state.boot.google.connected ? "" : `<a href="#/settings" style="color:var(--accent)">Connect Google Calendar</a>`}</div>`}</div></div>
      <div class="card col-5"><div class="card-head">${icon("sun")}<h3>My Day</h3><a class="more" href="#/tasks/myday">To Do →</a></div>
        <div class="card-body" id="todayTasks"></div></div>
      <div class="card col-7"><div class="card-head">${icon("bulb")}<h3>Recent ideas</h3><a class="more" href="#/ideas">All ideas →</a></div>
        <div class="card-body">${ideas.slice(0, 4).map((i) => `<div class="agenda-item"><div class="bar" style="background:var(--gold)"></div><div style="min-width:0"><div class="t">${esc(i.title || i.body.slice(0, 60))}</div><div class="m">${esc(i.project_name || "Unsorted")} · ${esc(i.body.slice(0, 90))}</div></div></div>`).join("") || `<div class="empty">No ideas captured yet. Press ⌘K and type “idea: …”</div>`}</div></div>
      <div class="card col-5"><div class="card-head">${icon("book")}<h3>Journal</h3><a class="more" href="#/journal">Open →</a></div>
        <div class="card-body">${jr.body ? `<div style="font-family:Georgia,serif;font-size:15px;line-height:1.7;color:var(--ink-2)">${esc(jr.body.slice(0, 260))}${jr.body.length > 260 ? "…" : ""}</div>` : `<p class="muted" style="margin:6px 0 14px">You haven't written today. One honest line is enough.</p><a class="btn sm" href="#/journal">${icon("edit")}Write today's entry</a>`}</div></div>
    </div></div>`;
  renderTaskMini($("#todayTasks"), open.slice(0, 7));
  $("#askForm").onsubmit = (e) => { e.preventDefault(); const v = $("#askInput").value.trim(); if (v) askDonna(v); };
  $$("[data-ask]", el).forEach((b2) => (b2.onclick = () => askDonna(b2.dataset.ask)));
  bindMic($("#askMic"), $("#askInput"), (t) => askDonna(t));
  renderMentorCard($("#mentorCard"));
  $("#playBrief").onclick = () => {
    if (Voice.speaking()) { Voice.stop(); $("#playBrief").innerHTML = icon("play"); return; }
    $("#playBrief").innerHTML = icon("stop");
    Voice.say(spokenBriefing(b, open, name), () => { const p = $("#playBrief"); if (p) p.innerHTML = icon("play"); });
  };
  $("#talkBtn").onclick = () => { state.handsFree = true; go("#/chat"); };
};

function spokenBriefing(b, open, name) {
  const parts = [`${greeting()}${name ? ", " + name : ""}. It's ${new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}.`];
  const evs = b.events.filter((e) => !e.error);
  if (!evs.length) parts.push("Your calendar is clear today.");
  else parts.push(`You have ${evs.length} ${evs.length === 1 ? "event" : "events"}. ` + evs.map((e) => e.all_day ? `${e.title}, all day` : `At ${fmtTime(e.start)}, ${e.title}`).join(". ") + ".");
  if (b.overdue.length) parts.push(`${b.overdue.length} ${b.overdue.length === 1 ? "task is" : "tasks are"} overdue, starting with ${b.overdue[0].title}.`);
  const due = open.filter((t) => !b.overdue.find((o) => o.id === t.id));
  if (due.length) parts.push(`On your list for today: ${due.slice(0, 5).map((t) => t.title).join(", ")}.`);
  (b.birthdays || []).forEach((p) => parts.push(`${p.name}'s birthday is ${p.in_days === 0 ? "today" : p.in_days === 1 ? "tomorrow" : "in " + p.in_days + " days"}.`));
  (b.trials_ending || []).forEach((t) => parts.push(`Your ${t.name} free trial ends ${t.in_days === 0 ? "today" : "in " + t.in_days + " days"}. Cancel by ${fmtDate(t.cancel_by, { weekday: "long", day: "numeric", month: "long" })} if you don't want to pay.`));
  (b.subscriptions_due || []).forEach((x) => parts.push(`${x.name} will charge ${x.charges.startsWith("₹") ? x.charges.slice(1) + " rupees" : x.charges} ${x.in_days === 0 ? "today" : "in " + x.in_days + " days"}.`));
  (b.renewals_due || []).forEach((r) => parts.push(`${r.title} is ${r.days_left < 0 ? "overdue" : r.days_left === 0 ? "due today" : "due in " + r.days_left + " days"}.`));
  if (b.reach_out?.length) parts.push(`You might want to reach out to ${b.reach_out.map((p) => p.name).join(" and ")}.`);
  if (b.inbox_commitments_pending) parts.push(`I found ${b.inbox_commitments_pending} commitments in your email for you to review.`);
  parts.push(b.overdue.length ? `If you do one thing first, clear ${b.overdue[0].title}.` : due.length ? `I'd start with ${due[0].title}.` : "Enjoy the breathing room.");
  return parts.join(" ");
}

function renderTaskMini(box, tasks) {
  if (!tasks.length) { box.innerHTML = `<div class="empty">All clear. Enjoy it, or <a href="#/tasks/myday" style="color:var(--accent)">plan your day</a>.</div>`; return; }
  box.innerHTML = tasks.map((t) => `<div class="agenda-item" style="align-items:center"><button class="check" data-done="${t.id}">${icon("tick")}</button><div style="flex:1;min-width:0"><div class="t">${esc(t.title)}</div><div class="m">${t.due_date && t.due_date < TODAY() ? `<span style="color:var(--warn)">Overdue · ${relDay(t.due_date)}</span>` : t.due_date ? relDay(t.due_date) : esc(t.project_name || "Tasks")}${t.reminder_at ? " · " + fmtTime(t.reminder_at) : ""}</div></div>${t.important ? `<span class="star on">${icon("star")}</span>` : ""}</div>`).join("");
  $$("[data-done]", box).forEach((b) => (b.onclick = async () => { b.classList.add("on"); const res = await PATCH(`/api/tasks/${b.dataset.done}`, { completed: true }); res.reward ? celebrate(res.reward) : toast("Nicely done."); await sleep(250); b.closest(".agenda-item").remove(); refreshBoot(); }));
}

// ============================== CHAT ==============================
const AGENT_LABEL = { subscriptions: "Subscriptions agent", goals: "Goals mentor", people: "People agent", renewals: "Renewals agent", tasks: "To-do agent", calendar: "Calendar agent", journal: "Journal agent", ideas: "Ideas agent", memory: "Memory agent", briefing: "Briefing agent", general: "Donna" };
const TOOL_LABEL = { list_subscriptions: "Checked subscriptions", add_subscription: "Saved subscription", update_subscription: "Updated subscription", cancel_subscription: "Cancelled subscription", record_subscription_charge: "Logged payment", subscription_spend: "Checked spending", subscription_suggestions: "Checked email finds", send_to_phone: "Sent to phone", list_tasks: "Checked tasks", add_task: "Added task", update_task: "Updated task", complete_task: "Completed task", delete_task: "Deleted task", list_projects: "Checked lists", get_events: "Checked calendar", create_event: "Booked event", delete_event: "Cancelled event", find_free_time: "Found free time", write_journal: "Wrote journal", read_journal: "Read journal", search_journal: "Searched journal", add_idea: "Saved idea", list_ideas: "Checked ideas", remember: "Remembered", recall: "Searched memory", vault_lookup: "Opened vault", get_briefing: "Prepared briefing" };

VIEWS.chat = async (el, r) => {
  if (r?.params.get("ask")) { state.pendingAsk = r.params.get("ask"); state.chat.cid = null; history.replaceState(null, "", "#/chat"); }
  el.innerHTML = `<div class="page wide"><div class="chat-layout">
    <aside class="convos"><button class="btn" id="newChat">${icon("plus")}New conversation</button><div id="convoList"></div></aside>
    <section class="thread-wrap"><div class="thread" id="thread"><div class="thread-inner" id="threadInner"></div></div>
      <div class="composer"><form class="composer-box" id="composer"><textarea id="chatInput" rows="1" placeholder="Message Donna…"></textarea><button type="button" class="icon-btn mic" id="chatMic" title="Speak (hold a conversation)">${icon("mic")}</button><button class="btn primary" id="sendBtn" style="padding:8px 10px">${icon("up")}</button></form>
      <div class="composer-hint"><span>${state.ai?.provider === "ollama" ? "Runs privately on your Mac (Ollama)" : "Powered by Claude"}</span><span><kbd>↵</kbd> send · <kbd>⇧↵</kbd> new line</span><span class="spacer"></span><label style="display:flex;gap:6px;align-items:center;cursor:pointer"><input type="checkbox" id="autoRead" ${Voice.autoRead() ? "checked" : ""}>Read replies aloud</label></div></div>
    </section></div></div>`;
  $("#autoRead").onchange = (e) => Voice.setAutoRead(e.target.checked);
  bindMic($("#chatMic"), $("#chatInput"), (t) => { $("#chatInput").value = ""; state.handsFree = true; sendChat(t); });
  $("#newChat").onclick = () => { state.chat.cid = null; loadThread(); loadConvos(); };
  const ta = $("#chatInput");
  ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = ta.scrollHeight + "px"; });
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("#composer").requestSubmit(); } });
  $("#composer").onsubmit = (e) => { e.preventDefault(); const v = ta.value.trim(); if (!v) return; ta.value = ""; ta.style.height = "auto"; sendChat(v); };
  await loadConvos();
  await loadThread();
  if (state.pendingAsk) { const t = state.pendingAsk; state.pendingAsk = null; sendChat(t); }
  else if (state.handsFree) { Voice.say("I'm listening."); setTimeout(() => $("#chatMic")?.click(), 900); }
  ta.focus();
};

async function loadConvos() {
  const list = await GET("/api/conversations");
  const box = $("#convoList");
  if (!box) return;
  box.innerHTML = list.map((c) => `<div class="convo ${c.id === state.chat.cid ? "active" : ""}" data-id="${c.id}"><span>${esc(c.title)}</span><button class="icon-btn" data-del="${c.id}">${icon("x")}</button></div>`).join("") || `<div class="muted" style="padding:8px 10px;font-size:12.5px">No conversations yet</div>`;
  $$(".convo", box).forEach((c) => (c.onclick = (e) => { if (e.target.closest("[data-del]")) return; state.chat.cid = +c.dataset.id; loadThread(); loadConvos(); }));
  $$("[data-del]", box).forEach((b) => (b.onclick = async () => { await DEL(`/api/conversations/${b.dataset.del}`); if (state.chat.cid === +b.dataset.del) { state.chat.cid = null; loadThread(); } loadConvos(); }));
}

async function loadThread() {
  const inner = $("#threadInner");
  if (!state.chat.cid) {
    const starters = [["To Do", "Remind me to renew my car insurance on Friday at 10am"], ["Calendar", "What does my week look like?"], ["Memory", "Remember that my shirt size is M, slim fit"], ["Journal", "Today was intense but I finally shipped the release"], ["Ideas", "Idea: a weekly digest of my journal moods"], ["Vault", "What's my Netflix password?"]];
    inner.innerHTML = `<div class="chat-empty"><div class="monogram">D</div><h2>What do you need?</h2><div class="muted">I already know. But tell me anyway.</div>
      <div class="starter-grid">${starters.map(([k, v]) => `<div class="starter" data-s="${esc(v)}"><b>${k}</b>${esc(v)}</div>`).join("")}</div></div>`;
    $$(".starter", inner).forEach((s) => (s.onclick = () => sendChat(s.dataset.s)));
    return;
  }
  const msgs = await GET(`/api/conversations/${state.chat.cid}`);
  inner.innerHTML = "";
  for (const m of msgs) {
    if (m.role === "user") addUserMsg(m.content);
    else { const d = addDonnaMsg(); finishDonnaMsg(d, m.content, m.meta); }
  }
  scrollThread();
}
const scrollThread = () => { const t = $("#thread"); if (t) t.scrollTop = t.scrollHeight; };
function addUserMsg(text) {
  const inner = $("#threadInner");
  $(".chat-empty", inner)?.remove();
  inner.insertAdjacentHTML("beforeend", `<div class="msg user"><div class="bubble">${esc(text)}</div></div>`);
}
function addDonnaMsg() {
  const inner = $("#threadInner");
  const wrap = document.createElement("div");
  wrap.className = "msg donna";
  wrap.innerHTML = `<div class="avatar">D</div><div class="content"><div class="trace"></div><div class="text"><span class="typing"><i></i><i></i><i></i></span></div><div class="cards"></div></div><button class="icon-btn speak-btn" title="Read aloud">${icon("volume")}</button>`;
  $(".speak-btn", wrap).onclick = () => (Voice.speaking() ? Voice.stop() : Voice.say($(".text", wrap).innerText));
  inner.appendChild(wrap);
  return wrap;
}
function finishDonnaMsg(d, text, meta = {}) {
  const trace = $(".trace", d);
  if (meta.agent && meta.agent !== "general") trace.innerHTML = `<span class="chip accent">${esc(AGENT_LABEL[meta.agent] || meta.agent)}</span>`;
  (meta.trace || []).forEach((t) => trace.insertAdjacentHTML("beforeend", `<span class="chip ${t.ok ? "ok" : "warn"}">${icon(t.ok ? "tick" : "x")}${esc(TOOL_LABEL[t.tool] || t.tool)}</span>`));
  $(".text", d).innerHTML = md(text);
  if (meta.vault_cards?.length) renderVaultCards($(".cards", d), meta.vault_cards);
}

async function sendChat(text) {
  addUserMsg(text);
  const d = addDonnaMsg();
  scrollThread();
  const trace = $(".trace", d), textEl = $(".text", d);
  let buf = "", meta = {};
  const toolChips = {};
  try {
    const res = await fetch("/api/chat", { method: "POST", headers: { ...HDR, "Content-Type": "application/json" }, body: JSON.stringify({ text, conversation_id: state.chat.cid }) });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let pending = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += dec.decode(value, { stream: true });
      const lines = pending.split("\n");
      pending = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const ev = JSON.parse(line);
        if (ev.type === "conversation") { if (!state.chat.cid) { state.chat.cid = ev.id; loadConvos(); } }
        else if (ev.type === "agent") { if (ev.agent !== "general") trace.insertAdjacentHTML("afterbegin", `<span class="chip accent">${esc(AGENT_LABEL[ev.agent])}</span>`); }
        else if (ev.type === "tool") { const c = document.createElement("span"); c.className = "chip"; c.innerHTML = `${icon("clock")}${esc(TOOL_LABEL[ev.name] || ev.name)}…`; trace.appendChild(c); toolChips[ev.name] = c; }
        else if (ev.type === "tool_result") { const c = toolChips[ev.name]; if (c) { c.className = "chip " + (ev.ok ? "ok" : "warn"); c.innerHTML = `${icon(ev.ok ? "tick" : "x")}${esc(TOOL_LABEL[ev.name] || ev.name)}`; } }
        else if (ev.type === "token") { buf += ev.text; textEl.innerHTML = md(buf); scrollThread(); }
        else if (ev.type === "reset") { buf = ""; textEl.innerHTML = `<span class="typing"><i></i><i></i><i></i></span>`; }
        else if (ev.type === "vault_cards") { renderVaultCards($(".cards", d), ev.ids); }
        else if (ev.type === "reward") { celebrate({ xp: ev.xp, level_up: ev.level_up, line: "Progress logged." }); }
        else if (ev.type === "final") { meta = ev.meta; textEl.innerHTML = md(ev.text || buf); }
        else if (ev.type === "error") { textEl.innerHTML = `<p style="color:var(--warn)">${esc(ev.text)}</p>`; }
      }
      scrollThread();
    }
  } catch (e) {
    textEl.innerHTML = `<p style="color:var(--warn)">${esc(e.message)}</p>`;
  }
  if (meta.trace?.some((t) => t.ok && /add|update|complete|delete|create|write|remember|save|log|mark/.test(t.tool))) refreshBoot();
  loadConvos();
  if (state.handsFree || Voice.autoRead()) {
    Voice.say(textEl.innerText, () => { if (state.handsFree && location.hash.startsWith("#/chat")) $("#chatMic")?.click(); });
  }
}

// ============================== VOICE ==============================
// Speech output uses the OS voices (fully local). Speech input uses the browser's recogniser:
// Safari/macOS may process on-device; Chrome sends audio to Google. Typed input is always private.
const Voice = {
  _utter: null,
  voice() {
    const vs = speechSynthesis.getVoices();
    const pref = localStorage.getItem("donna_voice");
    return vs.find((v) => v.name === pref) || vs.find((v) => /Samantha|Karen|Moira|Serena|Google UK English Female|Ava|Allison/.test(v.name) && /^en/.test(v.lang)) || vs.find((v) => /^en/.test(v.lang));
  },
  say(text, onEnd) {
    if (!("speechSynthesis" in window)) return onEnd && onEnd();
    speechSynthesis.cancel();
    const clean = String(text).replace(/[*_`#>•]/g, "").replace(/\s+/g, " ").trim();
    const u = new SpeechSynthesisUtterance(clean);
    const v = this.voice();
    if (v) u.voice = v;
    u.rate = +(localStorage.getItem("donna_rate") || 1.02);
    u.onend = u.onerror = () => { this._utter = null; onEnd && onEnd(); };
    this._utter = u;
    speechSynthesis.speak(u);
  },
  stop() { speechSynthesis.cancel(); this._utter = null; state.handsFree = false; },
  speaking() { return "speechSynthesis" in window && speechSynthesis.speaking; },
  autoRead() { try { return localStorage.getItem("donna_autoread") === "1"; } catch { return false; } },
  setAutoRead(v) { try { localStorage.setItem("donna_autoread", v ? "1" : "0"); } catch { /* ignore */ } },
};
if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = () => {};

function bindMic(btn, input, onFinal) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!btn) return;
  if (!SR) { btn.title = "Voice input isn't supported in this browser (try Safari or Chrome)"; btn.style.opacity = .35; btn.onclick = () => toast("Voice input isn't supported in this browser. Try Safari or Chrome.", { error: true }); return; }
  let rec = null;
  btn.onclick = () => {
    if (rec) { rec.stop(); return; }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    rec = new SR();
    rec.lang = localStorage.getItem("donna_lang") || navigator.language || "en-IN";
    rec.interimResults = true;
    rec.continuous = false;
    let finalText = "";
    btn.classList.add("listening");
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript; else interim += e.results[i][0].transcript;
      }
      input.value = (finalText + interim).trim();
    };
    rec.onerror = (e) => { if (e.error === "not-allowed") toast("Microphone permission was denied", { error: true }); else if (e.error !== "no-speech" && e.error !== "aborted") toast("Voice: " + e.error, { error: true }); state.handsFree = false; };
    rec.onend = () => {
      btn.classList.remove("listening");
      rec = null;
      const t = (finalText || input.value).trim();
      if (t) onFinal(t); else state.handsFree = false;
    };
    rec.start();
  };
}

// ============================== VAULT (shared bits) ==============================
const VAULT_SPEC = {
  card: { label: "Payment card", icon: "card", fields: [["bank", "Bank / issuer"], ["cardholder", "Name on card"], ["number", "Card number", "secret mono"], ["expiry", "Expiry (MM/YY)", "mono"], ["cvv", "CVV", "secret mono"], ["pin", "PIN", "secret mono"], ["network", "Network (Visa, Mastercard…)"], ["notes", "Notes", "area"]] },
  login: { label: "Login / password", icon: "key", fields: [["url", "Website"], ["username", "Username / email"], ["password", "Password", "secret mono"], ["notes", "Notes", "area"]] },
  bank: { label: "Bank account", icon: "bank", fields: [["bank", "Bank"], ["holder", "Account holder"], ["account_number", "Account number", "secret mono"], ["ifsc", "IFSC / routing", "mono"], ["branch", "Branch"], ["notes", "Notes", "area"]] },
  identity: { label: "ID document", icon: "id", fields: [["type", "Type (Passport, PAN, Licence…)"], ["name", "Name on document"], ["number", "Number", "secret mono"], ["issued", "Issued"], ["expiry", "Expiry"], ["notes", "Notes", "area"]] },
  note: { label: "Secure note", icon: "file", fields: [["content", "Content", "secret area"]] },
};

function vaultFieldsHTML(cat, data) {
  const spec = VAULT_SPEC[cat] || VAULT_SPEC.note;
  return spec.fields.filter(([k]) => data[k]).map(([k, label, flags = ""]) => {
    const secret = flags.includes("secret");
    return `<div class="vfield" data-k="${k}"><div class="k">${esc(label.replace(/ \(.*/, ""))}</div><div class="v ${flags.includes("mono") ? "mono" : ""}" data-val="${esc(data[k])}" data-secret="${secret ? 1 : ""}">${secret ? "••••••••" : esc(data[k])}</div>
      ${secret ? `<button class="icon-btn" data-reveal title="Reveal">${icon("eye")}</button>` : ""}<button class="icon-btn" data-copy title="Copy">${icon("copy")}</button></div>`;
  }).join("") || `<div class="muted" style="padding:8px 0">No details saved.</div>`;
}
function bindVaultFields(root) {
  $$("[data-reveal]", root).forEach((b) => (b.onclick = () => { const v = $(".v", b.parentElement); const shown = v.dataset.shown === "1"; v.textContent = shown ? "••••••••" : v.dataset.val; v.dataset.shown = shown ? "" : "1"; b.innerHTML = icon(shown ? "eye" : "eyeOff"); }));
  $$("[data-copy]", root).forEach((b) => (b.onclick = async () => { await navigator.clipboard.writeText($(".v", b.parentElement).dataset.val); toast("Copied. Clipboard clears in 30s."); setTimeout(() => navigator.clipboard.writeText("").catch(() => {}), 30000); }));
}
function unlockForm(onDone) {
  return { html: `<form class="unlock-inline" style="display:flex;gap:8px;margin-top:8px"><input class="input" type="password" placeholder="Master password" autocomplete="current-password"><button class="btn primary">Unlock</button></form>`,
    bind: (root) => { const f = $(".unlock-inline", root); f.onsubmit = async (e) => { e.preventDefault(); try { await POST("/api/vault/unlock", { password: $("input", f).value }); refreshBoot(); onDone(); } catch (err) { fail(err); } }; } };
}
async function renderVaultCards(box, ids) {
  const { items, unlocked } = await GET(`/api/vault-cards?ids=${ids.join(",")}`);
  box.innerHTML = "";
  for (const it of items) {
    const card = document.createElement("div");
    card.className = "vcard";
    const spec = VAULT_SPEC[it.category] || VAULT_SPEC.note;
    card.innerHTML = `<div class="vc-head"><div class="vc-icon">${icon(spec.icon)}</div><div style="flex:1"><div class="vc-title">${esc(it.title)}</div><div class="vc-sub">${esc(spec.label)}${it.hint ? " · " + esc(it.hint) : ""}</div></div>${icon("lock")}</div><div class="vc-body"></div>`;
    box.appendChild(card);
    const body = $(".vc-body", card);
    const show = async () => {
      try { const v = await GET(`/api/vault/${it.id}`); body.innerHTML = vaultFieldsHTML(v.category, v.data); bindVaultFields(body); }
      catch (e) { if (e.locked) { const u = unlockForm(show); body.innerHTML = `<div class="muted" style="font-size:12.5px">Vault is locked.</div>` + u.html; u.bind(body); } else fail(e); }
    };
    if (unlocked) { body.innerHTML = `<button class="btn sm">${icon("eye")}Show details</button>`; $("button", body).onclick = show; }
    else { const u = unlockForm(show); body.innerHTML = `<div class="muted" style="font-size:12.5px">Unlock your vault to view.</div>` + u.html; u.bind(body); }
  }
}

// ============================== TASKS ==============================
const SMART = [["myday", "My Day", "sun"], ["important", "Important", "star"], ["planned", "Planned", "calendar"], ["all", "All", "list"], ["completed", "Completed", "check"], ["inbox", "Tasks", "inbox"]];
const REPEAT_LABEL = { "": "Don't repeat", daily: "Daily", weekdays: "Weekdays", weekly: "Weekly", monthly: "Monthly", yearly: "Yearly" };

VIEWS.tasks = async (el, r) => {
  const view = r.parts[1] === "p" ? "project" : r.parts[1] || "myday";
  const pid = view === "project" ? +r.parts[2] : null;
  if (r.params.get("task")) state.tasks.selected = +r.params.get("task");
  state.tasks.view = view; state.tasks.pid = pid;
  if (!el.querySelector(".tasks-layout")) {
    el.innerHTML = `<div class="page wide"><div class="tasks-layout" id="tasksLayout"><nav class="lists-pane" id="listsPane"></nav><section class="task-main" id="taskMain"></section><aside class="detail" id="detail" hidden></aside></div></div>`;
  }
  await Promise.all([renderListsPane(), renderTaskMain()]);
  renderDetail();
};

async function renderListsPane() {
  const { counts, projects } = await GET("/api/tasks/counts");
  state.projects = projects;
  const { view, pid } = state.tasks;
  const pane = $("#listsPane");
  pane.innerHTML = SMART.map(([k, label, ic]) => `<a href="#/tasks/${k}" class="${view === k ? "active" : ""}">${icon(ic)}${label}<em>${counts[k] ?? ""}</em></a>`).join("") +
    `<div class="sep"></div>` + projects.map((p) => `<a href="#/tasks/p/${p.id}" class="${pid === p.id ? "active" : ""}"><span class="emoji">${esc(p.emoji || "•")}</span>${esc(p.name)}<em>${p.open_tasks || ""}</em></a>`).join("") +
    `<form class="new-list" id="newList">${icon("plus")}<input placeholder="New list" maxlength="60"></form>`;
  $("#newList").onsubmit = async (e) => { e.preventDefault(); const v = $("input", e.target).value.trim(); if (!v) return; const p = await POST("/api/projects", { name: v }); go(`#/tasks/p/${p.id}`); };
}

async function renderTaskMain() {
  const { view, pid } = state.tasks;
  const main = $("#taskMain");
  const project = pid ? state.projects.find((p) => p.id === pid) : null;
  const title = project ? `${project.emoji ? project.emoji + " " : ""}${project.name}` : SMART.find((s) => s[0] === view)?.[1] || "Tasks";
  const url = pid ? `/api/tasks?project_id=${pid}` : `/api/tasks?view=${view}`;
  const tasks = await GET(url);
  const open = tasks.filter((t) => !t.completed), done = tasks.filter((t) => t.completed);
  const sub = view === "myday" ? new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" }) : `${open.length} open`;
  main.innerHTML = `<div class="page-head"><div><h1>${esc(title)}</h1><div class="sub">${esc(sub)}</div></div>
    <div class="actions">${project ? `<button class="btn ghost sm" id="renameList">${icon("edit")}Rename</button><button class="btn ghost sm danger" id="deleteList">${icon("trash")}</button>` : ""}
    <button class="btn sm" id="planAI">${icon("sparkle")}Plan with Donna</button></div></div>
    ${view !== "completed" ? `<form class="add-task" id="addTask">${icon("plus")}<input class="title" placeholder="Add a task" autocomplete="off">
      <div class="opts"><label class="opt icon-btn" title="Due date">${icon("calendar")}<input type="date" name="due_date"></label>
      <label class="opt icon-btn" title="Remind me">${icon("bell")}<input type="datetime-local" name="reminder_at"></label>
      <label class="opt icon-btn" title="Repeat">${icon("repeat")}<select name="repeat" style="position:absolute;inset:0;opacity:0">${Object.entries(REPEAT_LABEL).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
      <button type="button" class="opt icon-btn" id="addImp" title="Important">${icon("star")}</button></div></form>` : ""}
    <div id="openList"></div>
    ${done.length && view !== "completed" ? `<button class="section-toggle" id="toggleDone">${icon(state.tasks.showDone ? "chevD" : "chevR")}Completed <span class="muted">${done.length}</span></button><div id="doneList" ${state.tasks.showDone ? "" : "hidden"}></div>` : ""}`;

  const openBox = $("#openList");
  if (view === "planned") {
    const groups = {};
    const order = ["Overdue", "Today", "Tomorrow", "This week", "Later"];
    const t0 = TODAY(), t1 = isoDate(addDays(new Date(), 1)), t7 = isoDate(addDays(new Date(), 7));
    for (const t of open) {
      const d = t.due_date;
      const g = d < t0 ? "Overdue" : d === t0 ? "Today" : d === t1 ? "Tomorrow" : d <= t7 ? "This week" : "Later";
      (groups[g] = groups[g] || []).push(t);
    }
    openBox.innerHTML = order.filter((g) => groups[g]).map((g) => `<div class="eyebrow" style="margin:18px 4px 8px;${g === "Overdue" ? "color:var(--warn)" : ""}">${g}</div>` + groups[g].map(taskRow).join("")).join("");
  } else openBox.innerHTML = (view === "completed" ? tasks : open).map(taskRow).join("");
  if (!openBox.innerHTML) openBox.innerHTML = emptyTasks(view);
  if ($("#doneList")) $("#doneList").innerHTML = done.map(taskRow).join("");
  bindTaskRows(main);

  const form = $("#addTask");
  if (form) {
    let important = view === "important";
    $("#addImp").classList.toggle("on", important);
    $("#addImp").onclick = () => { important = !important; $("#addImp").classList.toggle("on", important); };
    $$(".opt input, .opt select", form).forEach((i) => i.addEventListener("change", () => i.closest(".opt").classList.toggle("set", !!i.value)));
    form.onsubmit = async (e) => {
      e.preventDefault();
      const title = $("input.title", form).value.trim();
      if (!title) return;
      const body = { title, important: important ? 1 : 0, due_date: form.due_date.value || null, reminder_at: form.reminder_at.value || null, repeat: form.repeat.value || "" };
      if (body.reminder_at && !body.due_date) body.due_date = body.reminder_at.slice(0, 10);
      if (view === "myday") body.my_day = TODAY();
      if (view === "planned" && !body.due_date) body.due_date = TODAY();
      if (pid) body.project_id = pid;
      await POST("/api/tasks", body);
      await Promise.all([renderTaskMain(), renderListsPane()]);
      refreshBoot();
      $("#addTask input.title").focus();
    };
  }
  $("#toggleDone") && ($("#toggleDone").onclick = () => { state.tasks.showDone = !state.tasks.showDone; renderTaskMain(); });
  $("#planAI").onclick = () => askDonna(view === "myday" ? "Look at my tasks and calendar and suggest a realistic plan for today." : `Look at my ${title} tasks and suggest what to focus on first.`);
  if (project) {
    $("#renameList").onclick = () => modal({ title: "Rename list", body: `<div class="row"><div class="field" style="flex:0 0 70px"><label>Emoji</label><input class="input" name="emoji" value="${esc(project.emoji)}" maxlength="4"></div><div class="field"><label>Name</label><input class="input" name="name" value="${esc(project.name)}"></div></div>`,
      foot: `<button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="saveList">Save</button>`,
      onMount: (m, close) => { $("#saveList", m).onclick = async () => { await PATCH(`/api/projects/${pid}`, formData(m)); close(); renderListsPane(); renderTaskMain(); }; } });
    $("#deleteList").onclick = async () => { if (await confirmBox(`Delete “${project.name}” and all its tasks?`)) { await DEL(`/api/projects/${pid}`); go("#/tasks/myday"); refreshBoot(); } };
  }
}

function emptyTasks(view) {
  const m = { myday: ["A fresh start", "Add what matters today, or ask Donna to plan it."], important: ["Nothing starred", "Star a task to keep it front and centre."], planned: ["Nothing scheduled", "Tasks with due dates show up here."], completed: ["Nothing completed yet", "Done is better than perfect."] }[view] || ["All clear", "Add a task above."];
  return `<div class="empty big">${icon(view === "myday" ? "sun" : "check")}<h3>${m[0]}</h3><div>${m[1]}</div></div>`;
}

function taskRow(t) {
  const today = TODAY();
  const meta = [];
  if (state.tasks.view !== "project" && t.project_name) meta.push(`<span>${esc(t.project_name)}</span>`);
  if (t.my_day === today && state.tasks.view !== "myday") meta.push(`<span>${icon("sun")}My Day</span>`);
  if (t.steps?.length) meta.push(`<span>${t.steps.filter((s) => s.done).length} of ${t.steps.length}</span>`);
  if (t.due_date) meta.push(`<span class="${!t.completed && t.due_date < today ? "late" : t.due_date === today ? "today" : ""}">${icon("calendar")}${t.due_date < today && !t.completed ? "Overdue, " : ""}${relDay(t.due_date)}</span>`);
  if (t.reminder_at) meta.push(`<span>${icon("bell")}${fmtTime(t.reminder_at)}</span>`);
  if (t.repeat) meta.push(`<span>${icon("repeat")}${REPEAT_LABEL[t.repeat]}</span>`);
  if (t.note) meta.push(`<span>${icon("file")}Note</span>`);
  return `<div class="task ${t.completed ? "done" : ""} ${state.tasks.selected === t.id ? "selected" : ""}" data-id="${t.id}">
    <button class="check ${t.completed ? "on" : ""}" data-check>${icon("tick")}</button>
    <div class="body"><div class="title">${esc(t.title)}</div>${meta.length ? `<div class="meta">${meta.join("")}</div>` : ""}</div>
    <button class="icon-btn star ${t.important ? "on" : ""}" data-star>${icon("star")}</button></div>`;
}

function bindTaskRows(root) {
  $$(".task", root).forEach((row) => {
    const id = +row.dataset.id;
    row.onclick = (e) => {
      if (e.target.closest("[data-check]")) return toggleDone(id, row);
      if (e.target.closest("[data-star]")) return toggleStar(id, row);
      state.tasks.selected = state.tasks.selected === id ? null : id;
      $$(".task", root).forEach((r) => r.classList.toggle("selected", +r.dataset.id === state.tasks.selected));
      renderDetail();
    };
  });
}
async function toggleDone(id, row) {
  const done = !row.classList.contains("done");
  $("[data-check]", row).classList.toggle("on", done);
  row.classList.toggle("done", done);
  const res = await PATCH(`/api/tasks/${id}`, { completed: done });
  if (done && res.reward) celebrate(res.reward);
  await sleep(300);
  await Promise.all([renderTaskMain(), renderListsPane()]);
  if (state.tasks.selected === id) renderDetail();
  refreshBoot();
}
async function toggleStar(id, row) {
  const on = !$("[data-star]", row).classList.contains("on");
  $("[data-star]", row).classList.toggle("on", on);
  await PATCH(`/api/tasks/${id}`, { important: on ? 1 : 0 });
  renderListsPane();
  if (state.tasks.selected === id) renderDetail();
}

async function renderDetail() {
  const pane = $("#detail"), layout = $("#tasksLayout");
  const id = state.tasks.selected;
  if (!id) { pane.hidden = true; layout.classList.remove("with-detail"); return; }
  let t;
  let goals = [];
  try { [t, goals] = await Promise.all([GET(`/api/tasks/${id}`), GET("/api/goals?status=active")]); } catch { t = null; }
  if (!t) { state.tasks.selected = null; pane.hidden = true; layout.classList.remove("with-detail"); return; }
  pane.hidden = false; layout.classList.add("with-detail");
  const today = TODAY();
  const inMyDay = t.my_day === today;
  pane.innerHTML = `
    <div class="d-title"><button class="check ${t.completed ? "on" : ""}" id="dCheck">${icon("tick")}</button><textarea id="dTitle" rows="1">${esc(t.title)}</textarea><button class="icon-btn star ${t.important ? "on" : ""}" id="dStar">${icon("star")}</button></div>
    <div class="group">${t.steps.map((s) => `<div class="step ${s.done ? "done" : ""}" data-sid="${s.id}"><button class="check sq ${s.done ? "on" : ""}" data-stog>${icon("tick")}</button><span>${esc(s.title)}</span><button class="icon-btn" data-sdel>${icon("x")}</button></div>`).join("")}
      <form class="add-step" id="addStep">${icon("plus")}<input placeholder="${t.steps.length ? "Next step" : "Add step"}"></form></div>
    <div class="group"><div class="d-row ${inMyDay ? "set" : ""}" id="dMyDay">${icon("sun")}${inMyDay ? "Added to My Day" : "Add to My Day"}${inMyDay ? `<button class="icon-btn clear" data-clear="my_day">${icon("x")}</button>` : ""}</div></div>
    <div class="group">
      <label class="d-row ${t.reminder_at ? "set" : ""}">${icon("bell")}${t.reminder_at ? `Remind me at ${fmtTime(t.reminder_at)}, ${relDay(t.reminder_at)}` : "Remind me"}<input type="datetime-local" data-f="reminder_at" value="${t.reminder_at || ""}">${t.reminder_at ? `<button class="icon-btn clear" data-clear="reminder_at">${icon("x")}</button>` : ""}</label>
      <label class="d-row ${t.due_date ? "set" : ""}">${icon("calendar")}${t.due_date ? `Due ${relDay(t.due_date)}` : "Add due date"}<input type="date" data-f="due_date" value="${t.due_date || ""}">${t.due_date ? `<button class="icon-btn clear" data-clear="due_date">${icon("x")}</button>` : ""}</label>
      <label class="d-row ${t.repeat ? "set" : ""}">${icon("repeat")}${t.repeat ? REPEAT_LABEL[t.repeat] : "Repeat"}<select data-f="repeat">${Object.entries(REPEAT_LABEL).map(([k, v]) => `<option value="${k}" ${t.repeat === k ? "selected" : ""}>${v}</option>`).join("")}</select></label>
    </div>
    <div class="group"><label class="d-row">${icon("list")}${esc(t.project_name || "Tasks (no list)")}<select data-f="project_id"><option value="">Tasks (no list)</option>${state.projects.map((p) => `<option value="${p.id}" ${t.project_id === p.id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></label>
      <label class="d-row ${t.goal_id ? "set" : ""}">${icon("target")}${t.goal_id ? "Goal: " + esc(goals.find((g) => g.id === t.goal_id)?.title || "linked") : "Link to a goal"}<select data-f="goal_id"><option value="">No goal</option>${goals.map((g) => `<option value="${g.id}" ${t.goal_id === g.id ? "selected" : ""}>${esc(g.title)}</option>`).join("")}</select></label></div>
    <div class="group"><textarea class="note" id="dNote" placeholder="Add note">${esc(t.note)}</textarea></div>
    <div class="detail-foot"><button class="icon-btn" id="dClose" title="Close">${icon("chevR")}</button><span>Created ${fmtDate(t.created_at.slice(0, 10))}</span><button class="icon-btn" id="dDel" title="Delete">${icon("trash")}</button></div>`;

  const save = async (f) => { const res = await PATCH(`/api/tasks/${id}`, f); if (res.reward) celebrate(res.reward); await Promise.all([renderTaskMain(), renderListsPane()]); renderDetail(); refreshBoot(); };
  const ta = $("#dTitle");
  const fit = () => { ta.style.height = "auto"; ta.style.height = ta.scrollHeight + "px"; };
  fit(); ta.oninput = fit;
  ta.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); ta.blur(); } };
  ta.onblur = () => { const v = ta.value.trim(); if (v && v !== t.title) save({ title: v }); };
  $("#dCheck").onclick = () => save({ completed: !t.completed });
  $("#dStar").onclick = () => save({ important: t.important ? 0 : 1 });
  $("#dMyDay").onclick = (e) => { if (!e.target.closest("[data-clear]")) save({ my_day: inMyDay ? null : today }); };
  $$("[data-f]", pane).forEach((i) => i.addEventListener("change", () => {
    const f = { [i.dataset.f]: i.value || null };
    if (i.dataset.f === "project_id") f.project_id = i.value ? +i.value : null;
    if (i.dataset.f === "goal_id") f.goal_id = i.value ? +i.value : null;
    if (i.dataset.f === "repeat") f.repeat = i.value;
    if (i.dataset.f === "reminder_at" && i.value && !t.due_date) f.due_date = i.value.slice(0, 10);
    save(f);
  }));
  $$("[data-clear]", pane).forEach((b) => (b.onclick = (e) => { e.preventDefault(); e.stopPropagation(); save({ [b.dataset.clear]: null }); }));
  $("#dNote").onblur = (e) => { if (e.target.value !== t.note) save({ note: e.target.value }); };
  $("#addStep").onsubmit = async (e) => { e.preventDefault(); const v = $("input", e.target).value.trim(); if (!v) return; await POST(`/api/tasks/${id}/steps`, { title: v }); renderDetail(); renderTaskMain(); setTimeout(() => $("#addStep input")?.focus(), 50); };
  $$(".step", pane).forEach((s) => {
    $("[data-stog]", s).onclick = async () => { await PATCH(`/api/steps/${s.dataset.sid}`, { done: s.classList.contains("done") ? 0 : 1 }); renderDetail(); renderTaskMain(); };
    $("[data-sdel]", s).onclick = async () => { await DEL(`/api/steps/${s.dataset.sid}`); renderDetail(); renderTaskMain(); };
  });
  $("#dClose").onclick = () => { state.tasks.selected = null; renderDetail(); renderTaskMain(); };
  $("#dDel").onclick = async () => { if (await confirmBox(`“${t.title}” will be permanently deleted.`)) { await DEL(`/api/tasks/${id}`); state.tasks.selected = null; renderDetail(); renderTaskMain(); renderListsPane(); refreshBoot(); } };
}

// ============================== CALENDAR ==============================
const HOUR_PX = 52;
const mondayOf = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; };

VIEWS.calendar = async (el) => {
  if (!state.cal.weekStart) state.cal.weekStart = mondayOf(new Date());
  const ws = state.cal.weekStart, we = addDays(ws, 6);
  const { events, google } = await GET(`/api/events?start=${isoDate(ws)}&end=${isoDate(we)}`);
  const days = [...Array(7)].map((_, i) => addDays(ws, i));
  const label = ws.getMonth() === we.getMonth() ? ws.toLocaleDateString(undefined, { month: "long", year: "numeric" }) : `${ws.toLocaleDateString(undefined, { month: "short" })} – ${we.toLocaleDateString(undefined, { month: "short", year: "numeric" })}`;
  el.innerHTML = `<div class="page wide"><div class="cal-wrap">
    <div class="cal-top"><h1>${esc(label)}</h1>
      <button class="icon-btn" id="prevW">${icon("chevL")}</button><button class="btn sm" id="todayW">Today</button><button class="icon-btn" id="nextW">${icon("chevR")}</button>
      <span class="spacer"></span>
      <span class="status-pill ${google ? "on" : ""}"><i></i>${google ? "Google Calendar synced" : "Local calendar"}</span>
      ${google ? "" : `<a class="btn ghost sm" href="#/settings?s=google">Connect Google</a>`}
      <button class="btn sm" id="blockAI">${icon("sparkle")}Ask Donna to block time</button>
      <button class="btn primary sm" id="newEv">${icon("plus")}New event</button></div>
    <div class="week" id="week"></div></div></div>`;
  const week = $("#week");
  const todayIso = TODAY();
  let html = `<div class="wh" style="border-left:none"></div>`;
  for (const d of days) {
    const iso = isoDate(d);
    const allDay = events.filter((e) => e.all_day && e.start.slice(0, 10) <= iso && (e.end.slice(0, 10) > iso || e.start.slice(0, 10) === iso));
    html += `<div class="wh ${iso === todayIso ? "today" : ""}"><div class="dn">${d.toLocaleDateString(undefined, { weekday: "short" })}</div><div class="dd">${d.getDate()}</div><div class="allday">${allDay.map((e) => `<div class="ev allday ${e.source}" data-ev="${esc(e.id)}">${esc(e.title)}</div>`).join("")}</div></div>`;
  }
  html += `<div class="gutter">${[...Array(24)].map((_, h) => `<div>${h === 0 ? "" : new Date(2000, 0, 1, h).toLocaleTimeString([], { hour: "numeric" })}</div>`).join("")}</div>`;
  for (const d of days) {
    const iso = isoDate(d);
    const dayEvents = events.filter((e) => !e.all_day && e.start.slice(0, 10) === iso);
    html += `<div class="daycol ${iso === todayIso ? "today" : ""}" data-date="${iso}" style="height:${HOUR_PX * 24}px">${layoutDay(dayEvents)}${iso === todayIso ? `<div class="nowbar" style="top:${(new Date().getHours() * 60 + new Date().getMinutes()) * HOUR_PX / 60}px"></div>` : ""}</div>`;
  }
  week.innerHTML = html;
  week.scrollTop = HOUR_PX * 7.5;
  const byId = Object.fromEntries(events.map((e) => [String(e.id), e]));
  $$("[data-ev]", week).forEach((x) => (x.onclick = (e) => { e.stopPropagation(); eventDetail(byId[x.dataset.ev]); }));
  $$(".daycol", week).forEach((col) => (col.onclick = (e) => {
    if (e.target !== col) return;
    const mins = Math.floor((e.offsetY / HOUR_PX) * 2) * 30;
    eventForm({ date: col.dataset.date, start: `${pad(Math.floor(mins / 60))}:${pad(mins % 60)}` });
  }));
  $("#prevW").onclick = () => { state.cal.weekStart = addDays(ws, -7); render(); };
  $("#nextW").onclick = () => { state.cal.weekStart = addDays(ws, 7); render(); };
  $("#todayW").onclick = () => { state.cal.weekStart = mondayOf(new Date()); render(); };
  $("#newEv").onclick = () => eventForm({});
  $("#blockAI").onclick = () => askDonna("Find a free 2-hour slot tomorrow and block it for deep work.");
};

function layoutDay(evs) {
  evs.sort((a, b) => a.start.localeCompare(b.start));
  const cols = [], placed = [];
  for (const e of evs) {
    let c = cols.findIndex((end) => end <= e.start);
    if (c === -1) { c = cols.length; cols.push(e.end); } else cols[c] = e.end;
    placed.push({ e, c });
  }
  const n = Math.max(1, cols.length);
  return placed.map(({ e, c }) => {
    const s = parseD(e.start), en = parseD(e.end);
    const top = (s.getHours() * 60 + s.getMinutes()) * HOUR_PX / 60;
    const h = Math.max(22, ((en - s) / 60000) * HOUR_PX / 60 - 2);
    return `<div class="ev ${e.source}" data-ev="${esc(e.id)}" style="top:${top}px;height:${h}px;left:calc(${(c / n) * 100}% + 3px);width:calc(${100 / n}% - 6px);right:auto"><b>${esc(e.title)}</b><span>${fmtTime(e.start)}${h > 34 ? " – " + fmtTime(e.end) : ""}</span></div>`;
  }).join("");
}

function eventDetail(e) {
  modal({ title: e.title, body: `<div class="muted" style="margin-bottom:10px">${e.all_day ? fmtDate(e.start) + " · All day" : `${fmtDate(e.start, { weekday: "long", day: "numeric", month: "long" })} · ${fmtTime(e.start)} – ${fmtTime(e.end)}`}</div>
    ${e.location ? `<p>📍 ${esc(e.location)}</p>` : ""}${e.description ? `<p style="white-space:pre-wrap;color:var(--ink-2)">${esc(e.description)}</p>` : ""}
    ${e.attendees?.length ? `<p class="muted" style="font-size:12.5px">With ${e.attendees.map(esc).join(", ")}</p>` : ""}
    <span class="chip ${e.source === "google" ? "" : "accent"}">${e.source === "google" ? "Google Calendar" : "Donna calendar"}</span>
    <div id="prepPack"><div class="prep-box muted">Preparing your prep pack…</div></div>`,
    foot: `${e.link ? `<a class="btn ghost" target="_blank" href="${esc(e.link)}">${icon("link")}Open in Google</a>` : ""}<button class="btn danger" id="evDel">${icon("trash")}Delete</button>`,
    onMount: (m, close) => { renderPrep($("#prepPack", m), e); $("#evDel", m).onclick = async () => { if (!(await confirmBox(`Delete “${e.title}”?`))) return; try { await DEL(`/api/events/${e.source}/${encodeURIComponent(e.id)}`); close(); render(); toast("Event deleted"); } catch (err) { fail(err); } }; } });
}

async function renderPrep(box, e, ai = false) {
  try {
    const p = await POST(`/api/prep${ai ? "?ai=true" : ""}`, e);
    const has = p.people.length || p.open_tasks.length || p.related.length;
    if (!has) { box.innerHTML = `<div class="prep-box muted">No notes on this yet. Log people on the People page and Donna will brief you before meetings with them.</div>`; return; }
    box.innerHTML = `<div class="prep-box"><h4>${icon("sparkle")} Prep pack</h4>
      ${p.talking_points ? `<div style="margin-bottom:10px">${md(p.talking_points)}</div>` : `<button class="btn sm" id="tpBtn" style="margin-bottom:8px">${icon("sparkle")}Suggest talking points</button>`}
      ${p.people.map((x) => `<div style="margin:8px 0"><b>${esc(x.name)}</b>${x.relationship ? ` <span class="muted">· ${esc(x.relationship)}</span>` : ""}${x.family ? `<div class="muted">${esc(x.family)}</div>` : ""}${x.notes ? `<div>${esc(x.notes.slice(0, 220))}</div>` : ""}${x.last_contact ? `<div class="muted" style="font-size:12px">Last spoke ${esc(x.last_contact)}${x.last_note ? ": " + esc(x.last_note) : ""}</div>` : ""}</div>`).join("")}
      ${p.open_tasks.length ? `<h4 style="margin-top:10px">Open items</h4><ul>${p.open_tasks.map((t) => `<li>${esc(t.title)}</li>`).join("")}</ul>` : ""}
      ${p.related.length ? `<h4 style="margin-top:10px">Related</h4><ul>${p.related.map((r) => `<li><span class="muted">${esc(r.type)}:</span> ${esc(r.title || r.date || "")} ${esc((r.content || r.excerpt || r.body || "").slice(0, 100))}</li>`).join("")}</ul>` : ""}</div>`;
    const tb = $("#tpBtn", box);
    if (tb) tb.onclick = () => { tb.disabled = true; tb.textContent = "Thinking…"; renderPrep(box, e, true); };
  } catch (err) { box.innerHTML = ""; }
}

function eventForm({ date = TODAY(), start = "10:00" }) {
  const [h, mi] = start.split(":").map(Number);
  const endT = `${pad(Math.min(23, h + (mi + 30 >= 60 ? 1 : 0)))}:${pad((mi + 30) % 60)}`;
  modal({ title: "New event", body: `
    <div class="field"><label>Title</label><input class="input" name="title" placeholder="Dentist, Call with Priya, Focus time…"></div>
    <div class="row"><div class="field"><label>Date</label><input class="input" type="date" name="date" value="${date}"></div>
      <div class="field"><label>Start</label><input class="input" type="time" name="start" value="${start}"></div>
      <div class="field"><label>End</label><input class="input" type="time" name="end" value="${endT}"></div></div>
    <div class="field" style="flex-direction:row;align-items:center;gap:10px"><label class="switch"><input type="checkbox" name="all_day"><span></span></label><span>All day</span></div>
    <div class="field"><label>Location</label><input class="input" name="location"></div>
    <div class="field"><label>Notes</label><textarea class="textarea" name="description" style="min-height:70px"></textarea></div>
    <div class="hint muted" style="font-size:12px">${state.boot.google.connected ? "Saved to your Google Calendar." : "Saved to Donna's calendar. Connect Google in Settings to sync."} You'll get an email reminder before it starts.</div>`,
    foot: `<button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="evSave">Save event</button>`,
    onMount: (m, close) => { $("#evSave", m).onclick = async () => {
      const f = formData(m);
      if (!f.title.trim()) return toast("Give it a title", { error: true });
      try { await POST("/api/events", { title: f.title, start: `${f.date}T${f.start}`, end: `${f.date}T${f.end}`, all_day: f.all_day, location: f.location, description: f.description }); close(); toast("Event saved"); render(); } catch (e) { fail(e); }
    }; } });
}

// ============================== JOURNAL ==============================
const MOODS = [["great", "Great"], ["good", "Good"], ["okay", "Okay"], ["low", "Low"], ["rough", "Rough"]];
const PROMPTS = ["What happened today that you want to remember?", "What's taking up the most space in your head?", "What went well, and why?", "What would make tomorrow 1% better?", "Who made a difference to your day?", "What are you avoiding?", "What did you learn today?"];

VIEWS.journal = async (el, r) => {
  if (r.params.get("date")) state.journal.date = r.params.get("date");
  const { entries, streak } = await GET("/api/journal");
  state.journal.entries = entries;
  el.innerHTML = `<div class="page wide"><div class="journal-layout">
    <aside class="journal-side">
      <div class="card streak"><div class="n">${streak}</div><div><b>day streak</b><div class="muted" style="font-size:12.5px">${streak ? "Keep the thread going." : "Start one tonight."}</div></div></div>
      <div class="mini-cal" id="miniCal"></div>
      <input class="input" id="jSearch" placeholder="Search your journal…" style="margin-bottom:12px">
      <div id="jList"></div></aside>
    <section class="journal-editor" id="jEditor"></section></div></div>`;
  renderMiniCal(); renderJList(entries);
  $("#jSearch").oninput = debounce(async (e) => { const q = e.target.value.trim(); renderJList(q ? (await GET(`/api/journal?q=${encodeURIComponent(q)}`)).entries : state.journal.entries); }, 250);
  renderJEditor();
};

function renderMiniCal() {
  const sel = parseD(state.journal.date);
  const m = state.journal.month || new Date(sel.getFullYear(), sel.getMonth(), 1);
  state.journal.month = m;
  const has = new Set(state.journal.entries.filter((e) => e.body).map((e) => e.date));
  const start = mondayOf(m);
  let cells = "";
  for (let i = 0; i < 42; i++) {
    const d = addDays(start, i), iso = isoDate(d);
    if (i >= 35 && d.getMonth() !== m.getMonth()) break;
    cells += `<div class="d ${d.getMonth() !== m.getMonth() ? "other" : ""} ${iso === TODAY() ? "today" : ""} ${iso === state.journal.date ? "sel" : ""} ${has.has(iso) ? "has" : ""}" data-d="${iso}">${d.getDate()}</div>`;
  }
  $("#miniCal").innerHTML = `<div class="mc-head"><button class="icon-btn" id="mPrev">${icon("chevL")}</button><span>${m.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</span><button class="icon-btn" id="mNext">${icon("chevR")}</button></div>
    <div class="mc-grid">${["M", "T", "W", "T", "F", "S", "S"].map((x) => `<div class="dow">${x}</div>`).join("")}${cells}</div>`;
  $("#mPrev").onclick = () => { state.journal.month = new Date(m.getFullYear(), m.getMonth() - 1, 1); renderMiniCal(); };
  $("#mNext").onclick = () => { state.journal.month = new Date(m.getFullYear(), m.getMonth() + 1, 1); renderMiniCal(); };
  $$("#miniCal .d").forEach((d) => (d.onclick = () => { state.journal.date = d.dataset.d; renderMiniCal(); renderJEditor(); renderJList(state.journal.entries); }));
}
function renderJList(entries) {
  $("#jList").innerHTML = entries.filter((e) => e.body).slice(0, 60).map((e) => `<div class="jlist-item ${e.date === state.journal.date ? "active" : ""}" data-d="${e.date}"><div class="jd">${e.mood ? `<span class="mood-dot m-${e.mood}"></span>` : ""}${fmtDate(e.date, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</div><div class="jx">${esc(e.title || e.body.slice(0, 140))}</div></div>`).join("") || `<div class="muted" style="font-size:13px;padding:8px">Your entries will appear here.</div>`;
  $$("#jList .jlist-item").forEach((i) => (i.onclick = () => { state.journal.date = i.dataset.d; state.journal.month = null; renderMiniCal(); renderJEditor(); renderJList(state.journal.entries); }));
}
async function renderJEditor() {
  const d = state.journal.date;
  const j = await GET(`/api/journal/${d}`);
  const box = $("#jEditor");
  const prompt = PROMPTS[parseD(d).getDate() % PROMPTS.length];
  box.innerHTML = `<div class="je-inner">
    <div class="eyebrow">${parseD(d).toLocaleDateString(undefined, { weekday: "long" })}${d === TODAY() ? " · Today" : ""}</div>
    <h1 class="je-date">${parseD(d).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" })}</h1>
    <div class="moods">${MOODS.map(([k, l]) => `<button class="chip btnlike ${j.mood === k ? "active" : ""}" data-mood="${k}"><span class="mood-dot m-${k}"></span>${l}</button>`).join("")}</div>
    <input class="je-title" id="jeTitle" placeholder="Title (optional)" value="${esc(j.title)}">
    <textarea class="je-body" id="jeBody" placeholder="${esc(prompt)}">${esc(j.body)}</textarea>
    <div class="je-foot"><span id="jeWords"></span><span id="jeSaved"></span><span class="spacer"></span>
      <button class="btn sm" id="jeReflect">${icon("sparkle")}Reflect with Donna</button>${j.id ? `<button class="icon-btn" id="jeDel" title="Delete entry">${icon("trash")}</button>` : ""}</div></div>`;
  const body = $("#jeBody"), title = $("#jeTitle");
  let mood = j.mood;
  const fit = () => { body.style.height = "auto"; body.style.height = Math.max(body.scrollHeight, window.innerHeight * 0.5) + "px"; };
  const words = () => { const n = body.value.trim().split(/\s+/).filter(Boolean).length; $("#jeWords").textContent = `${n} ${n === 1 ? "word" : "words"}`; };
  fit(); words();
  const save = debounce(async () => {
    $("#jeSaved").textContent = "Saving…";
    const saved = await PUT(`/api/journal/${d}`, { body: body.value, title: title.value, mood });
    $("#jeSaved").textContent = "Saved";
    const i = state.journal.entries.findIndex((e) => e.date === d);
    if (i >= 0) state.journal.entries[i] = saved; else state.journal.entries.unshift(saved);
    state.journal.entries.sort((a, b) => b.date.localeCompare(a.date));
    renderJList(state.journal.entries); renderMiniCal();
  }, 700);
  body.oninput = () => { fit(); words(); save(); };
  title.oninput = save;
  $$("[data-mood]", box).forEach((b) => (b.onclick = () => { mood = mood === b.dataset.mood ? "" : b.dataset.mood; $$("[data-mood]", box).forEach((x) => x.classList.toggle("active", x.dataset.mood === mood)); save(); }));
  $("#jeReflect").onclick = () => askDonna(`Read my journal entry for ${d} and reflect on it with me.`);
  $("#jeDel") && ($("#jeDel").onclick = async () => { if (await confirmBox("Delete this journal entry?")) { await DEL(`/api/journal/${d}`); state.journal.entries = state.journal.entries.filter((e) => e.date !== d); renderJList(state.journal.entries); renderMiniCal(); renderJEditor(); } });
  if (!j.body) body.focus();
}

// ============================== IDEAS ==============================
const COLORS = ["", "yellow", "rose", "sage", "sky", "lilac", "sand"];

VIEWS.ideas = async (el) => {
  const projects = await GET("/api/projects");
  state.projects = projects;
  el.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Ideas</h1><div class="sub">Catch them before they fly away.</div></div>
      <div class="actions"><input class="input" id="iSearch" placeholder="Search ideas…" style="width:220px" value="${esc(state.ideas.q)}"></div></div>
    <div class="composer-note" id="cNote"><input id="cnTitle" placeholder="Title"><textarea id="cnBody" placeholder="Take a note… what's the idea?"></textarea>
      <div class="cn-foot"><div class="swatches" id="cnColors">${COLORS.map((c) => `<button class="swatch ${c ? "c-" + c : ""} ${c === state.ideas.color ? "sel" : ""}" data-c="${c}" title="${c || "Default"}" style="${c ? "" : "background:var(--surface)"}"></button>`).join("")}</div>
      <span class="spacer"></span><select class="select" id="cnProject" style="width:auto;padding:6px 10px"><option value="">Unsorted</option>${projects.map((p) => `<option value="${p.id}" ${state.ideas.projectId === p.id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select>
      <button class="btn primary sm" id="cnSave">Save</button></div></div>
    <div class="filter-bar" id="iFilters"></div>
    <div class="masonry" id="notes"></div></div>`;
  let color = state.ideas.color;
  $$("#cnColors .swatch").forEach((s) => (s.onclick = () => { color = s.dataset.c; $$("#cnColors .swatch").forEach((x) => x.classList.toggle("sel", x === s)); $("#cNote").className = "composer-note " + (color ? "c-" + color : ""); }));
  const body = $("#cnBody");
  body.oninput = () => { body.style.height = "auto"; body.style.height = body.scrollHeight + "px"; };
  const saveNew = async () => {
    const t = $("#cnTitle").value.trim(), b = body.value.trim();
    if (!t && !b) return;
    await POST("/api/ideas", { title: t, body: b, color, project_id: $("#cnProject").value ? +$("#cnProject").value : null });
    $("#cnTitle").value = ""; body.value = ""; body.style.height = "auto";
    toast("Idea saved"); renderNotes();
  };
  $("#cnSave").onclick = saveNew;
  $("#cNote").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) saveNew(); });
  $("#iSearch").oninput = debounce((e) => { state.ideas.q = e.target.value.trim(); renderNotes(); }, 250);
  renderNotes();
};

async function renderNotes() {
  const { projectId, archived, q } = state.ideas;
  const qs = new URLSearchParams();
  if (projectId) qs.set("project_id", projectId);
  if (archived) qs.set("archived", "true");
  if (q) qs.set("q", q);
  const items = await GET(`/api/ideas?${qs}`);
  const filters = $("#iFilters");
  filters.innerHTML = `<button class="chip btnlike ${!projectId && !archived ? "active" : ""}" data-p="">All ideas</button>` +
    state.projects.map((p) => `<button class="chip btnlike ${projectId === p.id && !archived ? "active" : ""}" data-p="${p.id}">${esc(p.emoji || "")} ${esc(p.name)} <span class="muted">${p.idea_count || ""}</span></button>`).join("") +
    `<span class="spacer"></span><button class="chip btnlike ${archived ? "active" : ""}" id="iArch">${icon("archive")}Archive</button>`;
  $$("[data-p]", filters).forEach((b) => (b.onclick = () => { state.ideas.projectId = b.dataset.p ? +b.dataset.p : null; state.ideas.archived = false; renderNotes(); }));
  $("#iArch").onclick = () => { state.ideas.archived = !state.ideas.archived; renderNotes(); };
  const box = $("#notes");
  box.innerHTML = items.map((i) => `<div class="note ${i.color ? "c-" + i.color : ""}" data-id="${i.id}">
      <button class="icon-btn pin ${i.pinned ? "on" : ""}" data-act="pin" title="Pin">${icon("pin")}</button>
      ${i.title ? `<h4>${esc(i.title)}</h4>` : ""}<div class="nb">${esc(i.body)}</div>
      <div class="nf">${i.project_name ? `<span class="chip">${esc(i.project_name)}</span>` : ""}${i.tags ? i.tags.split(",").filter(Boolean).map((t) => `<span class="chip">#${esc(t.trim())}</span>`).join("") : ""}
        <div class="tools"><button class="icon-btn" data-act="color" title="Colour">${icon("color")}</button><button class="icon-btn" data-act="task" title="Make it a task">${icon("check")}</button><button class="icon-btn" data-act="develop" title="Develop with Donna">${icon("sparkle")}</button><button class="icon-btn" data-act="archive" title="${i.archived ? "Unarchive" : "Archive"}">${icon("archive")}</button><button class="icon-btn" data-act="delete" title="Delete">${icon("trash")}</button></div></div></div>`).join("");
  if (!items.length) box.outerHTML = `<div id="notes" class="masonry"><div class="empty big" style="column-span:all">${icon("bulb")}<h3>${archived ? "Archive is empty" : q ? "No matches" : "No ideas here yet"}</h3><div>${archived ? "" : "Write one above, or tell Donna “idea: …” from anywhere with ⌘K."}</div></div></div>`;
  const byId = Object.fromEntries(items.map((i) => [i.id, i]));
  $$(".note", $("#notes")).forEach((n) => (n.onclick = async (e) => {
    const i = byId[n.dataset.id];
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "pin") { await PATCH(`/api/ideas/${i.id}`, { pinned: i.pinned ? 0 : 1 }); return renderNotes(); }
    if (act === "color") { await PATCH(`/api/ideas/${i.id}`, { color: COLORS[(COLORS.indexOf(i.color) + 1) % COLORS.length] }); return renderNotes(); }
    if (act === "archive") { await PATCH(`/api/ideas/${i.id}`, { archived: i.archived ? 0 : 1 }); toast(i.archived ? "Restored" : "Archived"); return renderNotes(); }
    if (act === "delete") { if (await confirmBox("Delete this idea?")) { await DEL(`/api/ideas/${i.id}`); renderNotes(); } return; }
    if (act === "task") { await POST(`/api/ideas/${i.id}/to-task`); toast("Added to your To Do"); refreshBoot(); return; }
    if (act === "develop") return askDonna(`Help me develop this idea: “${i.title}”. ${i.body}`);
    ideaEditor(i);
  }));
}

function ideaEditor(i) {
  modal({ title: "Edit idea", size: "lg", body: `
    <div class="field"><input class="input" name="title" value="${esc(i.title)}" placeholder="Title" style="font-weight:600;font-size:16px"></div>
    <div class="field"><textarea class="textarea" name="body" style="min-height:220px">${esc(i.body)}</textarea></div>
    <div class="row"><div class="field"><label>Project</label><select class="select" name="project_id"><option value="">Unsorted</option>${state.projects.map((p) => `<option value="${p.id}" ${i.project_id === p.id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></div>
    <div class="field"><label>Tags</label><input class="input" name="tags" value="${esc(i.tags)}" placeholder="pricing, growth"></div></div>`,
    foot: `<span class="muted" style="margin-right:auto;font-size:12px">Edited ${esc((i.updated_at || i.created_at || "").replace("T", " "))}</span><button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="iSave">Save</button>`,
    onMount: (m, close) => { $("#iSave", m).onclick = async () => { const f = formData(m); f.project_id = f.project_id ? +f.project_id : null; await PATCH(`/api/ideas/${i.id}`, f); close(); renderNotes(); }; } });
}

// ============================== MEMORY ==============================
const MEM_TEMPLATES = [["profile", "Home address"], ["profile", "Birthday"], ["profile", "Shirt / shoe size"], ["preference", "Coffee order"], ["preference", "Seat preference on flights"], ["person", "Mom's birthday"], ["goal", "Goal for this year"], ["wish", "Wishlist item"], ["health", "Allergies"], ["travel", "Frequent flyer number"]];

VIEWS.memory = async (el, r) => {
  const q = r.params.get("q") || "";
  const { items, categories } = await GET(`/api/memories${q ? "?q=" + encodeURIComponent(q) : ""}`);
  const groups = {};
  items.forEach((m) => (groups[m.category] = groups[m.category] || []).push(m));
  el.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Memory</h1><div class="sub">What Donna knows about you: details, preferences, people, goals and wishes.</div></div>
      <div class="actions"><input class="input" id="mSearch" placeholder="Search memory…" style="width:200px" value="${esc(q)}"><button class="btn primary" id="mAdd">${icon("plus")}Add</button></div></div>
    <div class="callout">${icon("shield")} Passwords, cards and ID numbers belong in the <a href="#/vault" style="color:var(--accent);font-weight:500">Vault</a>, where they're encrypted with your master password. Everything else goes here so Donna can use it in conversation.</div>
    <div class="filter-bar">${MEM_TEMPLATES.map(([c, t]) => `<button class="chip btnlike" data-tc="${c}" data-tt="${esc(t)}">${icon("plus")}${esc(t)}</button>`).join("")}</div>
    ${Object.keys(groups).length ? categories.filter((c) => groups[c]).map((c) => `<div class="mem-cat-head"><h3>${c === "person" ? "People" : c + (["goal", "wish", "preference"].includes(c) ? "s" : "")}</h3><span class="muted">${groups[c].length}</span></div>
      <div class="mem-grid">${groups[c].map((m) => `<div class="card mem" data-id="${m.id}"><div class="mt">${esc(m.title)}</div><div class="mc">${esc(m.content)}</div></div>`).join("")}</div>`).join("")
      : `<div class="empty big">${icon("user")}<h3>${q ? "Nothing matches" : "Tell Donna about you"}</h3><div>Use the shortcuts above, or just say “remember that…” in chat.</div></div>`}
  </div>`;
  const byId = Object.fromEntries(items.map((m) => [m.id, m]));
  $("#mAdd").onclick = () => memoryForm({}, categories);
  $$("[data-tc]", el).forEach((b) => (b.onclick = () => memoryForm({ category: b.dataset.tc, title: b.dataset.tt }, categories)));
  $$(".mem", el).forEach((c) => (c.onclick = () => memoryForm(byId[c.dataset.id], categories)));
  $("#mSearch").onkeydown = (e) => { if (e.key === "Enter") go(`#/memory?q=${encodeURIComponent(e.target.value.trim())}`); };
};
function memoryForm(m, categories) {
  modal({ title: m.id ? "Edit memory" : "Remember", body: `
    <div class="row"><div class="field" style="flex:0 0 160px"><label>Category</label><select class="select" name="category">${categories.map((c) => `<option ${(m.category || "general") === c ? "selected" : ""}>${c}</option>`).join("")}</select></div>
    <div class="field"><label>What is it?</label><input class="input" name="title" value="${esc(m.title || "")}" placeholder="e.g. Coffee order"></div></div>
    <div class="field"><label>Details</label><textarea class="textarea" name="content" placeholder="e.g. Oat flat white, extra hot">${esc(m.content || "")}</textarea></div>
    <div class="field"><label>Tags</label><input class="input" name="tags" value="${esc(m.tags || "")}"></div>`,
    foot: `${m.id ? `<button class="btn ghost danger" id="mDel" style="margin-right:auto">${icon("trash")}</button>` : ""}<button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="mSave">Save</button>`,
    onMount: (el, close) => {
      if (m.title && !m.id) setTimeout(() => $("[name=content]", el).focus(), 40);
      $("#mSave", el).onclick = async () => { const f = formData(el); if (!f.title.trim()) return; m.id ? await PATCH(`/api/memories/${m.id}`, f) : await POST("/api/memories", f); close(); toast("Donna will remember that."); render(); };
      $("#mDel", el) && ($("#mDel", el).onclick = async () => { await DEL(`/api/memories/${m.id}`); close(); render(); });
    } });
}

// ============================== VAULT ==============================
VIEWS.vault = async (el) => {
  const st = await GET("/api/vault/status");
  if (!st.configured) {
    el.innerHTML = `<div class="page"><div class="lock-screen"><div class="lock-icon">${icon("shield")}</div><h2>Create your vault</h2>
      <p class="muted">Cards, passwords, bank details and IDs are encrypted with AES-256 using a key derived from your master password. It is never stored, so <b>it cannot be recovered if you forget it</b>.</p>
      <form id="vSetup" style="text-align:left;margin-top:22px"><div class="field"><label>Master password</label><input class="input" type="password" name="p1" minlength="8" autocomplete="new-password" required></div>
      <div class="field"><label>Confirm</label><input class="input" type="password" name="p2" autocomplete="new-password" required></div><button class="btn primary" style="width:100%;justify-content:center">Create vault</button></form></div></div>`;
    $("#vSetup").onsubmit = async (e) => { e.preventDefault(); const f = formData(e.target); if (f.p1 !== f.p2) return toast("Passwords don't match", { error: true }); try { await POST("/api/vault/setup", { password: f.p1 }); refreshBoot(); render(); } catch (err) { fail(err); } };
    return;
  }
  if (!st.unlocked) {
    el.innerHTML = `<div class="page"><div class="lock-screen"><div class="lock-icon">${icon("lock")}</div><h2>Vault is locked</h2><p class="muted">Enter your master password. It auto-locks after ${st.autolock_min} minutes of inactivity.</p>
      <form id="vUnlock" style="margin-top:20px;display:flex;gap:8px"><input class="input" type="password" name="password" placeholder="Master password" autocomplete="current-password" autofocus><button class="btn primary">Unlock</button></form></div></div>`;
    $("#vUnlock").onsubmit = async (e) => { e.preventDefault(); try { await POST("/api/vault/unlock", formData(e.target)); refreshBoot(); render(); } catch (err) { fail(err); } };
    setTimeout(() => $("#vUnlock input")?.focus(), 50);
    return;
  }
  const { items } = await GET("/api/vault");
  const filter = state.vaultFilter || "";
  el.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Vault</h1><div class="sub">${items.length} encrypted ${items.length === 1 ? "item" : "items"} · unlocked</div></div>
      <div class="actions"><button class="btn ghost" id="vLock">${icon("lock")}Lock now</button><button class="btn primary" id="vAdd">${icon("plus")}Add item</button></div></div>
    <div class="filter-bar"><button class="chip btnlike ${!filter ? "active" : ""}" data-f="">All</button>${Object.entries(VAULT_SPEC).map(([k, s]) => `<button class="chip btnlike ${filter === k ? "active" : ""}" data-f="${k}">${icon(s.icon)}${s.label}s</button>`).join("")}</div>
    <div class="vault-grid">${items.filter((i) => !filter || i.category === filter).map((i) => { const s = VAULT_SPEC[i.category] || VAULT_SPEC.note; return `<div class="card vitem" data-id="${i.id}"><div class="vc-icon" style="width:38px;height:38px;border-radius:10px;background:var(--accent-soft);color:var(--accent);display:grid;place-items:center">${icon(s.icon)}</div><div style="min-width:0"><div style="font-weight:600">${esc(i.title)}</div><div class="muted" style="font-size:12.5px">${esc(s.label)}${i.hint ? " · " + esc(i.hint) : ""}</div></div></div>`; }).join("") || `<div class="empty">Nothing here yet.</div>`}</div>
    <p class="muted" style="font-size:12.5px;margin-top:26px">${icon("sparkle")} Ask Donna “what's my HDFC card number?” and she'll show the item in a secure card. The AI only sees the title and last 4 digits, never the secret itself.</p></div>`;
  $("#vLock").onclick = async () => { await POST("/api/vault/lock"); refreshBoot(); render(); };
  $("#vAdd").onclick = () => vaultTypePicker();
  $$("[data-f]", el).forEach((b) => (b.onclick = () => { state.vaultFilter = b.dataset.f; render(); }));
  $$(".vitem", el).forEach((c) => (c.onclick = () => vaultDetail(+c.dataset.id)));
};
function vaultTypePicker() {
  modal({ title: "Add to vault", body: `<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">${Object.entries(VAULT_SPEC).map(([k, s]) => `<button class="card vitem" data-k="${k}" style="text-align:left">${icon(s.icon)}<b style="font-weight:500">${s.label}</b></button>`).join("")}</div>`,
    onMount: (m, close) => $$("[data-k]", m).forEach((b) => (b.onclick = () => { close(); vaultForm({ category: b.dataset.k, data: {} }); })) });
}
function vaultForm(v) {
  const spec = VAULT_SPEC[v.category];
  const gen = () => { const c = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%&*?"; const a = crypto.getRandomValues(new Uint32Array(20)); return [...a].map((x) => c[x % c.length]).join(""); };
  modal({ title: v.id ? `Edit ${spec.label.toLowerCase()}` : `New ${spec.label.toLowerCase()}`, body: `
    <div class="field"><label>Title</label><input class="input" name="title" value="${esc(v.title || "")}" placeholder="${v.category === "card" ? "HDFC Regalia" : v.category === "login" ? "Netflix" : v.category === "bank" ? "SBI Savings" : v.category === "identity" ? "Passport" : "Wi-Fi password"}"></div>
    ${spec.fields.map(([k, label, flags = ""]) => `<div class="field"><label>${esc(label)}</label>${flags.includes("area") ? `<textarea class="textarea" name="d_${k}">${esc(v.data[k] || "")}</textarea>` : `<div style="display:flex;gap:6px"><input class="input ${flags.includes("mono") ? "mono" : ""}" name="d_${k}" value="${esc(v.data[k] || "")}" ${flags.includes("secret") ? 'type="password" autocomplete="off"' : ""}>${flags.includes("secret") ? `<button type="button" class="icon-btn" data-peek>${icon("eye")}</button>` : ""}${k === "password" ? `<button type="button" class="btn sm" data-gen>Generate</button>` : ""}</div>`}</div>`).join("")}`,
    foot: `<button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="vSave">${icon("lock")}Encrypt & save</button>`,
    onMount: (m, close) => {
      $$("[data-peek]", m).forEach((b) => (b.onclick = () => { const i = b.previousElementSibling; i.type = i.type === "password" ? "text" : "password"; }));
      $("[data-gen]", m) && ($("[data-gen]", m).onclick = () => { const i = $("[name=d_password]", m); i.value = gen(); i.type = "text"; });
      $("#vSave", m).onclick = async () => {
        const f = formData(m);
        if (!f.title.trim()) return toast("Add a title", { error: true });
        const data = {};
        Object.entries(f).forEach(([k, val]) => { if (k.startsWith("d_") && val.trim()) data[k.slice(2)] = val.trim(); });
        try { v.id ? await PATCH(`/api/vault/${v.id}`, { category: v.category, title: f.title.trim(), data }) : await POST("/api/vault", { category: v.category, title: f.title.trim(), data }); close(); toast("Encrypted and saved"); render(); }
        catch (e) { if (e.locked) { close(); render(); } fail(e); }
      };
    } });
}
async function vaultDetail(id) {
  let v;
  try { v = await GET(`/api/vault/${id}`); } catch (e) { if (e.locked) { render(); } return fail(e); }
  const d = v.data;
  const cardVis = v.category === "card" ? `<div class="payment-card" style="margin-bottom:16px"><div class="pc-bank">${esc(d.bank || v.title)}</div><div class="pc-num">•••• •••• •••• ${esc(String(d.number || "").replace(/\s/g, "").slice(-4))}</div><div class="pc-foot"><span>${esc(d.cardholder || "")}</span><span>${esc(d.expiry || "")} ${esc(d.network || "")}</span></div></div>` : "";
  modal({ title: v.title, body: cardVis + vaultFieldsHTML(v.category, d) + (d.url ? `<p><a href="${esc(/^https?:/.test(d.url) ? d.url : "https://" + d.url)}" target="_blank" style="color:var(--accent)">${icon("link")} Open website</a></p>` : ""),
    foot: `<button class="btn ghost danger" id="vDel" style="margin-right:auto">${icon("trash")}</button><button class="btn" id="vEdit">${icon("edit")}Edit</button>`,
    onMount: (m, close) => {
      bindVaultFields(m);
      $("#vEdit", m).onclick = () => { close(); vaultForm(v); };
      $("#vDel", m).onclick = async () => { if (await confirmBox(`Permanently delete “${v.title}” from the vault?`)) { await DEL(`/api/vault/${id}`); close(); render(); } };
    } });
}

// ============================== SETTINGS (Admin) ==============================
const S_SECTIONS = [["profile", "Profile", "user"], ["ai", "AI model", "cpu"], ["email", "Email & reminders", "mail"], ["inbox", "Inbox triage", "inbox"], ["automation", "Briefings & prep", "sun"], ["subs", "Subscriptions", "card"], ["google", "Google Calendar", "calendar"], ["phone", "Phone & Telegram", "phone"], ["voice", "Voice", "volume"], ["security", "Vault", "lock"], ["login", "Login & hosting", "shield"], ["skills", "Agent skills", "sparkle"], ["data", "Data & appearance", "download"]];

VIEWS.settings = async (el, r) => {
  const s = await GET("/api/settings");
  const g = r.params.get("google");
  if (g === "connected") toast("Google Calendar connected", { title: "Done." });
  if (g === "error") toast(r.params.get("msg") || "Google connection failed", { error: true });
  const ol = await GET("/api/ai/status");
  const sw = (name, on) => `<label class="switch"><input type="checkbox" name="${name}" ${on ? "checked" : ""}><span></span></label>`;
  const row = (lbl, sub, ctl) => `<div class="s-row"><div class="lbl"><b>${lbl}</b>${sub ? `<span>${sub}</span>` : ""}</div><div class="ctl">${ctl}</div></div>`;
  const inp = (name, val, attrs = "") => `<input class="input" name="${name}" value="${esc(val ?? "")}" ${attrs}>`;
  el.innerHTML = `<div class="page"><div class="page-head"><div><h1>Admin</h1><div class="sub">Configure how Donna works for you.</div></div></div>
  <div class="settings-layout"><nav class="settings-nav">${S_SECTIONS.map(([k, l, ic]) => `<a data-s="${k}">${icon(ic)}${l}</a>`).join("")}</nav><div>

  <section class="card s-section" id="s-profile" data-form><h2>Profile</h2><p class="desc">The basics Donna uses to address you, plan your day and send reminders.</p>
    ${row("Your name", "How Donna addresses you", inp("user_name", s.user_name))}
    ${row("Your email", "Reminders and briefings go here", inp("notify_email", s.notify_email, 'type="email"'))}
    ${row("Timezone", "All reminders, dates and Donna's sense of “today” use this", `<select class="select" name="timezone">${["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "Europe/Berlin", "America/New_York", "America/Los_Angeles", "Australia/Sydney", "UTC"].map((z) => `<option ${(s.timezone || "Asia/Kolkata") === z ? "selected" : ""}>${z}</option>`).join("")}</select>`)}
    ${row("Working hours", "Used when finding free time",`<div style="display:flex;gap:6px">${inp("work_start", s.work_start, 'type="time"')}${inp("work_end", s.work_end, 'type="time"')}</div>`)}
    <div class="field" style="margin-top:14px"><label>Standing instructions for Donna</label><textarea class="textarea" name="custom_instructions" placeholder="e.g. I'm vegetarian. Never book meetings before 10am. Keep replies very short. My manager is Priya.">${esc(s.custom_instructions)}</textarea><span class="hint">Added to every conversation, like briefing a new assistant on day one.</span></div>
    <button class="btn primary" data-save>Save profile</button></section>

  <section class="card s-section" id="s-ai" data-form><h2>AI model</h2><p class="desc">The brain behind Donna. Claude gives the best judgement, dates and mentoring. Ollama keeps everything on this Mac but is slower and less accurate.</p>
    <div style="margin-bottom:12px"><span class="status-pill ${ol.ok && ol.model_installed ? "on" : "off"}"><i></i>${ol.ok && ol.model_installed ? `Connected · ${esc(ol.display_name || ol.model)}` : esc(ol.error || (ol.provider === "ollama" ? `Ollama is running, but ${ol.model} isn't installed` : "Not connected"))}</span></div>
    ${row("Provider", "", `<select class="select" name="llm_provider" id="provSel"><option value="claude" ${s.llm_provider !== "ollama" ? "selected" : ""}>Claude (Anthropic API)</option><option value="ollama" ${s.llm_provider === "ollama" ? "selected" : ""}>Ollama (local)</option></select>`)}
    <div id="claudeFields" ${s.llm_provider === "ollama" ? "hidden" : ""}>
      ${row("Claude API key", "From console.anthropic.com → API keys. Stored encrypted on this Mac", `<input class="input" type="password" name="anthropic_api_key" autocomplete="off" placeholder="${s.secrets.anthropic_api_key ? "•••••••• saved (encrypted)" : "sk-ant-…"}">`)}
      ${row("Model", "Opus is the most capable; Sonnet is ~half the price; Haiku is the cheapest and fastest", `<select class="select" name="claude_model">${[["claude-opus-5-5", "Claude Opus 5.5"], ["claude-sonnet-5-5", "Claude Sonnet 5.5"], ["claude-haiku-5-5", "Claude Haiku 5.5"]].map(([v, l]) => `<option value="${v}" ${s.claude_model === v ? "selected" : ""}>${l}</option>`).join("")}</select>`)}
      ${row("Thinking effort", "Higher = more careful reasoning, slower and more tokens", `<select class="select" name="claude_effort">${["low", "medium", "high"].map((v) => `<option ${s.claude_effort === v ? "selected" : ""}>${v}</option>`).join("")}</select>`)}
      <div class="callout" style="margin-top:12px">${icon("shield")} With Claude, the text of your chats, tasks, journal, memories, documents and scanned emails is sent to Anthropic's API to generate replies. Vault secrets never are: Donna only ever sees an item's title and last 4 digits.</div>
    </div>
    <div id="ollamaFields" ${s.llm_provider === "ollama" ? "" : "hidden"}>
      ${row("Ollama URL", "", inp("ollama_url", s.ollama_url))}
      ${row("Model", ol.provider === "ollama" && ol.models.length ? `Installed: ${ol.models.map(esc).join(", ")}` : "", `<input class="input" name="ollama_model" value="${esc(s.ollama_model)}">`)}
      ${row("Creativity", "Lower = more precise tool use (0.2–0.5 recommended)", inp("llm_temperature", s.llm_temperature, 'type="number" step="0.1" min="0" max="1.5"'))}
      ${row("Context window", "Tokens. 8192 suits 8 GB RAM", inp("llm_num_ctx", s.llm_num_ctx, 'type="number" step="1024" min="2048"'))}
      ${row("Thinking mode", "Slower but more careful reasoning (Qwen thinking)", sw("llm_think", s.llm_think))}
    </div>
    <button class="btn primary" data-save>Save AI settings</button></section>

  <section class="card s-section" id="s-email" data-form><h2>Email & reminders</h2><p class="desc">Donna emails you task reminders, appointment alerts and a morning briefing over SMTP.</p>
    <div class="callout"><b>Using Gmail?</b><ol><li>Turn on 2-Step Verification on your Google account.</li><li>Create an <b>App Password</b> at myaccount.google.com/apppasswords.</li><li>Host <code>smtp.gmail.com</code>, port <code>587</code>, username = your Gmail address, password = the 16-character app password.</li></ol></div>
    <div class="row"><div class="field"><label>SMTP host</label>${inp("smtp_host", s.smtp_host, 'placeholder="smtp.gmail.com"')}</div><div class="field" style="flex:0 0 110px"><label>Port</label>${inp("smtp_port", s.smtp_port, 'type="number"')}</div></div>
    <div class="row"><div class="field"><label>Username</label>${inp("smtp_user", s.smtp_user, 'autocomplete="off"')}</div><div class="field"><label>Password</label><input class="input" type="password" name="smtp_password" autocomplete="new-password" placeholder="${s.secrets.smtp_password ? "•••••••• saved (encrypted)" : "App password"}"></div></div>
    <div class="field"><label>From address (optional)</label>${inp("smtp_from", s.smtp_from)}</div>
    ${row("Send emails", "Master switch for all email", sw("email_enabled", s.email_enabled))}
    ${row("Appointment reminder", "Minutes before an event", inp("event_reminder_min", s.event_reminder_min, 'type="number" min="1"'))}
    ${row("Default event length", "Minutes, when no end time is given", inp("default_event_minutes", s.default_event_minutes, 'type="number" min="5" step="5"'))}
    ${row("Morning briefing", "Email + notification with your day", `<div style="display:flex;gap:10px;align-items:center">${sw("briefing_enabled", s.briefing_enabled)}${inp("briefing_time", s.briefing_time, 'type="time"')}</div>`)}
    ${row("Evening journal nudge", "Notification if you haven't written yet (blank = off)", inp("journal_nudge_time", s.journal_nudge_time, 'type="time"'))}
    <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" data-save>Save</button><button class="btn" id="testEmail">${icon("mail")}Send test email</button><button class="btn" id="sendBrief">${icon("sun")}Send briefing now</button></div></section>

  <section class="card s-section" id="s-subs" data-form><h2>Subscriptions</h2><p class="desc">How Donna counts and watches what you pay for on repeat.</p>
    ${row("Home currency", "Totals are shown in this currency", `<select class="select" name="home_currency">${["INR", "USD", "EUR", "GBP", "AED", "SGD"].map((c) => `<option ${(s.home_currency || "INR") === c ? "selected" : ""}>${c}</option>`).join("")}</select>`)}
    ${row("Monthly budget", "Donna alerts you when subscriptions exceed it (0 = off)", inp("subs_budget", s.subs_budget, 'type="number" min="0" step="100"'))}
    ${row("Card forex markup %", "Added to foreign-currency subscriptions (many Indian cards charge 3.5% + GST, about 4.1%)", inp("fx_markup_percent", s.fx_markup_percent, 'type="number" min="0" step="0.1"'))}
    ${row("Watch email for subscriptions", "Daily check for receipts, trial sign-ups, price changes and AutoPay notices", sw("subs_email_watch", s.subs_email_watch))}
    ${row("USD rate override", "Leave blank to use the daily market rate", `<input class="input" name="fx_usd" type="number" step="0.01" value="${(s.fx_manual || {}).USD || ""}" placeholder="auto">`)}
    <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" data-save>Save</button><button class="btn" id="fxRefresh">${icon("refresh")}Refresh exchange rates</button><a class="btn" href="#/subscriptions">${icon("card")}Open Subscriptions</a></div></section>

  <section class="card s-section" id="s-google" data-form><h2>Google Calendar</h2><p class="desc">Let Donna read your calendar, block time and book appointments. Your OAuth credentials stay on this machine.</p>
    ${s.google_connected ? `<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px"><span class="status-pill on"><i></i>Connected${s.google_account ? " · " + esc(s.google_account) : ""}</span><button class="btn sm" id="gDisconnect">Disconnect</button></div>` : ""}
    <div class="callout"><b>One-time setup (about 5 minutes)</b><ol>
      <li>Open <b>console.cloud.google.com</b>, then create a project (e.g. “Donna”).</li>
      <li>Go to <b>APIs & Services → Library</b> and enable <b>Google Calendar API</b>.</li>
      <li>In <b>OAuth consent screen</b>, choose External, add your email as a <b>Test user</b>.</li>
      <li>In <b>Credentials</b>, Create credentials → OAuth client ID → <b>Web application</b>.</li>
      <li>Add this <b>Authorized redirect URI</b>: <code>${esc(s.google_redirect_uri)}</code></li>
      <li>Paste the Client ID and Client secret below, save, then click Connect.</li></ol></div>
    <div class="field"><label>Client ID</label>${inp("google_client_id", s.google_client_id, 'placeholder="xxxx.apps.googleusercontent.com"')}</div>
    <div class="field"><label>Client secret</label><input class="input" type="password" name="google_client_secret" autocomplete="off" placeholder="${s.secrets.google_client_secret ? "•••••••• saved (encrypted)" : "GOCSPX-…"}"></div>
    ${row("Calendar ID", "“primary” is your main calendar", inp("google_calendar_id", s.google_calendar_id))}
    <div style="display:flex;gap:8px"><button class="btn" data-save>Save credentials</button><button class="btn primary" id="gConnect">${icon("link")}${s.google_connected ? "Reconnect" : "Connect Google Calendar"}</button></div></section>

  <section class="card s-section" id="s-security" data-form><h2>Vault & security</h2><p class="desc">Your vault is AES-256-GCM encrypted with a key derived from your master password (scrypt). Integration secrets are encrypted with a local app key.</p>
    ${row("Auto-lock vault after", "Minutes of inactivity", inp("vault_autolock_min", s.vault_autolock_min, 'type="number" min="1"'))}
    <div style="display:flex;gap:8px"><button class="btn primary" data-save>Save</button><a class="btn" href="#/vault">${icon("lock")}Open vault</a><button class="btn" id="lockNow">Lock now</button></div></section>

  <section class="card s-section" id="s-inbox" data-form><h2>Inbox triage</h2><p class="desc">Donna reads your recent email (read-only over IMAP, never marks anything as read), including what you sent, and suggests the commitments as tasks. Uses the same login and app password as Email above. Processed entirely on this Mac.</p>
    ${row("Scan automatically", "Runs in the background", sw("inbox_enabled", s.inbox_enabled))}
    ${row("Every", "Hours between scans", inp("inbox_interval_hours", s.inbox_interval_hours, 'type="number" min="1" step="1"'))}
    ${row("Look back", "Days of email per scan", inp("inbox_days", s.inbox_days, 'type="number" min="1" max="14"'))}
    ${row("Include sent mail", "Catches promises you made (“I'll send it Friday”)", sw("inbox_scan_sent", s.inbox_scan_sent))}
    ${row("IMAP host", "Leave blank to derive from SMTP (smtp.gmail.com → imap.gmail.com)", inp("imap_host", s.imap_host, 'placeholder="imap.gmail.com"'))}
    <div style="display:flex;gap:8px"><button class="btn primary" data-save>Save</button><a class="btn" href="#/inbox">${icon("mail")}Open Inbox</a></div></section>

  <section class="card s-section" id="s-automation" data-form><h2>Briefings & prep</h2><p class="desc">The rhythms that make Donna feel like Donna.</p>
    ${row("Donna's daily note", "A mentor note on your home screen each morning, also sent to Telegram", sw("mentor_enabled", s.mentor_enabled))}
    ${row("Goal reflection nudge", "Evening reminder if you haven't reflected on your goals (blank = off)", inp("reflection_nudge_time", s.reflection_nudge_time, 'type="time"'))}
    ${row("Meeting prep packs","Notes on the people, open promises and related items before each meeting", sw("prep_enabled", s.prep_enabled))}
    ${row("Send prep", "Minutes before the meeting", inp("prep_lead_min", s.prep_lead_min, 'type="number" min="5" step="5"'))}
    ${row("AI talking points", "Donna writes 3–5 talking points (takes ~10s in the background)", sw("prep_ai", s.prep_ai))}
    ${row("Weekly review", "Wins, slips, moods, goals and next week's priorities", `<div style="display:flex;gap:6px;align-items:center">${sw("review_enabled", s.review_enabled)}<select class="select" name="review_day">${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d, i) => `<option value="${i}" ${+s.review_day === i ? "selected" : ""}>${d}</option>`).join("")}</select>${inp("review_time", s.review_time, 'type="time"')}</div>`)}
    ${row("Birthday heads-up", "Days before a birthday (plus the day before and on the day)", inp("birthday_remind_days", s.birthday_remind_days, 'type="number" min="1"'))}
    ${row("Keep-in-touch nudge", "Day of the week to remind you who to reach out to", `<select class="select" name="nudge_weekday">${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d, i) => `<option value="${i}" ${+s.nudge_weekday === i ? "selected" : ""}>${d}</option>`).join("")}</select>`)}
    <button class="btn primary" data-save>Save</button></section>

  <section class="card s-section" id="s-phone" data-form><h2>Phone & Telegram</h2><p class="desc">Talk to Donna from your phone and get reminders there. Telegram works even while Donna runs only on this Mac. No hosting needed.</p>
    <div id="tgStatus"></div>
    <div class="callout"><b>Set up (2 minutes)</b><ol><li>In Telegram, message <b>@BotFather</b> → <code>/newbot</code> → choose a name. Copy the token it gives you.</li><li>Paste it below and save.</li><li>Open your new bot in Telegram and send the pairing message shown here.</li></ol></div>
    <div class="field"><label>Bot token</label><input class="input" type="password" name="telegram_token" autocomplete="off" placeholder="${s.secrets.telegram_token ? "•••••••• saved (encrypted)" : "123456:ABC-DEF…"}"></div>
    ${row("Send reminders to Telegram", "Task, meeting, birthday and renewal alerts", sw("telegram_notify", s.telegram_notify))}
    <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" data-save>Save</button><button class="btn" id="tgTest">Send test message</button><button class="btn ghost" id="tgUnpair">Unpair</button></div>
    <div class="divider"></div><p class="muted" style="margin:0;font-size:13px">${icon("phone")} <b>Install as an app:</b> once Donna is reachable from your phone (see Login & hosting), open it in Safari → Share → <i>Add to Home Screen</i>. You can also share links and text straight to Donna from other apps (Android).</p></section>

  <section class="card s-section" id="s-voice"><h2>Voice</h2><p class="desc">Donna's voice uses your Mac's built-in voices (fully local). For the best sound, download a premium voice in System Settings → Accessibility → Spoken Content → System voice → Manage Voices (e.g. “Samantha (Enhanced)” or an Indian English voice).</p>
    ${row("Voice", "", `<select class="select" id="voicePick"></select>`)}
    ${row("Speed", "", `<input type="range" id="voiceRate" min="0.8" max="1.3" step="0.02" style="width:100%">`)}
    ${row("Recognition language", "For the microphone", `<select class="select" id="voiceLang">${["en-IN", "en-US", "en-GB", "hi-IN", "ta-IN"].map((l) => `<option>${l}</option>`).join("")}</select>`)}
    <div style="display:flex;gap:8px"><button class="btn" id="voiceTest">${icon("volume")}Test voice</button></div>
    <p class="muted" style="font-size:12.5px;margin-bottom:0">Privacy note: speaking <i>to</i> Donna uses your browser's speech recogniser. Safari can process on-device; Chrome sends audio to Google. Typing is always fully private.</p></section>

  <section class="card s-section" id="s-login"><h2>Login & hosting</h2><p class="desc">Right now Donna only answers this Mac. Before opening it to your phone or the internet, protect it with an app password and two-factor authentication.</p>
    <div id="loginBox"></div>
    <div class="divider"></div>
    <div class="field"><label>Allowed hosts</label><input class="input" id="allowedHosts" value="${esc(s.allowed_hosts)}" placeholder="donna.example.com, 192.168.1.20"><span class="hint">Extra hostnames Donna will answer on (the App URL's host is always allowed). Protects against DNS-rebinding attacks.</span></div>
    <button class="btn" id="saveHosts">Save hosts</button>
    <div class="callout" style="margin-top:18px"><b>Reach Donna from anywhere, the safe way (Cloudflare Tunnel)</b><ol>
      <li>Set an app password + 2FA above.</li>
      <li><code>brew install cloudflared</code>, then <code>cloudflared tunnel --url http://localhost:8765</code> for a quick test URL, or create a named tunnel on your own domain for a permanent one.</li>
      <li>Put the https URL in <b>Data → App URL</b> (and in Google's redirect URIs if you use Calendar).</li>
      <li>Your AI, data and vault stay on this Mac; only the encrypted tunnel is public.</li></ol></div></section>

  <section class="card s-section" id="s-skills"><h2>Agent skills</h2><p class="desc">Each specialist agent follows a skill: plain-language instructions loaded into its prompt. Edit them to change how Donna behaves. Changes apply to the next message.</p>
    <div class="filter-bar" id="skillTabs"></div><textarea class="textarea skill-editor" id="skillText"></textarea>
    <div style="display:flex;gap:8px;margin-top:10px"><button class="btn primary" id="skillSave">Save skill</button><span class="muted" id="skillHint" style="font-size:12.5px;align-self:center"></span></div></section>

  <section class="card s-section" id="s-data" data-form><h2>Data & appearance</h2><p class="desc">Everything lives in <code>donna/data/donna.db</code> on this Mac.</p>
    ${row("Theme", "", `<select class="select" name="theme">${["system", "light", "dark"].map((t) => `<option ${s.theme === t ? "selected" : ""}>${t}</option>`).join("")}</select>`)}
    ${row("App URL", "Change when you host Donna (affects email links and Google redirect)", inp("public_url", s.public_url))}
    <div style="display:flex;gap:8px"><button class="btn primary" data-save>Save</button><a class="btn" href="/api/export">${icon("download")}Export data (JSON)</a></div>
    <div class="divider"></div>
    <h3 style="margin:0 0 4px;font-weight:600">Full backup & move</h3>
    <p class="muted" style="margin:0 0 12px;font-size:13px">A full backup holds everything: database, encryption key, vault and documents. Use it to move Donna to a server, or keep it somewhere safe. <b>Treat the file like a password:</b> it contains your encrypted vault and the key for your integration secrets.</p>
    <div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn" href="/api/backup/full">${icon("download")}Download full backup (.zip)</a>
      <label class="btn">${icon("upload")}Restore from backup…<input type="file" id="restoreFile" accept=".zip" hidden></label></div></section>
  </div></div></div>`;

  // nav
  $$(".settings-nav a").forEach((a) => (a.onclick = () => { $(`#s-${a.dataset.s}`).scrollIntoView({ behavior: "smooth", block: "start" }); $$(".settings-nav a").forEach((x) => x.classList.toggle("active", x === a)); }));
  const target = r.params.get("s");
  if (target) setTimeout(() => $(`#s-${target}`)?.scrollIntoView({ block: "start" }), 50);
  // save per section
  $$("[data-save]", el).forEach((b) => (b.onclick = async () => {
    const sec = b.closest("[data-form]");
    const f = formData(sec);
    if ("fx_usd" in f) { f.fx_manual = f.fx_usd ? { USD: +f.fx_usd } : {}; delete f.fx_usd; }
    for (const k of ["subs_budget", "fx_markup_percent", "smtp_port", "event_reminder_min", "default_event_minutes", "llm_num_ctx", "vault_autolock_min", "inbox_interval_hours", "inbox_days", "review_day", "prep_lead_min", "birthday_remind_days", "nudge_weekday"]) if (k in f) f[k] = +f[k];
    if ("llm_temperature" in f) f.llm_temperature = +f.llm_temperature;
    try { await PUT("/api/settings", f); toast("Saved"); await refreshBoot(); if (["s-ai", "s-google", "s-phone"].includes(sec.id)) render(); } catch (e) { fail(e); }
  }));
  bindSettingsV2(el, s);
  $("#fxRefresh") && ($("#fxRefresh").onclick = async () => { try { const r = await POST("/api/subs/fx/refresh"); toast(Object.entries(r.rates).filter(([k]) => k !== (s.home_currency || "INR")).map(([k, v]) => `1 ${k} = ${(+v).toFixed(2)}`).join(" · ") || "Rates refreshed"); } catch (e) { fail(e); } });
  $("#restoreFile").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    if (!(await confirmBox(`Replace ALL of Donna's current data with “${f.name}”? Current files are kept aside on the server, but this Donna will show the backup's data from now on.`, "Restore"))) { e.target.value = ""; return; }
    const fd = new FormData(); fd.append("file", f);
    try { await api("POST", "/api/backup/restore", fd); toast("Restoring… Donna is restarting. Reload in about 20 seconds (on your Mac, start it again with ./run.sh).", { ms: 15000 }); }
    catch (err) { fail(err); }
  };
  $("#provSel").onchange = (e) => { $("#claudeFields").hidden = e.target.value === "ollama"; $("#ollamaFields").hidden = e.target.value !== "ollama"; };
  $("#testEmail").onclick = async () => { try { await POST("/api/settings/test-email"); toast("Check your inbox", { title: "Test email sent." }); } catch (e) { fail(e); } };
  $("#sendBrief").onclick = async () => { try { await POST("/api/briefing/send"); toast("Briefing sent"); } catch (e) { fail(e); } };
  $("#gConnect").onclick = async () => { const f = formData($("#s-google")); await PUT("/api/settings", f); location.href = "/api/google/auth"; };
  $("#gDisconnect") && ($("#gDisconnect").onclick = async () => { await POST("/api/google/disconnect"); refreshBoot(); render(); });
  $("#lockNow").onclick = async () => { await POST("/api/vault/lock"); refreshBoot(); toast("Vault locked"); };
  // skills editor
  const skills = await GET("/api/skills");
  const desc = { donna: "Core persona, shared by every agent", router: "Decides which agent handles a message", tasks: "To-do agent", calendar: "Calendar agent", journal: "Journal agent", ideas: "Ideas agent", memory: "Memory & vault agent", briefing: "Daily briefing agent", general: "Fallback for everything else" };
  let cur = skills.find((x) => x.name === "donna") || skills[0];
  const showSkill = () => { $("#skillTabs").innerHTML = skills.map((x) => `<button class="chip btnlike ${x === cur ? "active" : ""}" data-sk="${x.name}">${x.name}</button>`).join(""); $("#skillText").value = cur.content; $("#skillHint").textContent = desc[cur.name] || ""; $$("[data-sk]").forEach((b) => (b.onclick = () => { cur = skills.find((x) => x.name === b.dataset.sk); showSkill(); })); };
  showSkill();
  $("#skillSave").onclick = async () => { cur.content = $("#skillText").value; await PUT(`/api/skills/${cur.name}`, { content: cur.content }); toast(`Skill “${cur.name}” saved`); };
};

// ============================== Palette (⌘K) ==============================
const KIND_ROUTE = { memory: "#/memory", journal: "#/journal", idea: "#/ideas", task: "#/tasks/all", event: "#/calendar", vault_item: "#/vault" };
function openPalette(prefill = "") {
  const p = $("#palette"), input = $("#paletteInput"), res = $("#paletteResults");
  p.hidden = false; input.value = prefill; input.focus();
  let sel = -1, items = [];
  const draw = () => {
    const q = input.value.trim();
    res.innerHTML = (q ? `<div class="p-item ${sel === -1 ? "sel" : ""}" data-i="-1"><span class="pk">Ask</span><span class="pt">${icon("sparkle")} Ask Donna: “${esc(q)}”</span></div>` : `<div class="muted" style="padding:12px 14px;font-size:13px">Try “remind me to…”, “idea: …”, “what's my passport number”, or search anything.</div>`) +
      items.map((it, i) => `<div class="p-item ${sel === i ? "sel" : ""}" data-i="${i}"><span class="pk">${esc(it.type.replace("_item", ""))}</span><span class="pt">${esc(it.title || it.date || it.excerpt || "")}</span><span class="muted" style="font-size:12px">${esc((it.content || it.excerpt || it.body || "").slice(0, 50))}</span></div>`).join("");
    $$(".p-item", res).forEach((el) => (el.onclick = () => pick(+el.dataset.i)));
  };
  const pick = (i) => {
    const q = input.value.trim();
    closePalette();
    if (i === -1) { if (q) askDonna(q); return; }
    const it = items[i];
    go(it.type === "journal" ? `#/journal?date=${it.date}` : KIND_ROUTE[it.type] || "#/");
  };
  const search = debounce(async () => { const q = input.value.trim(); items = q.length > 1 ? await GET(`/api/search?q=${encodeURIComponent(q)}`) : []; sel = -1; draw(); }, 180);
  input.oninput = () => { draw(); search(); };
  input.onkeydown = (e) => {
    if (e.key === "Escape") closePalette();
    else if (e.key === "ArrowDown") { sel = Math.min(items.length - 1, sel + 1); draw(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { sel = Math.max(-1, sel - 1); draw(); e.preventDefault(); }
    else if (e.key === "Enter") { e.preventDefault(); pick(sel); }
  };
  p.onmousedown = (e) => { if (e.target === p) closePalette(); };
  draw();
}
const closePalette = () => { $("#palette").hidden = true; };
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("#palette").hidden ? openPalette() : closePalette(); }
});

// ============================== Notifications ==============================
async function pollNotifications(first = false) {
  try {
    const list = await GET("/api/notifications?unseen=true");
    $("#bellBtn .dot").hidden = !list.length;
    for (const n of list.reverse()) {
      if (state.notifSeen.has(n.id)) continue;
      state.notifSeen.add(n.id);
      if (first) continue;
      toast(n.body || "", { title: n.title, ms: 8000 });
      if ("Notification" in window && Notification.permission === "granted") {
        const bn = new Notification(n.title, { body: n.body, tag: "donna-" + n.id });
        bn.onclick = () => { window.focus(); if (n.link) location.hash = n.link.replace(/^#/, ""); };
      }
    }
  } catch { /* server restarting */ }
}
async function toggleNotifPanel() {
  const p = $("#notifPanel");
  if (!p.hidden) { p.hidden = true; return; }
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  const list = await GET("/api/notifications");
  p.innerHTML = list.map((n) => `<div class="n-item" data-link="${esc(n.link)}"><b>${esc(n.title)}</b><span>${esc(n.body)} · ${esc(n.created_at.slice(5, 16).replace("T", " "))}</span></div>`).join("") || `<div class="empty" style="padding:20px">No notifications yet.</div>`;
  p.hidden = false;
  $$(".n-item", p).forEach((i) => (i.onclick = () => { p.hidden = true; if (i.dataset.link) location.hash = i.dataset.link.replace(/^#/, ""); }));
  await POST("/api/notifications/seen");
  $("#bellBtn .dot").hidden = true;
}
document.addEventListener("mousedown", (e) => { const p = $("#notifPanel"); if (!p.hidden && !p.contains(e.target) && !e.target.closest("#bellBtn")) p.hidden = true; });

// ============================== Onboarding ==============================
async function onboarding() {
  const ol = await GET("/api/ai/status").catch(() => ({ ok: false }));
  modal({ title: "Hello. I'm Donna.", body: `
    <p style="margin-top:0;color:var(--ink-2)">I'll handle your to-dos, calendar, journal, ideas and the details you'd rather not remember. Two quick things and we're done.</p>
    <div class="field"><label>What should I call you?</label><input class="input" name="user_name" placeholder="Your first name"></div>
    <div class="field"><label>Where should reminders go?</label><input class="input" type="email" name="notify_email" placeholder="you@example.com"><span class="hint">Set up email sending later under Admin → Email.</span></div>
    <span class="status-pill ${ol.ok && ol.model_installed ? "on" : "off"}"><i></i>${ol.ok && ol.model_installed ? `AI ready · ${esc(ol.display_name || ol.model)}` : ol.provider === "claude" ? "Add your Claude API key in Admin → AI model to chat with me" : "Ollama not detected. Start it to chat with me"}</span>`,
    foot: `<button class="btn primary" id="obGo">Let's begin</button>`,
    onMount: (m, close) => { $("#obGo", m).onclick = async () => { await PUT("/api/settings", { ...formData(m), onboarded: true }); close(); await refreshBoot(); render(); if ("Notification" in window && Notification.permission === "default") Notification.requestPermission(); }; } });
}

// Init lives at the end of features.js (loaded after this file).
