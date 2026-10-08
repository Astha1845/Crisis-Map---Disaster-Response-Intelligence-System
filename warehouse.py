"""SQLite star-schema data warehouse + OLAP-style queries used by the dashboard.

Star schema
    Fact_Disaster  -> Dim_Time, Dim_Location, Dim_Disaster, Dim_Resource

OLAP operations (all driven by the dashboard filters)
    Roll-up    : year <- quarter <- month   (grain parameter)
    Drill-down : click a year, the trend expands to the months of that year
    Slice      : fix ONE dimension (e.g. year = 2023)
    Dice       : fix several dimensions together (year + state + disaster type)
"""
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent / "warehouse" / "disaster_dw.db"

SCHEMA = """
DROP TABLE IF EXISTS Fact_Disaster;
DROP TABLE IF EXISTS Dim_Time;
DROP TABLE IF EXISTS Dim_Location;
DROP TABLE IF EXISTS Dim_Disaster;
DROP TABLE IF EXISTS Dim_Resource;

CREATE TABLE Dim_Time (
    time_key INTEGER PRIMARY KEY, full_date TEXT, year INTEGER, quarter INTEGER,
    month INTEGER, month_name TEXT, year_quarter TEXT, year_month TEXT);
CREATE TABLE Dim_Location (
    location_key INTEGER PRIMARY KEY, state TEXT UNIQUE);
CREATE TABLE Dim_Disaster (
    disaster_key INTEGER PRIMARY KEY, disaster_type TEXT, damage_level TEXT,
    emergency_priority TEXT, UNIQUE (disaster_type, damage_level, emergency_priority));
CREATE TABLE Dim_Resource (
    resource_key INTEGER PRIMARY KEY, shelter_availability TEXT, food_availability TEXT,
    water_availability TEXT, UNIQUE (shelter_availability, food_availability, water_availability));
CREATE TABLE Fact_Disaster (
    disaster_id TEXT PRIMARY KEY,
    time_key INTEGER NOT NULL REFERENCES Dim_Time(time_key),
    location_key INTEGER NOT NULL REFERENCES Dim_Location(location_key),
    disaster_key INTEGER NOT NULL REFERENCES Dim_Disaster(disaster_key),
    resource_key INTEGER NOT NULL REFERENCES Dim_Resource(resource_key),
    rainfall_mm REAL, water_level_m REAL, wind_speed_kmph REAL, temperature_c REAL,
    population_affected INTEGER, infrastructure_damage_lakh REAL, houses_damaged INTEGER,
    casualties INTEGER, duration_days INTEGER, medical_need REAL,
    food_required_units INTEGER, water_required_litres INTEGER,
    medical_kits_required INTEGER, shelter_required INTEGER,
    impact_group TEXT);
CREATE INDEX idx_fact_time ON Fact_Disaster(time_key);
CREATE INDEX idx_fact_loc ON Fact_Disaster(location_key);
CREATE INDEX idx_fact_dis ON Fact_Disaster(disaster_key);
"""


