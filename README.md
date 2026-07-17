# Firebot 🔥🛰️

A small Discord bot that posts alerts about fires relevant to
**Grand Junction, CO** and its surrounding communities (default: a 100-mile radius,
reaching Ouray and Telluride).

It pulls from two **free** sources and posts **only new, relevant** fires (deduped via a
state file so it never double-posts). To keep the signal high, a newly seen named fire
only alerts once it's a **large fire or growing fast** — smaller fires are tracked
silently until they cross a size/growth threshold (see [Relevance filtering](#relevance-filtering)).

| Source | What it gives you | Notes |
| --- | --- | --- |
| **NIFC WFIGS** | Official named wildfire incidents (name, size, % contained, cause) | No API key. Low noise. |
| **NASA FIRMS** | Satellite thermal hotspots (VIIRS/MODIS) | Free map key. Earliest warning, but noisier. |

It also posts **follow-up updates** when a known incident changes meaningfully (see below).
Delivery is via a **Discord webhook** — no bot token, no gateway connection.

Each alert has two links:
- **Title → the incident page.** For NIFC fires this is the official
  [InciWeb](https://inciweb.wildfire.gov/) page when one exists (matched via InciWeb's
  feed by name + state), otherwise a Google search for the fire. The link is
  recomputed on every run, so an update alert picks up the InciWeb page once one appears.
  > Caveat: InciWeb's feed only lists its ~50 most-recently-updated incidents, so a fire
  > whose page has gone quiet can fall back to the Google search. In practice the fires we
  > alert on are active and significant, so their pages are fresh and matched.
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

## Relevance filtering

Several filters keep alerts focused on fires that matter to the local area:

- **Area** — the query box (`SQUARE_HALF_MILES`) is trimmed to a true great-circle
  `RELEVANCE_RADIUS_MILES` (default 100 mi), so the box corners don't leak in distant fires.
  Set `RELEVANCE_RADIUS_MILES=0` to use the plain square.
- **Size / growth gate (named fires)** — a newly seen NIFC incident only alerts once it
  reaches `NEW_ALERT_MIN_ACRES` (100), **or** is growing ≥ `NEW_ALERT_ACRES_PER_DAY`
  (50 ac/day, with ≥ `NEW_ALERT_GROWTH_FLOOR` acres of real growth) since first seen.
  Smaller fires are tracked silently ("pending") and re-checked each run, so a fast-growing
  small fire alerts within about one poll cycle. Once alerted, the usual
  [update alerts](#update-alerts) take over.
- **Hotspot gate (satellite)** — a FIRMS detection cluster only alerts if it has
  ≥ `FIRMS_MIN_CLUSTER_DETECTIONS` (2) detections, or a single pixel at least
  `FIRMS_SINGLE_DETECTION_MIN_FRP` (50 MW) hot — dropping lone weak-pixel noise.
- **Hotspots near a known fire** — suppressed within a radius scaled to the fire's own
  footprint (`FIRMS_SUPPRESS_NEAR_INCIDENT_MILES` floor + `FIRMS_SUPPRESS_BUFFER_MILES`
  beyond the acreage-derived radius), so a large fire's perimeter detections don't
  double-alert.

## Prerequisites

1. **Discord webhook URL** — in your server: *Server Settings → Integrations → Webhooks → New Webhook*, pick a channel, **Copy Webhook URL**.
2. **NASA FIRMS map key** (only if FIRMS is enabled) — request a free key at
   <https://firms.modaps.eosdis.nasa.gov/api/map_key/>.

## Configuration

All config is via environment variables — see [`.env.example`](.env.example).
Key ones:

- `DISCORD_WEBHOOK_URL` (required)
- `FIRMS_MAP_KEY` (required if FIRMS enabled)
- `CENTER_LAT`, `CENTER_LON`, `SQUARE_HALF_MILES`, `RELEVANCE_RADIUS_MILES` — the alert area (default Grand Junction, 100 mi radius)
- `NEW_ALERT_MIN_ACRES`, `NEW_ALERT_ACRES_PER_DAY`, `NEW_ALERT_GROWTH_FLOOR` — the new-fire size/growth gate
- `POLL_INTERVAL_MIN` — how often the loop runs (default 30)
- `NIFC_INCIDENT_TYPES` — `WF` (wildfires, default), or e.g. `WF,RX` to also include prescribed burns
- `FIRMS_FRP_MIN`, `FIRMS_MIN_CLUSTER_DETECTIONS`, `FIRMS_SINGLE_DETECTION_MIN_FRP`, `FIRMS_SUPPRESS_NEAR_INCIDENT_MILES` — noise controls

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
  ├─ geo.bbox_from_center_half_extent(center, SQUARE_HALF_MILES)  # query box
  ├─ sources.nifc.query_nifc(bbox)        # ArcGIS envelope query, WF only by default
  ├─ sources.firms.query_firms(bbox)      # FIRMS Area CSV + confidence/FRP filters
  ├─ trim to RELEVANCE_RADIUS_MILES       # true circle inside the box
  ├─ size/growth gate on new fires        # small fires held "pending" until they grow
  ├─ dedupe against state.json + suppress/gate hotspots
  ├─ discord.post_embeds(...)             # batches of <=10 embeds
  └─ state.save()                         # after post, plus pending baselines each run
```

## Data sources & limits

- NIFC WFIGS Incident Locations (ArcGIS REST, refreshed ~every 5 min, no key).
- NASA FIRMS Area API: `.../api/area/csv/{KEY}/{SOURCE}/{w,s,e,n}/{days}` — 5000 requests / 10 min.
- Default 30-minute polling is well within all free limits.

## Add later: fire-weather warnings

The National Weather Service API (`https://api.weather.gov/alerts/active`, no key) exposes
Red Flag Warnings / Fire Weather Watches — an easy future source module.
