/* Dashboard logic: fetch each analytics endpoint and render it. */

const API = "";
const charts = {};          // canvasId -> Chart instance (so we can destroy on refresh)
const PALETTE = [
  "#5b8cff", "#36d1a0", "#ffb454", "#ff6b8b", "#a78bfa",
  "#22d3ee", "#f472b6", "#84cc16", "#fb923c", "#60a5fa",
  "#e879f9", "#2dd4bf",
];

Chart.defaults.color = "#8a96b0";
Chart.defaults.borderColor = "rgba(37,48,74,0.6)";
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;

const $ = (id) => document.getElementById(id);
const fmtMoney = (v) => "$" + Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
const fmtNum = (v) => Number(v || 0).toLocaleString();

function currentParams(extra = {}) {
  const p = new URLSearchParams();
  p.set("days", $("days").value);
  for (const f of ["country", "category", "device", "channel"]) {
    const v = $(f).value;
    if (v) p.set(f, v);
  }
  for (const [k, v] of Object.entries(extra)) p.set(k, v);
  return p.toString();
}

async function api(path, extra) {
  const res = await fetch(`${API}/api/analytics/${path}?${currentParams(extra)}`);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

function draw(canvasId, config) {
  if (charts[canvasId]) charts[canvasId].destroy();
  const ctx = $(canvasId);
  if (!ctx) return;
  config.options = Object.assign(
    { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { boxWidth: 12 } } } },
    config.options || {}
  );
  charts[canvasId] = new Chart(ctx, config);
}

/* ----------------------------- renderers ------------------------------ */

async function renderKpis() {
  const k = await api("kpis");
  const ca = await api("cart-abandonment");
  const cards = [
    { label: "Revenue", value: fmtMoney(k.revenue), accent: true },
    { label: "Orders", value: fmtNum(k.orders) },
    { label: "Unique Users", value: fmtNum(k.users) },
    { label: "Conversion", value: (k.conversion_rate ?? 0) + "%" },
    { label: "Avg Order Value", value: fmtMoney(k.avg_order_value) },
    { label: "Cart Abandon", value: (ca.abandonment_rate ?? 0) + "%" },
  ];
  $("kpis").innerHTML = cards
    .map((c) => `<div class="kpi"><div class="label">${c.label}</div><div class="value ${c.accent ? "accent" : ""}">${c.value}</div></div>`)
    .join("");
}

async function renderRevenueOverTime() {
  const rows = await api("revenue-over-time");
  draw("revenue-over-time", {
    type: "line",
    data: {
      labels: rows.map((r) => r.date),
      datasets: [
        { label: "Revenue", data: rows.map((r) => r.revenue), borderColor: PALETTE[0], backgroundColor: "rgba(91,140,255,0.15)", fill: true, tension: 0.3, yAxisID: "y", pointRadius: 0 },
        { label: "Orders", data: rows.map((r) => r.orders), borderColor: PALETTE[1], tension: 0.3, yAxisID: "y1", pointRadius: 0 },
      ],
    },
    options: { scales: { y: { position: "left" }, y1: { position: "right", grid: { drawOnChartArea: false } } }, interaction: { mode: "index", intersect: false } },
  });
}

async function renderFunnel() {
  const rows = await api("conversion-funnel");
  draw("conversion-funnel", {
    type: "bar",
    data: {
      labels: rows.map((r) => r.stage.replace(/_/g, " ")),
      datasets: [{ label: "Sessions", data: rows.map((r) => r.sessions), backgroundColor: PALETTE.slice(0, rows.length) }],
    },
    options: { indexAxis: "y", plugins: { legend: { display: false } } },
  });
}

async function renderRevenueByCategory() {
  const rows = await api("revenue-by-category");
  draw("revenue-by-category", {
    type: "doughnut",
    data: { labels: rows.map((r) => r.category), datasets: [{ data: rows.map((r) => r.revenue), backgroundColor: PALETTE }] },
    options: { plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 10 } } } } },
  });
}

