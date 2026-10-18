/* Donna v2 screens: Inbox triage, Goals, People, Renewals, Documents, Weekly review, Admin extras, Login, Init. */
"use strict";

const initials = (n) => String(n || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
const money = (amt, cur) => {
  if (amt == null || amt === "") return "";
  try { if (/^[A-Z]{3}$/.test(cur || "")) return new Intl.NumberFormat(undefined, { style: "currency", currency: cur, maximumFractionDigits: amt % 1 ? 2 : 0 }).format(amt); } catch { /* fall through */ }
  return `${cur ? cur + " " : ""}${(+amt).toLocaleString()}`;
};
const ago = (s) => { if (!s) return "never"; const d = Math.round((new Date() - parseD(s)) / 60000); return d < 1 ? "just now" : d < 60 ? `${d} min ago` : d < 1440 ? `${Math.round(d / 60)} h ago` : `${Math.round(d / 1440)} d ago`; };

// ============================== INBOX TRIAGE ==============================
let inboxPoll = null;
VIEWS.inbox = async (el, r) => {
  clearTimeout(inboxPoll);
  const tab = r.params.get("tab") || "pending";
  const [d, projects] = await Promise.all([GET(`/api/inbox?status=${tab}`), GET("/api/projects")]);
  const st = d.status || {};
  const statusLine = !d.configured ? "" : st.running ? `<span class="status-pill on"><i></i>Reading your email… ${esc(st.progress || "")}</span>`
    : st.error ? `<span class="status-pill off"><i></i>${esc(st.error)}</span>`
    : `<span class="muted" style="font-size:13px">Last scan ${ago(st.last_scan)}${st.last_scan ? ` · read ${st.last_read || 0} emails · found ${st.last_found || 0}` : ""}${d.enabled ? "" : " · auto-scan is off"}</span>`;
  el.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Inbox</h1><div class="sub">Promises you made and requests you received, pulled from your email.</div></div>
      <div class="actions">${statusLine}<button class="btn primary" id="scanNow" ${!d.configured || st.running ? "disabled" : ""}>${icon("refresh")}Scan now</button></div></div>
    ${!d.configured ? `<div class="callout">${icon("mail")} Connect your email first: <a href="#/settings?s=email" style="color:var(--accent)">Admin → Email</a> (for Gmail, an App Password). Donna reads it over IMAP, read-only, and everything is processed on this Mac.</div>` : ""}
    <div class="filter-bar">${[["pending", "To review"], ["accepted", "Added to To Do"], ["dismissed", "Dismissed"]].map(([k, l]) => `<a class="chip btnlike ${tab === k ? "active" : ""}" href="#/inbox?tab=${k}">${l}</a>`).join("")}</div>
    <div class="card" id="inboxList">${d.items.map((it) => `<div class="inbox-item" data-id="${it.id}">
      <div class="vc-icon" style="width:34px;height:34px;border-radius:9px;background:${it.folder === "sent" ? "var(--accent-soft)" : "var(--hover)"};color:${it.folder === "sent" ? "var(--accent)" : "var(--ink-2)"};display:grid;place-items:center;flex:none">${icon(it.folder === "sent" ? "up" : "mail")}</div>
      <div style="flex:1;min-width:0"><div class="it">${esc(it.title)}</div>${it.reason ? `<div class="ir">“${esc(it.reason)}”</div>` : ""}
        <div class="is">${it.folder === "sent" ? "You promised" : "From"} ${esc(it.sender.replace(/<.*>/, "").trim() || it.sender)} · ${esc(it.subject)}${it.received ? " · " + relDay(it.received) : ""}</div></div>
      ${tab === "pending" ? `<div class="acts"><input class="input" type="date" value="${it.due_date || ""}" data-due style="width:150px;padding:6px 8px"><select class="select" data-proj style="width:auto;padding:6px 8px"><option value="">Tasks</option>${projects.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</select>
        <button class="btn accent sm" data-acc>${icon("plus")}Add</button><button class="icon-btn" data-dis title="Dismiss">${icon("x")}</button></div>`
      : it.due_date ? `<span class="chip">${relDay(it.due_date)}</span>` : ""}</div>`).join("") ||
      `<div class="empty big">${icon("mail")}<h3>${tab === "pending" ? "Nothing waiting" : "Nothing here"}</h3><div>${tab === "pending" ? "When Donna finds something you owe someone, it shows up here." : ""}</div></div>`}</div></div>`;
  $("#scanNow").onclick = async () => { try { await POST("/api/inbox/scan"); toast("Reading your email. This can take a minute."); setTimeout(render, 1200); } catch (e) { fail(e); } };
  $$(".inbox-item", el).forEach((row) => {
    const id = row.dataset.id;
    $("[data-acc]", row) && ($("[data-acc]", row).onclick = async () => {
      const pid = $("[data-proj]", row).value;
      await POST(`/api/inbox/${id}/accept`, { due_date: $("[data-due]", row).value || null, project_id: pid ? +pid : null });
      row.remove(); toast("Added to your To Do"); refreshBoot();
    });
    $("[data-dis]", row) && ($("[data-dis]", row).onclick = async () => { await POST(`/api/inbox/${id}/dismiss`); row.remove(); refreshBoot(); });
  });
  if (st.running) inboxPoll = setTimeout(() => { if (location.hash.startsWith("#/inbox")) render(); }, 3000);
};

// ============================== GOALS (3 slots · mentor · gamification) ==============================
const CONF = [[1, "Off track"], [2, "Shaky"], [3, "Steady"], [4, "On track"], [5, "Crushing it"]];

function celebrate(reward, big = false) {
  if (!reward) return;
  const n = big || reward.kind === "goal" ? 140 : reward.kind === "milestone" || reward.level_up ? 90 : 0;
  if (n) confetti(n);
  if (reward.xp) toast(reward.line || "Nice.", { title: `+${reward.xp} XP${reward.level_up ? " · Level up: " + reward.level_up : ""}`, ms: reward.level_up || n ? 6000 : 3500 });
  refreshGameChip();
  const ready = reward.milestone_ready;
  if (ready) setTimeout(() => modal({ title: "Milestone reached?", body: `<p style="margin-top:0">Every task under <b>${esc(ready.title)}</b> is done. Is the milestone itself achieved, or does it need more work?</p>`,
    foot: `<button class="btn ghost" data-close>Needs more</button><button class="btn accent" id="msYes">🏁 Yes, achieved</button>`,
    onMount: (m, close) => { $("#msYes", m).onclick = async () => { const res = await PATCH(`/api/milestones/${ready.id}`, { done: true }); close(); celebrate(res.reward); if (location.hash.startsWith("#/goals")) render(); }; } }), 700);
}
function confetti(n = 100) {
  const colors = ["#7A2E3A", "#C9A66F", "#3E7B57", "#3D6A99", "#E07B73", "#F2D06B"];
  const wrap = document.createElement("div");
  wrap.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:200;overflow:hidden";
  for (let i = 0; i < n; i++) {
    const c = document.createElement("i");
    const x = Math.random() * 100, dx = (Math.random() - .5) * 40, rot = Math.random() * 720, dur = 1.6 + Math.random() * 1.4, size = 6 + Math.random() * 6;
    c.style.cssText = `position:absolute;top:-12px;left:${x}vw;width:${size}px;height:${size * .45}px;background:${colors[i % colors.length]};border-radius:2px;opacity:.95;transform:rotate(${rot}deg);animation:confetti ${dur}s cubic-bezier(.2,.6,.4,1) forwards;--dx:${dx}vw;--rot:${rot + 540}deg`;
    wrap.appendChild(c);
  }
  document.body.appendChild(wrap);
  setTimeout(() => wrap.remove(), 3200);
}
async function refreshGameChip() {
  try { const g = await GET("/api/game"); const el = $("#gameChip"); if (el) el.innerHTML = gameChipHTML(g); } catch { /* ignore */ }
}
const gameChipHTML = (g) => `<span title="${g.level.xp} XP">${icon("target")}L${g.level.level} ${esc(g.level.title)}</span>${g.streak ? `<span title="Goal streak">🔥 ${g.streak}</span>` : ""}`;

function levelCard(game) {
  const L = game.level;
  return `<div class="card level-card"><div class="lv-badge">L${L.level}</div>
    <div style="flex:1;min-width:0"><div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap"><b class="lv-title">${esc(L.title)}</b><span class="muted" style="font-size:12.5px">${L.xp} XP${L.next_at ? ` · ${L.next_at - L.xp} to ${esc(L.next_title)}` : " · max level"}</span></div>
      <div class="progress" style="margin-top:8px"><i style="width:${L.pct}%"></i></div></div>
    <div class="lv-stat"><div class="n">🔥 ${game.streak}</div><div class="muted">day streak${game.active_today ? "" : game.streak ? " · keep it alive today" : ""}</div></div>
    <div class="badges">${game.badges.map((b) => `<span class="badge ${b.earned ? "on" : ""}" title="${esc(b.name)}: ${esc(b.desc)}">${({ first_step: "👣", mirror: "🪞", milestone: "🏁", streak7: "🔥", streak30: "⚡", closer: "🏆", hattrick: "🎩", reflect30: "🧠" })[b.id] || "★"}</span>`).join("")}</div></div>`;
}

VIEWS.goals = async (el, r) => {
  if (r.parts[1]) return goalPage(el, +r.parts[1]);
  const b = await GET("/api/goals/board");
  const slots = [...b.active, ...Array(Math.max(0, b.max - b.active.length)).fill(null)];
  const card = (g, i) => g ? `<a class="card goal-slot" href="#/goals/${g.id}">
      <div class="slot-n">Goal ${i + 1}</div>
      <h3>${esc(g.title)}</h3>
      <div style="display:flex;align-items:center;gap:12px"><div class="progress" style="flex:1"><i style="width:${g.progress}%"></i></div><b class="pct-s">${g.progress}%</b></div>
      <div class="gmeta">${g.target_date ? `<span class="chip ${g.days_left < 0 ? "warn" : g.days_left < 30 ? "accent" : ""}">${icon("calendar")}${g.days_left < 0 ? -g.days_left + "d overdue" : g.days_left + " days left"}</span>` : ""}
        <span class="chip">${g.done_count}/${g.total_count} milestones</span>${g.reflection_streak ? `<span class="chip">🔥 ${g.reflection_streak}</span>` : ""}<span class="chip">${g.xp} XP</span></div>
      ${g.next_milestone ? `<div class="next">Now: <b>${esc(g.next_milestone)}</b>${g.next_task ? `<br><span class="muted">Next task · ${esc(g.next_task)}</span>` : ""}</div>` : ""}
      <div class="slot-foot">${g.reflected_today ? `<span class="chip ok">${icon("tick")}Reflected today</span>` : `<span class="chip accent">${icon("edit")}Reflect today</span>`}</div></a>`
    : `<button class="card goal-slot empty" data-new>${icon("plus")}<b>Open slot</b><span class="muted">Add a goal. Choose the one that would change the most.</span></button>`;
  el.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Goals</h1><div class="sub">Three at a time. Chasing ten rabbits catches none.</div></div>
      <div class="actions"><button class="btn" id="goalAI" ${b.active.length >= b.max ? "disabled" : ""}>${icon("sparkle")}Plan a goal with Donna</button></div></div>
    ${levelCard(b.game)}
    <div class="slot-grid">${slots.map(card).join("")}</div>
    ${b.active.length >= b.max ? `<p class="muted" style="font-size:13px;margin-top:10px">${icon("lock")} All three slots are taken. Achieve or let go of a goal to open one.</p>` : ""}
    <div class="eyebrow" style="margin:38px 0 12px">History</div>
    ${b.history.length ? `<div class="card">${b.history.map((g) => `<a class="hist-row" href="#/goals/${g.id}"><span class="hist-icon">${g.status === "achieved" ? "🏆" : "🍃"}</span><div style="flex:1;min-width:0"><b>${esc(g.title)}</b><div class="muted" style="font-size:12.5px">${g.status === "achieved" ? "Achieved" : "Let go"} ${g.achieved_at ? fmtDate(g.achieved_at.slice(0, 10), { day: "numeric", month: "short", year: "numeric" }) : ""} · ${g.done_count}/${g.total_count} milestones · ${g.reflection_count} reflections · ${g.xp} XP</div></div>${g.closing_note ? `<span class="muted" style="font-size:12.5px;font-style:italic;max-width:40%">“${esc(g.closing_note.slice(0, 80))}”</span>` : ""}</a>`).join("")}</div>`
      : `<div class="muted" style="font-size:13.5px">Achieved goals will live here, your trophy shelf.</div>`}</div>`;
  $$("[data-new]", el).forEach((x) => (x.onclick = () => goalForm({})));
  $("#goalAI").onclick = () => modal({ title: "Plan a goal with Donna", body: `<div class="field"><label>What do you want to achieve?</label><input class="input" id="gq" placeholder="Reach 10,000 YouTube subscribers by June"></div><div class="field"><label>Why does it matter to you?</label><input class="input" id="gw" placeholder="Optional, but it's what keeps you going on hard days"></div>`,
    foot: `<button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="gGo">${icon("sparkle")}Plan it</button>`,
    onMount: (m, close) => { $("#gGo", m).onclick = () => { const q = $("#gq", m).value.trim(); if (!q) return; close(); askDonna(`Set a goal: ${q}.${$("#gw", m).value ? " Why it matters: " + $("#gw", m).value : ""} Break it into milestones and add my first small task.`); }; } });
};

function goalForm(g) {
  modal({ title: g.id ? "Edit goal" : "New goal", body: `
    <div class="field"><label>Goal</label><input class="input" name="title" value="${esc(g.title || "")}" placeholder="An outcome: e.g. Run a half marathon"></div>
    <div class="field"><label>Why it matters</label><textarea class="textarea" name="why" style="min-height:60px" placeholder="Donna will remind you of this on hard days">${esc(g.why || "")}</textarea></div>
    <div class="row"><div class="field"><label>Target date</label><input class="input" type="date" name="target_date" value="${g.target_date || ""}"></div>
    <div class="field"><label>Area</label><select class="select" name="area">${["", "career", "health", "money", "relationships", "learning", "creativity", "home", "fun"].map((a) => `<option ${g.area === a ? "selected" : ""}>${a}</option>`).join("")}</select></div></div>
    ${g.id ? "" : `<div class="field"><label>Milestones (one per line, optional)</label><textarea class="textarea" name="milestones" placeholder="Publish 7 videos in 7 days\nFirst 1,000 subscribers\n…"></textarea><span class="hint">Or leave empty and ask Donna for a game plan on the next screen.</span></div>`}`,
    foot: `<button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="gSave">Save</button>`,
    onMount: (m, close) => { $("#gSave", m).onclick = async () => {
      const f = formData(m);
      if (!f.title.trim()) return;
      if (f.milestones !== undefined) f.milestones = f.milestones.split("\n").map((x) => x.trim()).filter(Boolean);
      if (!f.target_date) f.target_date = null;
      try { const saved = g.id ? await PATCH(`/api/goals/${g.id}`, f) : await POST("/api/goals", f); close(); toast(g.id ? "Saved" : "Goal set. Let's go."); go(`#/goals/${saved.id}`); } catch (e) { fail(e); }
    }; } });
}

async function goalPage(el, id) {
  const g = await GET(`/api/goals/${id}`);
  const active = g.status === "active";
  const refToday = g.reflections.find((x) => x.date === TODAY());
  const msHTML = (m, i) => `<div class="ms ${m.done ? "done" : ""}" data-mid="${m.id}">
      <div class="ms-head"><button class="check ${m.done ? "on" : ""}" data-mdone title="Mark milestone done">${icon("tick")}</button>
        <div style="flex:1;min-width:0" data-mtoggle><div class="ms-title">${esc(m.title)}</div>
          <div class="ms-meta">${m.tasks.length ? `${m.tasks_done}/${m.tasks.length} tasks` : "No tasks yet"}${m.due_date ? ` · by ${fmtDate(m.due_date)}` : ""}</div></div>
        <div class="ms-ring" style="--p:${m.progress}">${m.progress}%</div>
        <button class="icon-btn" data-mdel title="Delete milestone">${icon("x")}</button></div>
      <div class="ms-body" ${m.tasks.some((t) => !t.completed) || (!m.done && g.milestones.find((x) => !x.done)?.id === m.id) ? "" : "hidden"}>
        ${m.tasks.map((t) => `<div class="ms-task ${t.completed ? "done" : ""}" data-tid="${t.id}"><button class="check sq ${t.completed ? "on" : ""}" data-tdone>${icon("tick")}</button><span>${esc(t.title)}</span>${t.due_date ? `<span class="chip ${!t.completed && t.due_date < TODAY() ? "warn" : ""}">${relDay(t.due_date)}</span>` : ""}</div>`).join("")}
        ${active ? `<form class="ms-add" data-tadd>${icon("plus")}<input placeholder="Add a small task under this milestone"><input type="date" class="ms-date"></form>
        <button class="btn ghost sm" data-break>${icon("sparkle")}Break it down with Donna</button>` : ""}</div></div>`;
  el.innerHTML = `<div class="page">
    <a href="#/goals" class="muted" style="font-size:13px">${icon("chevL")} All goals</a>
    <div class="goal-hero">
      <div style="flex:1;min-width:0"><div class="eyebrow">${g.status === "achieved" ? "🏆 Achieved" : g.status === "let_go" ? "🍃 Let go" : "Active goal"}${g.area ? " · " + esc(g.area) : ""}</div>
        <h1>${esc(g.title)}</h1>
        ${g.why ? `<p class="why">“${esc(g.why)}”</p>` : active ? `<p class="muted" style="font-size:13.5px">Add your “why” (Edit). Donna uses it to keep you going on hard days.</p>` : ""}
        <div class="gmeta">${g.target_date ? `<span class="chip">${icon("calendar")}${fmtDate(g.target_date, { day: "numeric", month: "short", year: "numeric" })}${active && g.days_left != null ? ` · ${g.days_left < 0 ? -g.days_left + "d overdue" : g.days_left + " days left"}` : ""}</span>` : ""}
          <span class="chip">🔥 ${g.reflection_streak}-day reflection streak</span><span class="chip">${g.xp} XP earned</span></div></div>
      <div class="big-ring" style="--p:${g.progress}"><div><b>${g.progress}%</b><span>${g.done_count}/${g.total_count}</span></div></div></div>
    <div class="goal-grid2">
      <div>
        <div class="card mentor-plan">${g.mentor_plan ? `<div class="eyebrow" style="margin-bottom:6px">${icon("sparkle")} Donna's game plan</div><div class="mp-text">${md(g.mentor_plan)}</div>${active ? `<button class="btn ghost sm" id="replan">${icon("refresh")}Rethink the plan</button>` : ""}`
          : active ? `<div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap"><div style="flex:1;min-width:220px"><b>Get Donna's game plan</b><div class="muted" style="font-size:13px">Strategy, the trap to avoid, a weekly rhythm, and small tasks for your next milestones.</div></div><button class="btn primary" id="replan">${icon("sparkle")}Build my plan</button></div>` : `<div class="muted">No plan was saved.</div>`}</div>
        <div class="sec-head"><h2>Milestones</h2><span class="muted">${g.done_count} of ${g.total_count} done</span></div>
        <div class="card ms-list">${g.milestones.map(msHTML).join("") || `<div class="empty" style="padding:18px">No milestones yet. Add checkpoints, or let Donna build the plan.</div>`}
          ${active ? `<form class="ms-new" id="msNew">${icon("flag")}<input placeholder="Add a milestone, e.g. “First 1,000 subscribers”"><input type="date" class="ms-date"></form>` : ""}</div>
        ${g.loose_tasks.length ? `<div class="sec-head"><h2>Other tasks</h2></div><div class="card ms-list"><div class="ms-body">${g.loose_tasks.map((t) => `<div class="ms-task ${t.completed ? "done" : ""}" data-tid="${t.id}"><button class="check sq ${t.completed ? "on" : ""}" data-tdone>${icon("tick")}</button><span>${esc(t.title)}</span>${t.due_date ? `<span class="chip">${relDay(t.due_date)}</span>` : ""}</div>`).join("")}</div></div>` : ""}
      </div>
      <div>
        ${active ? `<div class="card reflect-card"><div class="eyebrow">Today's reflection</div>
          <h3>${refToday ? "Reflected. Want to add more?" : "How did today go for this goal?"}</h3>
          <textarea class="textarea" id="refText" placeholder="What did you do? What got in the way? What did you learn? Honest beats impressive.">${esc(refToday?.text || "")}</textarea>
          <div class="conf">${CONF.map(([v, l]) => `<button class="chip btnlike ${refToday?.confidence === v ? "active" : ""}" data-conf="${v}">${v} · ${l}</button>`).join("")}</div>
          <button class="btn primary" id="refSave" style="width:100%;justify-content:center;margin-top:10px">${icon("sparkle")}${refToday ? "Update & get advice" : "Reflect & get Donna's advice"}</button>
          <div id="refReply">${refToday?.mentor_reply ? mentorBubble(refToday.mentor_reply) : ""}</div></div>` : ""}
        <div class="sec-head"><h2>Reflection log</h2><span class="muted">${g.reflections.length}</span></div>
        <div class="ref-log">${g.reflections.filter((x) => x.date !== TODAY() || !active).map((x) => `<details class="card ref-item"><summary><span class="ref-date">${fmtDate(x.date, { weekday: "short", day: "numeric", month: "short" })}</span>${x.confidence ? `<span class="chip">${x.confidence}/5</span>` : ""}<span class="ref-snip">${esc(x.text.slice(0, 70))}</span></summary><p>${esc(x.text)}</p>${x.mentor_reply ? mentorBubble(x.mentor_reply) : ""}</details>`).join("") || `<div class="muted" style="font-size:13px">Your daily reflections and Donna's advice will build up here.</div>`}</div>
      </div></div>
    <div class="goal-actions">${active ? `<button class="btn" id="gEdit">${icon("edit")}Edit</button><button class="btn" id="gCoach">${icon("sparkle")}Talk it through</button><span class="spacer"></span><button class="btn ghost" id="gLetGo">🍃 Let it go</button><button class="btn accent" id="gAchieve">🏆 Mark achieved</button>`
      : `<button class="btn" id="gReactivate">${icon("refresh")}Make active again</button><span class="spacer"></span><button class="btn ghost danger" id="gDel">${icon("trash")}Delete</button>`}</div></div>`;

  const reload = () => goalPage(el, id);
  // milestones
  $$(".ms", el).forEach((row) => {
    const mid = row.dataset.mid;
    $("[data-mtoggle]", row).onclick = () => { const b = $(".ms-body", row); b.hidden = !b.hidden; };
    $("[data-mdone]", row).onclick = async () => { const res = await PATCH(`/api/milestones/${mid}`, { done: !row.classList.contains("done") }); celebrate(res.reward); reload(); };
    $("[data-mdel]", row).onclick = async () => { if (await confirmBox("Delete this milestone? Its tasks stay in your To Do.")) { await DEL(`/api/milestones/${mid}`); reload(); } };
    const f = $("[data-tadd]", row);
    if (f) f.onsubmit = async (e) => { e.preventDefault(); const [t, d] = $$("input", f); if (!t.value.trim()) return; await POST(`/api/milestones/${mid}/tasks`, { title: t.value.trim(), due_date: d.value || null }); refreshBoot(); reload(); };
    const bk = $("[data-break]", row);
    if (bk) bk.onclick = () => breakdownModal(mid, row.querySelector(".ms-title").textContent, reload);
  });
  $$("[data-tid]", el).forEach((row) => ($("[data-tdone]", row).onclick = async () => {
    const res = await PATCH(`/api/tasks/${row.dataset.tid}`, { completed: !row.classList.contains("done") });
    celebrate(res.reward); refreshBoot(); reload();
  }));
  const msNew = $("#msNew");
  if (msNew) msNew.onsubmit = async (e) => { e.preventDefault(); const [t, d] = $$("input", msNew); if (!t.value.trim()) return; await POST(`/api/goals/${id}/milestones`, { title: t.value.trim(), due_date: d.value || null }); reload(); };
  // plan
  $("#replan") && ($("#replan").onclick = () => planModal(g, reload));
  // reflection
  let conf = refToday?.confidence || null;
  $$("[data-conf]", el).forEach((b) => (b.onclick = () => { conf = +b.dataset.conf; $$("[data-conf]", el).forEach((x) => x.classList.toggle("active", x === b)); }));
  $("#refSave") && ($("#refSave").onclick = async () => {
    const text = $("#refText").value.trim();
    if (!text) return toast("Write a line or two first", { error: true });
    const btn = $("#refSave"); btn.disabled = true; btn.innerHTML = `${icon("sparkle")}Donna is reading your reflection…`;
    $("#refReply").innerHTML = mentorBubble(null);
    try { const r = await POST(`/api/goals/${id}/reflections`, { text, confidence: conf }); $("#refReply").innerHTML = mentorBubble(r.mentor_reply); celebrate(r.reward); btn.innerHTML = `${icon("tick")}Saved`; bindSpeak($("#refReply")); }
    catch (e) { fail(e); btn.disabled = false; btn.innerHTML = "Try again"; }
  });
  bindSpeak(el);
  // actions
  $("#gEdit") && ($("#gEdit").onclick = () => goalForm(g));
  $("#gCoach") && ($("#gCoach").onclick = () => askDonna(`Let's talk about my goal "${g.title}". Where do I stand and what should I focus on this week?`));
  $("#gAchieve") && ($("#gAchieve").onclick = () => modal({ title: "You did it?", body: `<p style="margin-top:0">Mark <b>${esc(g.title)}</b> as achieved. It moves to your trophy shelf and frees a slot.</p><div class="field"><label>A closing thought for your future self (optional)</label><textarea class="textarea" id="cNote" placeholder="What made the difference?"></textarea></div>`,
    foot: `<button class="btn ghost" data-close>Not yet</button><button class="btn accent" id="doAch">🏆 Achieved</button>`,
    onMount: (m, close) => { $("#doAch", m).onclick = async () => { const res = await POST(`/api/goals/${id}/achieve`, { note: $("#cNote", m).value }); close(); celebrate(res.reward, true); reload(); }; } }));
  $("#gLetGo") && ($("#gLetGo").onclick = () => modal({ title: "Let this goal go?", body: `<p style="margin-top:0;color:var(--ink-2)">Letting go is a strategic choice, not a failure. It moves to history (you can bring it back) and frees a slot for what matters more now.</p><div class="field"><label>Why are you letting it go? (optional)</label><textarea class="textarea" id="lNote"></textarea></div>`,
    foot: `<button class="btn ghost" data-close>Keep it</button><button class="btn" id="doLet">🍃 Let it go</button>`,
    onMount: (m, close) => { $("#doLet", m).onclick = async () => { await POST(`/api/goals/${id}/let-go`, { note: $("#lNote", m).value }); close(); toast("Slot opened. Choose wisely."); go("#/goals"); }; } }));
  $("#gReactivate") && ($("#gReactivate").onclick = async () => { try { await POST(`/api/goals/${id}/reactivate`); toast("Back in play."); reload(); } catch (e) { fail(e); } });
  $("#gDel") && ($("#gDel").onclick = async () => { if (await confirmBox(`Delete “${g.title}” and its reflections permanently?`)) { await DEL(`/api/goals/${id}`); go("#/goals"); } });
}

const mentorBubble = (text) => `<div class="mentor-bubble"><div class="avatar">D</div><div class="mb-text">${text ? md(text) + `<button class="icon-btn speak-mini" title="Listen">${icon("volume")}</button>` : `<span class="typing"><i></i><i></i><i></i></span>`}</div></div>`;
function bindSpeak(root) { $$(".speak-mini", root).forEach((b) => (b.onclick = () => (Voice.speaking() ? Voice.stop() : Voice.say(b.closest(".mb-text").innerText)))); }

function planModal(g, reload) {
  const m = modal({ title: "Donna's game plan", size: "lg", body: `<div id="planBody"><div class="mentor-bubble"><div class="avatar">D</div><div class="mb-text"><span class="typing"><i></i><i></i><i></i></span> <span class="muted">Studying your goal and building the plan… (about 30–60s)</span></div></div></div>`,
    foot: `<button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="planApply" disabled>Add to my goal</button>` });
  POST(`/api/goals/${g.id}/plan`).then((p) => {
    const body = $("#planBody", m.el);
    if (!body) return;
    body.innerHTML = `<div class="mp-text" style="margin-bottom:14px">${md(p.strategy)}</div>
      ${p.milestones.map((ms, i) => `<div class="plan-ms"><label><input type="checkbox" data-ms="${i}" checked> <b>${esc(ms.title)}</b> ${ms.existing_id ? `<span class="chip">existing</span>` : `<span class="chip accent">new${ms.due_date ? " · by " + fmtDate(ms.due_date) : ""}</span>`}</label>
        ${ms.tasks.map((t, j) => `<label class="plan-task"><input type="checkbox" data-t="${i}:${j}" checked> ${esc(t.title)}${t.due_date ? ` <span class="muted">· ${relDay(t.due_date)}</span>` : ""}</label>`).join("")}</div>`).join("")}`;
    const btn = $("#planApply", m.el); btn.disabled = false;
    btn.onclick = async () => {
      const keep = { strategy: p.strategy, milestones: p.milestones.map((ms, i) => ({ ...ms, tasks: ms.tasks.filter((_, j) => $(`[data-t="${i}:${j}"]`, m.el).checked) })).filter((_, i) => $(`[data-ms="${i}"]`, m.el).checked) };
      btn.disabled = true; btn.textContent = "Adding…";
      const res = await POST(`/api/goals/${g.id}/plan/apply`, keep);
      m.close(); celebrate(res.reward); refreshBoot(); reload();
    };
  }).catch((e) => { const body = $("#planBody", m.el); if (body) body.innerHTML = `<p style="color:var(--warn)">${esc(e.message)}</p>`; });
}

function breakdownModal(mid, title, reload) {
  const m = modal({ title: "Break it down", body: `<p class="muted" style="margin-top:0">${esc(title)}</p><div id="bdBody"><span class="typing"><i></i><i></i><i></i></span></div>`,
    foot: `<button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="bdAdd" disabled>Add selected</button>` });
  POST(`/api/milestones/${mid}/breakdown`).then(({ tasks }) => {
    const body = $("#bdBody", m.el);
    if (!body) return;
    body.innerHTML = tasks.map((t, i) => `<label class="plan-task"><input type="checkbox" data-i="${i}" checked> <span contenteditable="true" data-title="${i}">${esc(t.title)}</span>${t.due_date ? ` <span class="muted">· ${relDay(t.due_date)}</span>` : ""}</label>`).join("") || "<p class='muted'>No suggestions this time.</p>";
    const btn = $("#bdAdd", m.el); btn.disabled = !tasks.length;
    btn.onclick = async () => {
      btn.disabled = true;
      for (const [i, t] of tasks.entries()) if ($(`[data-i="${i}"]`, m.el).checked) await POST(`/api/milestones/${mid}/tasks`, { title: $(`[data-title="${i}"]`, m.el).textContent.trim() || t.title, due_date: t.due_date });
      m.close(); toast("Tasks added. Small steps, big outcomes."); refreshBoot(); reload();
    };
  }).catch((e) => { const body = $("#bdBody", m.el); if (body) body.innerHTML = `<p style="color:var(--warn)">${esc(e.message)}</p>`; });
}

// ---------- Today: Donna's daily mentor note ----------
let mentorPoll = null;
async function renderMentorCard(box) {
  clearTimeout(mentorPoll);
  if (!box || !document.body.contains(box)) return;
  let d;
  try { d = await GET("/api/mentor/today"); } catch { return; }
  if (!d.enabled) { box.remove(); return; }
  const note = d.messages[0];
  const thread = d.messages.slice(1);
  box.innerHTML = `<div class="mentor-head"><div class="avatar">D</div><div style="flex:1"><b>Donna's note</b><div class="muted" style="font-size:12px">${new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })} · your mentor</div></div>
      <span class="game-chip" id="gameChip">${gameChipHTML(d.game)}</span>
      ${note ? `<button class="icon-btn" id="mnSpeak" title="Listen">${icon("volume")}</button><button class="icon-btn" id="mnRegen" title="New take">${icon("refresh")}</button>` : ""}</div>
    <div class="mentor-body">${note ? md(note.content) : `<div class="muted"><span class="typing"><i></i><i></i><i></i></span> Donna is reading your goals, journal and tasks…</div>`}</div>
    ${d.goals.length ? `<div class="mentor-goals">${d.goals.map((g) => `<a href="#/goals/${g.id}" class="mg"><span class="mg-t">${esc(g.title)}</span><div class="progress"><i style="width:${g.progress}%"></i></div><span class="mg-s">${g.reflected_today ? "✓ reflected" : "reflect →"}</span></a>`).join("")}</div>` : `<a class="btn sm" href="#/goals" style="margin-top:10px">${icon("target")}Set your first goal</a>`}
    <div class="mentor-thread">${thread.map((m) => m.role === "user" ? `<div class="mt-user">${esc(m.content)}</div>` : `<div class="mt-donna">${md(m.content)}</div>`).join("")}</div>
    ${note ? `<form class="mentor-reply" id="mnForm"><input placeholder="Reply to Donna…" autocomplete="off"><button type="button" class="icon-btn mic" id="mnMic">${icon("mic")}</button><button class="btn primary sm">${icon("up")}</button></form>` : ""}`;
  if (!note) { mentorPoll = setTimeout(() => renderMentorCard(box), 4000); return; }
  $("#mnSpeak").onclick = () => (Voice.speaking() ? Voice.stop() : Voice.say($(".mentor-body", box).innerText));
  $("#mnRegen").onclick = async () => { await POST("/api/mentor/regenerate"); box.querySelector(".mentor-body").innerHTML = `<div class="muted"><span class="typing"><i></i><i></i><i></i></span> Taking another look…</div>`; setTimeout(() => waitRegen(box, note.id), 4000); };
  const form = $("#mnForm"), input = $("input", form);
  bindMic($("#mnMic"), input, (t) => { input.value = t; form.requestSubmit(); });
  form.onsubmit = async (e) => {
    e.preventDefault();
    const text = input.value.trim(); if (!text) return;
    input.value = ""; input.disabled = true;
    const th = $(".mentor-thread", box);
    th.insertAdjacentHTML("beforeend", `<div class="mt-user">${esc(text)}</div><div class="mt-donna"><span class="typing"><i></i><i></i><i></i></span></div>`);
    const out = th.lastElementChild;
    let buf = "";
    try {
      const res = await fetch("/api/chat", { method: "POST", headers: { ...HDR, "Content-Type": "application/json" }, body: JSON.stringify({ text, conversation_id: d.conversation_id, agent: "goals" }) });
      const reader = res.body.getReader(), dec = new TextDecoder(); let pending = "";
      for (;;) {
        const { value, done } = await reader.read(); if (done) break;
        pending += dec.decode(value, { stream: true }); const lines = pending.split("\n"); pending = lines.pop();
        for (const l of lines) { if (!l.trim()) continue; const ev = JSON.parse(l);
          if (ev.type === "token") { buf += ev.text; out.innerHTML = md(buf); }
          else if (ev.type === "reset") { buf = ""; out.innerHTML = `<span class="typing"><i></i><i></i><i></i></span>`; }
          else if (ev.type === "final") out.innerHTML = md(ev.text || buf);
          else if (ev.type === "reward") celebrate({ xp: ev.xp, level_up: ev.level_up, line: "Progress logged." });
          else if (ev.type === "error") out.innerHTML = `<span style="color:var(--warn)">${esc(ev.text)}</span>`; }
      }
    } catch (err) { out.innerHTML = `<span style="color:var(--warn)">${esc(err.message)}</span>`; }
    input.disabled = false; input.focus(); refreshBoot();
    if (Voice.autoRead()) Voice.say(out.innerText);
  };
}
async function waitRegen(box, oldId) {
  const d = await GET("/api/mentor/today").catch(() => null);
  if (d && d.messages[0] && d.messages[0].id !== oldId) return renderMentorCard(box);
  if (document.body.contains(box)) setTimeout(() => waitRegen(box, oldId), 4000);
}

// ============================== PEOPLE ==============================
VIEWS.people = async (el, r) => {
  const q = r.params.get("q") || "";
  const { items, due, birthdays } = await GET(`/api/people${q ? "?q=" + encodeURIComponent(q) : ""}`);
  const byId = Object.fromEntries(items.map((p) => [p.id, p]));
  const bdays = birthdays.map((id) => byId[id]).filter(Boolean).sort((a, b) => a.birthday_in_days - b.birthday_in_days);
  const reach = due.map((id) => byId[id]).filter(Boolean);
  el.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>People</h1><div class="sub">Birthdays, families, and what you talked about last time.</div></div>
      <div class="actions"><input class="input" id="pSearch" placeholder="Search people…" style="width:200px" value="${esc(q)}"><button class="btn primary" id="pAdd">${icon("plus")}Add person</button></div></div>
    ${bdays.length || reach.length ? `<div class="strip">${bdays.map((p) => `<div class="card" data-id="${p.id}"><div class="avatar-i">🎂</div><div><b>${esc(p.name)}</b><div class="muted" style="font-size:12.5px">${p.birthday_in_days === 0 ? "Birthday today!" : p.birthday_in_days === 1 ? "Birthday tomorrow" : `Birthday in ${p.birthday_in_days} days`}${p.turning ? ` · turning ${p.turning}` : ""}</div></div></div>`).join("")}
      ${reach.map((p) => `<div class="card" data-id="${p.id}"><div class="avatar-i">${esc(initials(p.name))}</div><div><b>Reach out to ${esc(p.name)}</b><div class="muted" style="font-size:12.5px">${p.days_since_contact == null ? "No contact logged yet" : `${p.days_since_contact} days since you spoke`}</div></div></div>`).join("")}</div>` : ""}
    ${items.length ? `<div class="mem-grid">${items.map((p) => `<div class="card person-card" data-id="${p.id}"><div class="avatar-i">${esc(initials(p.name))}</div><div style="min-width:0;flex:1"><div class="pn">${esc(p.name)}</div><div class="pr">${esc(p.relationship || "")}</div>
        <div class="chips">${p.next_birthday ? `<span class="chip ${p.birthday_in_days <= 7 ? "accent" : ""}">🎂 ${fmtDate(p.next_birthday, { day: "numeric", month: "short" })}</span>` : ""}${p.last_contact ? `<span class="chip ${p.contact_due ? "warn" : ""}">${p.days_since_contact === 0 ? "Spoke today" : `${p.days_since_contact}d ago`}</span>` : p.contact_every_days ? `<span class="chip warn">Not contacted</span>` : ""}${p.family ? `<span class="chip">${esc(p.family.slice(0, 30))}</span>` : ""}</div></div></div>`).join("")}</div>`
      : `<div class="empty big">${icon("users")}<h3>${q ? "Nobody matches" : "Who matters to you?"}</h3><div>Add family, friends, colleagues and clients, or tell Donna “Priya's birthday is 12 May, her kids are Aarav and Mira”.</div></div>`}</div>`;
  $("#pAdd").onclick = () => personForm({});
  $("#pSearch").onkeydown = (e) => { if (e.key === "Enter") go(`#/people?q=${encodeURIComponent(e.target.value.trim())}`); };
  $$("[data-id]", el).forEach((c) => (c.onclick = () => personDetail(+c.dataset.id)));
};
const CADENCE = [[0, "No reminder"], [7, "Every week"], [14, "Every 2 weeks"], [30, "Every month"], [60, "Every 2 months"], [90, "Every quarter"], [180, "Every 6 months"]];
function personForm(p) {
  modal({ title: p.id ? `Edit ${p.name}` : "Add person", body: `
    <div class="row"><div class="field"><label>Name</label><input class="input" name="name" value="${esc(p.name || "")}"></div><div class="field"><label>Relationship</label><input class="input" name="relationship" value="${esc(p.relationship || "")}" placeholder="mother, friend, manager…"></div></div>
    <div class="row"><div class="field"><label>Birthday</label><input class="input" name="birthday" value="${esc(p.birthday || "")}" placeholder="1990-05-12 or 05-12"></div><div class="field"><label>Keep in touch</label><select class="select" name="contact_every_days">${CADENCE.map(([v, l]) => `<option value="${v}" ${+(p.contact_every_days || 0) === v ? "selected" : ""}>${l}</option>`).join("")}</select></div></div>
    <div class="row"><div class="field"><label>Email</label><input class="input" name="email" value="${esc(p.email || "")}"></div><div class="field"><label>Phone</label><input class="input" name="phone" value="${esc(p.phone || "")}"></div></div>
    <div class="field"><label>Family</label><input class="input" name="family" value="${esc(p.family || "")}" placeholder="Partner Neha; kids Aarav (7), Mira (4); dog Bruno"></div>
    <div class="field"><label>Notes</label><textarea class="textarea" name="notes" placeholder="Vegetarian. Loves cricket. Moving to Pune in Jan.">${esc(p.notes || "")}</textarea></div>`,
    foot: `<button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="pSave">Save</button>`,
    onMount: (m, close) => { $("#pSave", m).onclick = async () => {
      const f = formData(m); f.contact_every_days = +f.contact_every_days;
      if (!f.name.trim()) return;
      try { const saved = p.id ? await PATCH(`/api/people/${p.id}`, f) : await POST("/api/people", f); close(); render(); personDetail(saved.id); } catch (e) { fail(e); }
    }; } });
}
async function personDetail(id) {
  const p = await GET(`/api/people/${id}`);
  const facts = [["Relationship", p.relationship], ["Birthday", p.birthday ? `${p.birthday}${p.next_birthday ? ` · next in ${p.birthday_in_days} days${p.turning ? ", turning " + p.turning : ""}` : ""}` : ""], ["Family", p.family], ["Email", p.email], ["Phone", p.phone], ["Keep in touch", CADENCE.find(([v]) => v === +p.contact_every_days)?.[1] || ""]].filter(([, v]) => v);
  modal({ title: p.name, size: "lg", body: `
    ${facts.map(([k, v]) => `<div class="vfield"><div class="k">${k}</div><div class="v">${esc(v)}</div></div>`).join("")}
    ${p.notes ? `<p style="white-space:pre-wrap;color:var(--ink-2)">${esc(p.notes)}</p>` : ""}
    <div class="eyebrow" style="margin:18px 0 8px">Log a catch-up</div>
    <form id="ixForm" style="display:flex;gap:8px"><input class="input" name="note" placeholder="What did you talk about?"><input class="input" type="date" name="date" value="${TODAY()}" style="width:150px"><button class="btn primary">Log</button></form>
    <div class="timeline">${p.interactions.map((i) => `<div class="ti"><div class="d">${fmtDate(i.date, { weekday: "short", day: "numeric", month: "short", year: "numeric" })} <button class="icon-btn" data-ix="${i.id}" style="width:20px;height:20px;vertical-align:middle">${icon("x")}</button></div><div>${esc(i.note || "Caught up")}</div></div>`).join("") || `<div class="muted" style="font-size:13px;padding:8px 0">No catch-ups logged yet.</div>`}</div>`,
    foot: `<button class="btn ghost danger" id="pDel" style="margin-right:auto">${icon("trash")}</button>${p.phone ? `<a class="btn" href="tel:${esc(p.phone)}">${icon("phone")}Call</a>` : ""}<button class="btn" id="pEdit">${icon("edit")}Edit</button>`,
    onMount: (m, close) => {
      $("#ixForm", m).onsubmit = async (e) => { e.preventDefault(); await POST(`/api/people/${id}/interactions`, formData(e.target)); close(); personDetail(id); render(); };
      $$("[data-ix]", m).forEach((b) => (b.onclick = async () => { await DEL(`/api/interactions/${b.dataset.ix}`); close(); personDetail(id); }));
      $("#pEdit", m).onclick = () => { close(); personForm(p); };
      $("#pDel", m).onclick = async () => { if (await confirmBox(`Remove ${p.name} and their history?`)) { await DEL(`/api/people/${id}`); close(); render(); } };
    } });
}

// ============================== RENEWALS ==============================
const REN_ICON = { subscription: "refresh", bill: "file", insurance: "shield", document: "id", membership: "card", tax: "bank", other: "clock" };
const CYCLES = [["", "One-off"], ["weekly", "Weekly"], ["monthly", "Monthly"], ["quarterly", "Quarterly"], ["half-yearly", "Half-yearly"], ["yearly", "Yearly"]];
VIEWS.renewals = async (el) => {
  const { items, monthly, categories } = await GET("/api/renewals");
  state.renCats = categories;
  const overdue = items.filter((r) => r.days_left < 0), soon = items.filter((r) => r.days_left >= 0 && r.days_left <= 30), later = items.filter((r) => r.days_left > 30);
  const spend = Object.entries(monthly).map(([c, v]) => money(v, c)).join(" + ") || "–";
  const row = (r) => `<div class="ren-row" data-id="${r.id}" style="cursor:pointer"><div class="ri">${icon(REN_ICON[r.category] || "clock")}</div>
    <div style="flex:1;min-width:0"><div class="rt">${esc(r.title)}</div><div class="rm">${esc(r.category)}${r.cycle ? " · " + r.cycle : ""} · ${fmtDate(r.due_date, { day: "numeric", month: "short", year: "numeric" })}</div></div>
    <span class="chip ${r.days_left < 0 ? "warn" : r.days_left <= r.remind_days ? "accent" : ""}">${r.days_left < 0 ? `${-r.days_left}d overdue` : r.days_left === 0 ? "Today" : r.days_left === 1 ? "Tomorrow" : `${r.days_left} days`}</span>
    <div class="amt">${esc(money(r.amount, r.currency))}</div>
    <button class="btn sm" data-done>${r.cycle ? "Paid / renewed" : "Done"}</button></div>`;
  const group = (t, list) => list.length ? `<div class="eyebrow" style="margin:22px 4px 8px;${t === "Overdue" ? "color:var(--warn)" : ""}">${t}</div><div class="card">${list.map(row).join("")}</div>` : "";
  el.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Renewals</h1><div class="sub">Subscriptions, bills, insurance and expiring documents. Nothing lapses.</div></div>
      <div class="actions"><button class="btn primary" id="rAdd">${icon("plus")}Track something</button></div></div>
    <div class="stat-row"><div class="card stat"><div class="eyebrow">Overdue</div><div class="n" style="${overdue.length ? "color:var(--warn)" : ""}">${overdue.length}</div></div>
      <div class="card stat"><div class="eyebrow">Due in 30 days</div><div class="n">${soon.length}</div></div>
      <div class="card stat"><div class="eyebrow">Tracked</div><div class="n">${items.length}</div></div>
      <div class="card stat"><div class="eyebrow">Recurring / month</div><div class="n" style="font-size:24px;margin-top:14px">${esc(spend)}</div></div></div>
    ${items.length ? group("Overdue", overdue) + group("Next 30 days", soon) + group("Later", later)
      : `<div class="empty big">${icon("refresh")}<h3>Never miss a renewal</h3><div>Track Netflix, the electricity bill, car insurance or your passport. Or tell Donna: “my passport expires on 3 June 2029”.</div></div>`}</div>`;
  const byId = Object.fromEntries(items.map((r) => [r.id, r]));
  $("#rAdd").onclick = () => renewalForm({});
  $$(".ren-row", el).forEach((rw) => (rw.onclick = async (e) => {
    const r = byId[rw.dataset.id];
    if (e.target.closest("[data-done]")) { const n = await POST(`/api/renewals/${r.id}/done`); toast(n.status === "active" ? `Next due ${fmtDate(n.due_date)}` : "Marked done"); refreshBoot(); return render(); }
    renewalForm(r);
  }));
};
function renewalForm(r) {
  const cats = state.renCats || ["subscription", "bill", "insurance", "document", "membership", "tax", "other"];
  modal({ title: r.id ? "Edit renewal" : "Track a renewal", body: `
    <div class="field"><label>What is it?</label><input class="input" name="title" value="${esc(r.title || "")}" placeholder="Netflix, Car insurance, Passport…"></div>
    <div class="row"><div class="field"><label>Category</label><select class="select" name="category">${cats.map((c) => `<option ${(r.category || "subscription") === c ? "selected" : ""}>${c}</option>`).join("")}</select></div>
      <div class="field"><label>Next due / expiry</label><input class="input" type="date" name="due_date" value="${r.due_date || ""}"></div></div>
    <div class="row"><div class="field"><label>Repeats</label><select class="select" name="cycle">${CYCLES.map(([v, l]) => `<option value="${v}" ${(r.cycle || "") === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>
      <div class="field"><label>Amount</label><input class="input" type="number" step="0.01" name="amount" value="${r.amount ?? ""}"></div>
      <div class="field" style="flex:0 0 90px"><label>Currency</label><input class="input" name="currency" value="${esc(r.currency || "INR")}" maxlength="3"></div></div>
    <div class="field"><label>Remind me (days before)</label><input class="input" type="number" name="remind_days" value="${r.remind_days ?? 7}" min="0"></div>
    <div class="field"><label>Notes</label><textarea class="textarea" name="notes" style="min-height:60px" placeholder="Policy no., how to renew, login hint…">${esc(r.notes || "")}</textarea></div>`,
    foot: `${r.id ? `<button class="btn ghost danger" id="rDel" style="margin-right:auto">${icon("trash")}</button>` : ""}<button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="rSave">Save</button>`,
    onMount: (m, close) => {
      $("#rSave", m).onclick = async () => {
        const f = formData(m);
        if (!f.title.trim() || !f.due_date) return toast("Add a title and a date", { error: true });
        f.amount = f.amount === "" ? null : +f.amount; f.remind_days = +f.remind_days; f.currency = f.currency.toUpperCase();
        if (r.doc_id) f.doc_id = r.doc_id;
        r.id ? await PATCH(`/api/renewals/${r.id}`, f) : await POST("/api/renewals", f);
        close(); toast("Tracking it"); refreshBoot(); if (location.hash.startsWith("#/renewals")) render();
      };
      $("#rDel", m) && ($("#rDel", m).onclick = async () => { await DEL(`/api/renewals/${r.id}`); close(); render(); });
    } });
}

// ============================== DOCUMENTS ==============================
let docPoll = null;
VIEWS.documents = async (el) => {
  clearTimeout(docPoll);
  const docs = await GET("/api/documents");
  const size = (b) => b > 1e6 ? (b / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1e3)) + " KB";
  const stChip = (d) => d.status === "ready" ? "" : d.status === "error" ? `<span class="chip warn">Couldn't read</span>` : `<span class="chip accent">${d.status === "indexed" ? "Summarising…" : "Reading…"}</span>`;
  el.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Documents</h1><div class="sub">Drop in policies, warranties, tickets and statements. Then just ask.</div></div>
      <div class="actions"><input class="input" id="dSearch" placeholder="Search inside documents…" style="width:240px"></div></div>
    <label class="dropzone" id="drop">${icon("upload")}<div><b>Drop files here</b> or click to choose</div><div style="font-size:12.5px;margin-top:4px">PDF, Word, text or photos (read by your local Qwen vision model) · up to 25 MB · stored only on this Mac</div><input type="file" id="fileIn" multiple hidden accept=".pdf,.docx,.txt,.md,.csv,.json,.html,.htm,.eml,.png,.jpg,.jpeg,.webp"></label>
    <div id="dResults"></div>
    <div class="card">${docs.map((d) => `<div class="doc-row" data-id="${d.id}"><div class="vc-icon" style="width:38px;height:38px;border-radius:10px;background:var(--accent-soft);color:var(--accent);display:grid;place-items:center;flex:none">${icon("file")}</div>
      <div style="flex:1;min-width:0"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span class="dt">${esc(d.title)}</span>${stChip(d)}</div>
        <div class="muted" style="font-size:12px">${esc(d.filename)} · ${size(d.size)} · added ${fmtDate(d.created_at.slice(0, 10))}${d.chunks ? ` · ${d.chunks} passages indexed` : ""}</div>
        ${d.summary ? `<div class="ds">${esc(d.summary)}</div>` : ""}${d.error ? `<div class="ds" style="color:var(--warn)">${esc(d.error)}</div>` : ""}
        ${d.dates.length ? `<div class="dd">${d.dates.map((x, i) => `<button class="chip btnlike" data-track="${i}" title="Track as a renewal">${icon("calendar")}${esc(x.label)}: ${fmtDate(x.date, { day: "numeric", month: "short", year: "numeric" })} ${icon("plus")}</button>`).join("")}</div>` : ""}</div>
      <div style="display:flex;gap:2px;flex:none"><button class="icon-btn" data-ask title="Ask about it">${icon("sparkle")}</button><a class="icon-btn" href="/api/documents/${d.id}/file" target="_blank" title="Open">${icon("eye")}</a>${d.status === "error" ? `<button class="icon-btn" data-re title="Try again">${icon("refresh")}</button>` : ""}<button class="icon-btn" data-del title="Delete">${icon("trash")}</button></div></div>`).join("")
      || `<div class="empty big">${icon("file")}<h3>Your paperwork, answerable</h3><div>Upload your car insurance and ask “when does it expire?” or “what's my policy number?”</div></div>`}</div></div>`;
  const input = $("#fileIn"), drop = $("#drop");
  const upload = async (files) => {
    for (const f of files) {
      const fd = new FormData(); fd.append("file", f);
      try { await api("POST", "/api/documents", fd); toast(`Reading ${f.name}…`); } catch (e) { fail(e); }
    }
    render();
  };
  input.onchange = () => upload([...input.files]);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); upload([...e.dataTransfer.files]); };
  const byId = Object.fromEntries(docs.map((d) => [d.id, d]));
  $$(".doc-row", el).forEach((row) => {
    const d = byId[row.dataset.id];
    $("[data-del]", row).onclick = async () => { if (await confirmBox(`Delete “${d.title}”? The file is removed from this Mac.`)) { await DEL(`/api/documents/${d.id}`); render(); } };
    $("[data-ask]", row).onclick = () => openPalette(`In my “${d.title}” document, `);
    $("[data-re]", row) && ($("[data-re]", row).onclick = async () => { await POST(`/api/documents/${d.id}/reprocess`); render(); });
    $$("[data-track]", row).forEach((b) => (b.onclick = () => {
      const x = d.dates[+b.dataset.track];
      const cat = /insur|policy/i.test(d.title + x.label) ? "insurance" : /passport|licen[cs]e|visa|id\b|pan|aadhaar/i.test(d.title + x.label) ? "document" : "other";
      renewalForm({ title: `${d.title}`.slice(0, 60), due_date: x.date, category: cat, remind_days: 30, doc_id: d.id, notes: `${x.label} (from document)`, currency: "" });
    }));
  });
  $("#dSearch").oninput = debounce(async (e) => {
    const q = e.target.value.trim(), box = $("#dResults");
    if (q.length < 2) { box.innerHTML = ""; return; }
    const hits = (await GET(`/api/search?q=${encodeURIComponent(q)}`)).filter((h) => h.type === "document");
    box.innerHTML = `<div class="card" style="margin-bottom:18px;padding:6px 0">${hits.map((h) => `<div style="padding:10px 18px"><b>${esc(h.title)}</b><div class="muted" style="font-size:13px">…${esc(h.excerpt.slice(0, 300))}…</div></div>`).join("") || `<div class="empty" style="padding:14px 18px">No matches.</div>`}</div>`;
  }, 250);
  if (docs.some((d) => d.status === "processing" || d.status === "indexed")) docPoll = setTimeout(() => { if (location.hash.startsWith("#/documents")) render(); }, 3000);
};

// ============================== WEEKLY REVIEW ==============================
VIEWS.review = async (el, r) => {
  const data = await GET(`/api/review${r.params.get("week") ? "?week=" + r.params.get("week") : ""}`);
  const rev = data.review, s = rev ? rev.stats : data.live;
  const days = [...Array(7)].map((_, i) => addDays(parseD(s.week_start), i));
  const MOOD_WORD = { great: "Great", good: "Good", okay: "Okay", low: "Low", rough: "Rough" };
  el.innerHTML = `<div class="page">
    <div class="page-head"><div><div class="eyebrow">Week of ${esc(s.week)}</div><h1>Weekly review</h1></div>
      <div class="actions">${data.history.length > 1 ? `<select class="select" id="wkPick" style="width:auto">${data.history.map((h) => `<option value="${h.week_start}" ${rev && rev.week_start === h.week_start ? "selected" : ""}>Week of ${fmtDate(h.week_start, { day: "numeric", month: "short" })}</option>`).join("")}</select>` : ""}
        ${rev ? `<button class="btn" id="revSpeak">${icon("volume")}Listen</button>` : ""}<button class="btn primary" id="revGen">${icon("sparkle")}${rev ? "Refresh" : "Write this week's review"}</button></div></div>
    <div class="stat-row" style="grid-template-columns:repeat(5,1fr)">${[["Done", s.completed_count], ["Slipped", s.slipped.length], ["Overdue now", s.overdue_now], ["Journal days", s.journal_days], ["People", s.people_contacted.length]].map(([k, v]) => `<div class="card stat"><div class="eyebrow">${k}</div><div class="n">${v}</div></div>`).join("")}</div>
    <div class="grid">
      <div class="card col-8"><div class="card-body review-body" style="padding:24px 28px" id="revBody">${rev ? md(rev.narrative) : `<div class="empty big" style="padding:30px 10px">${icon("chart")}<h3>Your week, in perspective</h3><div>Donna writes this every ${["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][+(state.reviewDay ?? 6)]} evening. Want one now?</div></div>`}</div></div>
      <div class="col-4" style="display:flex;flex-direction:column;gap:16px">
        <div class="card"><div class="card-head"><h3>Mood</h3></div><div class="card-body" style="display:flex;justify-content:space-between">${days.map((d) => { const m = s.mood_by_day[isoDate(d)]; return `<div style="text-align:center" title="${m ? MOOD_WORD[m] : "No entry"}"><div class="muted" style="font-size:11px">${d.toLocaleDateString(undefined, { weekday: "narrow" })}</div><span class="mood-dot ${m ? "m-" + m : ""}" style="width:14px;height:14px;margin-top:6px;${m ? "" : "background:var(--line)"}"></span></div>`; }).join("")}</div></div>
        ${s.goals.length ? `<div class="card"><div class="card-head"><h3>Goals</h3><a class="more" href="#/goals">All →</a></div><div class="card-body">${s.goals.map((g) => `<div style="margin:8px 0"><div style="display:flex;justify-content:space-between;font-size:13px"><span>${esc(g.title)}</span><span class="muted">${g.progress}%${g.moved_this_week ? ` · +${g.moved_this_week}` : ""}</span></div><div class="progress" style="margin-top:5px"><i style="width:${g.progress}%"></i></div></div>`).join("")}</div></div>` : ""}
        ${s.completed.length ? `<div class="card"><div class="card-head"><h3>Completed</h3></div><div class="card-body" style="font-size:13px">${s.completed.slice(0, 12).map((t) => `<div style="padding:3px 0">✓ ${esc(t)}</div>`).join("")}${s.completed.length > 12 ? `<div class="muted">+${s.completed.length - 12} more</div>` : ""}</div></div>` : ""}
      </div></div></div>`;
  $("#revGen").onclick = async () => {
    const b = $("#revGen"); b.disabled = true; b.innerHTML = `${icon("sparkle")}Writing… (about 30s)`;
    $("#revBody").innerHTML = `<div class="typing"><i></i><i></i><i></i></div>`;
    try { await POST("/api/review/generate"); render(); } catch (e) { fail(e); b.disabled = false; }
  };
  $("#wkPick") && ($("#wkPick").onchange = (e) => go(`#/review?week=${e.target.value}`));
  $("#revSpeak") && ($("#revSpeak").onclick = () => (Voice.speaking() ? Voice.stop() : Voice.say($("#revBody").innerText)));
};

