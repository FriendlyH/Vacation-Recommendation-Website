# app.py
from __future__ import annotations

import json
import logging
import os
import time
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = Path(
    os.getenv("FRONTEND_DIST", ROOT / "templates/vacation-frontend/dist")
)
DATA_PATH = Path(
    os.getenv("TRAVEL_DATA_PATH", ROOT / "travel.csv")
)

DEV_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# ------------------------------------------------------------------------------
# App
# ------------------------------------------------------------------------------
app = Flask(__name__, static_folder=None)
CORS(
    app,
    resources={
        r"/health": {"origins": list(DEV_ORIGINS)},
        r"/recommend": {"origins": list(DEV_ORIGINS)},
    },
)

# ------------------------------------------------------------------------------
# Helpers / data prep
# ------------------------------------------------------------------------------
SEASONS_MAP: Dict[str, List[int]] = {
    "Mar-May": [3, 4, 5],
    "Jun-Aug": [6, 7, 8],
    "Sep-Nov": [9, 10, 11],
    "Dec-Feb": [12, 1, 2],
}

BASE_KEEP_COLS = [
    "id",
    "city",
    "country",
    "latitude",
    "longitude",
    "budget_level",
    "culture",
    "adventure",
    "nature",
    "beaches",
    "nightlife",
    "cuisine",
    "wellness",
    "urban",
    "seclusion",
]

ACT_KEYMAP = {
    "beach": "beaches",
    "nature": "nature",
    "cuisine": "cuisine",
    "adventure": "adventure",
    "nightlife": "nightlife",
    "urban": "urban",
    "culture": "culture",
    "wellness": "wellness",
    "seclusion": "seclusion",
}

def _mtime(p: Path) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))
    except Exception:
        return "N/A"

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

def flight_time(distance_km: float, speed_kmh: float = 900.0, extra_hours: float = 1.0) -> float:
    return (distance_km / speed_kmh) + extra_hours

def estimate_ticket_price(
    distance_km: float,
    flight_hours: float,
    base_fare: float = 50.0,
    per_km_rate: float = 0.12,
    per_hour_rate: float = 40.0,
) -> float:
    return base_fare + (distance_km * per_km_rate) + (flight_hours * per_hour_rate)

def quantile_bucket(series: pd.Series, k: int = 4) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if s.dropna().nunique() <= 1:
        return pd.Series(0, index=s.index, dtype=int)
    pct = s.rank(method="first", pct=True)
    bins = [i / k for i in range(k)] + [1.0]
    out = pd.cut(pct, bins=bins, labels=list(range(k)), include_lowest=True, right=True)
    return pd.to_numeric(out, errors="coerce").fillna(0).astype(int)

def temp_to_code(t: float) -> int:
    if pd.isna(t):
        return 0
    if t < 15:
        return 0
    if t < 20:
        return 1
    if t < 25:
        return 2
    return 3

def _load_monthlies(cell: str) -> dict:
    try:
        return json.loads(cell)
    except Exception:
        return {}

