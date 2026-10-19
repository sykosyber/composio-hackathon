/* Map UI. No build step, no framework, polls GET /pins every 3 seconds. */

/* One status system for markers, badges, legend and stepper. Glyphs keep it color-blind safe. */
const STATUS = {
  routing:      { label: "Routing",          glyph: "…", color: "var(--s-routing)" },
  routed:       { label: "Routed",           glyph: "→", color: "var(--s-routed)" },
  reported:     { label: "Draft ready",      glyph: "✉", color: "var(--s-reported)" },
  acknowledged: { label: "Acknowledged",     glyph: "✓", color: "var(--s-acknowledged)" },
  resolved:     { label: "Resolved",         glyph: "★", color: "var(--s-resolved)" },
  needs_human:  { label: "Needs a human",    glyph: "?",      color: "var(--s-needs_human)" },
  emergency:    { label: "Emergency: 911",   glyph: "!",      color: "var(--s-emergency)" },
};
const LIFECYCLE = ["routing", "routed", "reported", "acknowledged", "resolved"];

const map = L.map("map").setView([37.7599, -122.4208], 15);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

const markers = new Map();
const lastStatus = new Map();
let pending = null;
let pendingMarker = null;
let selectedId = new URLSearchParams(location.search).get("pin");
let lastRendered = "";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const title = (s) => {
  const t = String(s || "").replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
};
const safeUrl = (u) => (/^https?:\/\//i.test(String(u || "")) ? String(u) : "");
const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };
const statusKey = (pin) => (pin.emergency ? "emergency" : pin.status);
const meta = (key) => STATUS[key] || STATUS.routing;

function markerHtml(key, extra = "") {
  const m = meta(key);
  return `<div class="pin-marker ${esc(key)} ${extra}" style="background:${m.color}">${m.glyph}</div>`;
}
function icon(key, extra) {
  return L.divIcon({ className: "", html: markerHtml(key, extra), iconSize: [30, 30], iconAnchor: [15, 15] });
}
function badge(key) {
  const m = meta(key);
  return `<span class="badge s-${esc(key)}" style="background:${m.color}">${m.glyph} ${esc(m.label)}</span>`;
}

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(`${path} returned ${res.status}`);
  return res.json();
}

/* ---------- legend ---------- */

$("legend").innerHTML = Object.keys(STATUS).map((k) =>
  `<div class="item">${markerHtml(k)}<span>${esc(STATUS[k].label)}</span></div>`).join("");

/* ---------- pins ---------- */

async function refresh() {
  let pins;
  try {
    pins = await api("/pins");
  } catch (err) {
    $("health").textContent = "Offline, the map still works";
    return;
  }
  const seen = new Set();
  for (const pin of pins) {
    seen.add(pin.id);
    const key = statusKey(pin);
    const changed = lastStatus.has(pin.id) && lastStatus.get(pin.id) !== key;
    lastStatus.set(pin.id, key);
    let marker = markers.get(pin.id);
    if (!marker) {
      marker = L.marker([pin.lat, pin.lng], { title: `${title(pin.category)}: ${meta(key).label}` }).addTo(map);
      marker.on("click", () => showPin(pin.id));
      markers.set(pin.id, marker);
      marker._key = null;
    }
    const sel = pin.id === selectedId ? "selected" : "";
    const sig = key + sel + (changed ? "flash" : "");
    if (marker._key !== sig) {
      marker.setIcon(icon(key, `${sel} ${changed ? "flash" : ""}`));
      marker._key = changed ? key + sel + "flash" : key + sel;
      if (changed) setTimeout(() => { marker._key = null; }, 4000);
    }
    marker.bindTooltip(`${esc(title(pin.category))}: ${esc(meta(key).label)}`, { direction: "top", offset: [0, -14] });
    marker._pin = pin;
  }
  for (const [id, marker] of markers) {
    if (!seen.has(id)) { map.removeLayer(marker); markers.delete(id); lastStatus.delete(id); }
  }
  renderList(pins);
  if (selectedId && markers.has(selectedId)) renderPin(markers.get(selectedId)._pin);
}

