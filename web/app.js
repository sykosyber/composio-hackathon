/* Altruistic Agent map. No build step, no framework, polls GET /pins every 3 seconds. */

const COLORS = {
  routing: "#98a2b8", routed: "#4ea1ff", reported: "#4ea1ff",
  acknowledged: "#3ddc97", resolved: "#2f9e75", needs_human: "#ffb347",
};

const map = L.map("map").setView([37.7599, -122.4208], 14);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

const markers = new Map();
let pending = null;
let pendingMarker = null;
let selectedId = null;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const title = (s) => String(s || "").replace(/_/g, " ");

function dot(status) {
  const color = COLORS[status] || "#98a2b8";
  return L.divIcon({
    className: "",
    html: `<div style="width:15px;height:15px;border-radius:50%;background:${color};
           border:2px solid #0f1117;box-shadow:0 0 0 1px ${color}"></div>`,
    iconSize: [15, 15], iconAnchor: [8, 8],
  });
}

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(`${path} returned ${res.status}`);
  return res.json();
}

function row(label, value) {
  return `<div class="row"><span>${label}</span><span>${value}</span></div>`;
}

/* ---------- pins ---------- */

async function refresh() {
  let pins;
  try {
    pins = await api("/pins");
  } catch (err) {
    $("health").textContent = "offline, map still works";
    return;
  }
  const seen = new Set();
  for (const pin of pins) {
    seen.add(pin.id);
    let marker = markers.get(pin.id);
    if (!marker) {
      marker = L.marker([pin.lat, pin.lng], { icon: dot(pin.status) }).addTo(map);
      marker.on("click", () => showPin(pin.id));
      markers.set(pin.id, marker);
    }
    marker.setIcon(dot(pin.status));
    marker.bindTooltip(`${title(pin.category)} - ${title(pin.status)}`, { direction: "top" });
    marker._pin = pin;
  }
  for (const [id, marker] of markers) {
    if (!seen.has(id)) { map.removeLayer(marker); markers.delete(id); }
  }
  if (selectedId && markers.has(selectedId)) renderPin(markers.get(selectedId)._pin);
}

function showPin(id) {
  selectedId = id;
  const marker = markers.get(id);
  if (marker) renderPin(marker._pin);
}

function renderPin(pin) {
  const card = $("detail");
  card.classList.remove("hidden");
  const parts = [];
  parts.push(`<h2>${esc(title(pin.category))}
    <span class="badge b-${esc(pin.status)}">${esc(title(pin.status))}</span></h2>`);

  if (pin.emergency) {
    parts.push(`<p class="alert">Call 911 now.</p><p class="hint">${esc(pin.summary)}</p>`);
  } else if (pin.status === "routing") {
    parts.push(`<p class="hint">Routing in progress. Parallel is looking up the responsible agency.</p>`);
  }

  parts.push(`<p>${esc(pin.summary || pin.note)}</p>`);
  parts.push(row("Note", esc(pin.note)));
  parts.push(row("Where", esc(pin.address_hint || `${pin.lat.toFixed(4)}, ${pin.lng.toFixed(4)}`)));
  parts.push(row("Severity", esc(pin.severity)));
  parts.push(row("Reported by", esc(pin.reporter)));

  if (pin.status === "needs_human") {
    parts.push(`<p class="warn">${esc(pin.needs_human_reason || "Couldn't verify the right agency")}.
      No source, no claim, so the agent did not guess.</p>`);
  } else if (!pin.emergency && pin.agency) {
    parts.push(row("Agency", esc(pin.agency)));
    parts.push(row("Channel", esc(pin.channel)));
    if (pin.channel_url) {
      parts.push(row("Report at",
        `<a href="${esc(pin.channel_url)}" target="_blank" rel="noopener">${esc(pin.channel_url)}</a>`));
    }
    parts.push(row("Already reported", esc(pin.already_reported)));
  }

  if (pin.sources && pin.sources.length) {
    parts.push(`<h3>Sources</h3><ul class="sources">` + pin.sources.map((s) =>
      `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a></li>`
    ).join("") + `</ul>`);
  }

  if (pin.draft_subject) {
    const made = pin.draft_id ? "Draft created in Gmail: " + esc(pin.draft_id)
                              : "Draft prepared locally.";
    parts.push(`<h3>Gmail draft, never sent</h3>
      <p class="hint"><strong>${esc(pin.draft_subject)}</strong></p>
      <p class="hint">${esc(pin.draft_body).slice(0, 400)}</p>
      <p class="hint small">${made} A human clicks send.</p>`);
  }

  if (pin.updates && pin.updates.length) {
    parts.push(`<h3>Updates</h3><ul class="updates">` +
      pin.updates.map((u) => `<li>${esc(u.text)}</li>`).join("") + `</ul>`);
  }

  if (pin.trace && pin.trace.length) {
    parts.push(`<h3>Agent trace</h3><table class="trace">` + pin.trace.map((t) =>
      `<tr><td class="ok ${t.ok ? "dot-ok" : "dot-bad"}">${t.ok ? "ok" : "x"}</td>
        <td>${esc(t.step)}</td><td class="tool">${esc(t.tool)}</td>
        <td class="ms">${t.ms} ms</td></tr>`).join("") + `</table>`);
  }

  parts.push(`<button class="ghost" id="sim-btn">Simulate agency reply</button>`);
  card.innerHTML = parts.join("");
  const btn = $("sim-btn");
  if (btn) btn.addEventListener("click", () => simulateReply(pin.id));
}