async function renderCategoryTrend() {
  const rows = await api("category-revenue-trend");
  const dates = [...new Set(rows.map((r) => r.date))].sort();
  const cats = [...new Set(rows.map((r) => r.category))];
  const idx = new Map(dates.map((d, i) => [d, i]));
  const datasets = cats.map((cat, i) => {
    const arr = new Array(dates.length).fill(0);
    rows.filter((r) => r.category === cat).forEach((r) => (arr[idx.get(r.date)] = r.revenue));
    return { label: cat, data: arr, borderColor: PALETTE[i % PALETTE.length], backgroundColor: PALETTE[i % PALETTE.length] + "55", fill: true, tension: 0.3, pointRadius: 0 };
  });
  draw("category-revenue-trend", {
    type: "line",
    data: { labels: dates, datasets },
    options: { scales: { y: { stacked: true } }, plugins: { legend: { display: false } } },
  });
}

async function renderHBar(path, canvasId, labelKey, valueKey, color) {
  const rows = await api(path);
  draw(canvasId, {
    type: "bar",
    data: {
      labels: rows.map((r) => String(r[labelKey]).slice(0, 22)),
      datasets: [{ label: "Revenue", data: rows.map((r) => r[valueKey]), backgroundColor: color }],
    },
    options: { indexAxis: "y", plugins: { legend: { display: false } } },
  });
}

async function renderBar(path, canvasId, labelKey, valueKey, color) {
  const rows = await api(path);
  draw(canvasId, {
    type: "bar",
    data: { labels: rows.map((r) => r[labelKey]), datasets: [{ label: valueKey, data: rows.map((r) => r[valueKey]), backgroundColor: color }] },
    options: { plugins: { legend: { display: false } } },
  });
}

async function renderPie(path, canvasId, labelKey, valueKey) {
  const rows = await api(path);
  draw(canvasId, {
    type: "pie",
    data: { labels: rows.map((r) => r[labelKey]), datasets: [{ data: rows.map((r) => r[valueKey]), backgroundColor: PALETTE }] },
    options: { plugins: { legend: { position: "right", labels: { boxWidth: 10 } } } },
  });
}

async function renderNewVsReturning() {
  const rows = await api("new-vs-returning");
  draw("new-vs-returning", {
    type: "doughnut",
    data: { labels: rows.map((r) => r.segment), datasets: [{ data: rows.map((r) => r.users), backgroundColor: [PALETTE[2], PALETTE[0]] }] },
  });
}

async function renderAov() {
  const rows = await api("aov-over-time");
  draw("aov-over-time", {
    type: "line",
    data: { labels: rows.map((r) => r.date), datasets: [{ label: "AOV", data: rows.map((r) => r.aov), borderColor: PALETTE[2], backgroundColor: "rgba(255,180,84,0.15)", fill: true, tension: 0.3, pointRadius: 0 }] },
    options: { plugins: { legend: { display: false } } },
  });
}

async function renderHeatmap() {
  const rows = await api("traffic-heatmap");
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const max = Math.max(1, ...rows.map((r) => r.events));
  const grid = {};
  rows.forEach((r) => (grid[`${r.dow}-${r.hour}`] = r.events));
  let html = `<div class="hm-corner"></div>`;
  for (let h = 0; h < 24; h++) html += `<div class="hm-label" style="justify-content:center">${h % 3 === 0 ? h : ""}</div>`;
  for (let d = 1; d <= 7; d++) {
    html += `<div class="hm-label">${days[d - 1]}</div>`;
    for (let h = 0; h < 24; h++) {
      const v = grid[`${d}-${h}`] || 0;
      const a = (v / max).toFixed(2);
      html += `<div class="hm-cell" title="${days[d - 1]} ${h}:00 — ${fmtNum(v)} events" style="background:rgba(91,140,255,${0.08 + a * 0.92})"></div>`;
    }
  }
  $("traffic-heatmap").innerHTML = html;
}

async function renderSessionMetrics() {
  const m = await api("session-metrics");
  const rows = [
    ["Total sessions", fmtNum(m.total_sessions)],
    ["Avg events / session", m.avg_events_per_session],
    ["Avg session duration", (m.avg_session_seconds ?? 0) + "s"],
    ["Median session duration", (m.median_session_seconds ?? 0) + "s"],
  ];
  $("session-metrics").innerHTML = rows.map(([k, v]) => `<div class="row"><span class="k">${k}</span><span class="v">${v}</span></div>`).join("");
}

