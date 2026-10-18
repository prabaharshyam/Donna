/* Donna: Subscription manager screen. */
"use strict";

const SUB_TABS = [["live", "All"], ["trial", "Trials"], ["active", "Active"], ["cancelled", "Cancelled"], ["insights", "Insights"]];
const BILLED_VIA = ["", "Direct", "App Store", "Google Play", "Amazon", "Telecom bundle (Jio/Airtel/Vi)", "Credit card benefit", "Broadband bundle"];
const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD"];
const PER = { weekly: "wk", monthly: "mo", quarterly: "qtr", "half-yearly": "6 mo", yearly: "yr" };
const CHECK_LABEL = { service: "Cancelled in the app / website", mandate: "Revoked the UPI AutoPay / card e-mandate", confirmation: "Saved the cancellation confirmation" };
const subMoney = (v, cur) => (v == null || v === "" ? "—" : money(Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 100) / 100, cur || "INR"));
const CHECK_SHORT = { service: "cancel in the app", mandate: "revoke the AutoPay / e-mandate", confirmation: "save the confirmation" };
let subsPoll = null;

function subWhen(s) {
  if (s.status === "trial") {
    const d = s.days_to_trial_end;
    return { text: d == null ? "Trial" : d < 0 ? "Trial ended" : d === 0 ? "Trial ends today" : `Trial ends in ${d}d`, cls: d != null && d <= 2 ? "warn" : "accent", sub: s.cancel_by ? `cancel by ${fmtDate(s.cancel_by)}` : "" };
  }
  if (s.status === "cancelling") return { text: "Cancelling", cls: "", sub: s.cancel_effective_date ? `access until ${fmtDate(s.cancel_effective_date)}` : "" };
  if (s.status === "cancelled") return { text: "Cancelled", cls: "", sub: s.cancelled_at ? fmtDate(s.cancelled_at.slice(0, 10)) : "" };
  if (s.status === "paused") return { text: "Paused", cls: "", sub: "" };
  if (s.status === "expired") return { text: "Expired", cls: "", sub: "" };
  const d = s.days_to_billing;
  return { text: d == null ? "Active" : d === 0 ? "Renews today" : d === 1 ? "Renews tomorrow" : `Renews in ${d}d`, cls: d != null && d <= 3 ? "accent" : "", sub: s.next_billing_date ? fmtDate(s.next_billing_date) : "" };
}

