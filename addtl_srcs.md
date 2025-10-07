$1
> **Repo Alignment Addendum (loltrack)** — This blueprint is now mapped to your current FastAPI + React/Vite + SQLite codebase. The items below reference existing files and describe minimal diffs to enable the full Matches drill‑down + expanded metrics.

### A) What you already have (confirmations)
- **Riot client:** `core/riot.py` wraps Account‑V1 + Match‑V5 (+ Timeline) and does key verification via Status‑V4. (see `verify_key`, `resolve_account`, `match_ids_by_puuid`, `get_match`, `get_timeline`).
- **Sync endpoints:** `backend/server/routers/sync.py` exposes `/api/sync/pull` and a bootstrap flow that fetches recent matches, hydrates timelines, and rebuilds rolling windows.
- **Auth flow:** `backend/server/routers/auth.py` stores & verifies Riot key and resolves Riot ID→PUUID.
- **Ingest + metrics:** `core/metrics.py` already persists raw match/timeline, extracts frames/events, and computes early metrics (DL14, CS@10/14, GD@10, XPD@10, control‑wards pre‑14, KP‑early).

### B) Minimal changes to reach "per‑match deep dive" in Matches tab
1. **Backend: add an advanced summary joiner**
   - New function `core/metrics_extras.py`: compute DPM, GPM, damage breakdown, objective participation, item timing spikes from existing raw/timeline rows.
   - New route `GET /api/match/{id}/advanced` in `backend/server/routers/matches.py`: join `match_raw`, `timeline_raw`, and derived extras; return a compact DTO for the drawer.
   - Keep `/api/match/{id}` as is for full raw when needed (already returns timeline raw per spec).

2. **DB: zero‑risk extension path**
   - Prefer *wide* `metrics_extras` table (keyed by `match_id, puuid`) to avoid large schema churn; or add columns to `metrics` if you want everything in one row. Columns: `dpm, gpm, obj_participation, dmg_obj, dmg_turrets, mythic_at_s, two_item_at_s, vision_per_min, roam_distance_pre14`.
   - Optional: create views `v_lane_diffs_10` and `v_early_summary` to accelerate UI queries.

3. **Frontend: Match Drawer UI**
   - Add `frontend/src/components/MatchDrawer.tsx` with sections: Overview, Timeline (0–20m slider), Combat, Objectives, Vision, Build.
   - In `frontend/src/routes/Matches.tsx`, on row click fetch `/api/match/{id}/advanced`; lazy‑load raw `/api/match/{id}` if the user expands Timeline/Events.
   - Progressive disclosure: sections closed by default; remember last open state; "Simple/Advanced" toggle to hide Combat/Objectives/Vision unless enabled.

4. **Derived metrics formulas (server)**
   - **DPM/GPM:** divide totals from participant by game minutes.
   - **Objective participation:** count timeline events where participant is killer/assister (dragons/herald/baron+towers) / team objective count.
   - **Item spikes:** first mythic purchase timestamp; second item timestamp from `ITEM_PURCHASED` events.
   - **Vision/min:** `visionScore / (duration/60)`; optional ward heatmap later from stored XY frames.
   - **Roam distance pre‑14:** integrate XY movement away from lane centerline; reuse frames already persisted.

5. **Overwhelm controls**
   - Global toggle persisted in localStorage; drawer sections use accordions; small “Top Insights” chips (e.g., High DPM, Objective Beast) on the Overview card only.

### C) Concrete file‑level TODOs
- `core/metrics.py` — extend the event pass to compute: ward clears, plates, trinket swaps, objective proximity; expose in `row` (or `metrics_extras`).
- `core/store.py` — add `upsert_metrics_extras()` and new table or columns. Ensure indices on `(match_id, puuid)`.
- `backend/server/routers/matches.py` — add `/api/match/{id}/advanced` (and return 404→{ ok:false } envelope).
- `frontend/src/routes/Matches.tsx` — wire row→drawer with fetches; add filters (queue/role/champ/patch) and saved presets; add pagination controls.

### D) Acceptance checklist
- Drawer opens within <200ms (from cached summary), charts render under 400ms with 60fps scrub.
- Advanced DTO < 50 KB; raw fetch only when needed.
- New metrics backfill automatically when user re‑ingests recent 20 matches.

