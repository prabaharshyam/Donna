/* Donna: app shell (top bar, quick add, sidebar rail, profile card, shortcuts, skeletons, theme). */
"use strict";

const ROUTE_TITLES = {
  "": "Today", chat: "Ask Donna", inbox: "Inbox", tasks: "To Do", calendar: "Calendar", goals: "Goals", ideas: "Ideas",
  journal: "Journal", review: "Weekly review", people: "People", subscriptions: "Subscriptions", renewals: "Renewals",
  documents: "Documents", memory: "Memory", vault: "Vault", settings: "Admin & settings",
};
const ROUTE_GROUP = { tasks: "Organise", calendar: "Organise", goals: "Organise", ideas: "Organise", journal: "Reflect", review: "Reflect",
  people: "Life admin", subscriptions: "Life admin", renewals: "Life admin", documents: "Life admin", memory: "Remember", vault: "Remember" };

function setCrumb(r) {
  const el = $("#crumb");
  if (!el) return;
  const g = ROUTE_GROUP[r.route];
  el.innerHTML = `${g ? `<span>${g}</span><span>/</span>` : ""}<b>${ROUTE_TITLES[r.route] || "Donna"}</b>`;
  document.title = r.route ? `${ROUTE_TITLES[r.route] || "Donna"} · Donna` : "Donna";
}

function skeletonFor(route) {
  const line = (w, h = 14, mb = 10) => `<div class="sk" style="width:${w};height:${h}px;margin-bottom:${mb}px"></div>`;
  const card = (h) => `<div class="card" style="padding:18px 20px">${line("40%", 12, 16)}${line("90%")}${line("75%")}${h > 140 ? line("82%") + line("60%") : ""}</div>`;
  if (["tasks", "chat", "journal", "calendar"].includes(route)) {
    return `<div class="skel">${line("30%", 40, 22)}${[1, 2, 3, 4, 5].map(() => line("100%", 52, 8)).join("")}</div>`;
  }
  return `<div class="skel">${line("18%", 12, 14)}${line("46%", 46, 26)}
    <div class="stat-row">${[1, 2, 3, 4].map(() => `<div class="card" style="padding:18px">${line("50%", 10, 14)}${line("40%", 32, 0)}</div>`).join("")}</div>
    <div class="grid"><div class="col-7">${card(200)}</div><div class="col-5">${card(200)}</div></div></div>`;
}

// ---------------- profile card ----------------
async function updateShell(b) {
  const pc = $("#profileCard");
  if (!pc) return;
  const name = b.user_name || "You";
  let g = null;
  try { g = await GET("/api/game"); } catch { /* optional */ }
  const L = g?.level;
  pc.innerHTML = `<div class="avatar-i">${esc(initials(name))}</div>
    <div style="flex:1;min-width:0"><div class="pc-name">${esc(name)}</div>
      <div class="pc-sub">${L ? `L${L.level} · ${esc(L.title)}` : "Your progress"}${g?.streak ? ` · 🔥 ${g.streak}` : ""}</div>
      ${L ? `<div class="pc-xp" title="${L.xp} XP${L.next_at ? ` · ${L.next_at - L.xp} to ${L.next_title}` : ""}"><i style="width:${L.pct}%"></i></div>` : ""}</div>`;
  pc.onclick = () => go("#/goals");
  updateThemeBtn();
}

// ---------------- theme ----------------
const THEMES = ["system", "light", "dark"];
function updateThemeBtn() {
  const t = state.boot?.theme || "system";
  const btn = $("#themeBtn");
  if (btn) { btn.innerHTML = icon(t === "dark" ? "moon" : t === "light" ? "sun" : "palette"); btn.title = `Theme: ${t} (click to change)`; }
}
async function setLook(theme, accent) {
  if (theme) state.boot.theme = theme;
  if (accent) state.boot.accent = accent;
  applyTheme(state.boot.theme || "system", state.boot.accent || "wine");
  updateThemeBtn();
  try { await PUT("/api/settings", { ...(theme ? { theme } : {}), ...(accent ? { accent } : {}) }); } catch { /* offline */ }
}

