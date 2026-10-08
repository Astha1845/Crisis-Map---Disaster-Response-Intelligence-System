const form = document.getElementById("form");
const errBox = document.getElementById("err");
const resultBox = document.getElementById("result");
let PRIORITIES = ["Low", "Medium", "High", "Critical"];

async function init() {
  const meta = await api("/api/meta");
  PRIORITIES = meta.priorities;
  fillSelect(document.getElementById("Disaster_Type"), meta.disaster_types);
  fillSelect(document.getElementById("Damage_Level"), meta.damage_levels, "Moderate");
  fillSelect(document.getElementById("Shelter_Availability"), meta.shelter_levels, "High");
  ["Rainfall_mm", "Water_Level_m", "Population_Affected"].forEach((f) => {
    const n = meta.numeric[f];
    const input = document.getElementById(f);
    input.value = Math.round(n.median * 100) / 100;
    document.getElementById("h-" + f).textContent = `Dataset range: ${fmt(n.min)} – ${fmt(n.max)}`;
  });
}

function probRows(probs) {
  return PRIORITIES.map((p) => `
    <div class="prob-row"><span>${p}</span>
      <div class="bar"><i style="width:${probs[p]}%;background:${PRIORITY_COLORS[p]}"></i></div>
      <span>${probs[p].toFixed(1)}%</span></div>`).join("");
}

function render(r) {
  const dt = r.decision_tree, nb = r.naive_bayes;
  resultBox.innerHTML = `
    <h2>Predicted emergency priority</h2><p class="sub">Primary result from the Decision Tree model</p>
    <div class="result-top">
      <span class="badge-priority p-${dt.label}">${dt.label}</span>
      <div class="conf">Confidence<br><b>${dt.confidence.toFixed(1)}%</b></div>
    </div>
    <div class="meter">
      <div class="meter-row"><span>Risk of High / Critical emergency</span><span>${r.risk_percent.toFixed(1)}%</span></div>
      <div class="bar risk"><i style="width:${r.risk_percent}%"></i></div>
    </div>
    <h2 style="font-size:14px;margin-bottom:6px">Probability by priority</h2>
    ${probRows(dt.probabilities)}
    <div class="compare">
      <div><small>Decision Tree</small><b>${dt.label}</b> <span class="hint">· ${dt.confidence.toFixed(1)}% confidence</span></div>
      <div><small>Naive Bayes</small><b>${nb.label}</b> <span class="hint">· ${nb.confidence.toFixed(1)}% confidence</span></div>
    </div>`;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errBox.hidden = true;
  const btn = document.getElementById("submit");
  const payload = Object.fromEntries(new FormData(form).entries());
  btn.disabled = true; btn.textContent = "Predicting…";
  try {
    render(await api("/api/predict/emergency", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }));
  } catch (err) {
    errBox.textContent = err.message; errBox.hidden = false;
  } finally {
    btn.disabled = false; btn.textContent = "Predict emergency priority";
  }
});

init().catch((e) => { errBox.textContent = e.message; errBox.hidden = false; });