---

**Goal:** Max out actionable insight without overwhelming the user. Provide progressive‑disclosure UX with rich drill‑downs per match, while laying plumbing for *all* useful Riot endpoints. This doc is written for a coding agent to implement end‑to‑end.

---

## 0) Architecture at a Glance

- **Client**: Next.js (or React) app, modular tabs (Home, Matches, Live, Profile, Leaderboards, Challenges). Tailwind + Recharts for charts; Virtualized tables for long lists.
- **Server**: Node/TypeScript (or Python FastAPI) with a **RiotService** abstraction per API group.
- **Data/Cache**: Postgres (core entities) + Redis (hot cache) + optional ClickHouse (time‑series analytics at scale).
- **Jobs**: BullMQ/Temporal or Celery for background ingestion & recompute of derived metrics.
- **Secrets**: Riot API key via `RIOT_API_KEY`; RSO flows keep short‑lived tokens in server session store; never expose keys to browser.
- **Routing**: Respect routing clusters (AMERICAS/ASIA/EUROPE/SEA) and platform regions.
- **Rate limits**: Request coalescing, exponential backoff, jitter; per‑PUUID queueing for ingest.

---

## 1) API Coverage Matrix → Feature Map

> **Principle:** Pull *everything* we can, but surface it progressively.

| Feature | Endpoint(s) | Used For | Surface Area (Where) |
|---|---|---|---|
| Resolve player account | `account-v1 /accounts/by-riot-id/{gameName}/{tagLine}` or `/by-puuid/{puuid}` | Map Riot ID→PUUID and vice‑versa | Onboarding & Settings |
| Summoner profile
(basic) | `summoner-v4 /summoners/by-puuid/{encryptedPUUID}` | Level, icon, revision date | **Profile** header & **Matches** list badges |
| Champion rotations | `champion-v3 /platform/v3/champion-rotations` | F2P rotation context | Side panel tooltip |
| Ranked snapshot | `league-v4 /entries/by-puuid/{encryptedPUUID}` | Queue ranks, LP, hot streak, mini‑series | **Profile** + 5‑match overlay |
| Ladder (opt) | `league-v4 /challengerleagues/by-queue/{queue}` etc. | Contextual compare to tier | **Leaderboards** tab |
| Challenges | `lol-challenges-v1` (config, leaderboards, player‑data) | Challenge progress & percentile | **Challenges** tab + small chips per match |
| Status | `lol-status-v4 /platform-data` | Platform notices | Snackbar + Settings |
| Spectator (live) | `spectator-v5 /active-games/by-summoner/{puuid}`, `/featured-games` | Live game panel, pre‑match predictions | **Live** tab |
| Matches list | `match-v5 /matches/by-puuid/{puuid}/ids` | IDs (paged) | **Matches** tab list |
| Match detail | `match-v5 /matches/{matchId}` | Post‑game stats (info + metadata) | **Matches > Match Drawer/Page** |
| Timeline detail | `match-v5 /matches/{matchId}/timeline` | Events & frames for advanced KPIs | **Matches > Advanced Analytics** |
| Auth’d custom/RSO | `lol-rso-match-v1` (ids, match, timeline) | Full custom & private queues (when user signs in with Riot) | Hidden unless RSO connected |
| Tournament (opt) | `tournament-v5` / `tournament-stub-v5` | Custom lobbies, scrim tracking | Future “Scrims” tab |

> **Data Dragon** (static content): champion, item, rune, queue metadata for labeling/avatars.

---

## 2) Data Model (DB)

