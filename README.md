# Disaster Response & Emergency Resource Intelligence System

A Flask web application that analyses disaster-response data to help emergency authorities
**predict emergency priority, estimate resource demand, group affected areas by impact, and
discover patterns across disaster attributes** — presented through a clean, soft blue/teal analytics dashboard.

## Project overview

The system loads a 6,000-record disaster-response dataset, builds a small SQLite data warehouse
(star schema), trains machine-learning models once, and serves five pages that use the saved
models and live warehouse queries. Nothing on the site is hard-coded: statistics come from the
warehouse, predictions from the trained models, clusters from K-Means and rules from Apriori.

## Problem statement

During a disaster, authorities must decide quickly *how urgent* an incident is and *how much*
food, water, medical supplies and shelter to send. Doing this by intuition leads to delays and
shortages. This project turns historical incident data into data-driven priority and resource estimates.

## Objectives

1. Predict emergency priority (Low / Medium / High / Critical).
2. Estimate required emergency resources (food, water, medical kits, shelter).
3. Group disaster-affected areas by impact level.
4. Discover meaningful disaster patterns.
5. Evaluate model performance transparently.
6. Present useful analytics in a professional dashboard.

## Features

| Page | What it does |
|------|--------------|
| **Dashboard** | 4 KPI cards, disasters by type, an emergency-priority donut chart, affected population over time, resource demand by type, and generated insights. Filters and a time hierarchy provide OLAP operations. |
| **Emergency Prediction** | Form → predicted priority, confidence, High/Critical risk %, probability per class, Decision Tree vs Naive Bayes comparison. |
| **Resource Prediction** | Form → predicted food, water, medical kits and shelter, plus an *Actual vs Predicted* chart on held-out test data. |
| **Disaster Insights** | K-Means impact groups (cluster distribution, population-vs-damage scatter, group cards, state view) and Apriori patterns shown as top insight cards plus a full patterns table with support, confidence and lift. |
| **Model Performance** | Decision Tree & Naive Bayes accuracy cards, comparison chart, labelled Decision Tree confusion matrix with a generated interpretation, and a small regression R² / MAE section. |

## Design

Light, soft analytics UI: soft blue and soft teal as primary accents, with subtle rosewater and chiffon
accents (priority badges, highlights, chart colours) on white cards over a very light chiffon background.
Priority colours: Low = teal, Medium = blue, High = chiffon, Critical = rosewater. The layout is responsive
(desktop, tablet, mobile) and uses a system sans-serif font stack.

## Technology stack

- **Frontend:** HTML, CSS, JavaScript, Chart.js (loaded from the jsDelivr CDN)
- **Backend:** Python, Flask
- **Data processing:** Pandas, NumPy
- **Machine learning:** scikit-learn
- **Association rules:** mlxtend (with a built-in Apriori fallback, see below)
- **Database:** SQLite (data warehouse)

## Dataset description

`dataset/disaster_response_dataset_6000.csv` — 6,000 rows × 23 columns, 2019-01-02 to 2025-12-31,
10 Indian states, 5 disaster types (Flood, Earthquake, Landslide, Cyclone, Wildfire).
This is a **synthetic / engineered disaster-response dataset** prepared for this project; it is
**not** an official historical record, and results should be read as a demonstration of the method.

Columns: `Disaster_ID, Date, Disaster_Type, State, Rainfall_mm, Water_Level_m, Wind_Speed_kmph,
Temperature_C, Population_Affected, Infrastructure_Damage_Lakh, Houses_Damaged, Casualties,
Disaster_Duration_Days, Medical_Need, Shelter_Availability, Food_Availability, Water_Availability,
Damage_Level, Emergency_Priority, Food_Required_Units, Water_Required_Litres,
Medical_Kits_Required, Shelter_Required`.

Inspection findings: no duplicate rows; 30 missing values each in `Rainfall_mm`, `Water_Level_m`
and `Medical_Need`; `Emergency_Priority` is imbalanced (Low 2932, Medium 2244, High 703, Critical 121);
`Shelter_Availability` is almost always `High` (5995 of 6000), so the form only offers the values present in the data.

## Data preprocessing

Implemented in `train.py` and reused at prediction time through scikit-learn pipelines:

- **Duplicates:** checked and dropped (none found).
- **Missing values:** median imputation inside the model pipelines (no leakage — fitted on training data only); the cleaned copy used for the warehouse, K-Means and Apriori uses column medians.
- **Outliers:** a `Winsorizer` caps numeric features at the 1st/99th percentile (learned on training data).
- **Scaling:** `StandardScaler` on numeric features.
- **Categorical encoding:** one-hot for disaster type / shelter (and damage level for Naive Bayes); ordinal encoding (Low < Moderate < High) for damage level in the tree and regression models.
- **Feature selection:** emergency models use disaster type, rainfall, water level, population affected, damage level and shelter availability; the resource model uses population affected, damage level, duration and medical need.
- **Train/test split:** 80/20, stratified for the classifiers, random state 42.

