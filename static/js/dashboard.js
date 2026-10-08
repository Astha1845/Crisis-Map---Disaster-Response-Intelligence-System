const sel = {
  year: document.getElementById("f-year"),
  state: document.getElementById("f-state"),
  type: document.getElementById("f-type"),
};
const backBtn = document.getElementById("back-btn");
const grainButtons = document.querySelectorAll("#grain-seg button");
let grain = "year";
let optionsLoaded = false;

function setGrain(g) {
  grain = g;
  grainButtons.forEach((b) => b.classList.toggle("on", b.dataset.grain === g));
}

async function load() {
  const params = new URLSearchParams({ grain });
  if (sel.year.value) params.set("year", sel.year.value);
  if (sel.state.value) params.set("state", sel.state.value);
  if (sel.type.value) params.set("disaster_type", sel.type.value);
  const data = await api("/api/dashboard?" + params.toString());

  if (!optionsLoaded) {
    const f = data.filters;
    f.years.forEach((y) => sel.year.add(new Option(y, y)));
    f.states.forEach((s) => sel.state.add(new Option(s, s)));
    f.disaster_types.forEach((t) => sel.type.add(new Option(t, t)));
    optionsLoaded = true;
  }
  backBtn.hidden = !sel.year.value;
  renderKpis(data.kpis);
  renderTypes(data.by_type);
  renderPriority(data.priority_distribution);
  renderTrend(data.trend);
  renderResources(data.resources_by_type);
  renderInsights(data.insights);
}

function renderKpis(k) {
  document.getElementById("k-total").textContent = fmt(k.total_disasters);
  document.getElementById("k-pop").textContent = compact(k.affected_population);
  document.getElementById("k-crit").textContent = fmt(k.critical_areas);
  document.getElementById("k-res").textContent = compact(k.resources_required);
  document.getElementById("k-res-n").textContent = k.resources_detail;
  const share = k.total_disasters ? ((k.critical_areas / k.total_disasters) * 100).toFixed(1) : "0.0";
  document.getElementById("k-total-n").textContent = share + "% rated critical";
}

function renderTypes(rows) {
  drawChart("c-type", {
    type: "bar",
    data: {
      labels: rows.map((r) => r.label),
      datasets: [{ data: rows.map((r) => r.value), backgroundColor: COLORS.blue, hoverBackgroundColor: COLORS.teal,
                   borderRadius: 10, maxBarThickness: 46 }],
    },
    options: { plugins: { legend: { display: false } }, scales: { x: noGrid, y: { ...axisStyle, beginAtZero: true } } },
  });
}

// Draws the incident total in the middle of the donut.
const donutCenter = {
  id: "donutCenter",
  afterDraw(chart) {
    const meta = chart.getDatasetMeta(0);
    if (!meta.data.length) return;
    const { x, y } = meta.data[0];
    const total = chart.data.datasets[0].data.reduce((a, b) => a + b, 0);
    const ctx = chart.ctx;
    ctx.save();
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = COLORS.slate; ctx.font = '700 24px "Inter","Segoe UI",system-ui,sans-serif';
    ctx.fillText(fmt(total), x, y - 8);
    ctx.fillStyle = COLORS.muted; ctx.font = '500 12px "Inter","Segoe UI",system-ui,sans-serif';
    ctx.fillText("incidents", x, y + 14);
    ctx.restore();
  },
};

function renderPriority(rows) {
  const total = rows.reduce((a, r) => a + r.value, 0);
  const pct = (v) => (total ? ((v / total) * 100).toFixed(1) : "0.0");
  drawChart("c-priority", {
    type: "doughnut",
    data: {
      labels: rows.map((r) => r.label),
      datasets: [{
        data: rows.map((r) => r.value), backgroundColor: rows.map((r) => PRIORITY_COLORS[r.label]),
        borderColor: "#ffffff", borderWidth: 3, hoverOffset: 6,
      }],
    },
    options: {
      cutout: "66%",
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            padding: 14,
            generateLabels: (chart) => chart.data.labels.map((label, i) => ({
              text: `${label} · ${pct(chart.data.datasets[0].data[i])}%`,
              fillStyle: chart.data.datasets[0].backgroundColor[i], strokeStyle: chart.data.datasets[0].backgroundColor[i],
              pointStyle: "circle", index: i, hidden: !chart.getDataVisibility(i),
            })),
          },
          onClick: (e, item, legend) => { legend.chart.toggleDataVisibility(item.index); legend.chart.update(); },
        },
        tooltip: { callbacks: { label: (c) => ` ${c.label}: ${fmt(c.parsed)} incidents (${pct(c.parsed)}%)` } },
      },
    },
    plugins: [donutCenter],
  });
}