function renderList(pins) {
  const sorted = [...pins].sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
  $("pin-list").innerHTML = sorted.map((p) => `<li><button type="button" data-id="${esc(p.id)}">
      <span>${esc(title(p.category))}<span class="sub">${esc(p.address_hint || p.note)}</span></span>
      ${badge(statusKey(p))}</button></li>`).join("");
}
$("pin-list").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-id]");
  if (b) showPin(b.dataset.id, true);
});

function showPin(id, pan) {
  const prev = selectedId;
  selectedId = id;
  lastRendered = "";
  for (const mid of [prev, id]) { const m = markers.get(mid); if (m) m._key = null; }
  const marker = markers.get(id);
  if (marker) {
    if (pan) map.panTo(marker.getLatLng());
    renderPin(marker._pin);
    refresh();
  }
  const u = new URL(location.href); u.searchParams.set("pin", id); history.replaceState(null, "", u);
  $("detail").scrollIntoView({ block: "start", behavior: "smooth" });
}

function closePin() {
  const prev = markers.get(selectedId);
  selectedId = null; lastRendered = "";
  if (prev) prev._key = null;
  $("detail").classList.add("hidden");
  const u = new URL(location.href); u.searchParams.delete("pin"); history.replaceState(null, "", u);
  refresh();
}

function stepper(pin) {
  const idx = LIFECYCLE.indexOf(pin.status);
  return `<ol class="stepper" aria-label="Lifecycle">` + LIFECYCLE.map((s, i) => {
    const cls = idx < 0 ? "" : i < idx ? "done" : i === idx ? "current" : "";
    const aria = i === idx ? ' aria-current="step"' : "";
    return `<li class="${cls}"${aria}>${esc(STATUS[s].label)}</li>`;
  }).join("") + `</ol>`;
}

const SPONSORS = [
  ["typesafe-jev", "jev", "TypeSafe Jev"],
  ["parallel", "parallel", "Parallel"],
  ["llm", "llm", "Open model"],
  ["composio", "composio", "Composio"],
];
function chip(tool) {
  const t = String(tool || "");
  for (const [prefix, cls, label] of SPONSORS) if (t.startsWith(prefix)) return `<span class="chip ${cls}" title="${esc(t)}">${label}</span>`;
  return `<span class="chip local" title="${esc(t)}">Local</span>`;
}