## Data warehouse / star schema

Built by `warehouse.py` into `warehouse/disaster_dw.db` (SQLite):

```
              Dim_Time ──┐
          Dim_Location ──┤
                         ├── Fact_Disaster
          Dim_Disaster ──┤
          Dim_Resource ──┘
```

- **Fact_Disaster** – one row per incident; measures: rainfall, water level, wind, temperature, population affected, infrastructure damage, houses damaged, casualties, duration, medical need, food / water / medical kits / shelter required, plus the K-Means impact group.
- **Dim_Time** – date, year, quarter, month, month name.
- **Dim_Location** – state.
- **Dim_Disaster** – disaster type, damage level, emergency priority.
- **Dim_Resource** – shelter, food and water availability.

## OLAP concepts

Implemented as natural dashboard interactions (there is no separate OLAP page):

- **Roll-up:** switch the time chart from Month → Quarter → Year, or press *← All years*.
- **Drill-down:** click a year in the population chart to expand it into its months.
- **Slice:** fix one dimension, e.g. year = 2023.
- **Dice:** combine filters, e.g. year + state + disaster type.

All KPIs and charts are recomputed from the warehouse with SQL joins for the selected cube.

## ML models

- **Decision Tree (J48-style):** scikit-learn has no J48 class. J48 is Weka's implementation of C4.5, so the closest equivalent is `DecisionTreeClassifier(criterion="entropy")` — information-gain splits — with pruning approximated by `max_depth` / `min_samples_leaf`, tuned with 5-fold cross-validation.
- **Naive Bayes:** `GaussianNB` with `var_smoothing` tuned by cross-validation.
- **Regression:** a multi-output regressor for the four resource targets. Linear Regression and Random Forest are compared with cross-validation on the training set; the better one is saved (Linear Regression in the shipped run).
- Models are trained by `train.py`, saved as joblib files in `models/`, and only **loaded** by Flask.

## K-Means

Affected areas are clustered on population affected, infrastructure damage, houses damaged,
casualties and medical need (capped and standardised) with `k = 4`. Clusters are ranked by overall
severity and named **Low / Moderate / High / Critical Impact**.

## Apriori

Numeric attributes are split into Low / Medium / High terciles and combined with categorical
attributes into transactions. Rules are mined with Apriori (min support 4%, min confidence 50%,
lift ≥ 1.15), restricted to *conditions → outcomes* (for example rainfall, water level, population,
damage level and supplies implying priority, medical need, casualties or housing loss), de-duplicated, and
shown with support, confidence and lift.

`mlxtend` is the primary engine. If it cannot be imported, `ml_utils.py` falls back to an equivalent
built-in Apriori implementation so the project still runs; `models/analytics.json` records which engine was used.
**The shipped results were generated with the built-in fallback** because `mlxtend` could not be installed in the build environment;
re-running `python train.py` after `pip install -r requirements.txt` will regenerate them with `mlxtend`.

## Model evaluation

Held-out 20% test split (shipped run):

| Metric | Value |
|--------|-------|
| Decision Tree accuracy | ≈ 78.1% |
| Naive Bayes accuracy | ≈ 78.3% |
| Regression R² (uniform average over 4 resources) | ≈ 0.773 |
| Regression MAE | per resource: food ≈ 834, water ≈ 2,012, medical kits ≈ 17, shelter ≈ 642 |

The Critical class is rare (121 records), so it is the hardest to predict.

## Project structure

```
Disaster-Response-System/
├── app.py                  # Flask app: pages + JSON APIs (loads saved models)
├── train.py                # preprocessing, model training, K-Means, Apriori, warehouse build
├── warehouse.py            # star-schema creation + OLAP queries
├── ml_utils.py             # Winsorizer transformer + Apriori helpers
├── requirements.txt
├── README.md
├── .gitignore
├── dataset/disaster_response_dataset_6000.csv
├── models/                 # decision_tree, naive_bayes, resource_regressor, kmeans, analytics.json
├── warehouse/disaster_dw.db
├── templates/              # base, dashboard, emergency, resources, insights, performance
└── static/
    ├── css/style.css
    └── js/                 # common + one script per page
```

## Installation steps

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## How to run

```bash
python app.py                    # http://127.0.0.1:5000
```

Trained models and the warehouse are already included. To rebuild them from the CSV:

```bash
python train.py
```

(If the `models/` folder or warehouse is missing, `app.py` runs the training once automatically.)

**Deploying on Render:** build command `pip install -r requirements.txt`, start command `gunicorn app:app`.
The page charts load Chart.js from a CDN, so the browser needs internet access.

## Future scope

- Live data feeds (weather / river-gauge APIs) in place of the static CSV.
- Map-based visualisation of affected districts.
- Additional models (gradient boosting) and class-imbalance handling for the Critical class.
- Scheduled retraining and model versioning.
- Alerts and exports for field teams.
