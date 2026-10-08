async function load() {
  const { clusters, patterns } = await api("/api/insights");
  renderClusters(clusters);
  renderRules(patterns);
}

function renderClusters(c) {
  // Graph 1: impact cluster distribution (actual K-Means group sizes)
  const total = c.summary.reduce((a, g) => a + g.count, 0);
  drawChart("c-dist", {
    type: "bar",
    data: {
      labels: c.summary.map((g) => g.label),
      datasets: [{ data: c.summary.map((g) => g.count), backgroundColor: c.summary.map((g) => GROUP_COLORS[g.label]),
                   borderRadius: 10, maxBarThickness: 64 }],
    },
    options: {
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (x) => ` ${fmt(x.parsed.y)} incidents (${((x.parsed.y / total) * 100).toFixed(1)}%)` } },
      },
      scales: { x: noGrid, y: { ...axisStyle, beginAtZero: true, ticks: { callback: (v) => fmt(v) } } },
    },
  });

  // Graph 2: population vs infrastructure damage, grouped by impact cluster
  drawChart("c-cluster", {
    type: "scatter",
    data: {
      datasets: c.labels.map((label) => ({
        label,
        data: c.scatter.filter((p) => p.group === label).map((p) => ({ x: p.x, y: p.y })),
        backgroundColor: GROUP_COLORS[label] + "cc", pointRadius: 4, pointHoverRadius: 6,
      })),
    },
    options: {
      plugins: { legend: { position: "bottom" },
                 tooltip: { callbacks: { label: (x) => ` ${fmt(x.parsed.x)} people · ₹${fmt(x.parsed.y)} lakh damage` } } },
      scales: {
        x: { ...axisStyle, title: { display: true, text: "Population Affected" }, ticks: { callback: (v) => compact(v) } },
        y: { ...axisStyle, title: { display: true, text: "Infrastructure Damage (₹ lakh)" }, ticks: { callback: (v) => compact(v) } },
      },
    },
  });

  document.getElementById("groups").innerHTML = c.summary.map((g) => `
    <div class="group-card">
      <h3><i style="width:10px;height:10px;border-radius:50%;background:${GROUP_COLORS[g.label]};display:inline-block"></i>${esc(g.label)}</h3>
      <div class="meta">${fmt(g.count)} incidents · ${g.share}% of all</div>
      <div class="group-stats">
        <span>Population <b>${fmt(g.avg_population)}</b></span>
        <span>Damage <b>₹${fmt(g.avg_damage_lakh)} L</b></span>
        <span>Houses <b>${fmt(g.avg_houses)}</b></span>
        <span>Casualties <b>${g.avg_casualties}</b></span>
        <span>Medical need <b>${fmt(g.avg_medical_need)}</b></span>
      </div>
    </div>`).join("");

  drawChart("c-states", {
    type: "bar",
    data: {
      labels: c.severe_states.map((s) => s.state),
      datasets: [{ data: c.severe_states.map((s) => s.pct), backgroundColor: COLORS.blue, hoverBackgroundColor: COLORS.teal,
                   borderRadius: 8, maxBarThickness: 40 }],
    },
    options: {
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => ` ${x.parsed.y}% of incidents` } } },
      scales: { x: noGrid, y: { ...axisStyle, beginAtZero: true, ticks: { callback: (v) => v + "%" } } },
    },
  });
}

// ---- Apriori presentation helpers (values themselves are untouched) ----
const FAMILY_ICON = {
  "Rainfall": "🌧", "Water Level": "🌊", "Population": "👥", "Houses Damaged": "🏚", "Casualties": "⚠️",
  "Medical Need": "🩺", "Damage Level": "🏗", "Disaster": "🌪", "Food Supply": "🍞", "Water Supply": "💧", "Priority": "🚨",
};
function parseItem(item) {
  const [family, level] = item.split(": ");
  return { family, level };
}
function itemText(item) {
  const { family, level } = parseItem(item);
  if (family === "Priority") return `${level} Emergency Priority`;
  if (family === "Disaster") return level;
  return `${level} ${family}`;
}
const itemIcon = (item) => FAMILY_ICON[parseItem(item).family] || "•";
function outcomeClass(item) {
  const { family, level } = parseItem(item);
  if (level === "Critical" || (level === "High" && family !== "Population")) return "hot";
  if (level === "Medium" || level === "Moderate") return "warm";
  return "";
}

function renderRules(p) {
  const rules = [...p.rules].sort((a, b) => b.lift * b.confidence - a.lift * a.confidence);
  const top = rules.slice(0, 5);
  document.getElementById("pattern-sub").textContent =
    `Association rules mined from ${fmt(p.n_transactions)} incidents with Apriori. Support is how often a pattern occurs, ` +
    `confidence is how often the outcome follows, and lift shows how much stronger the link is than chance.`;

  document.getElementById("top-rules").innerHTML = top.map((r, i) => `
    <div class="card ic hover">
      <div class="ic-rank">Insight ${i + 1}</div>
      <div class="ic-cond">
        ${r.if.map((it, k) => `${k ? '<span class="ic-plus">+</span>' : ""}<span class="ic-pill"><span>${itemIcon(it)}</span>${esc(itemText(it))}</span>`).join("")}
      </div>
      <div class="ic-down">↓</div>
      <div class="ic-out ${outcomeClass(r.then)}">${itemIcon(r.then)} ${esc(itemText(r.then))}</div>
      <div class="ic-metrics">
        <div><small>Support</small><b>${(r.support * 100).toFixed(1)}%</b></div>
        <div><small>Confidence</small><b>${(r.confidence * 100).toFixed(1)}%</b></div>
        <div><small>Lift</small><b>${r.lift.toFixed(2)}</b></div>
      </div>
    </div>`).join("");

  document.getElementById("table-sub").textContent =
    `${rules.length} patterns, strongest first. ★ marks the top ${top.length} shown above.`;
  document.getElementById("rules-body").innerHTML = rules.map((r, i) => `
    <tr>
      <td>${i < top.length ? '<span class="star">★</span>' : ""}${r.if.map((it) => `<span class="tag">${esc(itemText(it))}</span>`).join("")}</td>
      <td><span class="tag out ${outcomeClass(r.then)}">${esc(itemText(r.then))}</span></td>
      <td class="num">${(r.support * 100).toFixed(1)}%</td>
      <td class="num">${(r.confidence * 100).toFixed(1)}%</td>
      <td class="num"><span class="lift">${r.lift.toFixed(2)}</span></td>
    </tr>`).join("");
}

load().catch((e) => { const b = document.getElementById("err"); b.textContent = e.message; b.hidden = false; });
