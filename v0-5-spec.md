# LoL Web Dashboard — Detailed Product Spec (Windows + macOS)

> Replace the CLI with a **modern local web app**. Keep all prior data plumbing (Live Client API + Match‑V5 + Timeline + Data Dragon), but present a clean browser UI with real‑time feedback and rolling‑window trends. Primary usage on **Windows**, dev/testing on **macOS**. Start/stop with simple scripts for both OSes.

---

## 0) Goals (what this delivers)
- **Live Game view**: 1 Hz updates pulled from the local **Live Client Data API** via the backend and streamed to the browser with **WebSockets**. Shows: DL14 on‑track, CS pace, GD/XPD early, ward targets, recall window, and quick tips.
- **Post‑Game dashboard**: Rolling windows (5/10/20 games and 30/60 days), trend arrows, EWMA, baseline vs target deltas, and an overall **Improvement Index**.
- **Data‑first**: Ingest & normalize rich data (match, timeline, events, DDragon) so we can add more analytics later without re‑ingesting.
- **Cross‑platform runner**: one‑click **start/stop** scripts for Windows and macOS that install deps, launch backend, and serve the UI.

Non‑goals: overlays, scripting, key hooks, or anything that automates gameplay. Local single‑user only.

---

## 1) Tech Stack
**Backend**
- **Python 3.11+** with **FastAPI**
- **Uvicorn** (ASGI) + **WebSockets** for live push
- **httpx** for Riot APIs, **tenacity** for retries, **orjson** for fast JSON
- **SQLAlchemy** over **SQLite** (WAL on)

**Frontend**
- **React** (Vite) + **TypeScript**
- **Tailwind CSS** + **shadcn/ui** components + **lucide‑react** icons
- **Recharts** for line/area/bar, sparklines

**Build/Run**
- Node 20+ for `vite` build (dev); production UI served as static files by FastAPI
- Scripts: PowerShell (`.ps1`) + Bash (`.sh`) to **start/stop**

---

## 2) Architecture Overview
```
Browser (React)  ⇆  FastAPI (localhost:8787)
        ▲  WS (/ws/live)  │  REST (/api/...)
        │                  │
        └──────── Polls local Live Client API (https://127.0.0.1:2999)
                          + Riot Web API (Account-V1, Match-V5 + Timeline)
                          + Data Dragon (cached per patch)
```
- The **backend** is the only process that touches the local Live Client port and Riot Web API (keeps keys out of the browser and avoids CORS/self‑signed TLS issues).
- The **frontend** subscribes to `/ws/live` for in‑game telemetry and hits REST endpoints for historical dashboards.

---

## 3) Key User Flows
1) **Onboarding** → paste Riot API key + Riot ID → backend resolves PUUID → fetch recent matches → compute baseline → land on Dashboard.
2) **Play a game** → hit **Live Game** tab → see on‑track indicators and targets in real‑time → game ends → backend hydrates match+timeline → Dashboard updates.
3) **Review** → filter dashboard by role/champion/patch → see rolling windows & trends → Improvement Index moves.

---

## 4) Primary Metrics (same definitions as before)
- **DL14** (deathless to 14:00)
- **CS@10** and **CS@14** (+ CS/min 0–10, 0–14)
- **GD@10** and **XPD@10** vs. lane opponent (teamPosition fallback → proximity map)
- **Control Wards pre‑14** (bought/placed)
- **KPEarly** (0–14)
- **First Recall time** (approx via position + gold drop heuristic)

Secondary (collected, optional in UI toggles): ward clears, trinket swaps, plates, objective proximity, recall count, lane presence, roam distance.

---