**Core tables**
- `player(id, puuid, riot_game_name, riot_tag_line, platform_region, routing_cluster, last_synced_at)`
- `summoner_profile(player_id FK, level, profile_icon, last_revision_at)`
- `rank_snapshot(player_id FK, queue, tier, rank, lp, hot_streak, veteran, fresh_blood, inactive, mini_series, as_of)`
- `match_header(id PK, routing_cluster, platform_region, queue, game_version, game_start, game_duration_s, winning_team_id)`
- `match_participant(match_id FK, puuid, champion_id, team_id, lane, role, kills, deaths, assists, gold, cs, vision_score, damage_total, damage_objectives, damage_turrets, wards_placed, wards_killed, kp, kda, dpm, gpm, csm, kill_streak_max, time_spent_dead_s, items jsonb, perks jsonb)`
- `match_objectives(match_id FK, team_id, baron, dragon, herald, towers, inhibitors, plates, first_blood, first_tower, first_herald, first_baron, first_dragon)`
- `timeline_frame(match_id FK, minute INT, team_gold jsonb, team_xp jsonb, team_cs jsonb, participants jsonb)`
- `timeline_events(match_id FK, idx, timestamp_ms, type, killer_id, victim_id, assisting_participant_ids jsonb, position jsonb, monster_type, tower_type, lane_type, ward_type, bounty, shutdown)`
- `challenge_progress(player_id FK, challenge_id, level, percentile, points_current, points_max, updated_at)`

**Indexes**
- `match_header(game_start)` for recency queries; `match_participant (puuid, match_id)`; GIN on jsonb metrics.

---

## 3) Ingestion & Caching

1) **Identify Player**: resolve (Riot ID→PUUID) via Account‑v1, persist mapping.
2) **Page Match IDs**: `/matches/by-puuid/{puuid}/ids?count=~20&start=offset` (store cursor; backfill async to 100/200 recent).
3) **Hydrate Details**: For each ID, fetch `/matches/{id}` then `/timeline` → normalize into DB + derived metrics (section 6).
4) **Warm Cache**: Redis key namespaces
   - `player:{puuid}:recentIds`
   - `match:{id}:summary` (JSON)
   - `match:{id}:adv` (aggregates)
5) **Jobs**: Queue backfills & recomputes; dedupe by match ID; respect rate limits (token bucket per routing cluster).
6) **Static Content Sync**: nightly Data Dragon content to `cdn_cache` for champion/item/rune lookup & icons.

---

## 4) UX: Progressive Disclosure (avoid overwhelm)

- **Matches tab (home for insights)**
  - **Row summary**: Champion tile, K/D/A, CS, Dmg, Vision, KP, Result, Queue, Date, Duration. Click → **Match Drawer**.
  - **Smart badges**: Top 1–2 standout stats (e.g., “High DPM” or “Objective Beast”).
  - **Filter/Sort**: Queue, role, champion, patch, result; saved presets.

- **Match Drawer/Page (drill‑down)** – collapsible sections:
  1. **Overview** (always expanded): K/D/A, KP, DPM, GPM, CS/M, Vision, Gold‑XP diff @10/@15, Objective contrib, Rune/Items path.
  2. **Timeline**: Gold & XP diff charts, CS accumulation, power spikes (mythic completion), death map. Frame scrubber.
  3. **Combat**: Damage breakdown (to champs/objectives/turrets), taken vs dealt; multi‑kill & shutdown map; skirmish clusters.
  4. **Objectives**: Dragon/Herald/Baron/tower plate timings; firsts; participation rate.
  5. **Vision**: Wards placed/killed over time, vision score per minute; ward heatmap (optional later).
  6. **Build & Runes**: Item timings, rune stats; compare to site‑wide medians for champ+role.
  7. **Team Compare**: Side‑by‑side with lane opponent + team averages.
  8. **Challenges**: What advanced to next threshold from this match.

- **Overwhelm Controls**:
  - Global **Simple / Advanced toggle** (persist in localStorage per user).
  - Section accordions defaulted by skill level (e.g., Advanced closed by default).
  - “Pin Favorites” to keep 3 metrics near top across all matches.
  - Inline definitions (ℹ︎ tooltips) and benchmark shading (percentile bands).

---

## 5) UI Data Contracts (per section)

### 5.1 Match Row (list)
```ts
interface MatchRowSummary {
  matchId: string
  queue: number
  startedAt: string
  durationSec: number
  championId: number
  role: 'TOP'|'JUNGLE'|'MIDDLE'|'BOTTOM'|'UTILITY'|null
  k: number; d: number; a: number
  cs: number; csm: number; gold: number
  dmgToChamps: number; dpm: number
  visionScore: number
  kp: number // (kills+assists)/team_kills
  result: 'Win'|'Lose'
  badges: string[] // e.g., ["High DPM", "Vision King"]
}
```