// ---------------- sidebar rail ----------------
function setRail(on) {
  $(".app").classList.toggle("rail", on);
  try { localStorage.setItem("donna_rail", on ? "1" : "0"); } catch { /* ignore */ }
  const t = $("#railToggle");
  if (t) t.title = on ? "Expand sidebar ( [ )" : "Collapse sidebar ( [ )";
  $$("#nav a, .foot-link").forEach((a) => { if (on) a.title = a.textContent.trim(); else a.removeAttribute("title"); });
}

// ---------------- quick add ----------------
const QUICK = [
  ["task", "check", "Task", "T", () => quickTask()],
  ["event", "calendar", "Event", "E", () => eventForm({})],
  ["idea", "bulb", "Idea", "I", () => quickIdea()],
  ["journal", "book", "Journal entry", "J", () => go("#/journal")],
  ["sep"],
  ["sub", "card", "Subscription or trial", "S", () => subForm({})],
  ["goal", "target", "Goal", "G", () => goalForm({})],
  ["person", "users", "Person", "P", () => personForm({})],
  ["sep"],
  ["ask", "sparkle", "Just tell Donna…", "⌘K", () => openPalette()],
];
function openMenu(anchor, items) {
  closeMenu();
  const m = document.createElement("div");
  m.className = "menu"; m.id = "menu";
  m.innerHTML = items.map((it) => it[0] === "sep" ? `<div class="menu-sep"></div>` : `<button data-k="${it[0]}"><span class="mi">${icon(it[1])}</span>${esc(it[2])}<small>${esc(it[3] || "")}</small></button>`).join("");
  document.body.appendChild(m);
  const r = anchor.getBoundingClientRect();
  const w = m.offsetWidth;
  m.style.top = `${Math.min(r.bottom + 8, innerHeight - m.offsetHeight - 10)}px`;
  m.style.left = `${Math.max(10, Math.min(r.right - w, innerWidth - w - 10))}px`;
  $$("button[data-k]", m).forEach((b) => (b.onclick = () => { closeMenu(); items.find((x) => x[0] === b.dataset.k)[4](); }));
  const keyer = (e) => {
    if (e.key === "Escape") return closeMenu();
    const hit = items.find((x) => x[3] && x[3].length === 1 && x[3].toLowerCase() === e.key.toLowerCase());
    if (hit) { e.preventDefault(); closeMenu(); hit[4](); }
  };
  setTimeout(() => { document.addEventListener("mousedown", outside); document.addEventListener("keydown", keyer); }, 0);
  m._cleanup = () => { document.removeEventListener("mousedown", outside); document.removeEventListener("keydown", keyer); };
  function outside(e) { if (!m.contains(e.target)) closeMenu(); }
}
function closeMenu() { const m = $("#menu"); if (m) { m._cleanup?.(); m.remove(); } }

function quickTask() {
  modal({ title: "New task", body: `
    <div class="field"><input class="input" name="title" placeholder="What needs doing?" style="font-size:16px"></div>
    <div class="row"><div class="field"><label>Due</label><input class="input" type="date" name="due_date"></div>
      <div class="field"><label>Remind me</label><input class="input" type="datetime-local" name="reminder_at"></div></div>
    <label style="display:flex;gap:8px;align-items:center;font-size:13px"><input type="checkbox" name="my_day" checked> Add to My Day</label>`,
    foot: `<button class="btn ghost" data-close>Cancel</button><button class="btn accent" id="qtSave">${icon("plus")}Add task</button>`,
    onMount: (m, close) => {
      const save = async () => {
        const f = formData(m);
        if (!f.title.trim()) return;
        const body = { title: f.title.trim(), due_date: f.due_date || (f.reminder_at ? f.reminder_at.slice(0, 10) : null), reminder_at: f.reminder_at || null, my_day: f.my_day ? TODAY() : null };
        await POST("/api/tasks", body); close(); toast("Task added"); refreshBoot();
        if (["", "tasks"].includes(parseHash().route)) render();
      };
      $("#qtSave", m).onclick = save;
      $("[name=title]", m).addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); save(); } });
    } });
}
function quickIdea() {
  modal({ title: "Capture an idea", body: `<div class="field"><input class="input" name="title" placeholder="Headline (optional)"></div><div class="field"><textarea class="textarea" name="body" placeholder="What's the idea?" style="min-height:120px"></textarea></div>`,
    foot: `<button class="btn ghost" data-close>Cancel</button><button class="btn accent" id="qiSave">${icon("bulb")}Save idea</button>`,
    onMount: (m, close) => { $("#qiSave", m).onclick = async () => { const f = formData(m); if (!f.title.trim() && !f.body.trim()) return; await POST("/api/ideas", f); close(); toast("Idea saved"); if (parseHash().route === "ideas") render(); }; } });
}