## 5) Data Model (SQLite)
Tables are extensions of the CLI spec; keep compatibility.
- `player(puuid, game_name, tag_line, region, platform)`
- `match(match_id, puuid, queue_id, game_version, game_creation, game_duration, team_position, champion_id, win, kills, deaths, assists, cs, gold, kp, control_wards_bought, control_wards_placed, first_recall_s, ...)`
- `timeline(match_id, minute, puuid, cs, jungle_cs, total_gold, xp, x, y, is_dead, ...)`
- `events(match_id, ts_ms, type, killer_puuid, victim_puuid, data_json)`
- `opponent_map(match_id, puuid, opp_puuid, method)`
- `metrics(match_id, puuid, name, value, at_s)`
- `windows(puuid, segment, name, window_type, n, start_ts, end_ts, mean, std, p50, p75, ewma, last_updated)`
- `settings(id, key, value_json)`  

Views: `v_lane_diffs@10`, `v_early_summary`.

---

## 6) API Contract (REST + WS)
**Auth/Config**
- `POST /api/auth/riot-key` → `{ ok: true }` (stores key securely; env > keyring fallback)
- `POST /api/auth/riot-id` → `{ puuid, region, platform }`
- `GET  /api/config` → current config (queues, windows, weights, palette)
- `PUT  /api/config` → update config

**Data & Sync**
- `POST /api/sync/pull?since=7d` → kicks ingestion; returns task id
- `GET  /api/matches?limit=50&queue=420` → list recent matches (summary rows)
- `GET  /api/match/{id}` → full parsed match (joined with timeline excerpt)
- `GET  /api/metrics/rolling?windows=5,10,20&days=30,60&segment=role:ADC` → per‑metric aggregates & trend arrays
- `GET  /api/targets` → current baseline/targets per metric

**Live**
- `WS  /ws/live` → server pushes `{ t, gameTime, early:{ cs, cs10_eta, dl14_ok, gd10_est, xpd10_est, ctrl_pre14_progress, recall_window_state, tips: [...] } }` once per second while in game. Closes when match ends.

**Health**
- `GET /api/health` → { status: up, live_client: reachable|down, riot_api: ok|rate_limited }

Error format: `{ error: { code, message, details? } }`

---

## 7) Frontend UI/UX
**Navigation (left sidebar)**
- Dashboard  
- Live Game  
- Matches  
- Targets  
- Settings

**Design system**
- **Dark‑first**, minimalist. 3–4 hues max:  
  - `accent` = cyan‑400  
  - `ok` = green‑500  
  - `warn` = amber‑500  
  - `bad` = red‑500  
  - neutrals = slate‑700/800/950  
- Rounded cards, soft shadows, clear grids. Avoid rainbow gradients.

**Dashboard (home)**
- **Improvement Index** big number with ▲/▼ vs baseline.  
- **Rolling window grid** (cards per metric): shows 5g / 10g / 30d columns with value, Δ vs baseline, tiny sparkline (last 8 games), and a trend arrow.  
- **Filters** tray (queue, role, champ, patch). Persist to URL query.

**Live Game**
- Header: `Game 08:37 | Patch 14.x | Role ADC | Champion Caitlyn`  
- Left: **On‑track panel** (DL14 ✓/✗, CS@10 pace, GD/XPD est, CtrlWard pre‑14 progress, Recall window: in/out) using clear badges.  
- Right: **Early stats** table (CS, CS/min, Gold@10, GD@10, XP@10, XPD@10) + **Tip** banner (e.g., “Buy 1 control ward before 10:00 to stay on pace”).  
- Subtle progress bars toward target thresholds.

**Matches**
- Paginated list of recent games with pill tags (role, champ, W/L, duration).  
- Click to open a drawer with early metrics, a per‑minute CS/Gold/XP mini‑timeline, and ward events pre‑14.

**Targets**
- Shows baseline P50/P75 per metric and current **auto‑target** (P75 or manual floor).  
- Sliders/inputs to override targets and weights → saves to config.

**Settings**
- Connection status, Riot ID, queues tracked, windows, color palette.  
- Buttons: **Rebuild windows**, **Resync last 14 days**, **Export CSV**.

