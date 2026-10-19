// Altruistic Agent map UI. No build step. Talks to the FastAPI backend:
//   GET /pins, POST /pins, GET /pins/{id}, GET /brief, POST /brief/send
// Falls back to web/fixtures.json when the API is unreachable so the map always renders.

const POLL_MS = 3000;
const MISSION = [37.7599, -122.4183];
const params = new URLSearchParams(location.search);
const DEMO_CONTROLS = params.has("demo");

const STATUS = {
  routing:      { label: "Routing",       desc: "Agent is working on it" },
  routed:       { label: "Routed",        desc: "Agency found" },
  reported:     { label: "Draft ready",   desc: "Report drafted, waiting on a human to send" },
  acknowledged: { label: "Acknowledged",  desc: "Agency replied" },
  resolved:     { label: "Resolved",      desc: "Fixed" },
  needs_human:  { label: "Needs a human", desc: "Could not verify the right agency" },
  emergency:    { label: "Emergency",     desc: "Call 911" },
};
const STEP_LABEL = {
  classify: "Classify", parallel_search: "Find agency", dedupe: "Already reported?",
  guardrails: "Guardrails", sheet: "Community sheet", gmail_draft: "Gmail draft", slack: "Slack post",
};
const TOOL_LABEL = { llm: "LLM", parallel: "Parallel", composio: "Composio" };

const state = {
  pins: [],
  byId: new Map(),
  markers: new Map(),
  selected: null,       // pin id
  draft: null,          // {lat, lng, marker}
  offline: false,
  lastRenderKey: "",
};

// ---------- utils ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => { try { const x = new URL(u); return /^https?:$/.test(x.protocol) ? x.href : null; } catch { return null; } };
const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };
const cssVar = (status) => `var(--s-${STATUS[status] ? status : "resolved"})`;
const statusLabel = (s) => (STATUS[s] || { label: s }).label;
const pretty = (s) => String(s || "").replace(/_/g, " ");

function ago(iso) {
  const t = Date.parse(iso);
  if (!t) return "";
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}
function badge(status) {
  return `<span class="badge" style="--c:${cssVar(status)}">${esc(statusLabel(status))}</span>`;
}
function showBanner(text) {
  const b = document.getElementById("banner");
  b.hidden = !text;
  b.textContent = text || "";
}

async function api(path, opts = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeout || 8000);
  try {
    const r = await fetch(path, { ...opts, signal: ctrl.signal, headers: { "Content-Type": "application/json", ...(opts.headers || {}) } });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    const ct = r.headers.get("content-type") || "";
    return ct.includes("json") ? r.json() : r.text();
  } finally {
    clearTimeout(timer);
  }
}

// ---------- map ----------
const map = L.map("map", { zoomControl: true }).setView(MISSION, 15);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