function renderTrend(rows) {
  document.getElementById("trend-sub").textContent =
    grain === "year" && !sel.year.value ? "Click a year to drill down into its months"
      : sel.year.value ? "Monthly view for " + sel.year.value : "Rolled up by " + grain;
  drawChart("c-trend", {
    type: "line",
    data: {
      labels: rows.map((r) => r.label),
      datasets: [{
        label: "People affected", data: rows.map((r) => r.population), borderColor: COLORS.teal,
        backgroundColor: COLORS.tealSoft, fill: true, tension: 0.35, pointRadius: rows.length > 40 ? 0 : 4,
        pointHoverRadius: 7, pointBackgroundColor: "#fff", pointBorderColor: COLORS.teal, pointBorderWidth: 2,
      }],
    },
    options: {
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => " " + fmt(c.parsed.y) + " people" } } },
      scales: { x: { ...noGrid, ticks: { maxTicksLimit: 12 } }, y: { ...axisStyle, beginAtZero: true, ticks: { callback: (v) => compact(v) } } },
      onClick: (_evt, items) => {
        if (items.length && grain === "year" && !sel.year.value) {
          sel.year.value = rows[items[0].index].label;  // drill-down: year -> its months
          setGrain("month");
          load();
        }
      },
      onHover: (evt, items) => { evt.native.target.style.cursor = items.length && grain === "year" ? "pointer" : "default"; },
    },
  });
}

function renderResources(rows) {
  drawChart("c-res", {
    data: {
      labels: rows.map((r) => r.label),
      datasets: [
        { type: "bar", label: "Food (units)", data: rows.map((r) => r.food), backgroundColor: COLORS.blue, borderRadius: 6, yAxisID: "y" },
        { type: "bar", label: "Shelter (units)", data: rows.map((r) => r.shelter), backgroundColor: COLORS.teal, borderRadius: 6, yAxisID: "y" },
        { type: "bar", label: "Water (kilolitres)", data: rows.map((r) => r.water_kl), backgroundColor: "#b9d4ee", borderRadius: 6, yAxisID: "y" },
        { type: "line", label: "Medical kits", data: rows.map((r) => r.kits), borderColor: COLORS.coral, backgroundColor: COLORS.coral,
          pointRadius: 5, tension: 0.3, yAxisID: "y1" },
      ],
    },
    options: {
      plugins: { legend: { position: "bottom" } },
      scales: {
        x: noGrid,
        y: { ...axisStyle, beginAtZero: true, title: { display: true, text: "Units / kL" } },
        y1: { position: "right", beginAtZero: true, grid: { display: false }, border: { display: false }, title: { display: true, text: "Kits" } },
      },
    },
  });
}

function renderInsights(items) {
  document.getElementById("insights").innerHTML = items
    .map((i) => `<div class="insight"><span class="dot"></span><div><b>${esc(i.title)}</b><span>${esc(i.text)}</span></div></div>`)
    .join("");
}

// ----- filter wiring (slice / dice) and time hierarchy (roll-up / drill-down)
sel.year.addEventListener("change", () => { setGrain(sel.year.value ? "month" : "year"); load(); });
sel.state.addEventListener("change", load);
sel.type.addEventListener("change", load);
grainButtons.forEach((b) => b.addEventListener("click", () => { setGrain(b.dataset.grain); load(); }));
backBtn.addEventListener("click", () => { sel.year.value = ""; setGrain("year"); load(); });  // roll-up
document.getElementById("f-reset").addEventListener("click", () => {
  sel.year.value = ""; sel.state.value = ""; sel.type.value = ""; setGrain("year"); load();
});

load().catch((e) => { document.getElementById("insights").innerHTML = `<div class="error">${esc(e.message)}</div>`; });
