/* Shared helpers: API calls, formatting, palette and Chart.js defaults. */
const COLORS = {
  blue: "#6fa3d8", blueSoft: "rgba(111,163,216,.18)", teal: "#62bdb3", tealSoft: "rgba(98,189,179,.18)",
  peach: "#e6cf80", coral: "#e3a39c", rose: "#e3a39c", chiffon: "#e6cf80", slate: "#2e3f57", muted: "#7b8ba3", grid: "#eaf1f7",
};
const PRIORITY_COLORS = { Low: "#62bdb3", Medium: "#6fa3d8", High: "#e6cf80", Critical: "#e3a39c" };
const GROUP_COLORS = { "Low Impact": "#62bdb3", "Moderate Impact": "#6fa3d8", "High Impact": "#e6cf80", "Critical Impact": "#e3a39c" };
const SERIES = [COLORS.blue, COLORS.teal, "#9cc5e8", "#8fd3cb", "#b9d4ee"];

if (window.Chart) {
  Chart.defaults.font.family = '"Inter","Segoe UI",system-ui,sans-serif';
  Chart.defaults.font.size = 12.5;
  Chart.defaults.color = COLORS.muted;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.layout.padding = 4;
  Chart.defaults.plugins.tooltip.backgroundColor = "#2e3f57";
  Chart.defaults.plugins.tooltip.cornerRadius = 10;
  Chart.defaults.plugins.tooltip.padding = 10;
}

const charts = {};
function drawChart(id, config) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), config);
  return charts[id];
}

async function api(url, options) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Request failed (" + res.status + ")");
  return data;
}

function esc(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const nf = new Intl.NumberFormat("en-IN");
const fmt = (n) => nf.format(Math.round(n));
function compact(n) {
  n = Number(n);
  if (n >= 1e7) return (n / 1e7).toFixed(2) + " Cr";
  if (n >= 1e5) return (n / 1e5).toFixed(2) + " L";
  return nf.format(Math.round(n));
}
function fillSelect(select, values, selected) {
  select.innerHTML = values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("");
  if (selected !== undefined) select.value = selected;
}
const axisStyle = { grid: { color: COLORS.grid }, border: { display: false } };
const noGrid = { grid: { display: false }, border: { display: false } };
