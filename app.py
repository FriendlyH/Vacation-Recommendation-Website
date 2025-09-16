# app.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
import numpy as np
import json, os, time
from math import radians, sin, cos, sqrt, atan2

# ----- FRONTEND BUILD PATH (single source of truth) -----
FRONTEND_DIST = r"C:\Users\herin\OneDrive\code\project\templates\vacation-frontend\dist"

app = Flask(__name__, static_folder=None)  # we serve static ourselves
CORS(app, resources={
    r"/health": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173"]},
    r"/recommend": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173"]},
})

# ---- Log what we're serving on startup ----
def _mtime(p):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(p)))
    except Exception:
        return "N/A"

print("[FLASK] Serving frontend from:", FRONTEND_DIST)
print("[FLASK] index.html exists:",
      os.path.isfile(os.path.join(FRONTEND_DIST, "index.html")),
      "mtime:", _mtime(os.path.join(FRONTEND_DIST, "index.html")))

# -------------------------
# Load & preprocessing (unchanged from your file)
# -------------------------
DATA_PATH = r"C:/Users/herin/OneDrive/code/project/travel.csv"

df_raw = pd.read_csv(DATA_PATH)
df_raw["id"] = df_raw.index

budget_map = {"Budget": 0, "Mid-range": 1, "Luxury": 2}
df_raw["budget_level"] = df_raw["budget_level"].map(budget_map)

BASE_KEEP_COLS = [
    "id", "city", "country", "latitude", "longitude",
    "budget_level", "culture", "adventure", "nature", "beaches",
    "nightlife", "cuisine", "wellness", "urban", "seclusion"
]

def _load_monthlies(cell):
    try:
        return json.loads(cell)
    except Exception:
        return {}

temps = df_raw["avg_temp_monthly"].apply(_load_monthlies)
flat = pd.json_normalize(temps)
avg_cols = [c for c in flat.columns if c.endswith(".avg")]
monthly_df = flat[avg_cols].copy() if len(avg_cols) else pd.DataFrame(index=df_raw.index)
if not monthly_df.empty:
    monthly_df.columns = [int(c.split(".")[0]) for c in avg_cols]

SEASONS_MAP = {
    "Mar-May": [3, 4, 5],
    "Jun-Aug": [6, 7, 8],
    "Sep-Nov": [9, 10, 11],
    "Dec-Feb": [12, 1, 2],
}

def temp_to_code(t: float) -> int:
    if pd.isna(t): return 0
    if t < 15: return 0
    if t < 20: return 1
    if t < 25: return 2
    return 3

for season_label, months in SEASONS_MAP.items():
    if monthly_df.empty or not all(m in monthly_df.columns for m in months):
        df_raw[season_label] = 0
    else:
        df_raw[season_label] = monthly_df[months].mean(axis=1).apply(temp_to_code)

climate_df = df_raw[["id", "city", "country", "Mar-May", "Jun-Aug", "Sep-Nov", "Dec-Feb"]].copy()
activities_df = df_raw[[
    "id", "city", "country",
    "culture", "adventure", "nature", "beaches", "nightlife",
    "cuisine", "wellness", "urban", "seclusion"
]].copy()

# -------------------------
# Utilities
# -------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1); dlon = radians(lon2 - lon1)
    a = (sin(dlat/2)**2 +
         cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2)
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

def flight_time(distance_km: float, speed_kmh: float = 900.0, extra_hours: float = 1.0) -> float:
    return (distance_km / speed_kmh) + extra_hours

def estimate_ticket_price(distance_km: float, flight_hours: float,
                          base_fare: float = 50.0, per_km_rate: float = 0.12, per_hour_rate: float = 40.0) -> float:
    return base_fare + (distance_km * per_km_rate) + (flight_hours * per_hour_rate)

