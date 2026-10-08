"""Flask application: serves the 5 pages and the JSON APIs behind them.

Models are trained by train.py and only LOADED here (never retrained per request).
"""
import json
import os
from pathlib import Path

import joblib
import pandas as pd
from flask import Flask, jsonify, render_template, request

import warehouse
from train import DAMAGE_ORDER, EM_FEATURES, PRIORITY_ORDER, RES_FEATURES, RES_TARGETS

BASE = Path(__file__).resolve().parent
MODELS = BASE / "models"

app = Flask(__name__)


def _ensure_artifacts():
    """First run on a fresh checkout without trained artifacts: train once."""
    needed = ["decision_tree.joblib", "naive_bayes.joblib", "resource_regressor.joblib", "analytics.json"]
    if not all((MODELS / n).exists() for n in needed) or not warehouse.DB_PATH.exists():
        import train
        train.main()


_ensure_artifacts()
DT_MODEL = joblib.load(MODELS / "decision_tree.joblib")
NB_MODEL = joblib.load(MODELS / "naive_bayes.joblib")
RES_MODEL = joblib.load(MODELS / "resource_regressor.joblib")
with open(MODELS / "analytics.json", encoding="utf-8") as fh:
    ANALYTICS = json.load(fh)
META = ANALYTICS["meta"]


# ----------------------------------------------------------------------- pages
@app.route("/")
def dashboard():
    return render_template("dashboard.html", active="dashboard")


@app.route("/emergency")
def emergency():
    return render_template("emergency.html", active="emergency")


@app.route("/resources")
def resources():
    return render_template("resources.html", active="resources")


@app.route("/insights")
def insights():
    return render_template("insights.html", active="insights")


@app.route("/performance")
def performance():
    return render_template("performance.html", active="performance")


# ------------------------------------------------------------------------ APIs
def _number(payload, field, label):
    rng = META["numeric"][field]
    try:
        value = float(payload.get(field))
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number.")
    if value != value or value < 0:
        raise ValueError(f"{label} must be a positive number.")
    return value


def _choice(payload, field, label, options):
    value = payload.get(field)
    if value not in options:
        raise ValueError(f"{label} must be one of: {', '.join(options)}.")
    return value


@app.get("/api/meta")
def api_meta():
    return jsonify({**META, "priorities": PRIORITY_ORDER, "resource_targets": RES_TARGETS})


@app.get("/api/dashboard")
def api_dashboard():
    flt = {k: request.args.get(k) or None for k in ("year", "state", "disaster_type")}
    data = warehouse.dashboard(flt, request.args.get("grain", "year"))
    data["filters"] = warehouse.filter_options()
    return jsonify(data)


def _proba(model, row):
    proba = model.predict_proba(row)[0]
    classes = list(model.classes_)
    probs = {c: float(proba[classes.index(c)]) if c in classes else 0.0 for c in PRIORITY_ORDER}
    label = max(probs, key=probs.get)
    return {"label": label, "confidence": round(probs[label] * 100, 1),
            "probabilities": {c: round(p * 100, 1) for c, p in probs.items()}}


@app.post("/api/predict/emergency")
def api_predict_emergency():
    payload = request.get_json(silent=True) or {}
    try:
        row = pd.DataFrame([{
            "Disaster_Type": _choice(payload, "Disaster_Type", "Disaster type", META["disaster_types"]),
            "Rainfall_mm": _number(payload, "Rainfall_mm", "Rainfall"),
            "Water_Level_m": _number(payload, "Water_Level_m", "Water level"),
            "Population_Affected": _number(payload, "Population_Affected", "Population affected"),
            "Damage_Level": _choice(payload, "Damage_Level", "Damage level", DAMAGE_ORDER),
            "Shelter_Availability": _choice(payload, "Shelter_Availability", "Shelter availability",
                                            META["shelter_levels"]),
        }])[EM_FEATURES]
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    dt, nb = _proba(DT_MODEL, row), _proba(NB_MODEL, row)
    risk = dt["probabilities"]["High"] + dt["probabilities"]["Critical"]
    return jsonify({"decision_tree": dt, "naive_bayes": nb, "risk_percent": round(risk, 1)})


@app.post("/api/predict/resources")
def api_predict_resources():
    payload = request.get_json(silent=True) or {}
    try:
        row = pd.DataFrame([{
            "Population_Affected": _number(payload, "Population_Affected", "Population affected"),
            "Damage_Level": _choice(payload, "Damage_Level", "Damage level", DAMAGE_ORDER),
            "Disaster_Duration_Days": _number(payload, "Disaster_Duration_Days", "Disaster duration"),
            "Medical_Need": _number(payload, "Medical_Need", "Medical need"),
        }])[RES_FEATURES]
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    pred = RES_MODEL.predict(row)[0]
    return jsonify({t: max(0, int(round(float(v)))) for t, v in zip(RES_TARGETS, pred)})


@app.get("/api/resource-points")
def api_resource_points():
    return jsonify(ANALYTICS["resource_points"])


@app.get("/api/insights")
def api_insights():
    return jsonify({"clusters": ANALYTICS["clusters"], "patterns": ANALYTICS["patterns"]})


@app.get("/api/performance")
def api_performance():
    return jsonify(ANALYTICS["performance"])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