VIEWS.subscriptions = async (el, r) => {
  clearTimeout(subsPoll);
  const tab = r.params.get("tab") || "live";
  const data = await GET(`/api/subs?status=${tab === "insights" ? "live" : tab}`);
  const a = data.analytics, home = a.home_currency;
  const live = data.items;
  const scan = data.scan || {};
  const pendingChecks = a.cancelling_open;
  const alerts = [
    ...a.trials.filter((t) => t.days != null && t.days <= 7).map((t) => `<div class="sub-alert ${t.days <= 2 ? "hot" : ""}"><span>⏳</span><div><b>${esc(t.name)}</b> trial ends ${t.days <= 0 ? "today" : `in ${t.days} day${t.days === 1 ? "" : "s"}`}. <span class="muted">Cancel by ${fmtDate(t.cancel_by, { weekday: "short", day: "numeric", month: "short" })}${t.amount != null ? `, or it becomes ${subMoney(t.amount, t.currency)}` : ""}.</span></div><button class="btn sm" data-open="${t.id}">Decide</button></div>`),
    ...a.price_changes.map((p) => `<div class="sub-alert"><span>📈</span><div><b>${esc(p.name)}</b> price changed: ${subMoney(p.from, p.currency)} → ${subMoney(p.to, p.currency)}</div><button class="btn sm" data-open="${p.id}">Review</button></div>`),
    ...pendingChecks.map((c) => `<div class="sub-alert"><span>🧾</span><div><b>${esc(c.name)}</b> cancellation: still to ${c.pending.map((k) => CHECK_SHORT[k] || k).join(" · ")}</div><button class="btn sm" data-open="${c.id}">Finish</button></div>`),
    ...(a.over_budget ? [`<div class="sub-alert hot"><span>⚠️</span><div>Over your monthly budget: <b>${subMoney(a.monthly, home)}</b> vs ${subMoney(a.budget, home)}</div></div>`] : []),
    ...(a.unconverted_currencies.length ? [`<div class="sub-alert"><span>💱</span><div>No exchange rate yet for ${a.unconverted_currencies.join(", ")}: those amounts aren't in the totals. <a href="#/settings?s=subs" style="color:var(--accent)">Set it in Admin</a></div></div>`] : []),
  ];
  el.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Subscriptions</h1><div class="sub">Everything you pay for on repeat, and nothing you forgot to cancel.</div></div>
      <div class="actions"><button class="btn" id="subScan" ${scan.running ? "disabled" : ""}>${icon("mail")}${scan.running ? "Scanning email…" : "Find in my email"}</button><button class="btn primary" id="subAdd">${icon("plus")}Add</button></div></div>
    <div class="stat-row sub-stats">
      <div class="card stat"><div class="eyebrow">Per month · your share</div><div class="n">${subMoney(a.monthly, home)}</div>${a.budget ? `<div class="progress" style="margin-top:10px" title="${subMoney(a.monthly, home)} of ${subMoney(a.budget, home)} budget"><i style="width:${Math.min(100, Math.round(100 * a.monthly / a.budget))}%;${a.over_budget ? "background:var(--warn)" : ""}"></i></div>` : ""}</div>
      <div class="card stat"><div class="eyebrow">Per year</div><div class="n">${subMoney(a.yearly, home)}</div><div class="muted" style="font-size:12px;margin-top:6px">≈ ${subMoney(a.daily, home)} a day</div></div>
      <div class="card stat"><div class="eyebrow">Paying for</div><div class="n">${a.counts.active + a.counts.cancelling}<small>${a.counts.trial ? ` + ${a.counts.trial} trial${a.counts.trial > 1 ? "s" : ""}` : "active"}</small></div></div>
      <div class="card stat"><div class="eyebrow">Could save</div><div class="n" style="${a.waste_monthly ? "color:var(--ok)" : ""}">${subMoney(a.waste_monthly * 12, home)}<small>/yr</small></div><div class="muted" style="font-size:12px;margin-top:6px">${a.waste.length ? `${a.waste.length} low-value or unused` : "nothing flagged"}</div></div>
    </div>
    ${alerts.length ? `<div class="card sub-alerts">${alerts.join("")}</div>` : ""}
    ${data.suggestions.length || scan.running || scan.error ? `<div class="card sub-found"><div class="card-head">${icon("mail")}<h3>Found in your email</h3><span class="more">${scan.running ? esc(scan.progress || "Scanning…") : scan.error ? `<span style="color:var(--warn)">${esc(scan.error)}</span>` : scan.last_scan ? `scanned ${ago(scan.last_scan)}` : ""}</span></div>
      <div class="card-body">${data.suggestions.map((g) => `<div class="found-row" data-g="${g.id}"><div style="flex:1;min-width:0"><b>${esc(g.service)}</b>${g.plan ? ` <span class="muted">${esc(g.plan)}</span>` : ""}
          <div class="muted" style="font-size:12.5px">${({ trial_started: "Free trial started", charged: "Payment", upcoming_charge: "Upcoming charge", price_change: "Price change", payment_failed: "Payment failed", cancelled: "Cancelled" })[g.event] || g.event}${g.amount ? " · " + subMoney(g.amount, g.currency) : ""}${g.trial_end ? " · trial ends " + fmtDate(g.trial_end) : g.date ? " · " + fmtDate(g.date) : ""} · “${esc((g.subject || "").slice(0, 70))}”</div></div>
          <button class="btn accent sm" data-gadd>${icon("plus")}Add</button><button class="icon-btn" data-gdis title="Not a subscription">${icon("x")}</button></div>`).join("") || `<div class="muted" style="font-size:13px">${scan.running ? "Reading receipts, trials and AutoPay notices…" : "No new subscriptions found."}</div>`}</div></div>` : ""}
    <div class="filter-bar">${SUB_TABS.map(([k, l]) => `<a class="chip btnlike ${tab === k ? "active" : ""}" href="#/subscriptions?tab=${k}">${l}${k === "trial" && a.counts.trial ? ` <span class="muted">${a.counts.trial}</span>` : ""}</a>`).join("")}</div>
    <div id="subBody"></div></div>`;
  const body = $("#subBody");
  if (tab === "insights") renderSubInsights(body, a, data.last_audit);
  else {
    body.innerHTML = live.length ? `<div class="card">${live.map((s) => {
      const w = subWhen(s);
      const foreign = s.currency && s.currency !== home && s.monthly_home_full != null;
      return `<div class="sub-row" data-open="${s.id}"><div class="sub-logo">${esc(s.emoji || "💳")}</div>
        <div style="flex:1;min-width:0"><div class="rt">${esc(s.name)}${s.plan ? ` <span class="muted" style="font-weight:400">${esc(s.plan)}</span>` : ""}</div>
          <div class="rm">${esc(s.category)}${s.payment_method ? " · " + esc(s.payment_method) : ""}${s.billed_via ? " · via " + esc(s.billed_via) : ""}${s.shared_with ? ` · shared (${Math.round(s.my_share)}% yours)` : ""}${s.value_rating ? ` · ${"★".repeat(s.value_rating)}${"☆".repeat(5 - s.value_rating)}` : ""}${s.unused_days != null && s.unused_days >= 30 ? ` · <span style="color:var(--warn)">unused ${s.unused_days}d</span>` : ""}</div></div>
        <div class="sub-when"><span class="chip ${w.cls}">${w.text}</span>${w.sub ? `<div class="muted" style="font-size:11.5px;margin-top:3px">${w.sub}</div>` : ""}</div>
        <div class="amt">${s.amount != null ? `${subMoney(s.amount, s.currency)}<span class="muted" style="font-weight:400">/${PER[s.cycle] || "mo"}</span>` : `<span class="muted">add price</span>`}${foreign ? `<div class="muted" style="font-size:11.5px;font-weight:400">≈ ${subMoney(s.monthly_home_full, home)}/mo</div>` : ""}</div>
        ${["active", "trial"].includes(s.status) ? `<button class="icon-btn" data-used="${s.id}" title="I used this today">${icon("tick")}</button>` : ""}</div>`;
    }).join("")}</div>` : `<div class="empty big">${icon("card")}<h3>${tab === "live" ? "What are you paying for?" : "Nothing here"}</h3><div>${tab === "live" ? `Add your subscriptions, or let Donna find them in your email. Free trials get a <b>cancel-by</b> reminder so you never pay by accident.` : ""}</div>${tab === "live" ? `<div style="margin-top:16px;display:flex;gap:8px;justify-content:center"><button class="btn primary" id="subAdd2">${icon("plus")}Add a subscription</button>${data.email_configured ? `<button class="btn" id="subScan2">${icon("mail")}Scan my email</button>` : ""}</div>` : ""}</div>`;
  }
  // events
  $("#subAdd").onclick = () => subForm({});
  $("#subAdd2") && ($("#subAdd2").onclick = () => subForm({}));
  const startScan = async () => {
    if (!data.email_configured) return toast("Connect your email first: Admin → Email (Gmail app password)", { error: true });
    try { await POST("/api/subs/scan-email", { days: 120 }); toast("Reading the last 4 months of receipts, trials and AutoPay notices…"); setTimeout(render, 1500); } catch (e) { fail(e); }
  };
  $("#subScan").onclick = startScan;
  $("#subScan2") && ($("#subScan2").onclick = startScan);
  $$("[data-open]", el).forEach((x) => (x.onclick = (e) => { if (e.target.closest("[data-used]")) return; subDetail(+x.dataset.open); }));
  $$("[data-used]", el).forEach((b) => (b.onclick = async () => { await POST(`/api/subs/${b.dataset.used}/used`); toast("Noted: used today. That helps spot what's worth keeping."); }));
  $$(".found-row", el).forEach((row) => {
    const g = data.suggestions.find((x) => x.id === +row.dataset.g);
    $("[data-gadd]", row).onclick = () => subForm({ _suggestion: g, name: g.service, plan: g.plan, amount: g.amount, currency: g.currency || home, cycle: g.cycle || "monthly",
      trial_end_date: g.event === "trial_started" ? g.trial_end : null, next_billing_date: g.next_date || null });
    $("[data-gdis]", row).onclick = async () => { await POST(`/api/subs/suggestions/${g.id}/dismiss`); row.remove(); refreshBoot(); };
  });
  if (scan.running) subsPoll = setTimeout(() => { if (location.hash.startsWith("#/subscriptions")) render(); }, 3500);
};

function renderSubInsights(box, a, lastAudit) {
  const bars = (rows, total) => rows.length ? rows.map((r) => `<div class="hbar" title="${esc(r.name)}: ${subMoney(r.monthly, a.home_currency)}/month (${total ? Math.round(100 * r.monthly / total) : 0}%)">
      <span class="hb-label">${esc(r.name)}</span><span class="hb-track"><i style="width:${total ? Math.max(2, (100 * r.monthly) / rows[0].monthly) : 0}%"></i></span><span class="hb-val">${subMoney(r.monthly, a.home_currency)}</span></div>`).join("") : `<div class="muted" style="font-size:13px">Add subscriptions to see this.</div>`;
  const maxT = Math.max(1, ...a.trend.map((t) => t.total));
  box.innerHTML = `<div class="grid">
    <div class="card col-12 audit-card"><div class="card-head">${icon("sparkle")}<h3>Donna's audit</h3><span class="more">${lastAudit ? `last run ${ago(lastAudit.at)}` : ""}</span></div>
      <div class="card-body"><div id="auditText" class="mp-text">${lastAudit ? md(lastAudit.text) : `<p class="muted">Donna reviews everything you pay for: overlaps, unused services, cheaper ways to pay, trials to watch and AutoPays to revoke.</p>`}</div>
      <button class="btn ${lastAudit ? "" : "primary"} sm" id="runAudit" style="margin-top:10px">${icon("sparkle")}${lastAudit ? "Run again" : "Audit my subscriptions"}</button></div></div>
    <div class="card col-6"><div class="card-head"><h3>Per month, by category</h3></div><div class="card-body">${bars(a.by_category, a.monthly)}</div></div>
    <div class="card col-6"><div class="card-head"><h3>Per month, by payment method</h3></div><div class="card-body">${bars(a.by_payment, a.monthly)}</div></div>
    <div class="card col-8"><div class="card-head"><h3>Charges, last 12 months</h3><span class="more">logged and expected payments</span></div>
      <div class="card-body"><div class="vbars">${a.trend.map((t) => `<div class="vb" title="${t.label}: ${subMoney(t.total, a.home_currency)}"><span class="vb-bar" style="height:${Math.round((100 * t.total) / maxT)}%"></span><span class="vb-l">${t.label}</span></div>`).join("")}</div></div></div>
    <div class="card col-4"><div class="card-head"><h3>Next 30 days</h3></div><div class="card-body">${a.upcoming.map((u) => `<div class="agenda-item"><div class="time">${fmtDate(u.date, { day: "numeric", month: "short" })}</div><div style="flex:1">${esc(u.emoji || "")} ${esc(u.name)}</div><b style="font-weight:500">${subMoney(u.amount, u.currency)}</b></div>`).join("") || `<div class="muted" style="font-size:13px">Nothing due.</div>`}</div></div>
    ${a.waste.length ? `<div class="card col-12"><div class="card-head"><h3>Worth a second look</h3><span class="more">${subMoney(a.waste_monthly * 12, a.home_currency)}/year</span></div><div class="card-body">${a.waste.map((w) => `<div class="agenda-item" style="cursor:pointer" data-open="${w.id}"><div style="flex:1"><b>${esc(w.name)}</b> <span class="muted">· ${esc(w.why)}</span></div><b style="font-weight:500">${subMoney(w.monthly, a.home_currency)}/mo</b></div>`).join("")}</div></div>` : ""}
    <div class="col-12 muted" style="font-size:12px">${a.fx_updated ? `Exchange rates updated ${ago(a.fx_updated)}` : "Exchange rates not loaded yet"}${a.fx_markup_percent ? ` · includes ${a.fx_markup_percent}% card forex markup on foreign charges` : ""} · Your share of shared plans only. <a href="#/settings?s=subs" style="color:var(--accent)">Settings</a></div>
  </div>`;
  $$("[data-open]", box).forEach((x) => (x.onclick = () => subDetail(+x.dataset.open)));
  $("#runAudit").onclick = async () => {
    const b = $("#runAudit"); b.disabled = true; b.innerHTML = `${icon("sparkle")}Reviewing…`;
    $("#auditText").innerHTML = `<span class="typing"><i></i><i></i><i></i></span>`;
    try { const r = await POST("/api/subs/audit"); $("#auditText").innerHTML = md(r.text); b.innerHTML = `${icon("refresh")}Run again`; } catch (e) { fail(e); }
    b.disabled = false;
  };
}

async function subForm(s) {
  const catalog = await GET("/api/subs/catalog").catch(() => []);
  const cats = ["entertainment", "music", "ai tools", "productivity", "cloud storage", "news & reading", "learning", "fitness & health", "food & delivery", "shopping & memberships", "gaming", "software & dev", "finance", "telecom & internet", "other"];
  const isTrial = !!s.trial_end_date || s.status === "trial";
  modal({ title: s.id ? `Edit ${s.name}` : s._suggestion ? "Add from email" : "Add a subscription", size: "lg", body: `
    <div class="row"><div class="field"><label>Service</label><input class="input" name="name" list="subCatalog" value="${esc(s.name || "")}" placeholder="Netflix, ChatGPT Plus, iCloud+…"><datalist id="subCatalog">${catalog.map((c) => `<option value="${esc(c.name)}">`).join("")}</datalist></div>
      <div class="field"><label>Plan</label><input class="input" name="plan" value="${esc(s.plan || "")}" placeholder="Premium, Pro annual…"></div></div>
    <div class="row"><div class="field"><label>Price</label><input class="input" type="number" step="0.01" name="amount" value="${s.amount ?? ""}"></div>
      <div class="field" style="flex:0 0 110px"><label>Currency</label><select class="select" name="currency">${[...new Set([s.currency || "INR", ...CURRENCIES])].map((c) => `<option ${(s.currency || "INR") === c ? "selected" : ""}>${c}</option>`).join("")}</select></div>
      <div class="field"><label>Billed</label><select class="select" name="cycle">${["weekly", "monthly", "quarterly", "half-yearly", "yearly"].map((c) => `<option ${(s.cycle || "monthly") === c ? "selected" : ""}>${c}</option>`).join("")}</select></div></div>
    <div class="field" style="flex-direction:row;align-items:center;gap:10px"><label class="switch"><input type="checkbox" id="isTrial" ${isTrial ? "checked" : ""}><span></span></label><span>This is a <b>free trial</b></span></div>
    <div class="row"><div class="field" id="trialField" ${isTrial ? "" : "hidden"}><label>Trial ends (first charge)</label><input class="input" type="date" name="trial_end_date" value="${s.trial_end_date || ""}"><span class="hint">Donna reminds you 3 days, 1 day and the morning before.</span></div>
      <div class="field" id="nextField" ${isTrial ? "hidden" : ""}><label>Next charge date</label><input class="input" type="date" name="next_billing_date" value="${s.next_billing_date || ""}"></div>
      <div class="field"><label>Category</label><select class="select" name="category">${cats.map((c) => `<option ${(s.category || "") === c ? "selected" : ""}>${c}</option>`).join("")}</select></div></div>
    <div class="row"><div class="field"><label>Paid with</label><input class="input" name="payment_method" value="${esc(s.payment_method || "")}" placeholder="HDFC credit card · UPI AutoPay (GPay)"><span class="hint">A label only. Never type card numbers here.</span></div>
      <div class="field"><label>Billed through</label><select class="select" name="billed_via">${BILLED_VIA.map((v) => `<option value="${esc(v)}" ${(s.billed_via || "") === v ? "selected" : ""}>${v || "Not sure"}</option>`).join("")}</select></div></div>
    <div class="row"><div class="field"><label>Shared with</label><input class="input" name="shared_with" value="${esc(s.shared_with || "")}" placeholder="e.g. family plan with wife & parents"></div>
      <div class="field" style="flex:0 0 140px"><label>Your share %</label><input class="input" type="number" min="0" max="100" name="my_share" value="${s.my_share ?? 100}"></div></div>
    <div class="row"><div class="field"><label>Manage / cancel page</label><input class="input" name="manage_url" value="${esc(s.manage_url || "")}" placeholder="filled in for popular services"></div>
      <div class="field" style="flex:0 0 160px"><label>Remind days before</label><input class="input" name="reminder_days" value="${esc(s.reminder_days || "")}" placeholder="auto, e.g. 7,2"></div></div>
    <div class="field"><label>Notes</label><input class="input" name="notes" value="${esc(s.notes || "")}" placeholder="account email, why you have it…"></div>
    ${!s.id ? `<label style="display:flex;gap:8px;align-items:center;font-size:13px" id="calWrap" ${isTrial ? "" : "hidden"}><input type="checkbox" id="addCal" checked> Also put “cancel trial” on my calendar</label>` : ""}`,
    foot: `${s.id ? `<button class="btn ghost danger" id="sDel" style="margin-right:auto">${icon("trash")}</button>` : ""}<button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="sSave">Save</button>`,
    onMount: (m, close) => {
      const nameIn = $("[name=name]", m);
      nameIn.addEventListener("change", () => { const c = catalog.find((x) => x.name.toLowerCase() === nameIn.value.trim().toLowerCase()); if (c) { $("[name=category]", m).value = c.category; if (!$("[name=manage_url]", m).value) $("[name=manage_url]", m).value = c.manage_url; } });
      $("#isTrial", m).onchange = (e) => { $("#trialField", m).hidden = !e.target.checked; $("#nextField", m).hidden = e.target.checked; if ($("#calWrap", m)) $("#calWrap", m).hidden = !e.target.checked; };
      $("#sSave", m).onclick = async () => {
        const f = formData(m);
        if (!f.name.trim()) return toast("Add the service name", { error: true });
        const trial = $("#isTrial", m).checked;
        if (trial && !f.trial_end_date) return toast("When does the trial end?", { error: true });
        const body = { ...f, amount: f.amount === "" ? null : +f.amount, my_share: +f.my_share || 100 };
        delete body.isTrial; delete body.addCal;
        if (trial) { body.status = "trial"; body.next_billing_date = f.trial_end_date; } else { body.trial_end_date = null; if (s.status === "trial") body.status = "active"; }
        try {
          let saved;
          if (s._suggestion) saved = await POST(`/api/subs/suggestions/${s._suggestion.id}/accept`, body).then(async (x) => PATCH(`/api/subs/${x.id}`, body));
          else saved = s.id ? await PATCH(`/api/subs/${s.id}`, body) : await POST("/api/subs", body);
          if (!s.id && trial && $("#addCal", m)?.checked && saved.cancel_by) {
            await POST("/api/events", { title: `Cancel ${saved.name} trial (or keep it)`, start: `${saved.cancel_by}T10:00`, end: `${saved.cancel_by}T10:15`, description: `Free trial converts to paid on ${saved.trial_end_date}.` }).catch(() => {});
          }
          close(); toast(trial ? `Saved. Cancel-by date: ${fmtDate(saved.cancel_by)}` : "Saved"); refreshBoot(); render();
        } catch (e) { fail(e); }
      };
      $("#sDel", m) && ($("#sDel", m).onclick = async () => { if (await confirmBox(`Delete ${s.name} and its payment history? (To stop paying, use Cancel instead.)`)) { await DEL(`/api/subs/${s.id}`); close(); render(); } });
    } });
}

async function subDetail(id) {
  const s = await GET(`/api/subs/${id}`);
  const w = subWhen(s);
  const home = (await GET("/api/subs?status=none").catch(() => ({ analytics: { home_currency: "INR" } }))).analytics.home_currency;
  const live = ["trial", "active", "paused"].includes(s.status);
  const facts = [["Price", s.amount != null ? `${subMoney(s.amount, s.currency)} / ${s.cycle}${s.currency !== home && s.monthly_home_full != null ? ` (≈ ${subMoney(s.monthly_home_full, home)}/month)` : ""}` : "Not set"],
    ["Status", `${w.text}${w.sub ? " · " + w.sub : ""}`], ["Paid with", s.payment_method], ["Billed through", s.billed_via], ["Category", s.category],
    ["Shared", s.shared_with ? `${s.shared_with} · your share ${Math.round(s.my_share)}%` : ""], ["Since", s.start_date ? fmtDate(s.start_date, { day: "numeric", month: "short", year: "numeric" }) : ""],
    ["Last used", s.last_used ? relDay(s.last_used) : ""], ["Previous price", s.previous_amount ? subMoney(s.previous_amount, s.currency) : ""], ["Notes", s.notes]].filter(([, v]) => v);
  const ckKeys = Object.keys(s.checklist || {});
  modal({ title: `${s.emoji || ""} ${s.name}`.trim(), size: "lg", body: `
    ${facts.map(([k, v]) => `<div class="vfield"><div class="k">${k}</div><div class="v">${esc(v)}</div></div>`).join("")}
    <div class="vfield"><div class="k">Worth it?</div><div class="v stars">${[1, 2, 3, 4, 5].map((n) => `<button class="star-btn ${s.value_rating >= n ? "on" : ""}" data-rate="${n}" title="${n}/5">★</button>`).join("")}</div></div>
    ${s.manage_url ? `<p style="margin:12px 0 0"><a href="${esc(s.manage_url)}" target="_blank" rel="noopener" style="color:var(--accent)">${icon("link")} Manage or cancel on ${esc(new URL(s.manage_url).hostname.replace("www.", ""))}</a></p>` : ""}
    ${ckKeys.length && ["cancelling", "cancelled"].includes(s.status) ? `<div class="prep-box"><h4>Cancellation checklist</h4>${ckKeys.map((k) => `<label class="plan-task" style="padding-left:0"><input type="checkbox" data-ck="${k}" ${s.checklist[k] ? "checked" : ""}> ${CHECK_LABEL[k] || k}</label>`).join("")}</div>` : ""}
    <div id="cancelGuide">${s.cancel_guide ? `<div class="prep-box"><h4>How to cancel</h4>${md(s.cancel_guide)}</div>` : ""}</div>
    <div class="eyebrow" style="margin:18px 0 6px">Payments</div>
    <form id="chargeForm" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px"><input class="input" type="number" step="0.01" name="amount" value="${s.amount ?? ""}" style="width:120px" placeholder="Amount"><input class="input" type="date" name="date" value="${TODAY()}" style="width:160px"><button class="btn sm">${icon("plus")}Log a payment</button></form>
    ${s.charges.map((c) => `<div class="agenda-item"><div class="time">${fmtDate(c.date, { day: "numeric", month: "short", year: "2-digit" })}</div><div style="flex:1">${subMoney(c.amount, c.currency)}${c.currency !== home && c.home != null ? ` <span class="muted">≈ ${subMoney(c.home, home)}</span>` : ""} <span class="muted" style="font-size:12px">· ${({ auto: "expected", email: "from email", manual: "logged" })[c.source] || c.source}${c.note ? " · " + esc(c.note) : ""}</span></div><button class="icon-btn" data-delc="${c.id}" title="Remove">${icon("x")}</button></div>`).join("") || `<div class="muted" style="font-size:13px">No payments logged yet. Donna adds the expected charge on each renewal date.</div>`}`,
    foot: `${live ? `<button class="btn ghost danger" id="sCancel" style="margin-right:auto">Cancel subscription</button>` : `<button class="btn ghost" id="sReact" style="margin-right:auto">${icon("refresh")}Reactivate</button>`}
      <button class="btn" id="sGuide">${icon("sparkle")}How to cancel</button><button class="btn" id="sEdit">${icon("edit")}Edit</button>`,
    onMount: (m, close) => {
      const reopen = () => { close(); subDetail(id); render(); };
      $$("[data-rate]", m).forEach((b) => (b.onclick = async () => { await PATCH(`/api/subs/${id}`, { value_rating: +b.dataset.rate }); reopen(); }));
      $$("[data-ck]", m).forEach((c) => (c.onchange = async () => { await POST(`/api/subs/${id}/checklist`, { key: c.dataset.ck, done: c.checked }); render(); }));
      $$("[data-delc]", m).forEach((b) => (b.onclick = async () => { await DEL(`/api/sub_charges/${b.dataset.delc}`); reopen(); }));
      $("#chargeForm", m).onsubmit = async (e) => {
        e.preventDefault(); const f = formData(e.target);
        const r = await POST(`/api/subs/${id}/charge`, { amount: f.amount === "" ? null : +f.amount, date: f.date });
        toast(r.duplicate ? "Already logged" : r.price_change ? `Logged. Price changed from ${subMoney(r.price_change[0], s.currency)} to ${subMoney(r.price_change[1], s.currency)}` : "Payment logged");
        reopen();
      };
      $("#sEdit", m).onclick = () => { close(); subForm(s); };
      $("#sGuide", m).onclick = async () => {
        const b = $("#sGuide", m); b.disabled = true; b.innerHTML = `${icon("sparkle")}Writing…`;
        $("#cancelGuide", m).innerHTML = `<div class="prep-box"><span class="typing"><i></i><i></i><i></i></span></div>`;
        try { const r = await POST(`/api/subs/${id}/cancel-guide`); $("#cancelGuide", m).innerHTML = `<div class="prep-box"><h4>How to cancel</h4>${md(r.text)}</div>`; } catch (e) { fail(e); }
        b.disabled = false; b.innerHTML = `${icon("sparkle")}How to cancel`;
      };
      $("#sReact", m) && ($("#sReact", m).onclick = async () => { await POST(`/api/subs/${id}/reactivate`); toast("Back on the list"); reopen(); });
      $("#sCancel", m) && ($("#sCancel", m).onclick = () => { close(); cancelForm(s); });
    } });
}

function cancelForm(s) {
  const until = s.status === "trial" ? s.trial_end_date : s.next_billing_date;
  modal({ title: `Cancel ${s.name}?`, body: `
    <p style="margin-top:0;color:var(--ink-2)">Donna stops the renewal reminders and gives you a checklist, so the money actually stops.</p>
    <div class="field"><label>Access ends</label><input class="input" type="date" name="effective_date" value="${until || TODAY()}"><span class="hint">Usually the end of the period you've paid for. Trials end immediately on most services.</span></div>
    <div class="field"><label>Why? (optional, helps Donna's advice)</label><input class="input" name="reason" placeholder="Not using it · too expensive · switched to …"></div>
    <div class="callout" style="margin-bottom:0">Don't forget the AutoPay: in India a UPI AutoPay or card e-mandate can keep debiting even after you cancel in the app. Revoke it in your UPI app (AutoPay section) or your bank's e-mandate page.</div>`,
    foot: `<button class="btn ghost" data-close>Keep it</button><button class="btn accent" id="doCancel">Mark as cancelled</button>`,
    onMount: (m, close) => { $("#doCancel", m).onclick = async () => { await POST(`/api/subs/${s.id}/cancel`, formData(m)); close(); toast("Cancelled. Finish the checklist to make sure nothing is charged."); refreshBoot(); render(); subDetail(s.id); }; } });
}