def quantile_bucket(series: pd.Series, k: int = 4) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if s.dropna().nunique() <= 1:
        return pd.Series(0, index=s.index, dtype=int)
    pct = s.rank(method="first", pct=True)
    bins = [0.0, 0.25, 0.50, 0.75, 1.0]
    labels = list(range(k))
    out = pd.cut(pct, bins=bins, labels=labels, include_lowest=True, right=True)
    return pd.to_numeric(out, errors="coerce").fillna(0).astype(int)

def compute_dynamic_costs(base_df: pd.DataFrame, user_lat: float, user_lon: float, user_country: str) -> pd.DataFrame:
    df = base_df.copy()
    df["distance_km"] = df.apply(lambda r: haversine(r["latitude"], r["longitude"], user_lat, user_lon), axis=1)
    df["flight_hours"] = df["distance_km"].apply(flight_time)
    df["ticket_price"] = df.apply(lambda r: estimate_ticket_price(r["distance_km"], r["flight_hours"]), axis=1)
    df["ticket_price_level"] = quantile_bucket(df["ticket_price"], k=4)
    df["final_cost_sum"] = pd.to_numeric(df["budget_level"], errors="coerce").fillna(0) + df["ticket_price_level"]
    df["final_cost_level"] = quantile_bucket(df["final_cost_sum"], k=4)
    df["domestic_intl"] = np.where(
        df["country"].str.lower() == (user_country or "").strip().lower(),
        "domestic", "international"
    )
    return df

def apply_filters(df_costs, climate_df, activities_df,
                  vacation_time, climate_codes, budget_levels,
                  country_pref, distance_buckets, activity_prefs):
    df = df_costs.copy()

    if country_pref in ("domestic", "international"):
        df = df[df["domestic_intl"] == country_pref]

    if distance_buckets:
        mask = pd.Series(False, index=df.index)
        for b in distance_buckets:
            if b == 0: mask |= (df["flight_hours"] < 2)
            elif b == 1: mask |= (df["flight_hours"] >= 2) & (df["flight_hours"] < 4)
            elif b == 2: mask |= (df["flight_hours"] >= 4) & (df["flight_hours"] < 6)
            elif b == 3: mask |= (df["flight_hours"] >= 6) & (df["flight_hours"] < 8)
            elif b == 4: mask |= (df["flight_hours"] >= 8)
        df = df[mask]

    if budget_levels:
        df = df[df["final_cost_level"].isin(budget_levels)]

    if vacation_time and climate_codes:
        climate_sub = climate_df[["id"] + vacation_time].copy()
        ok_ids = climate_sub.apply(lambda row: any((row[s] in climate_codes) for s in vacation_time), axis=1)
        df = df[df["id"].isin(climate_sub.loc[ok_ids, "id"])]
    elif climate_codes:
        seasons = ["Mar-May", "Jun-Aug", "Sep-Nov", "Dec-Feb"]
        climate_sub = climate_df[["id"] + seasons].copy()
        ok_ids = climate_sub.apply(lambda row: any((row[s] in climate_codes) for s in seasons), axis=1)
        df = df[df["id"].isin(climate_sub.loc[ok_ids, "id"])]

    act_map = {
        "beach": "beaches", "nature": "nature", "cuisine": "cuisine",
        "adventure": "adventure", "nightlife": "nightlife", "urban": "urban",
        "culture": "culture", "wellness": "wellness", "seclusion": "seclusion",
    }
    activity_cols = [act_map[a] for a in activity_prefs if a in act_map]
    if activity_cols:
        acts = activities_df[["id"] + activity_cols].copy()
        for col in activity_cols:
            acts = acts[acts[col] > 3]
        df = df[df["id"].isin(acts["id"])]

    out = df.merge(climate_df, on=["id", "city", "country"], how="left")
    out = out.sort_values(by=["final_cost_level", "ticket_price"]).reset_index(drop=True)
    return out

