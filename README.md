# Vacation Recommendation Website
#### Video Demo: https://youtu.be/9M5hcfIUcYo
## 1. What It Does
The Vacation Recommendation Website helps users instantly discover travel destinations that fit their preferred **season, climate, budget, activities, and travel distance**.  
It condenses data from weather statistics, cost estimates, and location details into a single filtered recommendation list, so users can decide where to go in just a few clicks.

I designed the background color to be **light blue** to reflect the excitement and freshness people often feel when planning a vacation. This subtle design choice sets the tone of the app before any interaction.

### Key Features
- **Destination filtering** by:
  - Vacation time (seasonal range)
  - Climate (temperature range)
  - Budget (local cost + estimated flight cost)
  - Preferences (beach, culture, nightlife, etc.)
  - Country type (domestic vs. international)
  - Distance (flight time categories)
- Flight cost level estimation based on calculated flight durations
- Final cost score from combined ticket price and destination budget level
- Instant UI updates after user input

### Inputs
- Vacation Time (multi-select)  
- Climate (multi-select)  
- Budget (multi-select)  
- Preferences (multi-select)  
- Country (select)  
- Distance (multi-select)  

---

## 2. Why I Made Certain Choices

1. **Dataset selection** – I chose a Kaggle dataset because it had **clean, structured data** with destination IDs, activity tags, and cost levels already assigned. This reduced preprocessing time and made it easier to integrate with my filtering logic.

2. **Seasonal naming** – Instead of “Spring,” “Summer,” etc., I used explicit month ranges like **March–May** and **June–August**. This is because the Southern Hemisphere experiences opposite seasons; using month ranges ensures accuracy regardless of location.

3. **Quartile-based cost levels** – Flight costs account for a significant portion of vacation expenses. According to NerdWallet, they average **36%** of the total trip cost. I treated **destination cost** and **flight price** as equally important, summing their levels and then quartiling again to produce the **final cost level (0–3)**.

---

## 3. How It Works & Tech Stack

### Frontend (React + MUI)
Located in `/templates/vacation-frontend/src`  

Built with **React** and styled using **Material-UI**.

**Main files:**
- `App.jsx` — Handles user inputs, sends requests to backend, renders results
- `main.jsx` — React entry point, mounts the app
- `App.css` & `index.css` — Custom styling (including the light blue background)

**Workflow:**
1. User selects filters in `App.jsx`
2. On submit, frontend sends a JSON payload to Flask’s `/recommend` endpoint
3. Flask returns a filtered destination list in JSON
4. React dynamically updates the display

---

### Backend (Python + Flask)
**Main file:** `app.py`

**Routes:**
- `/recommend` — Accepts POST/GET with filters, applies algorithm, returns matching destinations
- `/health` — Simple health check
- `/` — Serves the built React frontend (`index.html`) in production  
  The `/` route first tries to serve the requested static file; if it doesn’t exist, it falls back to serving `index.html`. This allows React Router (if added) to handle front-end navigation.

---

## 4. Data Processing

1. **Mapping categories to numeric codes** – e.g., `budget_level`: Budget → 0, Mid-range → 1, Luxury → 2
2. **Parsing temperatures** – Monthly averages (JSON) → seasonal means, then mapped to codes:
   - `<15°C` → 0  
   - `15–20°C` → 1  
   - `20–25°C` → 2  
   - `25°C+` → 3
3. **Distance & flight time** – Haversine formula to compute km from user location → flight time estimate
4. **Ticket price estimation** – Base fare + per-km rate + per-hour rate
5. **Cost quartiling** – Ticket price and final cost levels binned into 4 categories using quartiles
6. **Filtering** – Apply user’s selections for:
   - Season & climate
   - Budget & final cost level
   - Domestic/international
   - Distance buckets
   - Activity preferences (only destinations with matching activities rated >3)

---

## 5. Migration: Python Script → Flask API

The original code was a pure Python script:
- Loaded dataset
- Asked for user inputs via `input()`
- Applied filters
- Printed matching destinations

To make it web-ready:
1. Removed `input()` calls and replaced them with JSON payload parsing
2. Wrapped core functions into modular helpers:
   - `compute_dynamic_costs()` — adds distance, flight time, ticket price levels, and final cost levels
   - `apply_filters()` — applies user preferences to the dataset
3. Added Flask routes:
   - `/recommend` to handle filtering requests
   - `/` to serve the React frontend in production
4. Configured **CORS** so local React dev server could call Flask API
5. Ensured API responses are JSON-serializable (converted DataFrames to dicts)

---

## 6. Why Quartiles?

Both flight and destination costs vary widely between locations. A raw numerical filter would skew towards extremes, but quartiling:
- Normalizes scales  
- Ensures even distribution across categories  
- Matches common UX patterns (Low, Mid-Low, Mid-High, High)

This makes results more interpretable and fair.

---

## 7. Installation & Usage

```bash
# Clone repository
git clone https://github.com/FriendlyH/vacation-recommendation.git
cd vacation-recommendation

# Backend setup
pip install -r requirements.txt
python app.py

# Frontend setup
cd templates/vacation-frontend
npm install
npm run dev