async function simulateReply(id) {
  try {
    await api(`/demo/simulate_reply/${id}`, { method: "POST" });
  } catch (err) {
    console.error(err);
  }
  refresh();
}

/* ---------- drop a pin ---------- */

map.on("click", (ev) => {
  pending = ev.latlng;
  if (pendingMarker) map.removeLayer(pendingMarker);
  pendingMarker = L.marker(pending, { opacity: 0.6 }).addTo(map);
  $("coords").textContent = `Selected ${pending.lat.toFixed(5)}, ${pending.lng.toFixed(5)}`;
  $("submit").disabled = false;
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
    $("coords").textContent = "Click anywhere on the map to choose a location.";
    await refresh();
    showPin(pin.id);
  } catch (err) {
    $("coords").textContent = "Could not save the pin, try again.";
    $("submit").disabled = false;
  }
});

/* ---------- brief and demo controls ---------- */

$("brief-btn").addEventListener("click", async () => {
  const data = await api("/brief");
  const card = $("brief");
  card.classList.remove("hidden");
  card.innerHTML = `<h2>Morning brief</h2><pre class="brief">${esc(data.markdown)}</pre>`;
});

$("send-brief-btn").addEventListener("click", async () => {
  const res = await api("/brief/send", { method: "POST" });
  const card = $("brief");
  card.classList.remove("hidden");
  const status = res.sent ? "Posted to the neighborhood Slack channel."
                          : "Slack not configured: " + esc(res.detail);
  card.innerHTML = `<h2>Morning brief</h2><p class="hint">${status}</p>
    <pre class="brief">${esc(res.markdown)}</pre>`;
});

$("reset-btn").addEventListener("click", async () => {
  await api("/demo/reset", { method: "POST" });
  selectedId = null;
  $("detail").classList.add("hidden");
  for (const [id, marker] of markers) { map.removeLayer(marker); markers.delete(id); }
  refresh();
});

async function health() {
  try {
    const h = await api("/health");
    $("health").textContent = `${h.pins} pins · composio ${h.composio ? "on" : "off"}` +
      ` · parallel ${h.parallel ? "on" : "off"} · llm ${h.llm ? "on" : "off"}` +
      (h.demo_mode ? " · demo cache" : "");
  } catch (err) {
    $("health").textContent = "offline, map still works";
  }
}

refresh();
health();
setInterval(refresh, 3000);
