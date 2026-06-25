# Firebot 🔥🛰️

A small Discord bot that posts alerts about fires in a configurable square around
**Grand Junction, CO** (default: 300 miles from center to each edge).

It pulls from two **free** sources and posts **only new** fires (deduped via a state
file so it never double-posts):

| Source | What it gives you | Notes |
| --- | --- | --- |
| **NIFC WFIGS** | Official named wildfire incidents (name, size, % contained, cause) | No API key. Low noise. |
| **NASA FIRMS** | Satellite thermal hotspots (VIIRS/MODIS) | Free map key. Earliest warning, but noisier. |

It also posts **follow-up updates** when a known incident changes meaningfully (see below).
Delivery is via a **Discord webhook** — no bot token, no gateway connection.

Each alert has two links:
- **Title → the incident page.** For NIFC fires this is the official
  [InciWeb](https://inciweb.wildfire.gov/) page when one exists (matched via InciWeb's
  feed by name + state), otherwise a Google search for the fire.
- **📍 Coordinates → a map.** NIFC incidents link to the
  [AirNow Fire & Smoke Map](https://fire.airnow.gov/) (fire + smoke/air quality);
  FIRMS hotspots link to the [NASA FIRMS Fire Map](https://firms.modaps.eosdis.nasa.gov/map/)
  (the satellite detections). Link zoom is set by `MAP_LINK_ZOOM`.

## Update alerts

Beyond the first "new fire" alert, Firebot re-posts an update when a tracked NIFC
incident changes past a threshold (measured since the *last* alert, so growth
accumulates rather than resetting each run):

- **📈 Growth** — acreage rose by ≥ `UPDATE_ACRES_PCT` (25%) **or** ≥ `UPDATE_ACRES_ABS`
  (100 acres). The percent path also needs ≥ `UPDATE_ACRES_PCT_FLOOR` (10) acres of
  real growth, so tiny fires don't spam.
- **🧭 Containment** — % contained moved by ≥ `UPDATE_CONTAINMENT_DELTA` (20 points).
- **✅ Out / contained** — a one-time final alert when the fire is declared out or 100% contained.

Each toggle (`UPDATE_ON_GROWTH`, `UPDATE_ON_CONTAINMENT`, `UPDATE_ON_OUT`) and all
thresholds are configurable; set `ENABLE_INCIDENT_UPDATES=false` to get only first-sighting alerts.
FIRMS hotspots are one-shot (a satellite pixel has no stable identity to track).

> Note: the "out / contained" alert is best-effort — once a fire is fully resolved,
> NIFC may drop it from the *current* incidents feed before we observe the transition.

## Prerequisites

1. **Discord webhook URL** — in your server: *Server Settings → Integrations → Webhooks → New Webhook*, pick a channel, **Copy Webhook URL**.
2. **NASA FIRMS map key** (only if FIRMS is enabled) — request a free key at
   <https://firms.modaps.eosdis.nasa.gov/api/map_key/>.

## Configuration

All config is via environment variables — see [`.env.example`](.env.example).
Key ones:

- `DISCORD_WEBHOOK_URL` (required)
- `FIRMS_MAP_KEY` (required if FIRMS enabled)
- `CENTER_LAT`, `CENTER_LON`, `SQUARE_HALF_MILES` — the alert area (default Grand Junction, 300 mi)
- `POLL_INTERVAL_MIN` — how often the loop runs (default 30)
- `NIFC_INCIDENT_TYPES` — `WF` (wildfires, default), or e.g. `WF,RX` to also include prescribed burns
- `FIRMS_FRP_MIN`, `FIRMS_KEEP_LOW_CONFIDENCE`, `FIRMS_SUPPRESS_NEAR_INCIDENT_MILES` — noise controls

## Run locally

```bash
pip install -r requirements.txt
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
export FIRMS_MAP_KEY="your_key"      # optional; omit + ENABLE_FIRMS=false for NIFC-only

# 1. Confirm the webhook works
python -m firebot.main --test

# 2. See what would post without posting (and without touching state)
python -m firebot.main --once --dry-run

# 3. Real single pass
python -m firebot.main --once

# 4. Run forever (what the container does)
python -m firebot.main --loop
```

State is written to `STATE_PATH` (default `/data/state.json`; set it to `./data/state.json` locally).

## Deploy on Coolify

1. Create a new **Application** from this repo (or build the included `Dockerfile`).
2. Add **Persistent Storage** mounted at **`/data`** so `state.json` survives redeploys.
3. Set **Environment Variables** (`DISCORD_WEBHOOK_URL`, `FIRMS_MAP_KEY`, any overrides);
   mark the secrets as such.
4. Deploy. The default `CMD` runs `--loop`, self-scheduling every `POLL_INTERVAL_MIN`.

**Alternative (cron instead of a loop):** set the container command to `--once` and use a
Coolify **Scheduled Task** with cron `*/30 * * * *`.

### Auto-deploy

Pushes to `main` redeploy automatically: a GitHub push webhook notifies Coolify (the
app has **Auto Deploy** enabled). Just `git push` and Coolify rebuilds + restarts.

## How it works

```
main.run_once()
  ├─ geo.bbox_from_center_half_extent(center, SQUARE_HALF_MILES)  # the square IS the filter
  ├─ sources.nifc.query_nifc(bbox)        # ArcGIS envelope query, WF only by default
  ├─ sources.firms.query_firms(bbox)      # FIRMS Area CSV + confidence/FRP filters
  ├─ dedupe against state.json + suppress hotspots near known incidents
  ├─ discord.post_embeds(...)             # batches of <=10 embeds
  └─ state.save()                         # only after a successful post
```

## Data sources & limits

- NIFC WFIGS Incident Locations (ArcGIS REST, refreshed ~every 5 min, no key).
- NASA FIRMS Area API: `.../api/area/csv/{KEY}/{SOURCE}/{w,s,e,n}/{days}` — 5000 requests / 10 min.
- Default 30-minute polling is well within all free limits.

## Add later: fire-weather warnings

The National Weather Service API (`https://api.weather.gov/alerts/active`, no key) exposes
Red Flag Warnings / Fire Weather Watches — an easy future source module.