def load_data(csv_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if not csv_path.exists():
        raise FileNotFoundError(f"travel dataset not found: {csv_path}")
    df = pd.read_csv(csv_path)
    df["id"] = df.index

    # normalize budget
    budget_map = {"Budget": 0, "Mid-range": 1, "Luxury": 2}
    df["budget_level"] = df["budget_level"].map(budget_map)

    # climate codes by season
    temps = df["avg_temp_monthly"].apply(_load_monthlies)
    flat = pd.json_normalize(temps)
    avg_cols = [c for c in flat.columns if c.endswith(".avg")]
    monthly_df = flat[avg_cols].copy() if len(avg_cols) else pd.DataFrame(index=df.index)
    if not monthly_df.empty:
        monthly_df.columns = [int(c.split(".")[0]) for c in avg_cols]

    for season, months in SEASONS_MAP.items():
        if monthly_df.empty or not all(m in monthly_df.columns for m in months):
            df[season] = 0
        else:
            df[season] = monthly_df[months].mean(axis=1).apply(temp_to_code)

    climate_df = df[["id", "city", "country", *SEASONS_MAP.keys()]].copy()
    activities_df = df[
        [
            "id",
            "city",
            "country",
            "culture",
            "adventure",
            "nature",
            "beaches",
            "nightlife",
            "cuisine",
            "wellness",
            "urban",
            "seclusion",
        ]
    ].copy()

    return df, climate_df, activities_df

def compute_dynamic_costs(
    base_df: pd.DataFrame, user_lat: float, user_lon: float, user_country: str
) -> pd.DataFrame:
    df = base_df.copy()
    df["distance_km"] = df.apply(
        lambda r: haversine(r["latitude"], r["longitude"], user_lat, user_lon), axis=1
    )
    df["flight_hours"] = df["distance_km"].apply(flight_time)
    df["ticket_price"] = df.apply(
        lambda r: estimate_ticket_price(r["distance_km"], r["flight_hours"]), axis=1
    )
    df["ticket_price_level"] = quantile_bucket(df["ticket_price"], k=4)

    df["final_cost_sum"] = (
        pd.to_numeric(df["budget_level"], errors="coerce").fillna(0)
        + df["ticket_price_level"]
    )
    df["final_cost_level"] = quantile_bucket(df["final_cost_sum"], k=4)

    uc = (user_country or "").strip().lower()
    df["domestic_intl"] = np.where(df["country"].str.lower() == uc, "domestic", "international")
    return df

def apply_filters(
    df_costs: pd.DataFrame,
    climate_df: pd.DataFrame,
    activities_df: pd.DataFrame,
    vacation_time: List[str],
    climate_codes: List[int],
    budget_levels: List[int],
    country_pref: str,
    distance_buckets: List[int],
    activity_prefs: List[str],
) -> pd.DataFrame:
    df = df_costs.copy()

    # country
    if country_pref in {"domestic", "international"}:
        df = df[df["domestic_intl"] == country_pref]

    # distance
    if distance_buckets:
        mask = pd.Series(False, index=df.index)
        for b in distance_buckets:
            if b == 0:
                mask |= df["flight_hours"] < 2
            elif b == 1:
                mask |= (df["flight_hours"] >= 2) & (df["flight_hours"] < 4)
            elif b == 2:
                mask |= (df["flight_hours"] >= 4) & (df["flight_hours"] < 6)
            elif b == 3:
                mask |= (df["flight_hours"] >= 6) & (df["flight_hours"] < 8)
            elif b == 4:
                mask |= df["flight_hours"] >= 8
        df = df[mask]

    # budget
    if budget_levels:
        df = df[df["final_cost_level"].isin(budget_levels)]

    # climate
    if climate_codes:
        seasons = vacation_time or list(SEASONS_MAP.keys())
        climate_sub = climate_df[["id", *seasons]].copy()
        ok_ids = climate_sub.apply(
            lambda row: any((row[s] in climate_codes) for s in seasons), axis=1
        )
        df = df[df["id"].isin(climate_sub.loc[ok_ids, "id"])]

    # activities (threshold > 3)
    activity_cols = [ACT_KEYMAP[a] for a in activity_prefs if a in ACT_KEYMAP]
    if activity_cols:
        acts = activities_df[["id", *activity_cols]].copy()
        for col in activity_cols:
            acts = acts[acts[col] > 3]
        df = df[df["id"].isin(acts["id"])]

    out = df.merge(climate_df, on=["id", "city", "country"], how="left")
    return out.sort_values(by=["final_cost_level", "ticket_price"]).reset_index(drop=True)

def _round_cols(df: pd.DataFrame, cols: Iterable[str], ndigits: int = 2) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = df[c].round(ndigits)
    return df

# ------------------------------------------------------------------------------
# Load data once
# ------------------------------------------------------------------------------
logging.info("Frontend dist: %s | index.html=%s (mtime: %s)",
             FRONTEND_DIST, FRONTEND_DIST.joinpath("index.html").exists(),
             _mtime(FRONTEND_DIST / "index.html"))

try:
    df_raw_full, climate_df, activities_df = load_data(DATA_PATH)
    df_raw_full["id"] = df_raw_full.index
    df_raw = df_raw_full[BASE_KEEP_COLS].copy()
    logging.info("Loaded data: %s rows from %s", len(df_raw_full), DATA_PATH)
except Exception as e:
    logging.exception("Failed to load data")
    raise

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.get("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/recommend", methods=["POST", "GET", "OPTIONS"])
def recommend():
    if request.method == "GET":
        return jsonify(
            {
                "hint": "POST JSON to this endpoint.",
                "schema": {
                    "user_location": {
                        "city": "",
                        "country": "",
                        "latitude": 0,
                        "longitude": 0,
                    },
                    "VACATION_TIME": list(SEASONS_MAP.keys()),
                    "CLIMATE": [0, 1, 2, 3],
                    "BUDGET": [0, 1, 2, 3],
                    "PREFERENCES": list(ACT_KEYMAP.keys()),
                    "COUNTRY": "domestic|international",
                    "DISTANCE": [0, 1, 2, 3, 4],
                },
            }
        )

    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    try:
        loc = payload.get("user_location") or {}
        user_country = (loc.get("country") or "").strip()
        user_lat = float(loc.get("latitude"))
        user_lon = float(loc.get("longitude"))

        vacation_time = payload.get("VACATION_TIME") or []
        climate_codes = payload.get("CLIMATE") or []
        budget_levels = payload.get("BUDGET") or []
        activity_prefs = payload.get("PREFERENCES") or []
        country_pref = (payload.get("COUNTRY") or "").strip().lower()
        distance_buckets = payload.get("DISTANCE") or []

        # basic validation
        valid_seasons = set(SEASONS_MAP.keys())
        if any(s not in valid_seasons for s in vacation_time):
            return jsonify({"error": f"VACATION_TIME must be in {sorted(valid_seasons)}"}), 422
        if any(c not in (0, 1, 2, 3) for c in climate_codes):
            return jsonify({"error": "CLIMATE must be integers among [0,1,2,3]."}), 422
        if any(b not in (0, 1, 2, 3) for b in budget_levels):
            return jsonify({"error": "BUDGET must be integers among [0,1,2,3]."}), 422
        if any(d not in (0, 1, 2, 3, 4) for d in distance_buckets):
            return jsonify({"error": "DISTANCE must be integers among [0,1,2,3,4]."}), 422

        base_df = df_raw.copy()
        df_costs = compute_dynamic_costs(
            base_df, user_lat=user_lat, user_lon=user_lon, user_country=user_country
        )
        result_df = apply_filters(
            df_costs=df_costs,
            climate_df=climate_df,
            activities_df=activities_df,
            vacation_time=vacation_time,
            climate_codes=climate_codes,
            budget_levels=budget_levels,
            country_pref=country_pref,
            distance_buckets=distance_buckets,
            activity_prefs=activity_prefs,
        )

        out_cols = [
            "id",
            "city",
            "country",
            "distance_km",
            "flight_hours",
            "ticket_price",
            "ticket_price_level",
            "budget_level",
            "final_cost_sum",
            "final_cost_level",
            "Mar-May",
            "Jun-Aug",
            "Sep-Nov",
            "Dec-Feb",
            "domestic_intl",
        ]
        out = result_df[[c for c in out_cols if c in result_df.columns]].copy()
        out = _round_cols(out, ["distance_km", "flight_hours", "ticket_price"])
        return jsonify(out.to_dict(orient="records"))

    except Exception as e:
        logging.exception("recommend error")
        return jsonify({"error": str(e)}), 500

@app.get("/__dist_info")
def dist_info():
    assets_dir = FRONTEND_DIST / "assets"
    return jsonify(
        {
            "FRONTEND_DIST": str(FRONTEND_DIST),
            "index_html_exists": (FRONTEND_DIST / "index.html").is_file(),
            "index_html_mtime": _mtime(FRONTEND_DIST / "index.html"),
            "assets_dir_exists": assets_dir.is_dir(),
            "assets_examples": sorted(os.listdir(assets_dir))[:5] if assets_dir.is_dir() else [],
        }
    )

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path: str):
    """
    Serve prebuilt SPA from FRONTEND_DIST. No aggressive caching in dev.
    """
    candidate = FRONTEND_DIST / path
    if path and candidate.is_file():
        resp = send_from_directory(str(FRONTEND_DIST), path)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    index_html = FRONTEND_DIST / "index.html"
    if not index_html.is_file():
        return (
            jsonify(
                {
                    "error": "Frontend build not found",
                    "expected": str(index_html),
                }
            ),
            500,
        )
    resp = send_from_directory(str(FRONTEND_DIST), "index.html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp

# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", 5000)), debug=True)
