const form = document.getElementById("form");
const errBox = document.getElementById("err");
const resultBox = document.getElementById("result");
const TARGETS = {
  Food_Required_Units: { label: "Food required", unit: "units", tile: "blue" },
  Water_Required_Litres: { label: "Water required", unit: "litres", tile: "teal" },
  Medical_Kits_Required: { label: "Medical kits required", unit: "kits", tile: "teal" },
  Shelter_Required: { label: "Shelter required", unit: "shelter units", tile: "blue" },
};
let points = null;

async function init() {
  const meta = await api("/api/meta");
  fillSelect(document.getElementById("Damage_Level"), meta.damage_levels, "Moderate");
  ["Population_Affected", "Disaster_Duration_Days", "Medical_Need"].forEach((f) => {
    const n = meta.numeric[f];
    document.getElementById(f).value = Math.round(n.median * 100) / 100;
    document.getElementById("h-" + f).textContent = `Dataset range: ${fmt(n.min)} – ${fmt(n.max)}`;
  });
  points = await api("/api/resource-points");
  const seg = document.getElementById("target-seg");
  Object.entries(TARGETS).forEach(([key, t], i) => {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = t.label.replace(" required", ""); b.dataset.key = key;
    if (i === 0) b.className = "on";
    b.addEventListener("click", () => {
      seg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
      drawScatter(key);
    });
    seg.appendChild(b);
  });
  drawScatter("Food_Required_Units");
}

function drawScatter(key) {
  const p = points[key];
  const data = p.actual.map((a, i) => ({ x: a, y: p.predicted[i] }));
  const max = Math.max(...p.actual, ...p.predicted);
  const t = TARGETS[key];
  drawChart("c-avp", {
    type: "scatter",
    data: {
      datasets: [
        { label: "Test incidents", data, backgroundColor: "rgba(98,189,179,.55)", pointRadius: 4, pointHoverRadius: 6 },
        { type: "line", label: "Perfect prediction", data: [{ x: 0, y: 0 }, { x: max, y: max }], borderColor: COLORS.blue,
          borderDash: [6, 5], borderWidth: 2, pointRadius: 0, fill: false },
      ],
    },
    options: {
      plugins: { tooltip: { callbacks: { label: (c) => ` actual ${fmt(c.parsed.x)} · predicted ${fmt(c.parsed.y)}` } } },
      scales: {
        x: { ...axisStyle, beginAtZero: true, title: { display: true, text: "Actual " + t.unit }, ticks: { callback: (v) => compact(v) } },
        y: { ...axisStyle, beginAtZero: true, title: { display: true, text: "Predicted " + t.unit }, ticks: { callback: (v) => compact(v) } },
      },
    },
  });
}

function render(r) {
  resultBox.innerHTML = `<h2>Estimated resource demand</h2><p class="sub">Predicted by the trained regression model</p>
    <div class="res-tiles">` +
    Object.entries(TARGETS).map(([key, t]) => `
      <div class="tile ${t.tile}"><div class="t-label">${t.label.replace(" required", "")}</div>
      <div class="t-value">${fmt(r[key])}</div><div class="t-unit">${t.unit}</div></div>`).join("") + `</div>`;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errBox.hidden = true;
  const btn = document.getElementById("submit");
  const payload = Object.fromEntries(new FormData(form).entries());
  btn.disabled = true; btn.textContent = "Predicting…";
  try {
    render(await api("/api/predict/resources", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }));
  } catch (err) {
    errBox.textContent = err.message; errBox.hidden = false;
  } finally {
    btn.disabled = false; btn.textContent = "Predict resource demand";
  }
});

init().catch((e) => { errBox.textContent = e.message; errBox.hidden = false; });
