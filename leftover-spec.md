# Leftover Spec — Implementation Details to Close Gaps (v0.5 → v1.2)

This document lists every missing or deviating item found while cross‑checking `v0-5-spec.md`, `v0-6-spec.md`, and `v0-7-spec.md` against the current codebase, and describes how to implement each one. No code has been changed; this is an implementation guide.

---

## v0.5 gaps

- SQLAlchemy over SQLite (WAL on)
  - Gap: Current code uses `sqlite3` directly and does not enable WAL.
  - Implementation (lightweight, no ORM migration): enable WAL + sane pragmas on connection open.
    - Touch `loltrack/store.py` → in `Store.connect()`, run `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;` immediately after opening the connection.
    - Rationale: Meets the WAL requirement without a repo‑wide ORM migration.
    - Option B (full spec): Introduce SQLAlchemy models and session management; migrate CRUD in routers and helpers. This is larger scope and not required if WAL alone is acceptable.

- DB views `v_lane_diffs@10`, `v_early_summary`
  - Gap: No SQL views exist.
  - Implementation: Add views during schema bootstrap.
    - Touch `loltrack/store.py` → append `CREATE VIEW IF NOT EXISTS` statements after table creation.
      - `v_lane_diffs_10` (SQLite name cannot contain `@`):
        - Columns: `match_id, puuid, queue_id, patch, role, champion_id, gd10 AS gold_diff_10, xpd10 AS xp_diff_10, game_creation_ms` from `metrics`.
      - `v_early_summary`:
        - Columns: `match_id, puuid, cs10, cs14, dl14, first_recall_s, ctrl_wards_pre14, gd10, xpd10, game_creation_ms` from `metrics`.
    - Consumers: optional convenience for dashboard/targets endpoints.

- Live telemetry completeness (GD/XPD estimates, recall window, control wards progress)
  - Gap: `/ws/live` payload sets many early fields to `None`.
  - Implementation: Enhance `backend/backend/live/poller.py` using Live Client:
    - Source: `https://127.0.0.1:2999/liveclientdata/allgamedata` (already used) and `…/playerlist` if needed.
    - `gold10_est` and `gd10_est`:
      - `gold10_est = currentGold + max(0, (10m − t)) * (cs/min) * (avg_minion_gold)`; use 19g/6s melee+caster mix ≈ 1.8 CS/minion wave → 21–24g/cs as a heuristic; clamp to [0, 7000].
      - `gd10_est`: if inferred lane opponent available (see below), subtract opponent estimate from ours; otherwise omit (`null`).
    - `xp10_est` and `xpd10_est`:
      - Approximate from `activePlayer.level`, `championStats.experience` if available; else project via cs/min × avg XP/cs (use 60–65 XP per melee/caster mix) and clamp.
    - Lane opponent inference (best‑effort):
      - Use `role` heuristic: pick enemy with same position once available (if Live Client yields this), else proximity proxy when positions are available in other endpoints; otherwise leave diffs `null`.
    - `ctrlw_pre14_progress`: count control wards bought pre‑14 from `events` section when Live Client exposes them; otherwise use 0/1 with target 1 (progress UI still useful).
    - `recall_window`: implement a simple early recall window rule (e.g., 3:15–4:00 for most lanes) and set `in_window = (3:15 ≤ t ≤ 4:00)`; refine later with gold thresholds.
    - Keep payload ≤1 KB/s by sending compact numbers/strings.

- Secondary metrics (collected but optional UI toggles)
  - Gap: Not computed or exposed.
  - Implementation (post‑game via Timeline; store only):
    - Touch `loltrack/metrics.py` when iterating timeline events:
      - Ward clears: count `WARD_KILL` events by player pre‑14.
      - Trinket swaps: detect purchases of 3363/3364 and destruction of 3340; count swap timestamp.
      - Plates: count `TURRET_PLATE_DESTROYED` (if present) or infer from turret damage events between 5:00–14:00.
      - Objective proximity: compute min distance to pit during 8:00–14:00 windows using frame positions; store an aggregate (e.g., seconds within 2500 range).
      - Recall count: increment on first `ITEM_PURCHASED` after >10s being away from shop since last purchase (existing heuristic used for first recall can be reused).
      - Lane presence / roam distance: integrate distance from lane centerline using frame positions; store totals/pre‑14 share.
    - Touch `loltrack/store.py` to add columns if persisting these; or add a `metrics(name,value,at_s)` wide table if preferred.

- Matches drawer with mini‑timelines and ward events
  - Gap: UI lacks a drawer/detail view.
  - Implementation:
    - Frontend: add a `MatchDrawer.tsx` component; in `frontend/src/routes/Matches.tsx`, on row click fetch `GET /api/match/{id}` (already returns `timeline_raw`) and render 0–14 mini area charts for CS/Gold/XP plus ward events list.
    - Backend: `backend/backend/routers/matches.py` already exposes timeline raw; no changes required.

- Pagination UX for matches
  - Gap: No pagination controls.
  - Implementation:
    - Backend supports `limit`; add `page` and/or `before` cursors if desired.
    - Frontend: add simple next/prev using `?limit=25&before=<last_ts>` or a `page` state.