---

## 8) Live Telemetry Details
- Backend polls `https://127.0.0.1:2999/liveclientdata/allgamedata` every second (verify=False), derives early metrics, and emits compact payloads over `/ws/live`.
- When game ends (time stops or endpoint returns 404), backend queues post‑game hydration (Match‑V5 + Timeline) and closes the socket with `{ event: "game_end", matchId }`.

---

## 9) Rolling Windows & Scoring (unchanged logic)
- Windows: 5/10/20 games; 30/60 days; optional segment filters (role/champ/patch).  
- Smoothing: **EWMA** (half‑life 10 games).  
- Baseline: median of first 10 tracked games (per queue/segment).  
- Target: `max(P75, manual_floor)`; recompute weekly.  
- Score per metric: `clamp(50 * z, −100, +100)`; DL14 uses success‑rate.  
- **Improvement Index**: weighted average of selected metrics.

---

## 10) Start/Stop Scripts (cross‑platform)
**Windows (PowerShell)** — `scripts/start.ps1`
```powershell
param([switch]$Prod)
$ErrorActionPreference = "Stop"

# Python venv
if (-not (Test-Path .venv)) { python -m venv .venv }
./.venv/Scripts/python -m pip install -U pip
./.venv/Scripts/pip install -e backend

# Frontend
if (-not (Test-Path node_modules)) { npm ci }

# Build UI for production or run dev
if ($Prod) {
  npm run build
  $env:PORT=8787
  ./.venv/Scripts/uvicorn backend.app:app --host 127.0.0.1 --port 8787
} else {
  Start-Process powershell -ArgumentList "-NoLogo -NoProfile -Command npm run dev" -PassThru | Out-File -FilePath ./.vite.pid
  $env:PORT=8787
  ./.venv/Scripts/uvicorn backend.app:app --reload --host 127.0.0.1 --port 8787
}
```

**Windows (PowerShell)** — `scripts/stop.ps1`
```powershell
if (Test-Path ./.vite.pid) {
  $p = Get-Content ./.vite.pid | Select-Object -First 1
  Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
  Remove-Item ./.vite.pid -ErrorAction SilentlyContinue
}
Get-Process -Name uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force
```

**macOS/Linux (Bash)** — `scripts/start.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv || true
. ./.venv/bin/activate
pip install -U pip
pip install -e backend

if [ ! -d node_modules ]; then npm ci; fi

if [ "${PROD:-}" = "1" ]; then
  npm run build
  PORT=8787 uvicorn backend.app:app --host 127.0.0.1 --port 8787
else
  (npm run dev &) echo $! > .vite.pid
  PORT=8787 uvicorn backend.app:app --reload --host 127.0.0.1 --port 8787
fi
```

**macOS/Linux (Bash)** — `scripts/stop.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
if [ -f .vite.pid ]; then kill "$(head -n1 .vite.pid)" 2>/dev/null || true; rm -f .vite.pid; fi
pkill -f "uvicorn backend.app:app" 2>/dev/null || true
```

Notes:
- **Prod mode** serves the built UI (Vite `dist/`) via FastAPI’s StaticFiles.
- **Dev mode** runs Vite dev server (HMR) + FastAPI reload.

---

## 11) Backend Structure
```
backend/
  app.py                 # FastAPI app + mounts static in prod
  deps.py                # Riot key mgmt, clients, caches
  routers/
    auth.py              # riot-key, riot-id
    sync.py              # pull/rebuild endpoints
    metrics.py           # rolling windows, targets
    matches.py           # match list/detail
    health.py
  live/
    poller.py           # 1 Hz Live Client poll loop
    socket.py           # WebSocket manager, push payloads
  ingest/
    riot.py             # Account-V1, Match-V5, Timeline
    ddragon.py          # static cache per patch
    compute.py          # metrics derivation + windows
  db/
    models.py           # SQLAlchemy models
    schema.sql          # initial schema
  util/
    mapping.py, time.py, logging.py
```