# -------------------------
# API
# -------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/recommend", methods=["POST", "GET", "OPTIONS"])
def recommend():
    if request.method == "GET":
        return jsonify({
            "hint": "Use POST with JSON to this endpoint.",
            "schema": {
                "user_location": {"city":"", "country":"", "latitude":0, "longitude":0},
                "VACATION_TIME": ["Mar-May","Jun-Aug","Sep-Nov","Dec-Feb"],
                "CLIMATE": [0,1,2,3],
                "BUDGET": [0,1,2,3],
                "PREFERENCES": ["beach","nature","cuisine","adventure","nightlife","urban","culture","wellness","seclusion"],
                "COUNTRY": "domestic|international",
                "DISTANCE": [0,1,2,3,4]
            }
        })

    try:
        payload = request.get_json(force=True)
        loc = payload.get("user_location", {}) or {}
        user_country = (loc.get("country") or "").strip()
        user_lat = float(loc.get("latitude"))
        user_lon = float(loc.get("longitude"))

        vacation_time = payload.get("VACATION_TIME") or []
        climate_codes = payload.get("CLIMATE") or []
        budget_levels = payload.get("BUDGET") or []
        activity_prefs = payload.get("PREFERENCES") or []
        country_pref = (payload.get("COUNTRY") or "").strip().lower()
        distance_buckets = payload.get("DISTANCE") or []

        valid_seasons = set(SEASONS_MAP.keys())
        if any(s not in valid_seasons for s in vacation_time):
            return jsonify({"error": f"VACATION_TIME must be in {sorted(valid_seasons)}"}), 400
        if any(c not in (0, 1, 2, 3) for c in climate_codes):
            return jsonify({"error": "CLIMATE must be integers among [0,1,2,3]."}), 400
        if any(b not in (0, 1, 2, 3) for b in budget_levels):
            return jsonify({"error": "BUDGET must be integers among [0,1,2,3]."}), 400
        if any(d not in (0, 1, 2, 3, 4) for d in distance_buckets):
            return jsonify({"error": "DISTANCE must be integers among [0,1,2,3,4]."}), 400

        base_df = df_raw[BASE_KEEP_COLS].copy()
        df_costs = compute_dynamic_costs(base_df, user_lat=user_lat, user_lon=user_lon, user_country=user_country)
        result_df = apply_filters(
            df_costs=df_costs,
            climate_df=climate_df,
            activities_df=activities_df,
            vacation_time=vacation_time,
            climate_codes=climate_codes,
            budget_levels=budget_levels,
            country_pref=country_pref,
            distance_buckets=distance_buckets,
            activity_prefs=activity_prefs
        )

        out_cols = [
            "id", "city", "country",
            "distance_km", "flight_hours",
            "ticket_price", "ticket_price_level",
            "budget_level", "final_cost_sum", "final_cost_level",
            "Mar-May", "Jun-Aug", "Sep-Nov", "Dec-Feb",
            "domestic_intl"
        ]
        out_cols = [c for c in out_cols if c in result_df.columns]
        return jsonify(result_df[out_cols].to_dict(orient="records"))

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------------
# Serve built React app
# -------------------------
@app.route("/__dist_info", methods=["GET"])
def dist_info():
    idx = os.path.join(FRONTEND_DIST, "index.html")
    assets = os.path.join(FRONTEND_DIST, "assets")
    return jsonify({
        "FRONTEND_DIST": FRONTEND_DIST,
        "index_html_exists": os.path.isfile(idx),
        "index_html_mtime": _mtime(idx),
        "assets_dir_exists": os.path.isdir(assets),
        "assets_examples": sorted(os.listdir(assets))[:5] if os.path.isdir(assets) else [],
    })

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    candidate = os.path.join(FRONTEND_DIST, path)
    if path and os.path.isfile(candidate):
        # prevent stale caching during dev
        resp = send_from_directory(FRONTEND_DIST, path)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp
    index_html = os.path.join(FRONTEND_DIST, "index.html")
    if not os.path.isfile(index_html):
        return jsonify({"error": "Frontend build not found", "expected": index_html}), 500
    resp = send_from_directory(FRONTEND_DIST, "index.html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
