"""Training pipeline: preprocess -> train/save models -> K-Means -> Apriori -> warehouse.

Run once (python train.py). Everything is written to models/ and warehouse/ and
is loaded (never retrained) by the Flask app.
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import accuracy_score, confusion_matrix, mean_absolute_error, r2_score
from sklearn.model_selection import GridSearchCV, cross_val_score, train_test_split
from sklearn.naive_bayes import GaussianNB
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

import warehouse
from ml_utils import Winsorizer, mine_rules

BASE = Path(__file__).resolve().parent
DATA = BASE / "dataset" / "disaster_response_dataset_6000.csv"
MODELS = BASE / "models"
RANDOM_STATE = 42

PRIORITY_ORDER = ["Low", "Medium", "High", "Critical"]
DAMAGE_ORDER = ["Low", "Moderate", "High"]

EM_NUM = ["Rainfall_mm", "Water_Level_m", "Population_Affected"]
EM_CAT = ["Disaster_Type", "Shelter_Availability"]
EM_FEATURES = ["Disaster_Type", "Rainfall_mm", "Water_Level_m", "Population_Affected",
               "Damage_Level", "Shelter_Availability"]

RES_NUM = ["Population_Affected", "Disaster_Duration_Days", "Medical_Need"]
RES_FEATURES = ["Population_Affected", "Damage_Level", "Disaster_Duration_Days", "Medical_Need"]
RES_TARGETS = ["Food_Required_Units", "Water_Required_Litres", "Medical_Kits_Required", "Shelter_Required"]

CLUSTER_FEATURES = ["Population_Affected", "Infrastructure_Damage_Lakh", "Houses_Damaged",
                    "Casualties", "Medical_Need"]
IMPACT_LABELS = ["Low Impact", "Moderate Impact", "High Impact", "Critical Impact"]


def num_pipeline():
    return Pipeline([("cap", Winsorizer()), ("impute", SimpleImputer(strategy="median")),
                     ("scale", StandardScaler())])


def emergency_preprocessor(onehot_damage=False):
    """Trees use damage as an ordered value; Naive Bayes gets it one-hot encoded."""
    if onehot_damage:
        return ColumnTransformer([
            ("num", num_pipeline(), EM_NUM),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), EM_CAT + ["Damage_Level"]),
        ])
    return ColumnTransformer([
        ("num", num_pipeline(), EM_NUM),
        ("damage", OrdinalEncoder(categories=[DAMAGE_ORDER]), ["Damage_Level"]),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), EM_CAT),
    ])


def resource_preprocessor():
    return ColumnTransformer([
        ("num", num_pipeline(), RES_NUM),
        ("damage", OrdinalEncoder(categories=[DAMAGE_ORDER]), ["Damage_Level"]),
    ])


def load_raw():
    df = pd.read_csv(DATA)
    print(f"[data] {df.shape[0]} rows x {df.shape[1]} cols | duplicates: {df.duplicated().sum()} "
          f"| missing: {int(df.isna().sum().sum())}")
    return df.drop_duplicates().reset_index(drop=True)


def clean(df):
    """Cleaned copy for the warehouse / K-Means / Apriori (models impute inside their pipelines)."""
    out = df.copy()
    out["Date"] = pd.to_datetime(out["Date"])
    for col in ["Rainfall_mm", "Water_Level_m", "Medical_Need"]:
        out[col] = out[col].fillna(out[col].median())
    return out


# --------------------------------------------------------------------------- #
def train_emergency(raw):
    X, y = raw[EM_FEATURES], raw["Emergency_Priority"]
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y)

    # J48 ~ C4.5: entropy (information-gain) splits + pruning via depth / min-leaf-size, tuned by CV.
    dt_pipe = Pipeline([("prep", emergency_preprocessor()),
                        ("model", DecisionTreeClassifier(criterion="entropy", random_state=RANDOM_STATE))])
    grid = GridSearchCV(dt_pipe, {"model__max_depth": [4, 5, 6, 8, 10],
                                  "model__min_samples_leaf": [5, 10, 20, 40]}, cv=5, n_jobs=1)
    grid.fit(Xtr, ytr)
    dt = grid.best_estimator_
    nb_pipe = Pipeline([("prep", emergency_preprocessor(onehot_damage=True)), ("model", GaussianNB())])
    nb_grid = GridSearchCV(nb_pipe, {"model__var_smoothing": [1e-3, 1e-2, 1e-1, 0.3, 1.0]}, cv=5, n_jobs=1)
    nb = nb_grid.fit(Xtr, ytr).best_estimator_

    dt_pred, nb_pred = dt.predict(Xte), nb.predict(Xte)
    dt_acc, nb_acc = accuracy_score(yte, dt_pred), accuracy_score(yte, nb_pred)
    cm = confusion_matrix(yte, dt_pred, labels=PRIORITY_ORDER)
    print(f"[emergency] best DT params {grid.best_params_} | DT acc {dt_acc:.4f} | NB acc {nb_acc:.4f}")
    joblib.dump(dt, MODELS / "decision_tree.joblib", compress=3)
    joblib.dump(nb, MODELS / "naive_bayes.joblib", compress=3)
    return {"dt_accuracy": dt_acc, "nb_accuracy": nb_acc,
            "confusion_labels": PRIORITY_ORDER, "confusion_matrix": cm.tolist(),
            "dt_params": {k.replace("model__", ""): v for k, v in grid.best_params_.items()},
            "train_size": len(Xtr), "test_size": len(Xte)}


def train_resources(raw):
    X, Y = raw[RES_FEATURES], raw[RES_TARGETS]
    Xtr, Xte, Ytr, Yte = train_test_split(X, Y, test_size=0.2, random_state=RANDOM_STATE)
    candidates = {
        "Linear Regression": LinearRegression(),
        "Random Forest Regressor": RandomForestRegressor(n_estimators=80, max_depth=10, min_samples_leaf=5,
                                                         random_state=RANDOM_STATE, n_jobs=1),
    }
    scores = {}
    for name, est in candidates.items():
        pipe = Pipeline([("prep", resource_preprocessor()), ("model", est)])
        scores[name] = float(cross_val_score(pipe, Xtr, Ytr, cv=3, scoring="r2").mean())
    best = max(scores, key=scores.get)
    model = Pipeline([("prep", resource_preprocessor()), ("model", candidates[best])]).fit(Xtr, Ytr)
    pred = model.predict(Xte)
    r2 = r2_score(Yte, pred)
    maes = {t: float(mean_absolute_error(Yte[t], pred[:, i])) for i, t in enumerate(RES_TARGETS)}
    print(f"[resources] CV R2 {scores} -> {best} | test R2 {r2:.4f} | MAE {maes}")
    joblib.dump(model, MODELS / "resource_regressor.joblib", compress=3)

    rng = np.random.RandomState(RANDOM_STATE)
    idx = rng.choice(len(Xte), size=min(250, len(Xte)), replace=False)
    points = {t: {"actual": [round(float(v), 1) for v in Yte[t].to_numpy()[idx]],
                  "predicted": [round(float(v), 1) for v in pred[idx, i]]}
              for i, t in enumerate(RES_TARGETS)}
    return {"model_name": best, "cv_r2": scores, "r2": float(r2), "mae": maes,
            "mae_mean": float(np.mean(list(maes.values()))), "points": points}


def run_kmeans(df):
    X = df[CLUSTER_FEATURES]
    prep = num_pipeline().fit(X)
    Z = prep.transform(X)
    km = KMeans(n_clusters=4, n_init=10, random_state=RANDOM_STATE).fit(Z)
    # Rank clusters by overall severity so labels read Low -> Critical.
    order = np.argsort(km.cluster_centers_.sum(axis=1))
    remap = {int(c): i for i, c in enumerate(order)}
    groups = np.array([remap[int(c)] for c in km.labels_])
    df = df.copy()
    df["Impact_Group"] = [IMPACT_LABELS[g] for g in groups]
    joblib.dump({"preprocess": prep, "kmeans": km, "remap": remap, "labels": IMPACT_LABELS},
                MODELS / "kmeans.joblib", compress=3)

    summary = []
    for i, lab in enumerate(IMPACT_LABELS):
        sub = df[df["Impact_Group"] == lab]
        summary.append({"label": lab, "count": int(len(sub)), "share": round(len(sub) / len(df) * 100, 1),
                        "avg_population": round(float(sub["Population_Affected"].mean())),
                        "avg_damage_lakh": round(float(sub["Infrastructure_Damage_Lakh"].mean())),
                        "avg_houses": round(float(sub["Houses_Damaged"].mean())),
                        "avg_casualties": round(float(sub["Casualties"].mean()), 1),
                        "avg_medical_need": round(float(sub["Medical_Need"].mean()))})
    sample = df.sample(n=700, random_state=RANDOM_STATE)
    scatter = [{"x": int(r.Population_Affected), "y": float(r.Infrastructure_Damage_Lakh), "group": r.Impact_Group}
               for r in sample.itertuples()]
    severe = df.assign(severe=df["Impact_Group"].isin(["High Impact", "Critical Impact"]))
    states = (severe.groupby("State")["severe"].mean().mul(100).round(1).sort_values(ascending=False))
    print("[kmeans]", {s["label"]: s["count"] for s in summary})
    return df, {"labels": IMPACT_LABELS, "summary": summary, "scatter": scatter,
                "severe_states": [{"state": s, "pct": float(p)} for s, p in states.items()]}


def run_apriori(df):
    def tier(series, name):
        t = pd.qcut(series.rank(method="first"), 3, labels=["Low", "Medium", "High"])
        return name + ": " + t.astype(str)

    items = pd.DataFrame({
        "rain": tier(df["Rainfall_mm"], "Rainfall"),
        "water": tier(df["Water_Level_m"], "Water Level"),
        "pop": tier(df["Population_Affected"], "Population"),
        "houses": tier(df["Houses_Damaged"], "Houses Damaged"),
        "cas": tier(df["Casualties"], "Casualties"),
        "med": tier(df["Medical_Need"], "Medical Need"),
        "dmg": "Damage Level: " + df["Damage_Level"],
        "prio": "Priority: " + df["Emergency_Priority"],
        "type": "Disaster: " + df["Disaster_Type"],
        "food": "Food Supply: " + df["Food_Availability"],
        "wsup": "Water Supply: " + df["Water_Availability"],
    })
    onehot = pd.get_dummies(items.astype(str)).astype(bool)
    onehot.columns = [c.split("_", 1)[1] if "_" in c and c.split("_", 1)[0] in items.columns else c
                      for c in onehot.columns]
    rules, engine = mine_rules(onehot, min_support=0.04, min_confidence=0.5, max_len=3)
    # Conditions (hazard / exposure / supply) may only imply outcomes (priority, medical need, casualties, housing loss).
    cond = ("Rainfall", "Water Level", "Population", "Damage Level", "Disaster", "Food Supply", "Water Supply")
    outc = ("Priority", "Medical Need", "Casualties", "Houses Damaged")
    fam = lambda item: item.split(":")[0]
    rules = rules[(rules["lift"] >= 1.15)
                  & rules["antecedents"].apply(lambda a: all(fam(i) in cond for i in a))
                  & rules["consequents"].apply(lambda c: fam(c[0]) in outc)].copy()
    rules["key"] = rules.apply(lambda r: frozenset(r["antecedents"]) | frozenset(r["consequents"]), axis=1)
    rules["score"] = rules["lift"] * rules["confidence"]
    rules = rules.sort_values("score", ascending=False).drop_duplicates("key")
    rules["then"] = rules["consequents"].apply(lambda c: c[0])
    # Keep the list varied: at most 3 rules per consequent, 12 rules overall.
    rules = rules.groupby("then", sort=False).head(3).head(12)
    out = [{"if": list(r.antecedents), "then": list(r.consequents)[0], "support": round(float(r.support), 4),
            "confidence": round(float(r.confidence), 4), "lift": round(float(r.lift), 3)}
           for r in rules.itertuples()]
    print(f"[apriori] engine={engine} | {len(out)} rules kept")
    return {"engine": engine, "n_transactions": int(len(df)), "rules": out}


def build_meta(raw):
    num = {}
    for col in ["Rainfall_mm", "Water_Level_m", "Population_Affected", "Disaster_Duration_Days", "Medical_Need"]:
        s = raw[col].dropna()
        num[col] = {"min": float(s.min()), "max": float(s.max()), "median": float(s.median())}
    return {"disaster_types": sorted(raw["Disaster_Type"].unique()),
            "damage_levels": [d for d in DAMAGE_ORDER if d in set(raw["Damage_Level"])],
            "shelter_levels": sorted(raw["Shelter_Availability"].unique(), reverse=True),
            "numeric": num}


def main():
    MODELS.mkdir(exist_ok=True)
    raw = load_raw()
    emergency = train_emergency(raw)
    resources = train_resources(raw)
    cleaned = clean(raw)
    cleaned, clusters = run_kmeans(cleaned)
    patterns = run_apriori(cleaned)
    warehouse.build(cleaned)
    performance = {"emergency": emergency,
                   "regression": {k: v for k, v in resources.items() if k != "points"}}
    analytics = {"meta": build_meta(raw), "performance": performance,
                 "resource_points": resources["points"], "clusters": clusters, "patterns": patterns}
    with open(MODELS / "analytics.json", "w", encoding="utf-8") as fh:
        json.dump(analytics, fh)
    print("[done] models/, analytics.json and warehouse/disaster_dw.db written")


if __name__ == "__main__":
    main()