function renderPin(pin) {
  const sig = JSON.stringify(pin);
  const card = $("detail");
  if (sig === lastRendered && !card.classList.contains("hidden")) return;
  const prevStatus = card.dataset.status;
  const prevId = card.dataset.id;
  lastRendered = sig;
  card.classList.remove("hidden");
  const key = statusKey(pin);
  const where = pin.address_hint || `${pin.lat.toFixed(4)}, ${pin.lng.toFixed(4)}`;
  const parts = [];

  parts.push(`<div class="detail-head"><div>
      <h2>${esc(title(pin.category))} ${badge(key)}</h2>
      <p class="where">${esc(where)}</p></div>
      <button type="button" class="close" id="close-btn" aria-label="Close pin">Close</button></div>`);

  if (pin.emergency) {
    parts.push(`<div class="callout emergency" role="alert">
      <p class="big">Call 911 now</p>
      <a class="call" href="tel:911">Call 911</a>
      <p>${esc(pin.summary)}</p>
      <p class="hint">The agent never routes a possible emergency. Nothing was posted or drafted.</p></div>`);
  } else {
    parts.push(stepper(pin));
  }

  parts.push(`<blockquote class="note-quote">${esc(pin.note)}
    <span class="by">Pinned by ${esc(pin.reporter || "a neighbor")} · ${esc(title(pin.severity))} severity</span></blockquote>`);

  if (pin.emergency) {
    // Nothing else to show for an emergency.
  } else if (pin.status === "routing") {
    parts.push(`<p class="hint">Working on it. Parallel is looking up the responsible agency with citations.</p>`);
  } else if (pin.status === "needs_human") {
    parts.push(`<div class="callout human">
      <p class="big">Couldn't verify the right agency</p>
      <p>${esc(pin.needs_human_reason || "No cited source named a responsible agency")}.</p>
      <p><strong>No source, no claim.</strong> The agent did not guess. A neighbor can pick this up.</p></div>`);
  } else if (pin.agency) {
    const url = safeUrl(pin.channel_url);
    const known = { yes: "Yes, already reported", no: "Not yet reported", unknown: "Not sure yet" }[pin.already_reported] || title(pin.already_reported);
    parts.push(`<div class="hero">
      <div class="k">Who fixes it</div>
      <div class="agency">${esc(pin.agency)}</div>
      <div class="k">How to report</div>
      <div class="channel">${esc(pin.channel || "Official form")}<br>
        ${url ? `<a class="btn-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Open official form <span class="host">(${esc(host(url))})</span></a>` : ""}</div>
      <div class="k">Already known?</div>
      <div><span class="known">${esc(known)}</span></div>
      <div class="trust">
        <span>✓ No source, no claim: ${pin.sources ? pin.sources.length : 0} cited</span>
        <span>✉ Draft only, a human clicks send</span>
      </div></div>`);
  }

  const sources = (pin.sources || []).filter((s) => safeUrl(s.url));
  if (sources.length) {
    parts.push(`<h3>Sources</h3><ul class="sources">` + sources.map((s) =>
      `<li><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title || host(s.url))}</a>
       <span class="host">${esc(host(s.url))}</span></li>`).join("") + `</ul>`);
  }

  if (pin.updates && pin.updates.length) {
    parts.push(`<h3>Agency updates</h3><ul class="updates">` + pin.updates.map((u) =>
      `<li><span class="from">${esc(u.from || "Update")}${u.jev ? ` · TypeSafe Jev: ${esc(u.jev)}` : ""}</span>${esc(u.text)}</li>`).join("") + `</ul>`);
  }

  if (pin.draft_subject) {
    const made = pin.draft_id ? "Saved as a Gmail draft." : "Prepared locally. Gmail is not connected in this demo.";
    parts.push(`<h3>Email to the agency</h3>
      <details class="draft"><summary>${esc(pin.draft_subject)}</summary>
      <pre>${esc(pin.draft_body)}</pre></details>
      <p class="hint small">${made} Never sent automatically: a human clicks send.</p>`);
  }

  if (pin.trace && pin.trace.length) {
    parts.push(`<h3>Agent trace</h3><ol class="trace">` + pin.trace.map((t) =>
      `<li class="${t.ok ? "ok" : "skip"}">
        <span class="step">${esc(title(t.step))} ${chip(t.tool)}
          <span class="state ${t.ok ? "ok" : "skip"}">${t.ok ? "✓ done" : "skipped"}</span></span>
        <span class="ms">${Number(t.ms) || 0} ms</span>
        ${t.detail ? `<span class="det">${esc(t.detail)}</span>` : ""}</li>`).join("") + `</ol>`);
  }

  if (!pin.emergency && !["acknowledged", "resolved"].includes(pin.status)) {
    parts.push(`<button type="button" class="ghost" id="sim-btn" style="margin-top:16px">Simulate agency reply</button>`);
  }
  card.innerHTML = parts.join("");
  card.dataset.status = key;
  card.dataset.id = pin.id;
  if (prevId === pin.id && prevStatus && prevStatus !== key) {
    card.classList.remove("flash"); void card.offsetWidth; card.classList.add("flash");
  }
  $("close-btn").addEventListener("click", closePin);
  const btn = $("sim-btn");
  if (btn) btn.addEventListener("click", () => simulateReply(pin.id));
}

async function simulateReply(id) {
  try {
    await api(`/demo/simulate_reply/${encodeURIComponent(id)}`, { method: "POST" });
  } catch (err) {
    console.error(err);
  }
  refresh();
}

/* ---------- drop a pin ---------- */

map.on("click", (ev) => {
  pending = ev.latlng;
  if (pendingMarker) map.removeLayer(pendingMarker);
  pendingMarker = L.marker(pending, { opacity: 0.7 }).addTo(map);
  $("coords").textContent = `Spot selected: ${pending.lat.toFixed(5)}, ${pending.lng.toFixed(5)}`;
  $("submit").disabled = false;
  $("note").focus({ preventScroll: true });
});

$("submit").addEventListener("click", async () => {
  const note = $("note").value.trim();
  if (!pending || !note) return;
  $("submit").disabled = true;
  try {
    const pin = await api("/pins", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lat: pending.lat, lng: pending.lng, note, reporter: $("reporter").value,
      }),
    });
    $("note").value = "";
    if (pendingMarker) { map.removeLayer(pendingMarker); pendingMarker = null; }
    pending = null;
    $("coords").textContent = "Click the map to choose a spot.";
    await refresh();
    showPin(pin.id);
  } catch (err) {
    $("coords").textContent = "Could not save the pin. Try again.";
    $("submit").disabled = false;
  }
});

/* ---------- morning brief ---------- */

/* Tiny renderer for the brief. Escapes first, then formats bold, links and bullets. */
function inline(s) {
  let h = esc(s);
  h = h.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_m, t, u) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${t}</a>`);
  h = h.replace(/&lt;(https?:\/\/[^|&\s]+)\|([^&]+?)&gt;/g, (_m, u, t) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${t}</a>`);
  h = h.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\*([^*]+)\*/g, "<strong>$1</strong>");
  return h;
}
function renderMarkdown(md) {
  const out = [];
  let list = false;
  const lines = String(md || "").split("\n");
  lines.forEach((line, i) => {
    const t = line.trim();
    if (t.startsWith("- ")) {
      if (!list) { out.push("<ul>"); list = true; }
      out.push(`<li>${inline(t.slice(2))}</li>`);
      return;
    }
    if (list) { out.push("</ul>"); list = false; }
    if (!t) return;
    const head = t.match(/^\*\*?([^*]+)\*\*?$/) || t.match(/^#+\s+(.*)$/);
    if (head && i > 0) out.push(`<h4>${inline(head[1])}</h4>`);
    else if (head) out.push(`<h2>${inline(head[1])}</h2>`);
    else out.push(`<p>${inline(t)}</p>`);
  });
  if (list) out.push("</ul>");
  return `<div class="brief-body">${out.join("")}</div>`;
}

function showBrief(markdown, status) {
  const card = $("brief");
  card.classList.remove("hidden");
  card.innerHTML = (status ? `<p class="hint">${esc(status)}</p>` : "") + renderMarkdown(markdown) +
    `<button type="button" class="ghost" id="brief-close" style="margin-top:12px">Close brief</button>`;
  $("brief-close").addEventListener("click", () => card.classList.add("hidden"));
  card.scrollIntoView({ block: "start", behavior: "smooth" });
}

$("brief-btn").addEventListener("click", async () => {
  const data = await api("/brief");
  showBrief(data.markdown);
});

$("send-brief-btn").addEventListener("click", async () => {
  const res = await api("/brief/send", { method: "POST" });
  showBrief(res.markdown, res.sent ? "Posted to the neighborhood Slack channel."
                                   : "Slack is not connected in this demo: " + res.detail);
});

$("reset-btn").addEventListener("click", async () => {
  await api("/demo/reset", { method: "POST" });
  closePin();
  for (const [id, marker] of markers) { map.removeLayer(marker); markers.delete(id); }
  lastStatus.clear();
  refresh();
});

async function health() {
  try {
    const h = await api("/health");
    const on = (b) => (b ? "on" : "off");
    $("health").textContent = `${h.pins} pins · Composio ${on(h.composio)} · Parallel ${on(h.parallel)}` +
      ` · model ${on(h.llm)}` + (h.demo_mode ? " · demo cache" : "");
  } catch (err) {
    $("health").textContent = "Offline, the map still works";
  }
}

refresh();
health();
setInterval(refresh, 3000);
if (new URLSearchParams(location.search).get("brief")) $("brief-btn").click();
