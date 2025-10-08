# Leftover Spec — Remaining Items to Implement (v0.5 → v1.2)

This trimmed document includes **only** what still needs to be implemented. Items that are already completed or intentionally different have been removed.

**Alignment notes for this repo:**
- Core modules live under `core/` (not `loltrack/`).
- Server routes live under `backend/server/routers/` (not `backend/backend/routers/`).
- Live poller is at `backend/server/live/poller.py`.
- Rolling metrics use discrete query params (`queue`, `role`, `champion`, `patch`) instead of a single `segment` string.

---

## v0.5 — Remaining

### Live telemetry completeness (GD/XPD estimates, recall window, control‑ward progress)
**Gap:** `/ws/live` payload sets early‑game estimate fields to `null` / placeholders.

**Implementation:** Enhance `backend/server/live/poller.py` using the Riot Live Client endpoints.
- **Sources:** `https://127.0.0.1:2999/liveclientdata/allgamedata` (+ `…/playerlist` if needed).
- **`gold10_est` & `gd10_est`:**
  - `gold10_est = currentGold + max(0, (600 − t_s)) * (cs_per_sec) * (avg_minion_gold)`.
  - Use a simple heuristic: ~21–24 gold per CS; clamp to `[0, 7000]`.
  - `gd10_est`: if lane opponent can be inferred (below), subtract opponent estimate; else leave `null`.
- **`xp10_est` & `xpd10_est`:**
  - Prefer `activePlayer.level` / `championStats.experience` when available; otherwise project via `cs/min × avg XP/CS` (~60–65 XP per melee/caster mix). Clamp to sane bounds.
- **Lane‑opponent inference (best‑effort):**
  - If Live Client surfaces `position/role`, pick enemy with same role; otherwise proximity proxy once any positional hints are available. If ambiguous, leave diffs `null`.
- **Control‑ward progress pre‑14 (`ctrlw_pre14_progress`):**
  - Count control wards bought pre‑14 from the `events` section when exposed; otherwise fallback to 0/1 with target 1 so the UI can still show progress.
- **Early recall window:**
  - Implement a simple window (e.g., 3:15–4:00) and set `in_window = (3:15 ≤ t ≤ 4:00)`; refine later using gold thresholds.
- **Payload budget:** Keep ≤ ~1 KB/s by sending compact numbers / short keys.

---

## v0.6 — Remaining

### Persist player row in DB
**Gap:** `players` table is unused; `set_riot_id` only writes to config.

**Implementation:** In `backend/server/routers/auth.py` → `set_riot_id`:
- After account resolution, create a `Store()` and `INSERT OR REPLACE` into `players(puuid, game_name, tag_line, region, platform)` using values from the resolve‑account response and `cfg['riot']`.

### Health `/api/health` should surface Riot **429** distinctly
**Gap:** Result caches `ok|down`; rate‑limit (429) is not surfaced.

**Implementation:** In `backend/server/routers/health.py`:
- Perform a low‑cost probe (e.g., `RiotClient.verify_key()` hitting `platform‑data`) and capture a 429 branch that returns `{ status: '429' }`.
- Cache status for ≥60 s; keep total time budget under ~300 ms by early‑exiting when cached.

---

## v0.7 — Remaining

### Extend `/targets` to accept the same filters (Optional)
**Gap:** Rolling metrics already honor `queue`, `role`, `champion`, `patch`; targets remain global.

**Implementation:**
- **Backend (`backend/server/routers/metrics.py`):** accept the four params for `/targets`; compute P50/P75 within the filtered segment. Optionally extend cache keys and `core/windows.py` to memoize common filter combos.
- **Frontend:** params flow from the existing top filter bar via `useSearchParams` → include in `/targets` requests.

### Outlier handling + “Outlier” pill
**Gap:** No outlier detection; EWMA includes extreme values.

**Implementation:**
- **Backend (`core/windows.py`):** add `is_outlier(metric, v)` thresholds (e.g., `abs(GD10)>2000`, `abs(XPD10)>1500`). Exclude outliers from EWMA/trend but keep in `values` history. Expose an `outliers` boolean array or recent count in `/api/metrics/rolling` for the last N points (e.g., 8).
- **Frontend (`MiniLine` / cards):** dim outlier points or show a small **Outlier** pill when the latest value is flagged.

### Error surfacing without raw 500s (Optional)
**Gap:** We already return a uniform envelope for 500s; mapping of known cases to structured codes is partial.

**Implementation:**
- Keep 500 for unexpected errors while ensuring `{ ok:false, error:{ code:'INTERNAL', … } }` remains consistent.
- Map expected cases (e.g., missing prereqs, rate limits) to specific codes so the UI can show friendly messages.

---

## Acceptance checkpoints (for the above items)
- **Live estimates:** Live page shows `gold10_est` (and `gd10_est` when opponent is inferable), plus `xp10_est/xpd10_est`, early‑recall window flag, and control‑ward progress; payload stays < 1 KB/s.
- **Player row persisted:** `players` contains the current user after setting Riot ID; existing DB health unchanged.
- **Riot 429 surfaced:** `/api/health` includes `riot_api.status: '429'` when rate‑limited.
- **Targets filters (opt):** `/api/targets` recomputes P50/P75 for the requested `queue/role/champion/patch` subset.
- **Outliers:** EWMA excludes extreme diffs; card shows an **Outlier** indicator when the latest point is flagged.
- **Error mapping (opt):** Known cases return stable `error.code` values consumed by the UI.

---

## Notes
- API responses already use a uniform `{ ok, data?, error? }` envelope.