async function renderCohort() {
  const rows = await api("retention-cohort");
  const weeks = [...new Set(rows.map((r) => r.cohort_week))].sort();
  const maxWk = Math.max(0, ...rows.map((r) => r.week_number));
  const grid = {};
  rows.forEach((r) => (grid[`${r.cohort_week}-${r.week_number}`] = r.users));
  let head = `<th>Cohort</th><th>Size</th>`;
  for (let w = 0; w <= maxWk; w++) head += `<th>W${w}</th>`;
  let body = "";
  for (const week of weeks) {
    const size = grid[`${week}-0`] || 0;
    let tds = `<td>${week}</td><td>${fmtNum(size)}</td>`;
    for (let w = 0; w <= maxWk; w++) {
      const v = grid[`${week}-${w}`];
      if (v === undefined || size === 0) { tds += `<td></td>`; continue; }
      const pct = Math.round((v / size) * 100);
      tds += `<td class="cell" style="background:rgba(54,209,160,${0.15 + (pct / 100) * 0.85})">${pct}%</td>`;
    }
    body += `<tr>${tds}</tr>`;
  }
  $("retention-cohort").innerHTML = `<table class="cohort"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

async function renderRecent() {
  const rows = await api("recent-events", { limit: 25 });
  const cols = ["time", "event_type", "user_id", "product_id", "category", "brand", "revenue", "country", "device", "channel"];
  const head = cols.map((c) => `<th>${c.replace(/_/g, " ")}</th>`).join("");
  const body = rows
    .map((r) => `<tr>${cols.map((c) => `<td>${c === "event_type" ? `<span class="badge">${r[c]}</span>` : c === "revenue" ? (r[c] ? fmtMoney(r[c]) : "—") : r[c]}</td>`).join("")}</tr>`)
    .join("");
  $("recent-events").innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

/* ----------------------------- orchestration ------------------------------ */

async function populateFilters() {
  try {
    const meta = await (await fetch(`${API}/api/meta`)).json();
    const fill = (id, values) => {
      const sel = $(id);
      (values || []).sort().forEach((v) => {
        const o = document.createElement("option");
        o.value = v; o.textContent = v; sel.appendChild(o);
      });
    };
    fill("country", meta.countries);
    fill("category", meta.categories);
    fill("device", meta.devices);
    fill("channel", meta.channels);
  } catch (e) { /* meta is optional */ }
}

async function refreshAll() {
  $("status").textContent = "Loading…";
  const t0 = performance.now();
  const tasks = [
    renderKpis(), renderRevenueOverTime(), renderFunnel(), renderRevenueByCategory(),
    renderCategoryTrend(),
    renderHBar("top-products", "top-products", "product", "revenue", PALETTE[0]),
    renderHBar("top-brands", "top-brands", "brand", "revenue", PALETTE[4]),
    renderBar("sales-by-country", "sales-by-country", "country", "revenue", PALETTE[1]),
    renderPie("sales-by-device", "sales-by-device", "device", "sessions"),
    renderBar("sales-by-channel", "sales-by-channel", "channel", "revenue", PALETTE[3]),
    renderNewVsReturning(), renderAov(), renderHourly(), renderHeatmap(),
    renderSessionMetrics(), renderCohort(), renderRecent(),
  ];
  const results = await Promise.allSettled(tasks);
  const failed = results.filter((r) => r.status === "rejected");
  const ms = Math.round(performance.now() - t0);
  $("status").textContent = failed.length
    ? `Loaded with ${failed.length} error(s) in ${ms}ms — ${failed[0].reason}`
    : `All analytics loaded in ${ms}ms`;
}

async function renderHourly() {
  await renderBar("hourly-traffic", "hourly-traffic", "hour", "events", PALETTE[5]);
}

document.addEventListener("DOMContentLoaded", async () => {
  await populateFilters();
  await refreshAll();
  $("refresh").addEventListener("click", refreshAll);
  for (const id of ["days", "country", "category", "device", "channel"]) {
    $(id).addEventListener("change", refreshAll);
  }
});