### 5.2 Match Overview (drawer)
```ts
interface MatchOverview {
  kda: number; kp: number
  dpm: number; gpm: number; csm: number
  gd10: number; gd15: number // from timeline
  xpd10: number; xpd15: number
  dmgObj: number; dmgTurrets: number
  visionPerMin: number; wardsPlaced: number; wardsKilled: number
  runes: { primary: number; sub: number; shards: number[] }
  items: { id: number; t: number }[] // timings
}
```

### 5.3 Timeline payloads
- **Gold/XP/CS per minute** arrays
- **Event slices**: `ELITE_MONSTER_KILL`, `BUILDING_KILL`, `CHAMPION_KILL`, `WARD_PLACED/KILL`, `ITEM_PURCHASED`.

---

## 6) Derived Metrics (how to compute)

> Inputs: `match-v5 /matches/{id}` (InfoDto/ParticipantDto), `timeline` frames & events, plus Data Dragon for items/runes.

- **KDA**: `(K+A)/max(1,D)`.
- **KP**: `(K+A)/TeamKills` for your team.
- **CS/M**: `totalMinionsKilled + neutralMinionsKilled` divided by `duration_s/60`.
- **DPM / GPM**: Damage to champions & gold per minute from totals.
- **Gold/XP Diffs @10/@15**: From `frames[10|15].participantFrames[me].totalGold` minus lane opponent at those frames; same for XP.
- **Objective Participation**: Count events where you’re killer or assister (dragons, herald, baron, towers).
- **Item Spike Timings**: First mythic purchase time; track big spikes (2‑item) and correlate with K/D swings.
- **Vision per min**: `visionScore / duration_minutes`; ward events for heatmaps.
- **Damage Efficiency**: `DamageToChamps / (Gold * coeff)`; champion/role normalized percentile for context.
- **Roam Score** (proxy): champion kills/assists out of lane before 14 min + position deltas between frames.
- **Tempo Swings**: rolling ±gold diff slope across 3‑min windows.

> Store computed metrics in `match_participant` and `derived_metrics(match_id, puuid, jsonb)` for future evolution.

---

## 7) Services Layer (server)

```
/services/riot/
  account.ts  // resolveRiotId, resolvePuuid
  summoner.ts // getSummonerByPuuid
  league.ts   // getRanksByPuuid
  matches.ts  // listMatchIds(puuid, cursor)
              // getMatch(id)
              // getTimeline(id)
  spectator.ts// getActiveGame(puuid)
  challenges.ts // getPlayerChallenges(puuid)

/services/ingest/
  ingestRecentMatches(puuid, limit)
  hydrateMatch(id)
  computeDerived(matchId)
```

**Pseudocode: ingest**
```ts
async function ingestRecentMatches(puuid: string, count=40) {
  const ids = await Riot.matches.listMatchIds(puuid, { count })
  for (const id of ids) queue.enqueue('hydrateMatch', { id })
}

async function hydrateMatch({ id }) {
  const [m, t] = await Promise.all([
    Riot.matches.getMatch(id),
    Riot.matches.getTimeline(id)
  ])
  const normalized = normalizeMatch(m, t)
  await db.persist(normalized)
  await computeDerived(id)
}
```

**Resilience**: backoff on 429/5xx; per‑cluster queues; memoize Data Dragon lookups.

---

## 8) Front‑End Components

- `MatchesList` (virtualized): renders `MatchRowSummary[]` with client‑side filters.
- `MatchDrawer` sections as described (Overview, Timeline, Combat, Objectives, Vision, Build, Team Compare, Challenges).
- Charts: area charts for gold/xp diffs; stacked bars for damage types; step chart for item timings; heatmap canvas for ward placements.
- Tooltips: explain every metric; “Compare to your tier median” (needs cohort service).

---

## 9) RSO‑only Enhancements (optional)

If the user logs in with Riot (RSO):
- Use `lol-rso-match-v1` for **custom games** & **private** match data not available to public `match-v5`.
- Store short‑lived `Authorization` bearer; pass only server‑side.
- Gate a **Customs** sub‑tab showing scrim analytics.

---

## 10) Performance & Rate‑Limit Strategy

