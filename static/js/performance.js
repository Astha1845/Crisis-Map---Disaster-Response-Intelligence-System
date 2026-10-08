// Builds a short plain-English reading of the confusion matrix from its actual numbers.
function interpretMatrix(labels, m) {
  const stats = labels.map((label, i) => {
    const rowTotal = m[i].reduce((a, b) => a + b, 0);
    const hit = rowTotal ? m[i][i] / rowTotal : 0;
    // most common wrong prediction for this class
    let worst = -1, worstCount = 0;
    m[i].forEach((v, j) => { if (j !== i && v > worstCount) { worst = j; worstCount = v; } });
    return { label, hit, rowTotal, confusedWith: worst >= 0 ? labels[worst] : null };
  }).filter((s) => s.rowTotal > 0);
  const strong = stats.filter((s) => s.hit >= 0.7);
  const weak = stats.filter((s) => s.hit < 0.7);
  const join = (arr) => (arr.length > 1 ? arr.slice(0, -1).join(", ") + " and " + arr[arr.length - 1] : arr[0]);
  const parts = [];
  if (strong.length) parts.push(`Most ${join(strong.map((s) => s.label))} priority cases are correctly classified`);
  if (weak.length) {
    const idx = (name) => labels.indexOf(name);
    const neighbours = weak.every((s) => s.confusedWith && Math.abs(idx(s.confusedWith) - idx(s.label)) === 1);
    const where = neighbours ? ", mostly as a neighbouring priority level" : "";
    parts.push(`${strong.length ? "while some" : "Some"} ${join(weak.map((s) => s.label))} cases are misclassified${where}`);
  }
  return parts.length ? parts.join(", ") + "." : "";
}

function renderMatrix(labels, m) {
  const max = Math.max(...m.flat(), 1);
  const cell = (v, i, j) => {
    const strength = v / max;
    const bg = i === j ? `rgba(98,189,179,${0.15 + strength * 0.65})` : `rgba(227,163,156,${v ? 0.14 + strength * 0.5 : 0.05})`;
    return `<td style="background:${bg}">${v}</td>`;
  };
  document.getElementById("cm").innerHTML = `
    <table class="cm2">
      <thead>
        <tr><th colspan="2"></th><th class="axis-top" colspan="${labels.length}">Predicted Priority →</th></tr>
        <tr><th colspan="2"></th>${labels.map((l) => `<th class="collab">${esc(l)}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${m.map((row, i) => `<tr>
          ${i === 0 ? `<th class="axis-left" rowspan="${labels.length}">Actual<br>Priority<br>↓</th>` : ""}
          <th class="rowlab">${esc(labels[i])}</th>${row.map((v, j) => cell(v, i, j)).join("")}</tr>`).join("")}
      </tbody>
    </table>`;
  document.getElementById("interp").textContent = interpretMatrix(labels, m);
}

async function load() {
  const p = await api("/api/performance");
  const e = p.emergency, r = p.regression;
  const dt = e.dt_accuracy * 100, nb = e.nb_accuracy * 100;

  document.getElementById("m-dt").textContent = dt.toFixed(1) + "%";
  document.getElementById("m-nb").textContent = nb.toFixed(1) + "%";
  document.getElementById("b-dt").style.width = dt + "%";
  document.getElementById("b-nb").style.width = nb + "%";
  document.getElementById("m-r2").textContent = r.r2.toFixed(3);
  document.getElementById("m-mae").textContent = fmt(r.mae_mean);
  const short = { Food_Required_Units: "Food", Water_Required_Litres: "Water", Medical_Kits_Required: "Kits", Shelter_Required: "Shelter" };
  document.getElementById("mae-list").innerHTML = Object.entries(r.mae)
    .map(([k, v]) => `<span>${short[k]} <b>${fmt(v)}</b></span>`).join("");

  drawChart("c-acc", {
    type: "bar",
    data: {
      labels: ["Decision Tree", "Naive Bayes"],
      datasets: [{ data: [dt, nb], backgroundColor: [COLORS.blue, COLORS.teal], borderRadius: 12, maxBarThickness: 90 }],
    },
    options: {
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => " " + c.parsed.y.toFixed(1) + "% accuracy" } } },
      scales: { x: noGrid, y: { ...axisStyle, min: 0, max: 100, ticks: { callback: (v) => v + "%" } } },
    },
  });

  renderMatrix(e.confusion_labels, e.confusion_matrix);
}

load().catch((e) => { const b = document.getElementById("err"); b.textContent = e.message; b.hidden = false; });