function pinIcon(pin) {
  const cls = ["pin-dot"];
  if (pin.status === "routing") cls.push("pulse");
  if (pin.id === state.selected) cls.push("sel");
  return L.divIcon({
    className: "pin-icon",
    html: `<div class="${cls.join(" ")}" style="--c:${cssVar(pin.status)}"></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

function syncMarkers() {
  const seen = new Set();
  for (const pin of state.pins) {
    seen.add(pin.id);
    const key = `${pin.status}|${pin.id === state.selected}`;
    let m = state.markers.get(pin.id);
    if (!m) {
      m = L.marker([pin.lat, pin.lng], { icon: pinIcon(pin), riseOnHover: true }).addTo(map);
      m.on("click", (e) => { L.DomEvent.stopPropagation(e); select(pin.id); });
      m.bindTooltip(() => esc(state.byId.get(pin.id)?.note || ""), { direction: "top", offset: [0, -8] });
      m._key = key;
      state.markers.set(pin.id, m);
    } else if (m._key !== key) {
      m.setIcon(pinIcon(pin));
      m._key = key;
    }
    if (pin.id === state.selected) m.setZIndexOffset(1000); else m.setZIndexOffset(0);
  }
  for (const [id, m] of state.markers) {
    if (!seen.has(id)) { map.removeLayer(m); state.markers.delete(id); }
  }
}

map.on("click", (e) => startDraft(e.latlng));

// ---------- data ----------
async function loadPins() {
  try {
    const pins = await api("/pins", { timeout: 5000 });
    state.offline = false;
    showBanner("");
    setPins(Array.isArray(pins) ? pins : pins.pins || []);
  } catch (err) {
    if (!state.offline) {
      state.offline = true;
      showBanner("Backend unreachable. Showing sample pins so the map still works.");
      try {
        const fx = await (await fetch("fixtures.json")).json();
        // keep any locally-dropped pins
        const local = state.pins.filter((p) => p._local);
        setPins([...fx, ...local]);
      } catch { setPins(state.pins); }
    }
  }
}

function setPins(pins) {
  state.pins = pins.slice().sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
  state.byId = new Map(state.pins.map((p) => [p.id, p]));
  syncMarkers();
  render();
}

// ---------- panel ----------
const panel = document.getElementById("panel");

function render() {
  if (state.draft) return; // don't clobber the form while typing
  const pin = state.selected && state.byId.get(state.selected);
  const key = pin ? `pin|${pin.id}|${pin.updated_at}|${pin.status}|${(pin.trace || []).length}` :
    `list|${state.pins.map((p) => p.id + p.status + p.updated_at).join(",")}`;
  if (key === state.lastRenderKey) return;
  state.lastRenderKey = key;
  const openDetails = [...panel.querySelectorAll("details[open]")].map((d) => d.dataset.k);
  panel.innerHTML = pin ? renderPin(pin) : renderList();
  for (const k of openDetails) panel.querySelector(`details[data-k="${k}"]`)?.setAttribute("open", "");
}

function renderList() {
  const counts = {};
  for (const p of state.pins) counts[p.status] = (counts[p.status] || 0) + 1;
  const countChips = Object.keys(STATUS).filter((s) => counts[s])
    .map((s) => `<span class="badge" style="--c:${cssVar(s)}">${counts[s]} ${esc(statusLabel(s).toLowerCase())}</span>`).join("");
  const items = state.pins.map((p) => `
    <li data-id="${esc(p.id)}">
      <span class="dot" style="--c:${cssVar(p.status)}"></span>
      <div>
        <p class="note">${esc(p.note)}</p>
        <div class="meta">${esc(statusLabel(p.status))} &middot; ${esc(p.card?.category ? pretty(p.card.category) : "unclassified")} &middot; ${esc(ago(p.updated_at))}</div>
      </div>
    </li>`).join("");
  return `
    <h2>Neighborhood pins</h2>
    <p class="hint">Tap anywhere on the map to drop a pin. Your agent finds who can fix it, drafts the report, and tells your neighbors.</p>
    <div class="counts">${countChips}</div>
    <ul class="list">${items || '<li class="muted">No pins yet.</li>'}</ul>`;
}

function renderTrace(trace) {
  if (!trace?.length) return '<p class="muted">No steps yet.</p>';
  const chips = trace.map((t) => {
    const tool = TOOL_LABEL[t.tool] ? t.tool : "llm";
    const secs = t.ms >= 1000 ? `${(t.ms / 1000).toFixed(1)}s` : `${t.ms}ms`;
    return `<span class="tchip ${t.ok ? "" : "fail"}" style="--tc:var(--t-${tool})" title="${esc(t.step)} via ${esc(t.tool)}">
      <span class="tool">${esc(TOOL_LABEL[t.tool] || t.tool)}</span>${esc(STEP_LABEL[t.step] || pretty(t.step))}
      <span class="muted">${secs}</span><span class="ok">${t.ok ? "&#10003;" : "&#10007;"}</span></span>`;
  }).join("");
  return `<div class="trace">${chips}</div>
    <div class="legend-tools"><span style="--tc:var(--t-llm)">Open model</span><span style="--tc:var(--t-parallel)">Parallel</span><span style="--tc:var(--t-composio)">Composio</span></div>`;
}

function renderPin(p) {
  const c = p.card;
  let out = `
    <button class="link-btn" data-act="back">&larr; All pins</button>
    <div class="row" style="margin-top:10px">${badge(p.status)}
      ${c?.category ? `<span class="chip">${esc(pretty(c.category))}</span>` : ""}
      ${c?.severity ? `<span class="chip">${esc(c.severity)} severity</span>` : ""}
    </div>
    <div class="quote">${esc(p.note)}</div>
    <div class="meta muted" style="font-size:12px">${esc(p.reporter || "neighbor")} &middot; ${esc(p.address_hint || `${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}`)} &middot; ${esc(ago(p.created_at))}</div>`;

  if (p.status === "emergency") {
    out += `<div class="alert emergency"><strong>Call 911 now.</strong>This sounds like an emergency, so your agent did not route it. Get to safety first.</div>`;
    return out;
  }
  if (p.status === "routing") {
    out += `<div class="alert working"><span class="spinner"></span><span>Your agent is finding who can fix this...</span></div>`;
  }
  if (p.status === "needs_human") {
    out += `<div class="alert warn"><strong>Couldn't verify the right agency.</strong>No cited source backed a specific agency, so your agent is not guessing. A neighbor needs to check this one.</div>`;
  }

  if (c) {
    const chUrl = safeUrl(c.channel_url);
    out += `
      <h3>Routing card</h3>
      ${c.summary ? `<p style="margin:0 0 10px">${esc(c.summary)}</p>` : ""}
      <dl class="kv">
        <dt>Who fixes it</dt><dd>${c.agency ? esc(c.agency) : '<span class="muted">Not verified</span>'}</dd>
        <dt>How to report</dt><dd>${c.channel ? esc(c.channel) : '<span class="muted">Not verified</span>'}${chUrl ? `<br><a href="${esc(chUrl)}" target="_blank" rel="noopener">${esc(host(chUrl))}</a>` : ""}</dd>
        <dt>Already known?</dt><dd>${esc({ yes: "Yes, already reported", likely: "Likely already reported", unknown: "No existing report found" }[c.already_reported] || c.already_reported)}</dd>
      </dl>
      <h3>Sources</h3>
      ${c.sources?.length ? `<ol class="sources">${c.sources.map((s) => {
        const u = safeUrl(s.url);
        return `<li>${u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(s.title || host(u))}</a> <span class="src-host">${esc(host(u))}</span>` : esc(s.title)}</li>`;
      }).join("")}</ol>` : '<p class="muted" style="margin:0">No sources. No source, no claim.</p>'}`;

    if (c.draft_body) {
      out += `
        <h3>Report</h3>
        <details class="draft" data-k="draft">
          <summary>${p.draft_id ? "Gmail draft ready" : "Draft"}: ${esc(c.draft_subject)}</summary>
          <pre>${esc(c.draft_body)}</pre>
        </details>
        <p class="hint" style="margin-top:6px">Draft only. Your agent never sends email or files reports. You review it and click send.</p>`;
    }
  }

  const done = [];
  if ((p.trace || []).some((t) => t.step === "sheet" && t.ok)) done.push("Added to the community sheet");
  if (p.slack_ts) done.push("Posted to the neighborhood Slack");
  if (done.length) out += `<div class="row" style="margin-top:8px">${done.map((d) => `<span class="chip">&#10003; ${esc(d)}</span>`).join("")}</div>`;

  if (p.updates?.length) {
    out += `<h3>Updates</h3><ul class="updates">${p.updates.slice().reverse().map((u) => `<li>${esc(u)}</li>`).join("")}</ul>`;
  }

  out += `<h3>Agent trace</h3>${renderTrace(p.trace)}`;

  if (DEMO_CONTROLS && ["reported", "routed"].includes(p.status)) {
    out += `<h3>Demo</h3><button class="btn" data-act="simulate-reply">Simulate agency reply</button>`;
  }
  return out;
}

panel.addEventListener("click", async (e) => {
  const li = e.target.closest("li[data-id]");
  if (li) return select(li.dataset.id);
  const act = e.target.closest("[data-act]")?.dataset.act;
  if (act === "back") return select(null);
  if (act === "cancel") return cancelDraft();
  if (act === "simulate-reply") {
    e.target.disabled = true;
    try {
      await api("/webhooks/composio", { method: "POST", body: JSON.stringify({ simulate: true, pin_id: state.selected }) });
      await loadPins();
    } catch (err) { alert(`Simulated reply failed: ${err.message}`); e.target.disabled = false; }
  }
});

function select(id) {
  state.selected = id;
  state.lastRenderKey = "";
  syncMarkers();
  render();
  const p = id && state.byId.get(id);
  if (p) map.panTo([p.lat, p.lng], { animate: true });
  panel.scrollTop = 0;
}

// ---------- new pin ----------
function startDraft(latlng) {
  cancelDraft(false);
  const marker = L.marker(latlng, {
    icon: L.divIcon({ className: "pin-icon", html: '<div class="pin-dot draft"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }),
  }).addTo(map);
  state.draft = { lat: latlng.lat, lng: latlng.lng, marker };
  let name = "";
  try { name = localStorage.getItem("aa_name") || ""; } catch {}
  panel.innerHTML = `
    <h2>Drop a pin</h2>
    <p class="hint">${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}</p>
    <form class="newpin" id="newpin">
      <label for="note">What's going on?</label>
      <textarea id="note" name="note" required maxlength="500" placeholder="Streetlight out at Valencia and 18th, very dark at night."></textarea>
      <label for="reporter">Your display name</label>
      <input id="reporter" name="reporter" maxlength="40" placeholder="neighbor" value="${esc(name)}">
      <p class="hint" style="margin-top:8px">We store only the note, the location, and a display name. Personal info is stripped before anything is shared.</p>
      <div class="form-actions">
        <button class="btn primary" type="submit">Send to my agent</button>
        <button class="btn" type="button" data-act="cancel">Cancel</button>
      </div>
    </form>`;
  panel.querySelector("#note").focus();
  panel.querySelector("#newpin").addEventListener("submit", submitDraft);
}

function cancelDraft(rerender = true) {
  if (state.draft) { map.removeLayer(state.draft.marker); state.draft = null; }
  if (rerender) { state.lastRenderKey = ""; render(); }
}

async function submitDraft(e) {
  e.preventDefault();
  const f = e.target;
  const note = f.note.value.trim();
  if (!note) return;
  const reporter = f.reporter.value.trim() || "neighbor";
  try { localStorage.setItem("aa_name", reporter); } catch {}
  const body = { lat: state.draft.lat, lng: state.draft.lng, note, reporter };
  f.querySelector("button[type=submit]").disabled = true;
  let pin;
  try {
    pin = await api("/pins", { method: "POST", body: JSON.stringify(body), timeout: 10000 });
  } catch {
    // offline: keep the pin locally so the map still accepts it
    const now = new Date().toISOString();
    pin = { id: `local-${Date.now().toString(36)}`, created_at: now, updated_at: now, ...body, status: "routing", card: null, trace: [], updates: ["Saved locally. The agent will route it when the backend is back."], _local: true };
  }
  cancelDraft(false);
  setPins([pin, ...state.pins.filter((p) => p.id !== pin.id)]);
  select(pin.id);
}

// ---------- morning brief ----------
const dlg = document.getElementById("briefDlg");
dlg.addEventListener("click", (e) => { if (e.target === dlg || e.target.closest("[data-close]")) dlg.close(); });

function mdToHtml(md) {
  // tiny, safe markdown: headings, bullets, bold, links, paragraphs
  const inline = (s) => esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(?!\s)(.+?)\*/g, "<strong>$1</strong>")
    .replace(/&lt;(https?:\/\/[^|&]+)\|([^&]+)&gt;/g, (_, u, t) => `<a href="${u}" target="_blank" rel="noopener">${t}</a>`)
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  const out = [];
  let inList = false;
  for (const raw of String(md || "").split(/\r?\n/)) {
    const line = raw.trimEnd();
    const li = line.match(/^\s*[-*•]\s+(.*)/);
    if (li) { if (!inList) { out.push("<ul>"); inList = true; } out.push(`<li>${inline(li[1])}</li>`); continue; }
    if (inList) { out.push("</ul>"); inList = false; }
    const h = line.match(/^(#{1,3})\s+(.*)/);
    if (h) out.push(`<h${h[1].length + 1}>${inline(h[2])}</h${h[1].length + 1}>`);
    else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  if (inList) out.push("</ul>");
  return out.join("");
}

document.getElementById("briefBtn").addEventListener("click", async () => {
  const body = document.getElementById("briefBody");
  const status = document.getElementById("briefStatus");
  body.textContent = "Loading...";
  status.textContent = "";
  document.getElementById("briefSend").disabled = false;
  dlg.showModal();
  try {
    const b = await api("/brief", { timeout: 10000 });
    body.innerHTML = mdToHtml(b.markdown || "");
  } catch (err) {
    body.innerHTML = `<p class="muted">Couldn't load the brief (${esc(err.message)}).</p>`;
  }
});

document.getElementById("briefSend").addEventListener("click", async (e) => {
  const status = document.getElementById("briefStatus");
  e.target.disabled = true;
  status.textContent = "Sending...";
  try {
    const r = await api("/brief/send", { method: "POST", timeout: 20000 });
    status.textContent = r?.ok === false ? "Slack post failed. Check the server log." : "Sent to Slack.";
  } catch (err) {
    status.textContent = `Failed: ${err.message}`;
    e.target.disabled = false;
  }
});

// ---------- boot ----------
if (params.get("pin")) state.selected = params.get("pin");
loadPins();
setInterval(() => { if (!document.hidden) loadPins(); }, POLL_MS);