// ============================== ADMIN extras ==============================
function loadScript(src) {
  return new Promise((res, rej) => { if ([...document.scripts].some((s) => s.src === src)) return res(); const s = document.createElement("script"); s.src = src; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
}
async function bindSettingsV2(el, s) {
  state.reviewDay = s.review_day;
  // Telegram
  const tg = async () => {
    const t = await GET("/api/telegram");
    $("#tgStatus").innerHTML = !t.configured ? `<span class="status-pill"><i></i>Not set up</span>`
      : t.paired ? `<span class="status-pill on"><i></i>Paired${t.bot ? " with @" + esc(t.bot) : ""}</span>`
      : t.error ? `<span class="status-pill off"><i></i>${esc(t.error)}</span>`
      : `<div class="callout" style="background:var(--accent-soft);border-color:transparent">Open <b>${t.bot ? "@" + esc(t.bot) : "your bot"}</b> in Telegram and send:<div class="code-big" style="margin-top:6px">/start ${esc(t.code)}</div></div>`;
  };
  tg();
  $("#tgTest").onclick = async () => { try { await POST("/api/telegram/test"); toast("Sent. Check Telegram"); } catch (e) { fail(e); } };
  $("#tgUnpair").onclick = async () => { await POST("/api/telegram/unpair"); tg(); };
  // Voice
  const vp = $("#voicePick");
  const fillVoices = () => { const vs = speechSynthesis.getVoices().filter((v) => /^(en|hi|ta)/.test(v.lang)); const cur = Voice.voice(); vp.innerHTML = vs.map((v) => `<option ${cur && cur.name === v.name ? "selected" : ""}>${esc(v.name)}</option>`).join("") || "<option>Default</option>"; };
  if ("speechSynthesis" in window) { fillVoices(); speechSynthesis.onvoiceschanged = fillVoices; }
  vp.onchange = () => localStorage.setItem("donna_voice", vp.value);
  $("#voiceRate").value = localStorage.getItem("donna_rate") || 1.02;
  $("#voiceRate").oninput = (e) => localStorage.setItem("donna_rate", e.target.value);
  $("#voiceLang").value = localStorage.getItem("donna_lang") || "en-IN";
  $("#voiceLang").onchange = (e) => localStorage.setItem("donna_lang", e.target.value);
  $("#voiceTest").onclick = () => Voice.say(`Hello${s.user_name ? " " + s.user_name : ""}. I'm Donna. I know everything, and I'll take care of it.`);
  // Hosts
  $("#saveHosts").onclick = async () => { await PUT("/api/settings", { allowed_hosts: $("#allowedHosts").value }); toast("Saved"); };
  // Login
  const box = $("#loginBox");
  const drawLogin = async () => {
    const a = await GET("/api/auth/status");
    if (!a.enabled) {
      box.innerHTML = `<span class="status-pill"><i></i>No app password, so only this Mac can open Donna</span>
        <form id="pwSet" style="margin-top:14px"><div class="row"><div class="field"><label>New app password</label><input class="input" type="password" name="password" minlength="10" autocomplete="new-password"></div><div class="field"><label>Confirm</label><input class="input" type="password" name="confirm" autocomplete="new-password"></div></div><button class="btn primary">${icon("shield")}Turn on login</button><span class="hint muted" style="margin-left:10px;font-size:12px">10+ characters. Different from your vault master password.</span></form>`;
      $("#pwSet").onsubmit = async (e) => { e.preventDefault(); const f = formData(e.target); if (f.password !== f.confirm) return toast("Passwords don't match", { error: true }); try { await POST("/api/auth/password", { password: f.password }); toast("Login is on. You're signed in on this device."); drawLogin(); } catch (err) { fail(err); } };
      return;
    }
    box.innerHTML = `<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center"><span class="status-pill on"><i></i>Login on</span><span class="status-pill ${a.totp ? "on" : ""}"><i></i>2FA ${a.totp ? "on" : "off"}</span><span class="muted" style="font-size:13px">${a.sessions} signed-in ${a.sessions === 1 ? "device" : "devices"}</span></div>
      <div id="totpArea" style="margin-top:14px">${a.totp ? "" : `<button class="btn" id="totpOn">${icon("phone")}Set up two-factor (authenticator app)</button>`}</div>
      <form id="pwChange" style="margin-top:16px"><div class="row"><div class="field"><label>Current password</label><input class="input" type="password" name="current" autocomplete="current-password"></div><div class="field"><label>New password</label><input class="input" type="password" name="password" autocomplete="new-password"></div></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn">Change password</button>${a.totp ? `<button type="button" class="btn ghost" id="totpOff">Turn off 2FA</button>` : ""}<button type="button" class="btn ghost" id="endAll">Sign out everywhere</button><button type="button" class="btn ghost" id="logout">Sign out</button><button type="button" class="btn ghost danger" id="authOff">Remove login</button></div></form>`;
    const cur = () => $("#pwChange [name=current]").value;
    $("#pwChange").onsubmit = async (e) => { e.preventDefault(); try { await POST("/api/auth/password", { current: cur(), password: $("#pwChange [name=password]").value }); toast("Password changed. Other devices were signed out."); drawLogin(); } catch (err) { fail(err); } };
    $("#endAll").onclick = async () => { await POST("/api/auth/sessions/end"); location.reload(); };
    $("#logout").onclick = async () => { await POST("/api/auth/logout"); location.reload(); };
    $("#authOff").onclick = async () => { if (!cur()) return toast("Enter your current password first", { error: true }); try { await POST("/api/auth/disable", { current: cur() }); toast("Login removed"); drawLogin(); } catch (err) { fail(err); } };
    $("#totpOff") && ($("#totpOff").onclick = async () => { if (!cur()) return toast("Enter your current password first", { error: true }); try { await POST("/api/auth/totp/disable", { current: cur() }); drawLogin(); } catch (err) { fail(err); } });
    $("#totpOn") && ($("#totpOn").onclick = async () => {
      const t = await POST("/api/auth/totp/begin");
      $("#totpArea").innerHTML = `<div class="callout">Scan with Google Authenticator, 1Password, Authy or Apple Passwords:<div><div class="qr" id="qrBox"></div></div><div class="muted" style="font-size:12px">Or enter this key manually: <code>${esc(t.secret)}</code></div>
        <form id="totpConfirm" style="display:flex;gap:8px;margin-top:10px"><input class="input" name="code" placeholder="6-digit code" inputmode="numeric" style="width:160px"><button class="btn primary">Confirm</button></form></div>`;
      try { await loadScript("https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"); new QRCode($("#qrBox"), { text: t.uri, width: 168, height: 168 }); } catch { $("#qrBox").outerHTML = ""; }
      $("#totpConfirm").onsubmit = async (e) => { e.preventDefault(); try { await POST("/api/auth/totp/confirm", formData(e.target)); toast("Two-factor is on"); drawLogin(); } catch (err) { fail(err); } };
    });
  };
  drawLogin();
}

// ============================== LOGIN ==============================
async function showLogin() {
  const box = $("#login");
  if (!box.hidden) return;
  const st = await fetch("/api/auth/status").then((r) => r.json()).catch(() => ({}));
  box.hidden = false;
  $("[name=code]", box).hidden = !st.totp;
  $("[name=password]", box).focus();
  $("#loginForm").onsubmit = async (e) => {
    e.preventDefault();
    try { await POST("/api/auth/login", formData(e.target)); location.reload(); }
    catch (err) { $("#loginErr").textContent = err.message; }
  };
}

// ============================== Init ==============================
(async function init() {
  hydrateIcons();
  $("#paletteBtn").onclick = () => openPalette();
  $("#bellBtn").onclick = toggleNotifPanel;
  $("#mobileMenu").onclick = () => $("#sidebar").classList.toggle("open");
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  const st = await fetch("/api/auth/status").then((r) => r.json()).catch(() => null);
  if (st && st.enabled && !st.signed_in) return showLogin();
  await refreshBoot();
  await render();
  if (!state.boot.onboarded) onboarding();
  await pollNotifications(true);
  setInterval(pollNotifications, 30000);
  setInterval(() => refreshBoot().catch(() => {}), 120000);
})();