- Global limiter per cluster; token bucket tuned to free/production limits.
- Coalesce concurrent requests for same match ID; write‑through cache to Redis.
- Request priority: UI → cache → DB → network.
- Nightly reconcile for older matches; patch boundary refresh when `gameVersion` changes.

---

## 11) Security & PII

- Never store access tokens client‑side.
- Only store public match data unless user consents to RSO scopes.
- Obfuscate other players when required (configurable privacy modes).

---

## 12) End‑to‑End Flows

### 12.1 First‑time setup
1. Resolve PUUID from Riot ID; persist.
2. Kick off recent 40 matches; show skeletons; hydrate rows as they arrive.
3. Upon opening a match, lazy‑fetch timeline if absent.

### 12.2 Ongoing usage
- On app open → check for new matches since `last_synced_at`; ingest diff.
- User switches tab → no network unless cache miss; background refresh updates silently.

---

## 13) Testing & Validation

- **API Facades** unit tests (mock fetchers) for all endpoints.
- **Golden match fixtures** (a few queues/roles) validate derived metrics.
- Visual regression on charts.
- Contract tests for Data Dragon mappings (champion IDs ↔ names).

---

## 14) Implementation Tasks & Acceptance Criteria

1) **RiotService scaffolding**
   - ✅ Methods for each endpoint with cluster routing & backoff.
   - ✅ Per‑endpoint zod schemas; throw on mismatch.

2) **DB schema & migrations**
   - ✅ Tables in §2; indexes present; `derived_metrics` jsonb column; seeds for lookup tables.

3) **Ingestion jobs**
   - ✅ `ingestRecentMatches` fetches IDs, hydrates details, persists.
   - ✅ `computeDerived` produces metrics in §6 within 500ms per match.

4) **Matches list**
   - ✅ Renders 20+ rows in < 75ms paint; K/D/A, KP, CS, DPM, Vision, badges.
   - ✅ Filters: queue, role, champ, patch, result; stored presets.

5) **Match drawer**
   - ✅ Overview & Timeline sections working; charts reflect frame data.
   - ✅ Objectives & Vision sections parse events; heatmap behind feature flag.

6) **Ranks & Challenges**
   - ✅ Rank snapshot call; chips on rows; Challenges tab shows progress + deltas.

7) **Live (optional)**
   - ✅ Spectator call for active games; link to pre‑match insights card.

8) **Overwhelm Controls**
   - ✅ Simple/Advanced toggle; accordions closed by default; tooltips; pin favorites.

9) **Analytics & benchmarks**
   - ✅ Percentile context from cohort service (phase 2) or local medians fallback.

---

## 15) API Request Templates (TypeScript)

```ts
// GET match ids
GET https://{cluster}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count=20
headers: { 'X-Riot-Token': process.env.RIOT_API_KEY }

// GET match
GET https://{cluster}.api.riotgames.com/lol/match/v5/matches/{matchId}

// GET timeline
GET https://{cluster}.api.riotgames.com/lol/match/v5/matches/{matchId}/timeline

// GET ranks
GET https://{platform}.api.riotgames.com/lol/league/v4/entries/by-puuid/{encryptedPUUID}

// GET challenges player-data
GET https://{platform}.api.riotgames.com/lol/challenges/v1/player-data/{puuid}
```

> **Clusters**: AMERICAS, ASIA, EUROPE, SEA. **Platforms**: region codes (e.g., NA1, EUW1…). Store both on the player.

---

## 16) Future Enhancements

- **Role consistency model** to normalize Riot’s `individualPosition` vs `teamPosition` for lane compare.
- **Teammate synergy** scores across N matches.
- **Model‑based predictions** (win prob over time) using timeline diffs.
- **Scrims/Tournaments** via tournament APIs (opt‑in).

---

## 17) Env & Config

```dotenv
RIOT_API_KEY=********
RIOT_ROUTING_CLUSTER=AMERICAS
DATABASE_URL=postgres://...
REDIS_URL=redis://...
DATA_DRAGON_CDN=https://ddragon.leagueoflegends.com/cdn
```

---

### TL;DR for the Agent
- Build **Matches** as the central hub with progressive drill‑downs.
- Implement ingestion + cache + derived metrics pipeline first.
- Layer in Ranks & Challenges chips next; Spectator/Live last.
- Keep everything behind toggles/accordions to avoid overwhelm.