def build(df: pd.DataFrame) -> None:
    """Create the warehouse from the cleaned dataframe (needs an 'Impact_Group' column)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)

    dates = pd.to_datetime(df["Date"])
    dim_time = pd.DataFrame({"full_date": dates.dt.strftime("%Y-%m-%d")}).drop_duplicates()
    d = pd.to_datetime(dim_time["full_date"])
    dim_time["time_key"] = d.dt.strftime("%Y%m%d").astype(int)
    dim_time["year"] = d.dt.year
    dim_time["quarter"] = d.dt.quarter
    dim_time["month"] = d.dt.month
    dim_time["month_name"] = d.dt.strftime("%b")
    dim_time["year_quarter"] = d.dt.year.astype(str) + " Q" + d.dt.quarter.astype(str)
    dim_time["year_month"] = d.dt.strftime("%Y-%m")

    dim_loc = pd.DataFrame({"state": sorted(df["State"].unique())})
    dim_loc.insert(0, "location_key", range(1, len(dim_loc) + 1))

    dim_dis = (df[["Disaster_Type", "Damage_Level", "Emergency_Priority"]].drop_duplicates()
               .sort_values(["Disaster_Type", "Damage_Level", "Emergency_Priority"]).reset_index(drop=True))
    dim_dis.insert(0, "disaster_key", range(1, len(dim_dis) + 1))
    dim_dis.columns = ["disaster_key", "disaster_type", "damage_level", "emergency_priority"]

    dim_res = (df[["Shelter_Availability", "Food_Availability", "Water_Availability"]].drop_duplicates()
               .sort_values(["Shelter_Availability", "Food_Availability", "Water_Availability"])
               .reset_index(drop=True))
    dim_res.insert(0, "resource_key", range(1, len(dim_res) + 1))
    dim_res.columns = ["resource_key", "shelter_availability", "food_availability", "water_availability"]

    fact = pd.DataFrame({
        "disaster_id": df["Disaster_ID"],
        "time_key": dates.dt.strftime("%Y%m%d").astype(int),
    })
    fact["location_key"] = df["State"].map(dict(zip(dim_loc["state"], dim_loc["location_key"])))
    dkey = {tuple(r[1:]): r[0] for r in dim_dis.itertuples(index=False)}
    fact["disaster_key"] = [dkey[t] for t in zip(df["Disaster_Type"], df["Damage_Level"], df["Emergency_Priority"])]
    rkey = {tuple(r[1:]): r[0] for r in dim_res.itertuples(index=False)}
    fact["resource_key"] = [rkey[t] for t in zip(df["Shelter_Availability"], df["Food_Availability"], df["Water_Availability"])]
    measures = {
        "Rainfall_mm": "rainfall_mm", "Water_Level_m": "water_level_m", "Wind_Speed_kmph": "wind_speed_kmph",
        "Temperature_C": "temperature_c", "Population_Affected": "population_affected",
        "Infrastructure_Damage_Lakh": "infrastructure_damage_lakh", "Houses_Damaged": "houses_damaged",
        "Casualties": "casualties", "Disaster_Duration_Days": "duration_days", "Medical_Need": "medical_need",
        "Food_Required_Units": "food_required_units", "Water_Required_Litres": "water_required_litres",
        "Medical_Kits_Required": "medical_kits_required", "Shelter_Required": "shelter_required",
        "Impact_Group": "impact_group",
    }
    for src, dst in measures.items():
        fact[dst] = df[src].values

    dim_time.to_sql("Dim_Time", con, if_exists="append", index=False)
    dim_loc.to_sql("Dim_Location", con, if_exists="append", index=False)
    dim_dis.to_sql("Dim_Disaster", con, if_exists="append", index=False)
    dim_res.to_sql("Dim_Resource", con, if_exists="append", index=False)
    fact.to_sql("Fact_Disaster", con, if_exists="append", index=False)
    con.commit()
    con.close()


# --------------------------------------------------------------------------- #
# OLAP queries
# --------------------------------------------------------------------------- #
FROM = ("FROM Fact_Disaster f JOIN Dim_Time t ON f.time_key=t.time_key "
        "JOIN Dim_Location l ON f.location_key=l.location_key "
        "JOIN Dim_Disaster d ON f.disaster_key=d.disaster_key "
        "JOIN Dim_Resource r ON f.resource_key=r.resource_key")

PRIORITY_ORDER = ["Low", "Medium", "High", "Critical"]

GRAINS = {  # roll-up levels of the time hierarchy (whitelisted SQL expressions)
    "year": "CAST(t.year AS TEXT)",
    "quarter": "t.year_quarter",
    "month": "t.year_month",
}


def _connect():
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _where(flt):
    clauses, params = [], []
    if flt.get("year"):
        clauses.append("t.year=?")
        params.append(int(flt["year"]))
    if flt.get("state"):
        clauses.append("l.state=?")
        params.append(flt["state"])
    if flt.get("disaster_type"):
        clauses.append("d.disaster_type=?")
        params.append(flt["disaster_type"])
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def filter_options():
    con = _connect()
    out = {
        "years": [r[0] for r in con.execute("SELECT DISTINCT year FROM Dim_Time ORDER BY year")],
        "states": [r[0] for r in con.execute("SELECT state FROM Dim_Location ORDER BY state")],
        "disaster_types": [r[0] for r in con.execute(
            "SELECT DISTINCT disaster_type FROM Dim_Disaster ORDER BY disaster_type")],
    }
    con.close()
    return out


def _fmt(n):
    n = float(n)
    if n >= 1e7:
        return f"{n / 1e7:.2f} Cr"
    if n >= 1e5:
        return f"{n / 1e5:.2f} L"
    return f"{n:,.0f}"


def dashboard(flt, grain="year"):
    grain = grain if grain in GRAINS else "year"
    where, params = _where(flt)
    con = _connect()
    q = lambda sql: con.execute(sql, params).fetchall()

    k = con.execute(f"""SELECT COUNT(*) n, COALESCE(SUM(f.population_affected),0) pop,
                        COALESCE(SUM(d.emergency_priority='Critical'),0) crit,
                        COALESCE(SUM(f.food_required_units),0) food,
                        COALESCE(SUM(f.water_required_litres),0) water,
                        COALESCE(SUM(f.medical_kits_required),0) kits,
                        COALESCE(SUM(f.shelter_required),0) shelter {FROM} {where}""", params).fetchone()
    kpis = {
        "total_disasters": k["n"],
        "affected_population": k["pop"],
        "critical_areas": k["crit"],
        "resources_required": k["food"] + k["kits"] + k["shelter"],
        "resources_detail": f"{_fmt(k['food'])} food · {_fmt(k['kits'])} kits · {_fmt(k['shelter'])} shelter",
        "water_litres": k["water"],
    }

    by_type = [dict(r) for r in q(f"""SELECT d.disaster_type label, COUNT(*) value {FROM} {where}
                                      GROUP BY d.disaster_type ORDER BY value DESC""")]

    expr = GRAINS[grain]
    trend = [dict(r) for r in q(f"""SELECT {expr} label, SUM(f.population_affected) population, COUNT(*) disasters
                                    {FROM} {where} GROUP BY {expr} ORDER BY {expr}""")]

    counts = {r["label"]: r["value"] for r in q(f"""SELECT d.emergency_priority label, COUNT(*) value
                                                   {FROM} {where} GROUP BY d.emergency_priority""")}
    priority = [{"label": p, "value": counts.get(p, 0)} for p in PRIORITY_ORDER]

    resources = [dict(r) for r in q(f"""SELECT d.disaster_type label,
                    ROUND(AVG(f.food_required_units)) food,
                    ROUND(AVG(f.water_required_litres)/1000.0, 1) water_kl,
                    ROUND(AVG(f.shelter_required)) shelter,
                    ROUND(AVG(f.medical_kits_required), 1) kits
                    {FROM} {where} GROUP BY d.disaster_type ORDER BY d.disaster_type""")]

    insights = _insights(con, where, params, k["n"])
    con.close()
    return {"kpis": kpis, "by_type": by_type, "trend": trend, "grain": grain,
            "resources_by_type": resources, "priority_distribution": priority, "insights": insights}


def _insights(con, where, params, n):
    if n == 0:
        return [{"title": "No records", "text": "No disasters match the selected filters."}]
    out = []
    r = con.execute(f"""SELECT l.state, SUM(f.population_affected) p {FROM} {where}
                        GROUP BY l.state ORDER BY p DESC LIMIT 1""", params).fetchone()
    out.append({"title": "Most affected state",
                "text": f"{r['state']} has the largest affected population ({_fmt(r['p'])} people)."})
    r = con.execute(f"""SELECT d.disaster_type, AVG(f.casualties) c {FROM} {where}
                        GROUP BY d.disaster_type ORDER BY c DESC LIMIT 1""", params).fetchone()
    out.append({"title": "Highest casualty rate",
                "text": f"{r['disaster_type']} events average {r['c']:.1f} casualties per incident."})
    r = con.execute(f"""SELECT d.disaster_type, AVG(d.emergency_priority IN ('High','Critical'))*100 s, COUNT(*) c
                        {FROM} {where} GROUP BY d.disaster_type HAVING c >= 5 ORDER BY s DESC LIMIT 1""",
                    params).fetchone()
    if r:
        out.append({"title": "Highest emergency share",
                    "text": f"{r['s']:.0f}% of {r['disaster_type']} incidents are rated High or Critical priority."})
    r = con.execute(f"""SELECT t.year_month m, COUNT(*) c {FROM} {where}
                        GROUP BY t.year_month ORDER BY c DESC, m DESC LIMIT 1""", params).fetchone()
    out.append({"title": "Busiest month", "text": f"{r['m']} recorded the most incidents ({r['c']})."})
    r = con.execute(f"""SELECT r.food_availability fa, COUNT(*) c {FROM} {where}
                        GROUP BY r.food_availability ORDER BY c DESC LIMIT 1""", params).fetchone()
    low = con.execute(f"""SELECT AVG(r.food_availability='Low')*100 s, AVG(r.water_availability='Low')*100 w
                          {FROM} {where}""", params).fetchone()
    out.append({"title": "Supply pressure",
                "text": f"Food availability is Low in {low['s']:.0f}% and water in {low['w']:.0f}% of incidents."})
    return out
