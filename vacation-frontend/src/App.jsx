import React, { useMemo, useState } from 'react';
import {
  Container, Box, Typography, Stack,
  Button, TextField, MenuItem,
  FormControl, InputLabel, Select, OutlinedInput, Chip,
  Autocomplete, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, Pagination, Divider, Alert, CircularProgress, Tooltip
} from '@mui/material';
import MyLocationIcon from '@mui/icons-material/MyLocation';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:5000/recommend';
console.log('API_URL =', import.meta.env.VITE_API_URL);

/* ====== Options ====== */
const VACATION_TIME_OPTIONS = [
  { label: 'March - May', value: 'Mar-May' },
  { label: 'June - August', value: 'Jun-Aug' },
  { label: 'September - November', value: 'Sep-Nov' },
  { label: 'December - February', value: 'Dec-Feb' },
];

const CLIMATE_OPTIONS = [
  { label: 'Cold', value: 0, desc: 'Under 15°C' },
  { label: 'Moderately cold', value: 1, desc: '15–20°C' },
  { label: 'Moderately Hot', value: 2, desc: '20–25°C' },
  { label: 'Hot', value: 3, desc: '25°C+' },
];

/* Updated cost labels (no Q1/Median text) */
const BUDGET_OPTIONS = [
  { label: 'Low', value: 0 },
  { label: 'Mid-Low', value: 1 },
  { label: 'Mid-High', value: 2 },
  { label: 'High', value: 3 },
];

const PREFERENCE_OPTIONS = [
  { label: 'Beach', value: 'beach' },
  { label: 'Nature', value: 'nature' },
  { label: 'Cuisine', value: 'cuisine' },
  { label: 'Adventure', value: 'adventure' },
  { label: 'Nightlife', value: 'nightlife' },
  { label: 'Urban', value: 'urban' },
  { label: 'Culture', value: 'culture' },
  { label: 'Wellness', value: 'wellness' },
];

const COUNTRY_OPTIONS = [
  { label: 'Domestic', value: 'domestic' },
  { label: 'International', value: 'international' },
];

const DISTANCE_OPTIONS = [
  { label: '<2 hour flight', value: 0 },
  { label: '2–4 hour flight', value: 1 },
  { label: '4–6 hour flight', value: 2 },
  { label: '6–8 hour flight', value: 3 },
  { label: '8+ hour flight', value: 4 },
];

/* ====== Helpers ====== */
const km = (n) => `${Math.round(n).toLocaleString()} km`;
const hours = (n) => `${Number(n).toFixed(1)} h`;

const climateCodeToText = (code) => {
  const hit = CLIMATE_OPTIONS.find(o => o.value === code);
  return hit ? `${hit.label} (${hit.desc})` : 'n/a';
};

/* Map numeric final_cost_level -> label */
const costLabel = (n) => {
  const hit = BUDGET_OPTIONS.find(o => o.value === Number(n));
  return hit?.label ?? '—';
};

/* Tooltip text for Estimated Cost */
const tooltipContent =
  `How we compute Estimated Cost:
1) Compute flight distance from your location (Haversine) → flight hours.
2) Estimate ticket cost and bucket it into four groups (0–3) using quartiles.
3) Add the city's base budget_level (0–2).
4) Re-bucket the sum into four groups → Low / Mid-Low / Mid-High / High.`;

