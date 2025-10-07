# LoL CLI Stat‑Tracker — Detailed Product Spec (Windows)

> Purpose: a fast, reliable Windows command‑line tool that shows **whether you’re improving** at the few metrics you actually care about (CS & deaths early, lane diffs @10, warding discipline, recall hygiene), with **live match feedback** and **rolling windows**. It also collects rich data (match + timeline + live client) for deeper analysis later.

---

## 0) TL;DR (what it does)
- **Live Mode**: while a match is running, read the **Live Client Data API** on `https://127.0.0.1:2999/` once per second, compute early‑game targets (e.g., CS@10, *deathless to 14:00*, wards placed by 10/14, first recall time) and display a **clean, colorized dashboard** with OK/Warning/Fail signals.
- **Post‑Game Mode**: after a match ends, fetch full **Match‑V5 (+ Timeline)** by your **PUUID** and persist to a local **SQLite** DB. Update rolling windows (last 5/10/20 games, last 30/60 days) and show **trend arrows** with EWMA smoothing.
- **Baseline & Targets**: first 10–20 tracked games establish a **personal baseline**; targets auto‑calibrate to your P75 (or manual overrides). Scores show **% improvement vs. baseline**.
- **Storage for later**: keep normalized tables for matches, frames, events, items, runes, and static patch data (Data Dragon) so we can add richer analytics without re‑ingesting old games.

---

## 1) Non‑Goals / Guardrails
- **No overlays, no key‑hooking, no scripting**. CLI only; informational, not assistive. Staying within Riot’s allowed tool boundaries.
- **No private data collection** beyond what’s needed for your own account’s metrics. Keys live locally.

---

## 2) Primary Metrics (what the CLI emphasizes)
> Tight set that maps to your focus: *CS & survival early, lane advantage at 10, warding discipline, recall hygiene*. Everything else is captured but not front‑and‑center.

**Early‑game core**
1. **DL14 (Deathless to 14:00)** — Boolean per game; streak length tracked.  
2. **CS@10** — Integer; also show **CS/min (0–10)**.  
3. **CS@14** — Integer; also **CS/min (0–14)**.
4. **GD@10 (Gold Diff @10 vs lane opponent)** — in gold.  
5. **XPD@10 (XP Diff @10 vs lane opponent)** — in XP.
6. **First Recall Time** — mm:ss (lower is not always better; aim is *intentionality*; we trend toward an individualized target window per role/champ).
7. **Control Wards Bought / Placed (pre‑14 and total)** — integers.
8. **KP‑Early (Kill Participation 0–14)** — % of team kills you participated in pre‑14.

**Secondary (captured; not prioritized in CLI yet)**
- Ward clears (count), trinket swaps, plates taken/assisted, first blood involvement, herald/dragon proximity, turret deaths, roam distance (approx.), recall count pre‑14, lane presence ratio.

---

## 3) Metric Definitions (exact computation)
**Notation**: use Match‑V5 **timeline** for time‑sliced stats, participant mapping by `teamPosition` (`TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY`). Your PUUID resolves via Account‑V1. All timestamps refer to **gameTime** unless stated.

- **DL14**: `1` if no `ChampionKill` event with you as victim before `t < 14:00`, else `0`.
- **CS@10 / CS@14**: from timeline frames: `minionsKilled + jungleMinionsKilled` at frame nearest to 10:00 / 14:00. Also compute `CS/min` by dividing by elapsed minutes.
- **GD@10**: `your_totalGold@10 - opponent_totalGold@10`, where opponent is enemy participant with same `teamPosition` (fallback: laning proximity in first 10 minutes by median XY distance if `teamPosition` missing).
- **XPD@10**: `your_xp@10 - opponent_xp@10`.
- **First Recall Time**: first `ITEM_PURCHASED` after a `Recall` detection. Since recall isn’t a direct event, approximate as: any frame where your **currentGold** sharply drops with **position** near fountain (or `respa wn`/shop region) and you weren’t dead; choose earliest such time. (We store raw frames to refine later.)
- **Control Wards Bought/Placed**: count `ITEM_PURCHASED` where item id ∈ {`Control Ward`}, and `WARD_PLACED` with `wardType == CONTROL_WARD`.
- **KP‑Early**: `(your_kills_0-14 + your_assists_0-14) / (team_kills_0-14)`.

All metrics carry flags: `queueId`, `patch`, `role`, `championId` to allow segmented windows later (e.g., Ranked only, ADC only, specific champ pool).

---

## 4) Rolling Windows & Scoring
**Windows**
- **By count**: last **5**, **10**, **20** matches (queue‑filtered).  
- **By time**: last **30** and **60** days.
- **Segmented** (optional filters): role (`teamPosition`), champion, patch.