- Start/stop scripts: dev auto‑open
  - Gap: Dev mode doesn’t open the browser automatically.
  - Implementation:
    - `scripts/start.sh`: after `npm run dev` background start, `open http://localhost:5173` (macOS) guarded with `|| true`.
    - `scripts/start.ps1`: after spawning Vite, run `Start-Process "http://localhost:5173/"`.

---

## v0.6 gaps

- Persist player row in DB
  - Gap: PUUID is saved to config only; `players` table remains unused.
  - Implementation:
    - Touch `backend/backend/routers/auth.py` in `set_riot_id`: after resolving account, create a `Store()` and `INSERT OR REPLACE` into `players(puuid, game_name, tag_line, region, platform)`.
    - Source values: from resolved account response and existing config (`cfg['riot']`).

- Health `/api/health` should surface Riot 429 distinctly
  - Gap: Current result caches `ok|down`; does not mark `429`.
  - Implementation:
    - Touch `backend/backend/routers/health.py`: perform a low‑cost `GET` (or `HEAD`) to `platform-data` using `RiotClient.verify_key()` but capture a 429 branch via a small helper that returns `{'status':'429'}`; cache for ≥60s.
    - Keep timing budget <300 ms by early exiting when cached.

- `POST /api/auth/riot-key` response shape
  - Gap: Returns `{ ok:true, data:{ verified:true } }` vs spec’s `{ ok:true }`.
  - Implementation options:
    - Keep as is (superset; UI already tolerates it), or
    - Align to spec: drop `data` payload and return `{ ok:true }`.

---

## v0.7 gaps

- Global segment filters (Queue, Role, Champion, Patch) with URL persistence
  - Gap: No global filters bar; API isn’t honoring segment filters.
  - Implementation (frontend):
    - Add a top bar component with four controls; drive state from `useSearchParams` and reflect changes back to the URL.
    - Pass `segment` to APIs: e.g., `/api/metrics/rolling?segment=role:ADC&queue=420&patch=14.20`.
  - Implementation (backend):
    - `backend/backend/routers/metrics.py`:
      - Parse `segment` (`role:<ROLE>`, `champ:<ID|name>`, `patch:<STR>`) and optional `queue`.
      - Apply filters when building `rows` for windows and when computing series/baseline/current: add `WHERE` predicates on `role`, `champion_id`, `patch`, and `queue_id`.
      - Optionally fold segment into the windows cache key (e.g., `key = f"puuid:{...}:queue:{...}:role:{...}:champ:{...}:patch:{...}"`) and update `loltrack/windows.py` to compute segmented caches when needed.
    - `backend/backend/routers/targets.py` (part of `metrics.py` here): accept `segment` and compute P50/P75 within segment.

- Outlier handling and “Outlier” pill
  - Gap: No outlier detection; EWMA includes all values.
  - Implementation (backend):
    - In `loltrack/windows.py`, add `is_outlier(metric, v)` with thresholds: `abs(GD10)>2000`, `abs(XPD10)>1500` (others optional).
    - Exclude outliers from EWMA and trend calculations, but keep them in `values` history.
    - Expose an `outliers` boolean array or count per metric in `/api/metrics/rolling` for the last 8 points.
  - Implementation (frontend):
    - In `MiniLine`, optionally dim outlier points or show a small `Outlier` pill in the card when the last value was flagged.

- Matches drawer (0–14 mini charts + ward events)
  - Gap: Not implemented.
  - Implementation details: see “Matches drawer” in v0.5 section; UI only.

- Error surfacing without raw 500s
  - Gap: Global exception handler returns HTTP 500 (with envelope). The spec allows `ok:false` with appropriate 4xx or `200`, but emphasizes “no raw 500 to user”.
  - Implementation (optional):
    - Map unexpected exceptions to HTTP 200 while keeping `{ ok:false, error:{ code:'INTERNAL', … } }`, or map to 400 with `INVALID_INPUT` when appropriate.
    - Frontend `api.ts` already consumes envelope and shows mapped messages; no UI change required.

---

## Acceptance checkpoints per item

- WAL enabled: `PRAGMA journal_mode` returns `wal` and DB remains responsive under concurrent reads; ingest unaffected.
- Views created: `SELECT * FROM v_lane_diffs_10` and `v_early_summary` return rows post‑ingest.
- Live estimates: Live page shows `gold10_est` and `cs10_eta`; optional diffs appear when opponent inference works; payload remains <1 KB/s.
- Secondary metrics: New columns/fields populated for recent matches; not yet shown unless toggled.
- Matches drawer: Rows open a drawer with 0–14 mini charts; images load from `/assets/*`.
- Player row persisted: `players` contains the current user; `/api/health` `db.ok=true` unchanged.
- Riot 429 health: `/api/health` `riot_api.status` shows `429` when the key is rate‑limited.
- Segment filters: Changing filters updates URL and dashboards; `/api/metrics/rolling` and `/api/targets` reflect the subset.
- Outlier handling: EWMA excludes extreme diffs; an “Outlier” label displays when latest point is flagged.

---

## Notes

- Frontend charting: Current custom mini components satisfy v1.2 visual goals; adopting Recharts/shadcn/lucide from v0.5 is optional and not required to meet v1.2.
- Response envelopes: The API already uses a uniform `{ ok, data?, error? }` envelope and `Cache-Control: no-store` for `/api/*`.

