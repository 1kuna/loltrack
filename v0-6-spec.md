# LoL Web Dashboard — Spec v1.1 (Hotfix + UX Stabilization)

> Purpose: Fix the “Loading…”/blank pages, make the app usable end‑to‑end, add Data Dragon asset caching, and harden UX with skeletons, empty/error states, and solid start/stop behavior on Windows + macOS. This spec supersedes v1 where noted and includes a concise copy‑paste brief for the coding agent.

---

## 0) TL;DR / Copy‑Paste for the Coding Agent

```
MAKE THESE CHANGES (v1.1):

1) BACKEND (FastAPI)
- Add a consistent JSON envelope everywhere: { ok: true|false, data?, error? }.
- Implement GET /api/health → { db, riot_api, live_client, ddragon, version } and ensure it returns in < 300 ms.
- Fix config endpoints:
  • GET /api/config → returns saved config (no secrets).
  • PUT /api/config → validates and returns the new config.
  • POST /api/auth/riot-key → saves key; return { ok:true }.
  • POST /api/auth/riot-id  → resolves PUUID; return { ok:true, data:{ puuid, region, platform } }.
- Targets: GET /api/targets must ALWAYS return an object.
  • If baseline < 10 games → provisional:true using manual floors from config.
- Rolling metrics: GET /api/metrics/rolling?windows=5,10,20&days=30,60 returns arrays (possibly empty) plus summary; never 204.
- Bootstrap ingest:
  • POST /api/sync/bootstrap (last 14 days or 20 matches) → returns task id.
  • GET /api/sync/status?id=... → { phase: 'ddragon'|'match_ids'|'hydrating'|'computing', progress: 0..1 }.
- Data Dragon cache (per patch) and local icon proxy routes:
  • GET /assets/champion/{id}.png
  • GET /assets/item/{id}.png
  • GET /assets/summoner/{id}.png
  Cache under .cache/ddragon/{version}/...
- WS /ws/live must send a final { event:'live_end' } before closing; heartbeat every 5s.

2) FRONTEND (React + Vite)
- Replace infinite spinners with:
  • Skeletons for first 300–600 ms.
  • Empty states with CTAs (Matches: “Sync last 14 days”).
  • Error states with retry + surfaced error code.
- Settings:
  • Health status pills (db/live/riot/ddragon); poll every 10s.
  • Riot Key/ID → show success/error toasts on save; disable button while pending.
- Dashboard/Targets/Matches must render even with empty data (use em-dash '—' when window empty).
- Live view must show “Not in game” when WS closes.
- API base:
  • Dev: VITE_API_BASE=http://127.0.0.1:8787
  • Prod: same-origin; backend serves built UI (no Vite dev server).
- Keep palette to 4 hues (accent cyan, ok green, warn amber, bad red). No rainbow gradients.

3) SCRIPTS + SERVE
- In prod, FastAPI must mount frontend/dist as static at '/'.
- Windows start.ps1 / macOS start.sh: build UI, start Uvicorn, open http://127.0.0.1:8787/.

4) QUICK TRIAGE
- Visit /api/health in browser → must return JSON quickly.
- Network tab: /api/config, /api/targets, /api/matches must be 200; if empty data, show empty states, not spinners.
- If no matches, call /api/sync/bootstrap then poll /api/sync/status.
```

---

## 1) Uniform API Envelope & Errors (Breaking Change)
**Every endpoint returns:**
```json
{ "ok": true, "data": { ... } }
```
**On error:**
```json
{ "ok": false, "error": { "code": "RIOT_429", "message": "Rate limited", "details": { "retryAfter": 45 } } }
```
- Add a global exception handler that maps unexpected errors to `{ ok:false, error:{ code:"INTERNAL", message } }`.
- Set `Cache-Control: no-store` for dynamic endpoints.

---

## 2) Health Endpoint
**Route:** `GET /api/health`
**Response (≤300 ms):**
```json
{
  "ok": true,
  "data": {
    "version": "1.1.0",
    "db": { "ok": true, "schema_version": 3 },
    "riot_api": { "status": "ok|429|down", "last_check_epoch": 1730 },
    "live_client": { "status": "up|down", "last_error": null },
    "ddragon": { "version": "14.XX.1", "assets_cached": true }
  }
}
```
**Implementation notes:**
- `db`: ensure `schema.sql` ran; create `.meta(schema_version int, updated_at int)`.
- `riot_api`: do a cached HEAD/ping (>=60s cache) to avoid burning rate‑limit.
- `live_client`: GET `https://127.0.0.1:2999/liveclientdata/gamestats` with `verify=False`, 500 ms timeout.
- `ddragon`: check `.cache/ddragon/{version}/champion.json` exists.

---