**Smoothing**
- **EWMA** with half‑life `H=10` games for per‑metric trend:  
  \[ \alpha = 1 - 0.5^{\frac{1}{H}} \]\n  `ewma_t = α * value_t + (1-α) * ewma_{t-1}`

**Baseline & Targets**
- **Baseline** per metric = median of first **N=10** tracked games (filter to target queue).  
- **Auto‑target** per metric = max(`baseline_P75`, `manual_floor`) where `manual_floor` is optional seed (e.g., CS@10=65 for ADC).  
- **Score (−100..+100)**: `score = clamp( 50 * z , −100, +100 )` where `z = (rolling_mean − baseline_mean) / baseline_std`. For Boolean DL14 use rolling **success rate**.
- **Improvement Index**: weighted average of selected metric scores (default equal weights; configurable).

---

## 5) Data Sources & Endpoints
- **Live Client Data API** (local, no key): `/liveclientdata/allgamedata`, `/activeplayer`, `/playerlist`, `/eventdata`, `/gamestats`. Poll 1 Hz in Live Mode.
- **Riot Web API**:  
  - Account‑V1 (Riot ID → PUUID)  
  - Summoner‑V4 (optional; convenience)  
  - Match‑V5: `/matches/by-puuid/{puuid}/ids` → `/matches/{matchId}` (+ `/matches/{matchId}/timeline`).  
  - Spectator‑V5 (optional, detect in‑progress by PUUID/Platform).
- **Data Dragon** (static): versions, champions, items, runes, queues mapping. Cache per‑patch.

**Rate limits**: personal/dev keys typically `20 req/s` and `100 / 120s`. The tool batches & caches to stay well under caps.

---

## 6) Architecture Overview
**Processes**
- **CLI (Typer)** with subcommands: `auth`, `live`, `pull`, `dash`, `rebuild`, `config`, `doctor`.
- **Ingestor**: pulls match IDs, hydrates missing matches, timelines, DDragon refs.
- **Compute**: derives metrics & windows; writes summary tables.
- **Renderer**: Rich‑based TUI for live and dashboards.

**Tech stack**
- **Python 3.11+**
- **Libraries**: `httpx` (async), `rich` (UI), `typer` (CLI), `pydantic` (schemas), `sqlite3`/`sqlalchemy`, `platformdirs` (paths), `tenacity` (retry), `orjson` (fast JSON), `cachetools`.
- **Storage**: **SQLite** file `loltrack.db` in user data dir; write‑ahead logging (WAL) on; indices on `(puuid, gameCreation, queueId)`.

