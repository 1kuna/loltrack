LoL Stat-Tracker (Web)

Local web app (FastAPI + React) that tracks the League metrics you care about: early-game CS & deaths, lane diffs @10, warding discipline, and recall hygiene — with a live in-game panel and rolling post-game trends.

Quick Start (macOS/Linux)
- Prereqs: Python 3.11+, Node 20+
- Start dev: `scripts/start.sh` (runs Vite on 5173 + FastAPI on 8787)
- Open: http://localhost:5173 (dev) or http://127.0.0.1:8787 (prod)
- Stop: `scripts/stop.sh`

Quick Start (Windows)
- Prereqs: Python 3.11+, Node 20+
- Start dev: `scripts\start.ps1`
- Stop: `scripts\stop.ps1`

On first run
- Go to Settings → paste Riot API key (dev key) and Riot ID (GameName#TAG)
- Click Dashboard → if empty, click Sync in Settings or run `POST /api/sync/pull?since=7d`

CLI
- The legacy CLI has been removed. Use the web app (Settings → add key/ID → Sync) or call the HTTP APIs directly.

Config
- Server-side YAML at OS-specific path:
  - Windows: %APPDATA%/loltrack/config.yaml
  - macOS: ~/Library/Application Support/loltrack/config.yaml
  - Linux: ~/.config/loltrack/config.yaml

Notes
- Live Client API is at https://127.0.0.1:2999 (self-signed). The backend disables SSL verification for this localhost endpoint only.
- Data is stored locally in SQLite with rolling windows cached for quick dashboards.

## Generalized Improvement Score (GIS)

GIS provides a stable 0–100 improvement score, per-domain breakdowns, and clear “what to fix” guidance. It is role- and queue-aware, scoped per (queue, role), and only uses ranked SR (Solo/Duo 420, Flex 440) for scoring and gating.

Key properties:
- Personal baselines: EWMA mean/variance per metric; robust z-scores with Huber clipping.
- Domains: Laning, Economy, Damage, Objectives, Vision, Discipline, Macro → each 0–100 per match; then smoothed.
- Overall GIS: role-weighted blend of domain inst scores; per‑match delta clamped to ±6.
- Patch easing: widen Huber clamp for the first 3 matches after a `gameVersion`/patch change.
- Champion mastery guardrail: cap per-match negative domain impact when champion mastery is low (knob `gis.maxNegativeImpactLowMastery`, default 3.0).

### Calibration & Gating

Gating is computed per (queue, role) and only counts ranked SR matches.

- Stage 0 (≤4 ranked SR matches):
  - GIS number hidden; show “Calibrating”.
  - Achilles/secondary suppressed.
- Stage 1 (5–7):
  - GIS visible with “Calibrating” chip; confidence band shown.
  - Achilles/secondary suppressed.
- Stage 2 (≥8):
  - GIS normal; Achilles surfaces only when all hold:
    - Confidence band ≤ ±6 pts
    - EWMA domain deficit ≤ −4.0
    - Primary beats runner‑up by ≥ 2.0 for 3 consecutive matches (hysteresis)
  - Secondary issues require ≥ 8 and ≤ −2.0.

Knobs in `config.yaml` (created in your user config directory):

```
gis:
  minMatchesForGIS: 5
  minMatchesForFocus: 8
  minPrimaryGap: -4.0
  minPrimaryLead: 2.0
  hysteresisMatches: 3
  maxBandForFocus: 6.0
  secondaryGap: -2.0
  rankedQueues: [420, 440]
  maxNegativeImpactLowMastery: 3.0
```

### API: Summary

GET `/api/gis/summary?queue=420&role=JUNGLE`

Returns (envelope omitted):

```
{
  "schema_version": "gis.v1",
  "context": { "queue": 420, "role": "JUNGLE" },
  "overall": 52.3,
  "domains": { "laning": 48.1, "vision": 54.0, ... },
  "delta5": 1.4,
  "confidence_band": 4.8,
  "ranked_sr_sample_count": 12,
  "calibration_stage": 2,
  "gis_visible": true,
  "achilles_eligible": true,
  "secondary_eligible": true,
  "focus_debug": {
    "primary_domain": "Objectives",
    "primary_deficit": -6.3,
    "second_deficit": -3.9,
    "lead_over_second": 2.4,
    "streak_matches": 3,
    "band_width": 4.8,
    "eligible": true
  },
  "focus": {
    "primary": "objectives",
    "secondary": ["vision", "economy"],
    "advice": "Low objective presence; plan earlier rotations to dragons/herald."
  }
}
```

Note: `focus_debug` is intended for debugging and is not shown in the UI unless `LOLTRACK_ADMIN=1` is set.

### API: Weights (Admin)

Role domain weights are file-backed (`weights.json`) and can be adjusted at runtime.

- GET `/api/gis/weights` → current weights (schema_version `weights.v1`).
- PUT `/api/gis/weights` → replace after validation (requires `LOLTRACK_ADMIN=1`).

PUT payload shape:

```
{
  "roles": {
    "TOP":    { "Laning":0.30,"Economy":0.20,"Damage":0.15,"Macro":0.15,"Objectives":0.10,"Vision":0.05,"Discipline":0.05 },
    "JUNGLE": { "Objectives":0.30,"Macro":0.20,"Laning":0.10,"Economy":0.10,"Damage":0.10,"Vision":0.10,"Discipline":0.10 },
    "MID":    { "Laning":0.28,"Damage":0.20,"Economy":0.18,"Macro":0.14,"Objectives":0.10,"Vision":0.05,"Discipline":0.05 },
    "ADC":    { "Economy":0.25,"Damage":0.22,"Laning":0.22,"Objectives":0.12,"Macro":0.09,"Vision":0.05,"Discipline":0.05 },
    "SUPPORT":{ "Vision":0.28,"Objectives":0.20,"Macro":0.14,"Laning":0.14,"Damage":0.12,"Economy":0.06,"Discipline":0.06 }
  }
}
```

Validation:
- All roles present; domains known; each role’s weights sum to 1.0 (±1e‑6).
- Admin gate via `LOLTRACK_ADMIN=1`; otherwise 403.
- Persists to `weights.json` (path can be overridden with `LOLTRACK_WEIGHTS_PATH`).