---

## 12) Frontend Structure (React)
```
frontend/
  index.html
  src/
    main.tsx
    routes/
      Dashboard.tsx
      Live.tsx
      Matches.tsx
      Targets.tsx
      Settings.tsx
    components/
      MetricCard.tsx
      ImprovementIndex.tsx
      LivePanel.tsx
      Sparkline.tsx
      Filters.tsx
      Header.tsx
    lib/
      api.ts             # fetch helpers
      ws.ts              # WebSocket client
      format.ts          # number/time helpers
    styles/
      tailwind.css
```

**Component notes**
- `MetricCard`: props `{ name, value, delta, windowBreakdown, sparkline, state }` with color logic (ok/warn/bad)
- `LivePanel`: consumes `/ws/live` stream, renders badges and progress bars
- `ImprovementIndex`: large weighted score with trend arrow

---

## 13) Visual Spec (quick wireframes)
**Dashboard cards**
```
┌──────────────┬───────────────┬───────────────┐
│ CS@10        │ 66  (▲ +3)    │ sparkline ▃▅▆█│
│ 5g  10g  30d │ 64  63  63    │ target 65     │
└──────────────┴───────────────┴───────────────┘
```
**Live panel**
```
DL14: ✓ on track   CS@10 pace: +2   GD@10: +180   XPD@10: +110
CtrlWard pre‑14: 0/1   Recall window: ✓ (3:15–4:00)
Tip: Buy 1 control ward before 10:00 to stay on pace.
```

---

## 14) Config & Theming
`config.yaml` (kept server‑side; editable via UI)
```yaml
player:
  riot_id: "GameName#TAG"
  region: americas
  platform: na1
queues: [420]
windows: { counts: [5,10,20], days: [30,60] }
metrics:
  primary: [DL14, CS10, CS14, GD10, XPD10, CtrlWardsPre14, KPEarly, FirstRecall]
  weights: { DL14:1.2, CS10:1.0, CS14:0.8, GD10:1.0, XPD10:1.0, KPEarly:0.6, CtrlWardsPre14:0.6, FirstRecall:0.4 }
palette:
  accent: cyan
  ok: green
  warn: amber
  bad: red
```

---

## 15) Performance Budgets
- WS payload ≤ 1 KB/second during live.
- Dashboard API responds ≤ 150 ms from cached `windows` table.
- Frontend bundle ≤ 250 KB gz (production).

---

## 16) Reliability & Error Handling
- If Live Client unreachable → UI shows "Waiting for match" with guidance.
- If Riot API 429 → exponential backoff, resume later; banner in UI.
- Partial data (no timeline) → compute what’s possible; flag metrics as `partial`.

---

## 17) Security & Privacy
- Bind to `127.0.0.1` only by default; optional LAN toggle.  
- Store Riot key in env or OS keyring; never ship to client.  
- No telemetry; all data local.

---

## 18) Testing
- **Backend unit**: metric derivations against fixed fixture timelines.  
- **Integration**: ingest known matches; validate windows & trends.  
- **Frontend**: component tests (vitest) for color logic and formatting; WS mock for LivePanel.

---

## 19) Roadmap (later)
- Per‑champ targets (auto P75 by champ).
- Export CSV/Parquet + shareable PNG of dashboard.
- Coach annotations tied to timestamps.
- Optional Docker/Compose for one‑shot install.

---

## 20) Acceptance Criteria
- Live panel updates every second with stable colors; no flicker.
- Dashboard shows correct rolling windows (5/10/20; 30/60d) and **Improvement Index** that matches backend calc.
- Start/stop scripts work on **Windows** (PowerShell) and **macOS** (Bash). One command to run; one to stop.
- No rainbow vomit: max four hues; readable in dark mode; consistent spacing and alignment.