**Data flow**
1. **Auth**: save Riot key (env var or `.env`), save Riot ID (gameName#tagLine). Resolve **PUUID** once.
2. **Live Mode**: poll local API → compute live targets → render.
3. **Post‑Game Sync**: detect new finished game via `/by-puuid/ids` → hydrate `match` & `timeline` → compute metrics → update windows.
4. **Dashboard**: read summary tables & render trends/sparklines.

---

## 7) Data Model (SQLite)
**Tables (normalized)**
- `player(id INTEGER PK, puuid TEXT UNIQUE, game_name TEXT, tag_line TEXT)`
- `match(match_id TEXT PK, puuid TEXT, queue_id INT, game_version TEXT, game_creation INT, game_duration INT, team_position TEXT, champion_id INT, win INT, kills INT, deaths INT, assists INT, cs INT, gold INT, kp REAL, control_wards_bought INT, control_wards_placed INT, first_recall_s REAL, …)`
- `timeline(match_id TEXT, minute INT, puuid TEXT, cs INT, jungle_cs INT, total_gold INT, xp INT, x INT, y INT, is_dead INT, …, PRIMARY KEY(match_id, minute, puuid))`
- `events(match_id TEXT, ts_ms INT, type TEXT, killer_puuid TEXT, victim_puuid TEXT, data JSON)`
- `opponent_map(match_id TEXT, puuid TEXT, opp_puuid TEXT, method TEXT, PRIMARY KEY(match_id, puuid))`
- `ddragon_items(version TEXT PK, data JSON)`
- `ddragon_champions(version TEXT PK, data JSON)`
- `metrics(match_id TEXT, puuid TEXT, name TEXT, value REAL, at_s INT, PRIMARY KEY(match_id, puuid, name))`
- `windows(puuid TEXT, segment TEXT, name TEXT, window_type TEXT, n INT, start_ts INT, end_ts INT, mean REAL, std REAL, p50 REAL, p75 REAL, ewma REAL, last_updated INT, PRIMARY KEY(puuid, segment, name, window_type, n))`

**Views**
- `v_lane_diffs@10` (join your and opponent frame@10).  
- `v_early_summary` (DL14, CS10/14, GD10, XPD10, wards@14, KP‑early).

---

## 8) Config (YAML)
```yaml
# %APPDATA%/loltrack/config.yaml
riot:
  api_key_env: RIOT_API_KEY
  region: americas   # routing value for Match-V5 (americas/europe/asia)
  platform: na1     # platform for Spectator/Summoner (na1, euw1, etc.)
player:
  riot_id: "GameName#TAG"
  track_queues: [420]   # 420=Ranked Solo/Duo; add as needed
windows:
  counts: [5, 10, 20]
  days: [30, 60]
render:
  theme: dark
  palette:
    ok: "green"
    warn: "yellow"
    bad: "red"
    accent: "cyan"
    neutral: "grey70"
metrics:
  primary: [DL14, CS10, CS14, GD10, XPD10, FirstRecall, CtrlWardsPre14, KPEarly]
  targets:
    CS10:
      mode: auto
      manual_floor: 60
    DL14:
      mode: auto   # success-rate target based on baseline P75
    GD10:
      mode: auto
  weights:
    DL14: 1.2
    CS10: 1.0
    CS14: 0.8
    GD10: 1.0
    XPD10: 1.0
    KPEarly: 0.6
    CtrlWardsPre14: 0.6
    FirstRecall: 0.4
```

---

## 9) CLI Commands (Typer)
```
loltrack auth            # set riot key & Riot ID, resolve PUUID
loltrack live            # live dashboard (poll local client)
loltrack pull --since 7d # hydrate matches & timelines since X
loltrack dash            # show rolling windows & trends
loltrack config edit     # open YAML in default editor
loltrack rebuild         # rebuild windows from raw tables
loltrack doctor          # env check, ports, SSL, key, rate-limit
```

---

## 10) Live Mode UI (Rich)
**Layout (80×24 friendly)**
```
┌──────────────────────────────────────────────────────────────────────────────┐
│  LIVE  |  Game 08:37  |  Patch 14.x  |  Role: ADC  |  Champ: Caitlyn        │
├───────────────────────┬──────────────────────────────────────────────────────┤
│ Targets vs Now        │ Early Stats                                         │
│ • DL14:  ✅  on track │ CS:  67 (target ≥ 65)  CS/min(0–10): 6.7            │
│ • CS@10: ✅ +2        │ Gold@10:  4,300   GD@10:  +180 (▲)                  │
│ • CS@14: ?  (ETA 5:23)│ XP@10:   4,120   XPD@10:  +110 (▲)                  │
│ • CtrlW@14: ⚠ 0/1     │ First Recall:  3:42 (✓ in target window 3:15–4:00)  │
│ • KPEarly: ✅ 60%     │ Wards Placed: 1 (pre‑14)  Wards Cleared: 0          │
├───────────────────────┴──────────────────────────────────────────────────────┤
│ Tips: Need 1 control ward before 10:00 to stay on P75 pace.                 │
└──────────────────────────────────────────────────────────────────────────────┘
```
**Color rules**
- **Green** for ≥ target or good direction (e.g., GD/XPD positive).
- **Yellow** for within 10% of target or marginal.
- **Red** for below target or regressing.
- **Cyan** accent for headings and values.

**Update cadence**: 1 Hz; avoid flicker via `Live` context; throttle expensive calcs.

---

## 11) Dashboard (Post‑Game)
```
┌──────────────────────────────────────────────────────────────────────────────┐
│  DASH  |  Queue: Ranked Solo  |  Windows: 5g / 10g / 30d                    │
├──────────────┬──────────────┬──────────────┬──────────────┬──────────────────┤
│ Metric       │ 5 games      │ 10 games     │ 30 days      │ Trend            │
├──────────────┼──────────────┼──────────────┼──────────────┼──────────────────┤
│ DL14 (rate)  │ 60% (▲ +10%) │ 50% (→)      │ 45% (▼ −5%)  │ ▁▂▄▆▇            │
│ CS@10        │ 66 (▲ +3)    │ 64 (▲ +2)    │ 63 (→)       │ ▃▄▅▆▆            │
│ CS@14        │ 96 (→)       │ 94 (→)       │ 93 (→)       │ ▄▄▅▅▄            │
│ GD@10        │ +120 (▲)     │ +80 (▲)      │ +30 (→)      │ ▁▃▅▆▇            │
│ XPD@10       │ +90 (▲)      │ +70 (→)      │ +40 (→)      │ ▂▃▄▆▇            │
│ CtrlW@14     │ 1.2 (→)      │ 1.1 (→)      │ 1.0 (→)      │ ▂▃▃▄▅            │
├──────────────┴──────────────┴──────────────┴──────────────┴──────────────────┤
│ Improvement Index: +18 (on track)                                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 12) Implementation Details
**A. Live Client polling**
- Endpoint priority: `allgamedata` → fallback to `activeplayer`, `playerlist`, `eventdata`.
- SSL: `verify=False` on `https://127.0.0.1:2999` (local, self‑signed). Handle connection refused when not in game.
- Session ends when `gamestats.gameMode` or gameTime stops advancing; then schedule post‑game sync.

**B. Match ingestion**
- `ids = GET /matches/by-puuid/{puuid}/ids?start=0&count=20`; skip already‑seen.
- Hydrate each `match` + `timeline`. Persist raw JSON (for audit) and parsed rows.
- Queue filter: default `420` (Ranked Solo/Duo). Configurable.

**C. Lane opponent mapping**
- Prefer `participant.info.teamPosition` if set on both sides; else derive opponent by: compute median XY distance to each enemy from 02:00–10:00, take min as lane opponent.

**D. Targets auto‑calibration**
- After baseline window (10 games), compute P50/P75; choose target= max(P75, manual_floor). Recompute weekly or on `rebuild`.

**E. Windows**
- Maintain rolling aggregates per `(segment, metric, window)` and cache in `windows` table to render instantly.

**F. Trend rendering**
- Mini sparklines per metric using Unicode blocks `▁▂▃▄▅▆▇` over last 8 games.

**G. Error handling**
- Live API missing → show “waiting for match”.  
- Timeline unavailable (remake/bug) → compute what’s possible; mark metric `partial`.
- Rate‑limit (429) → backoff with jitter; resume.

---

## 13) Color & Theme
- **Palette** (default dark terminal):  
  - `accent = cyan` (headers, labels)  
  - `ok = green`  
  - `warn = yellow`  
  - `bad = red`  
  - `neutral = grey70`  
- Keep **3–4 hues max** to avoid rainbow vomit. Use bold sparingly; boxes with rounded borders where available.

---

## 14) Windows Setup
1. Install Python 3.11+ (add to PATH).  
2. `py -m pip install --upgrade pip`  
3. `py -m pip install loltrack` (package name TBD)  
4. Set `RIOT_API_KEY` in **User Environment Variables** (or `.env` alongside DB).  
5. `loltrack auth` → enter `GameName#TAG`; tool resolves PUUID.  
6. `loltrack live` to test in‑game; `loltrack dash` for post‑game trends.

**Optional**: bundle as single‑file EXE with **PyInstaller** for zero‑Python install.

---

## 15) Security & Privacy
- Riot key stored in OS‑specific keyring or `.env` (user choice).  
- No telemetry, no uploads. All data stays local.  
- Respect dev/personal key usage; no public distribution without production key.

---

## 16) Testing Plan
- **Unit**: metric calculators from fixed fixture timelines (gold/xp/CS vs expected).  
- **Integration**: ingest N sample matches across roles; assert window stats and opponent mapping.  
- **Smoke**: live polling in custom stub (recorded `allgamedata`).

---

## 17) Edge Cases & Rules
- **Remakes** (`gameDuration < 300s`): exclude from windows by default.  
- **ARAM/URF**: ignored unless explicitly enabled (different targets).  
- **Position swaps**: use opponent‑mapping fallback.  
- **Disconnected spans**: consider gaps >120s; mark partial for DL14 if death events missing but end data present.

---

## 18) Roadmap (later)
- Per‑champion target ladders (auto‑per‑champ P75).  
- Position‑aware ward value (lane vs river vs objective windows).  
- Roam quality heuristics (distance + timing around wave states).  
- Export to CSV/Parquet; simple web report.  
- Coach view to annotate mistakes by timestamp.

---

## 19) Minimal Pseudocode (core loops)
```python
# live loop
while in_game():
    data = get_allgamedata()
    now = data["gameData"]["gameTime"]
    cs = compute_cs(data)
    gd10, xpd10 = estimate_diffs_partial(data, now)
    targets = eval_targets(now, cs, gd10, xpd10, wards, recall_time)
    render_live(now, targets)
    sleep(1)

# post-game sync
ids = fetch_recent_match_ids(puuid)
for mid in unseen(ids):
    m = fetch_match(mid)
    t = fetch_timeline(mid)
    rows = derive_metrics(m, t, puuid)
    db.insert(rows)
    update_windows(puuid)
render_dashboard()
```

---

## 20) Success Criteria
- **Latency**: live panel updates ≤150 ms/frame; no flicker.  
- **Stability**: zero crashes on client not running; graceful 429 handling.  
- **Signal**: at least **three** primary metrics show clear, trustworthy trend over 10 games.  
- **Aesthetics**: readable at 80×24; 3–4 colors max; passes dark/light terminals.

---

## 21) What you’ll actually look at (daily)
- **During game**: a single box that tells you if you’re on pace: DL14 ✔/✖, CS pace, GD/XPD early, ward target progress, recall window.  
- **After game**: a compact table with rolling windows and arrows. No fluff. Just *am I improving or not*, and by **how much**.