## 3) Config & Auth
**GET /api/config → 200**
```json
{ "ok": true, "data": { "player": {"riot_id":"Game#TAG","region":"americas","platform":"na1"},
  "queues":[420], "windows": {"counts":[5,10,20], "days":[30,60]},
  "metrics": {"primary":["DL14","CS10", "CS14", "GD10", "XPD10", "CtrlWardsPre14", "KPEarly", "FirstRecall"],
               "weights": {"DL14":1.2, "CS10":1.0, "CS14":0.8, "GD10":1.0, "XPD10":1.0, "KPEarly":0.6, "CtrlWardsPre14":0.6, "FirstRecall":0.4}},
  "palette": {"accent":"cyan", "ok":"green", "warn":"amber", "bad":"red"} } }
```
**PUT /api/config → 200** returns the saved config in the same format. Validate with Pydantic.

**POST /api/auth/riot-key → 200**
```json
{ "ok": true }
```
- Store in keyring or `.env` (masked in logs). 

**POST /api/auth/riot-id → 200**
```json
{ "ok": true, "data": { "puuid": "...", "region": "americas", "platform": "na1" } }
```
- Resolve via Account‑V1; persist `player` row.

---

## 4) Data Dragon (Static Data + Icons)
**Startup:**
- Load latest version from `https://ddragon.leagueoflegends.com/api/versions.json` (cache daily).
- Download JSON:
  - `cdn/{ver}/data/en_US/champion.json`
  - `cdn/{ver}/data/en_US/item.json`
  - `cdn/{ver}/data/en_US/summoner.json`
  - `cdn/{ver}/data/en_US/runesReforged.json`
- Store JSON under `.cache/ddragon/{ver}/...` and persist `ddragon_version` in `.meta`.

**Icon proxy routes:**
- `GET /assets/champion/{id}.png` → fetch/copy `cdn/{ver}/img/champion/{name}.png` (map id→name via champion.json), cache on disk.
- `GET /assets/item/{id}.png` → `cdn/{ver}/img/item/{id}.png`.
- `GET /assets/summoner/{id}.png` → `cdn/{ver}/img/spell/{name}.png`.
- On offline error, return HTTP 200 with placeholder PNG.

---

## 5) Sync/Bootstrap & Status
**POST /api/sync/bootstrap → 202**
```json
{ "ok": true, "data": { "task_id": "boot-20251007-1" } }
```
- Action: ingest last **14 days** (or **20** matches if shorter), hydrate match + timeline, compute metrics, warm windows, and ensure DDragon cached.

**GET /api/sync/status?id=boot-20251007-1 → 200**
```json
{ "ok": true, "data": { "phase": "hydrating", "progress": 0.65, "detail": "12/20 matches" } }
```
**Phases:** `ddragon` → `match_ids` → `hydrating` → `computing` → `done`.

---

## 6) Targets & Windows (Empty‑Safe)
**GET /api/targets → 200 always**
```json
{ "ok": true, "data": {
  "provisional": true,
  "by_metric": {
    "CS10": { "target": 60, "p50": null, "p75": null },
    "DL14": { "target": 0.55, "p50": null, "p75": null },
    "GD10": { "target": 50 }
  }
} }
```
- When ≥10 baseline games exist (segmented by queue/role if needed), include `p50/p75` and set `provisional:false`, `target = max(p75, manual_floor)`.

**GET /api/metrics/rolling?windows=5,10,20&days=30,60 → 200**
```json
{ "ok": true, "data": {
  "windows": {
    "CS10": { "5g": {"values":[64,61,66], "mean":64, "delta_vs_baseline":+3, "ewma":63.5 }, ... },
    "DL14": { "5g": {"rate": 0.6, "delta_vs_baseline": +0.1 }, ... }
  },
  "summary": { "improvement_index": 18 }
} }
```
- Empty arrays are fine; never leave the client hanging.

---

## 7) WebSocket /ws/live
**Server → Client payload (1 Hz):**
```json
{ "t": 1730, "gameTime": 523.4,
  "early": {
    "dl14_on_track": true,
    "cs": 67, "cs10_eta": "on_pace",
    "gold10_est": 4300, "gd10_est": 180,
    "xp10_est": 4120,  "xpd10_est": 110,
    "ctrlw_pre14_progress": {"have":1, "need":1},
    "recall_window": {"in_window": true, "range":"3:15–4:00"},
    "tip": "Buy 1 control ward before 10:00"
  }
}
```
**Lifecycle:**
- Heartbeat `{ event:"hb" }` every 5s.
- On end/exception, send `{ event:"live_end" }` then close.

---

## 8) Frontend: Loading/Empty/Error States
**Pattern:** each page has three layers: Skeleton → Data → Empty/Error.
- **Skeletons**: 300–600 ms shimmer.
- **Empty**: explanatory message + CTA button (e.g., Sync last 14 days) + subtle icon.
- **Error**: toast + inline message with code and Retry.

**Settings**
- Health pills: db/live/riot/ddragon with green/amber/red.
- Riot Key/ID forms: Save shows success toast on 200; show inline validation errors; disable while pending.

**Dashboard**
- Metric cards always render; show `—` when window empty; small sparkline from last 8 values; Improvement Index at top.