// ---------------- keyboard shortcuts ----------------
const GOTO = { h: "#/", a: "#/chat", t: "#/tasks", c: "#/calendar", g: "#/goals", i: "#/ideas", j: "#/journal", r: "#/review", p: "#/people", s: "#/subscriptions", d: "#/documents", m: "#/memory", v: "#/vault", x: "#/inbox", ",": "#/settings" };
function showShortcuts() {
  const rows = [["⌘ K", "Ask Donna or search"], ["C", "Quick add"], ["[", "Collapse / expand sidebar"], ["?", "This help"], ["G then H", "Today"], ["G then A", "Ask Donna"],
    ["G then T", "To Do"], ["G then C", "Calendar"], ["G then G", "Goals"], ["G then I", "Ideas"], ["G then J", "Journal"], ["G then S", "Subscriptions"],
    ["G then P", "People"], ["G then M", "Memory"], ["G then V", "Vault"], ["G then ,", "Settings"]];
  modal({ title: "Keyboard shortcuts", size: "lg", body: `<div class="shortcuts">${rows.map(([k, l]) => `<div><span>${l}</span><span>${k.split(" ").map((x) => x === "then" ? `<span class="muted" style="font-size:11px;margin:0 4px">then</span>` : `<kbd>${x}</kbd>`).join("")}</span></div>`).join("")}</div>` });
}
let gPending = 0;
document.addEventListener("keydown", (e) => {
  const tag = (e.target.tagName || "").toLowerCase();
  if (e.metaKey || e.ctrlKey || e.altKey || ["input", "textarea", "select"].includes(tag) || e.target.isContentEditable) return;
  if ($(".modal-root .overlay") || !$("#palette").hidden || $("#menu")) return;
  const k = e.key.toLowerCase();
  if (gPending && Date.now() - gPending < 1200 && GOTO[k]) { e.preventDefault(); gPending = 0; go(GOTO[k]); return; }
  gPending = 0;
  if (k === "g") { gPending = Date.now(); return; }
  if (k === "c" || k === "n") { e.preventDefault(); openMenu($("#quickAdd"), QUICK); }
  else if (k === "/") { e.preventDefault(); openPalette(); }
  else if (k === "[") { setRail(!$(".app").classList.contains("rail")); }
  else if (e.key === "?") { showShortcuts(); }
});

// ---------------- wiring ----------------
(function initShell() {
  hydrateIcons();
  if (document.documentElement.classList.contains("rail-pref") && innerWidth > 800) setRail(true);
  $("#railToggle").onclick = () => setRail(!$(".app").classList.contains("rail"));
  $("#quickAdd").onclick = (e) => openMenu(e.currentTarget, QUICK);
  $("#themeBtn").onclick = () => setLook(THEMES[(THEMES.indexOf(state.boot?.theme || "system") + 1) % THEMES.length]);
  window.addEventListener("hashchange", closeMenu);
  $("#tabMore").onclick = () => $("#sidebar").classList.toggle("open");
  document.addEventListener("mousedown", (e) => { const sb = $("#sidebar"); if (sb.classList.contains("open") && !sb.contains(e.target) && !e.target.closest("#tabMore, #mobileMenu")) sb.classList.remove("open"); });
})();