export default function App() {
  /* ====== Form state ====== */
  const [vacationTime, setVacationTime] = useState([]); // ['Mar-May', ...]
  const [climate, setClimate] = useState([]);           // [0..3]
  const [budget, setBudget] = useState([]);             // [0..3]
  const [preferences, setPreferences] = useState([]);   // ['beach', ...]
  const [country, setCountry] = useState('');           // 'domestic'|'international'
  const [distance, setDistance] = useState([]);         // [0..4]

  // user location (required by backend)
  const [city, setCity] = useState('Seoul');
  const [countryName, setCountryName] = useState('Korea, Republic of');
  const [lat, setLat] = useState(37.5665);
  const [lon, setLon] = useState(126.9780);

  /* ====== Query/result state ====== */
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState(1);
  const rowsPerPage = 10;

  const totalPages = Math.max(1, Math.ceil(rows.length / rowsPerPage));
  const pageRows = useMemo(() => {
    const start = (page - 1) * rowsPerPage;
    return rows.slice(start, start + rowsPerPage);
  }, [rows, page]);

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      setErr('Geolocation not supported in this browser.');
      return;
    }
    setErr('');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude);
        setLon(pos.coords.longitude);
      },
      (e) => setErr(`Failed to get location: ${e.message}`)
    );
  };

  const handleSubmit = async () => {
    setLoading(true);
    setErr('');
    setRows([]);
    setPage(1);

    try {
      const payload = {
        user_location: {
          city: city || '',
          country: countryName || '',
          latitude: lat,
          longitude: lon
        },
        VACATION_TIME: vacationTime,
        CLIMATE: climate,
        BUDGET: budget,
        PREFERENCES: preferences,
        COUNTRY: country,
        DISTANCE: distance
      };

      const res = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const msg = await res.json().catch(() => ({}));
        throw new Error(msg?.error || `Request failed (${res.status})`);
      }

      const data = await res.json();
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  /* ====== Render ====== */
  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" sx={{ mb: 2, fontWeight: 700 }}>
        Vacation Recommender
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Fill the form and get destinations matching your preferences. Results are paginated (10 per page).
      </Typography>

      <Paper sx={{ p: 3, mb: 3 }}>
        <Stack spacing={2}>
          {/* Location block */}
          <Typography variant="h6">Your Location</Typography>
          <Stack direction="row" spacing={2}>
            <TextField label="City" value={city} onChange={e => setCity(e.target.value)} fullWidth />
            <TextField label="Country" value={countryName} onChange={e => setCountryName(e.target.value)} fullWidth />
          </Stack>
          <Stack direction="row" spacing={2} alignItems="center">
            <TextField
              label="Latitude"
              type="number"
              value={lat}
              onChange={e => setLat(Number(e.target.value))}
              fullWidth
            />
            <TextField
              label="Longitude"
              type="number"
              value={lon}
              onChange={e => setLon(Number(e.target.value))}
              fullWidth
            />
            <Button variant="outlined" startIcon={<MyLocationIcon />} onClick={useMyLocation}>
              Use my location
            </Button>
          </Stack>

          <Divider sx={{ my: 2 }} />

          {/* VACATION_TIME */}
          <FormControl fullWidth>
            <InputLabel>Vacation Time</InputLabel>
            <Select
              multiple
              value={vacationTime}
              onChange={(e) => setVacationTime(e.target.value)}
              input={<OutlinedInput label="Vacation Time" />}
              renderValue={(selected) => (
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {selected.map((v) => {
                    const o = VACATION_TIME_OPTIONS.find(x => x.value === v);
                    return <Chip key={v} label={o?.label ?? v} />;
                  })}
                </Box>
              )}
            >
              {VACATION_TIME_OPTIONS.map(o => (
                <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* CLIMATE */}
          <FormControl fullWidth>
            <InputLabel>Climate</InputLabel>
            <Select
              multiple
              value={climate}
              onChange={(e) => setClimate(e.target.value)}
              input={<OutlinedInput label="Climate" />}
              renderValue={(selected) => (
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {selected.map((v) => {
                    const o = CLIMATE_OPTIONS.find(x => x.value === v);
                    return <Chip key={v} label={`${o?.label} (${o?.desc})`} />;
                  })}
                </Box>
              )}
            >
              {CLIMATE_OPTIONS.map(o => (
                <MenuItem key={o.value} value={o.value}>{o.label} — {o.desc}</MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* BUDGET (final cost level) */}
          <FormControl fullWidth>
            <InputLabel>Budget (final cost level)</InputLabel>
            <Select
              multiple
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              input={<OutlinedInput label="Budget (final cost level)" />}
              renderValue={(selected) => (
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {selected.map((v) => {
                    const o = BUDGET_OPTIONS.find(x => x.value === v);
                    return <Chip key={v} label={o?.label ?? v} />;
                  })}
                </Box>
              )}
            >
              {BUDGET_OPTIONS.map(o => (
                <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* PREFERENCES */}
          <Autocomplete
            multiple
            options={PREFERENCE_OPTIONS}
            getOptionLabel={(o) => o.label}
            onChange={(_, newVal) => setPreferences(newVal.map(v => v.value))}
            renderInput={(params) => <TextField {...params} label="Preferences" placeholder="Select one or more" />}
          />

          {/* COUNTRY */}
          <FormControl fullWidth>
            <InputLabel>Country Preference</InputLabel>
            <Select
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              input={<OutlinedInput label="Country Preference" />}
            >
              {COUNTRY_OPTIONS.map(o => (
                <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* DISTANCE */}
          <FormControl fullWidth>
            <InputLabel>Distance (flight time)</InputLabel>
            <Select
              multiple
              value={distance}
              onChange={(e) => setDistance(e.target.value)}
              input={<OutlinedInput label="Distance (flight time)" />}
              renderValue={(selected) => (
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {selected.map((v) => {
                    const o = DISTANCE_OPTIONS.find(x => x.value === v);
                    return <Chip key={v} label={o?.label ?? v} />;
                  })}
                </Box>
              )}
            >
              {DISTANCE_OPTIONS.map(o => (
                <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* Submit */}
          <Stack direction="row" spacing={2} alignItems="center">
            <Button variant="contained" onClick={handleSubmit} disabled={loading}>
              {loading ? 'Loading…' : 'Find Destinations'}
            </Button>
            {loading && <CircularProgress size={24} />}
          </Stack>

          {err && <Alert severity="error">{err}</Alert>}
        </Stack>
      </Paper>

      {/* Results */}
      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>Results</Typography>
        <TableContainer component={Paper}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>City</TableCell>
                <TableCell>Country</TableCell>
                <TableCell>Activities</TableCell>
                <TableCell>
                  <Tooltip
                    title={<Box sx={{ whiteSpace: 'pre-line' }}>{tooltipContent}</Box>}
                    placement="top"
                    arrow
                  >
                    <span>Estimated Cost</span>
                  </Tooltip>
                </TableCell>
                <TableCell>Distance</TableCell>
                <TableCell>Flight Hours</TableCell>
                <TableCell>Avg Temp (selected season)</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {pageRows.map((r, idx) => {
                const acts = preferences.length
                  ? preferences.map(v => PREFERENCE_OPTIONS.find(p => p.value === v)?.label).filter(Boolean).join(', ')
                  : '—';

                let tempText = 'n/a';
                if (vacationTime.length) {
                  const chosenSeason = vacationTime[0];
                  tempText = climateCodeToText(r[chosenSeason]);
                }

                return (
                  <TableRow key={`${r.id}-${idx}`}>
                    <TableCell>{r.city}</TableCell>
                    <TableCell>{r.country}</TableCell>
                    <TableCell>{acts || '—'}</TableCell>
                    {/* mapped label instead of number */}
                    <TableCell>{costLabel(r.final_cost_level)}</TableCell>
                    <TableCell>{r.distance_km != null ? km(r.distance_km) : '—'}</TableCell>
                    <TableCell>{r.flight_hours != null ? hours(r.flight_hours) : '—'}</TableCell>
                    <TableCell>{tempText}</TableCell>
                  </TableRow>
                );
              })}
              {pageRows.length === 0 && !loading && (
                <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                    No results yet. Submit the form to see destinations.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>

        <Stack alignItems="center" sx={{ mt: 2 }}>
          <Pagination
            count={totalPages}
            page={page}
            onChange={(_, p) => setPage(p)}
            color="primary"
          />
        </Stack>

        {/* Kaggle citation */}
        <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
          Source: Kaggle — “Worldwide Travel Cities: Ratings and Climate” by furkanima.{' '}
          <a
            href="https://www.kaggle.com/datasets/furkanima/worldwide-travel-cities-ratings-and-climate"
            target="_blank"
            rel="noreferrer"
          >
            View dataset
          </a>.
        </Typography>
      </Paper>
    </Container>
  );
}