**Targets**
- Display P50/P75/Target per metric; show a banner if `provisional:true`.

**Matches**
- If empty → empty state with “Sync last 14 days” button that calls `/api/sync/bootstrap` and tracks `/api/sync/status`.
- If populated → table with champ/role/W‑L/duration + early metrics; drawer with mini timelines.

**Live**
- 3 states: Waiting (not in game) / Live / Ended. Handle WS close gracefully.

**Theme**
- Dark‑first, 4 hues max: accent **cyan‑400**, ok **green‑500**, warn **amber‑500**, bad **red‑500**, neutrals **slate‑800/900**.
- Recharts: max 2 series, thin lines, no loud gradients.

---

## 9) Start/Stop & Serving (Prod)
**Backend serves SPA in prod**
- Mount `StaticFiles(directory="frontend/dist", html=True)` at `/` and `/assets`.
- All `/api/*` routed to FastAPI.

**Windows PowerShell: scripts/start.ps1**
```powershell
param([switch]$Prod)
$ErrorActionPreference = "Stop"
if (-not (Test-Path .venv)) { python -m venv .venv }
./.venv/Scripts/python -m pip install -U pip
./.venv/Scripts/pip install -e backend
if (-not (Test-Path node_modules)) { npm ci }
if ($Prod) { npm run build } else { npm run build }  # always build for now
$env:PORT=8787
Start-Process "http://127.0.0.1:8787/" | Out-Null
./.venv/Scripts/uvicorn backend.app:app --host 127.0.0.1 --port 8787
```

**macOS Bash: scripts/start.sh**
```bash
#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv || true
. ./.venv/bin/activate
pip install -U pip
pip install -e backend
[ -d node_modules ] || npm ci
npm run build
PORT=${PORT:-8787} uvicorn backend.app:app --host 127.0.0.1 --port "$PORT" &
sleep 1; open "http://127.0.0.1:${PORT}/" 2>/dev/null || true
wait
```

---

## 10) Acceptance Criteria / Definition of Done
- **Health:** `/api/health` returns JSON under 300 ms; Settings shows status pills and updates every 10s.
- **Config & Auth:** Saving Riot Key/ID shows success toasts; values are persisted and echoed by `GET /api/config`.
- **Bootstrap:** Clicking Sync ingests recent matches; progress visible; Matches page fills; icons render without external CORS errors.
- **Targets:** Always renders; if baseline < 10 games, shows provisional banner and defaults.
- **Dashboard:** All metric cards show values/sparklines or `—`; Improvement Index present.
- **Live:** Updates at 1 Hz during game; on exit, shows “Game ended” state; no infinite spinner.
- **Icons:** Champion/item/summoner icons display offline after first fetch (cached on disk).
- **Prod Serving:** App runs from FastAPI‑served `dist/` with a single start command on Win/mac.

---

## 11) Manual Test Plan
1. **Health**: open `/api/health` directly; verify fields and load time.
2. **Settings**: save Riot key and Riot ID → see success toast; reload page → values persist.
3. **Bootstrap**: run Sync; watch status tick through phases; confirm 10–20 matches in DB; DDragon version recorded.
4. **Targets**: confirm `provisional:true` before baseline; play/ingest ≥10 games → `provisional:false` and targets use P75.
5. **Dashboard/Matches**: verify empty states before ingest and real data after.
6. **Live**: start a custom game; see Live page populate; exit; confirm graceful close state.

---

## 12) Implementation Notes & Gotchas
- Live Client uses self‑signed cert; the backend must call with `verify=False` (local loopback only).
- Cache riot health checks (≥60s) to avoid blowing rate limits.
- Timelines can be missing for remakes; mark `partial` not `error`.
- Store schema version; on upgrade, run migrations or rebuild windows.

---

## 13) Nice‑to‑Haves (if time permits)
- Add CSV export for Matches and window summaries.
- Show a small “Live now” pill on the Dashboard when WS is connected.
- Footer build info (git SHA, build time) for debugging.

---

## 14) Appendix — Example Types
**Health (TS type)**
```ts
export type Health = {
  version: string
  db: { ok: boolean; schema_version: number }
  riot_api: { status: 'ok'|'429'|'down'; last_check_epoch: number }
  live_client: { status: 'up'|'down'; last_error?: string|null }
  ddragon: { version: string; assets_cached: boolean }
}
```

**Rolling window value**
```ts
export type WindowSeries = { values: number[]; mean: number|null; delta_vs_baseline: number|null; ewma: number|null }
```

**Live message**
```ts
export type LiveFrame = { t:number; gameTime:number; early:{ dl14_on_track:boolean; cs:number; cs10_eta:'ahead'|'on_pace'|'behind'; gold10_est:number; gd10_est:number; xp10_est:number; xpd10_est:number; ctrlw_pre14_progress:{have:number;need:number}; recall_window:{in_window:boolean; range:string}; tip?:string } } | { event:'hb'|'live_end' }
```
