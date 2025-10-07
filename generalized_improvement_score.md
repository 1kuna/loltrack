# Generalized Improvement Score (GIS) – Algorithm & Implementation Plan

This is a concrete, repo‑ready system that turns **all** the Riot endpoints you can reach into (1) a stable **overall improvement score** and (2) **granular “what to fix” guidance** with one clear Achilles heel plus a short list of secondary issues. It’s built so the dashboard can be simple, while the Matches tab provides deep drill‑downs when you click a match.

Endpoint references below point back to your “League of Legends API endpoints (Riot Games Developer Portal)” inventory (page numbers are noted for wiring confidence).

---

## 0) Data we’ll ingest (mapped to endpoints)

- **Match history core**: match list, match detail, timeline (for events/frames). *Use `match-v5`*:
  - `/matches/by-puuid/{puuid}/ids`, `/matches/{matchId}`, `/matches/{matchId}/timeline`. *(See inventory, pages 4–5.)*
- **Live (optional)**: show a “pre‑match baseline” and “live score delta” with *`spectator-v5`* (`/active-games/by-summoner/{puuid}`). *(Page 5.)*
- **Player context**:
  - *`league-v4`*: ranked entries by PUUID → tier/queue weighting & “cohort” context. *(Page 3.)*
  - *`summoner-v4`* by PUUID for profile meta. *(Page 5.)*
  - *`champion-mastery-v4`* for mastery‑based expectation adjustment. *(Pages 1–2.)*
  - *`lol-challenges-v1`* for challenge progress and percentiles (bonus signals). *(Pages 3–4.)*
- **Auth/identity**: *`account-v1`* to resolve Riot ID ↔ PUUID. *(Page 1.)*
- **Routing & status** (for jobs/retries): *`lol-status-v4`* platform data. *(Page 4.)*

> *Notes*: We limit the **GIS** to SR 5v5 queues by queueId (Ranked Solo/Flex; Normals optional). ARAM/Customs can be excluded from the main score or shown as “sandbox impact” so the number doesn’t jump around due to mode noise.

---

## 1) Score tree (one overall + domain sub‑scores)

- **Overall GIS** (0–100; 50 = personal baseline)
- **Domains (per‑match, then smoothed over time)**  
  1) **Laning** (GD@10/@15, XPD@10/@15, CSD@10/@15, early deaths, plate involvement)  
  2) **Economy/CS** (CS/min by time bins, GPM, item spike timings)  
  3) **Damage/Skirmish** (DPM, damage share, kill conversion, multi‑kills, shutdowns)  
  4) **Objectives** (dragons/herald/baron/towers—presence & participation; firsts)  
  5) **Vision** (vision score/min, wards placed/killed, detector usage; ward map later)  
  6) **Teamfight Discipline** (isolated deaths, death timing vs objectives, time alive)  
  7) **Macro/Rotations** (roam distance & timing, participation in cross‑map fights)

> Domains are role‑aware. E.g., Support weights Vision > Damage; Jungle weights Objectives > Laning; Top/Mid weights Laning/Economy > Vision.

---

## 2) Features (from match & timeline)

From `match-v5` `info.participants` and `timeline` frames/events (kills, objectives, item purchased, ward events). *(Inventory pages 4–5.)*

- **Core**: K/D/A, KP, CS, gold, DPM, GPM, vision score, dmg to turrets/objectives, time spent dead, items with timestamps, perks.
- **Early diffs**: GD@10/@15, XPD@10/@15, CSD@10/@15 (via frames).
- **Events**: `ELITE_MONSTER_KILL`, `BUILDING_KILL`, `CHAMPION_KILL`, `WARD_PLACED/KILL`, `ITEM_PURCHASED`, plates, shutdowns.
- **Role tags**: `teamPosition` (Top/Jungle/Mid/Bottom/Utility) from match info.

**Optional context adjustments**
- **Champion Mastery**: down‑weight penalties when playing a champ with low mastery; up‑weight when on mains. *(Inventory pages 1–2.)*
- **Rank/Tier**: use `league-v4` to fetch the player’s tier/LP so we can select role/queue‑specific weights and display cohort comparisons. *(Page 3.)*
- **Challenges**: when a challenge is directly related (e.g., vision, objectives), treat its progress/percentiles as secondary signals, not core drivers. *(Pages 3–4.)*

---

## 3) Normalization (stability without external “global” data)

We want a score that **doesn’t flip every match** but still tracks real change.

**A. Personal baselines (primary)**
- For each metric \(m\), maintain an **EWMA** baseline \( \mu_m \) and EWMA std \( \sigma_m \) over the past N ranked SR matches with half‑life \(HL_m\).
- Compute standardized value per match:  
  \( z_m = (x_m - \mu_m) / \max(\sigma_m, \epsilon) \).

**B. Role/queue weighting**
- Maintain separate baselines per **(queue, role)** and optionally **champion class** (if you add DDragon tags later).
- If you switch roles/queues, the correct baseline applies; no cross‑contamination.

**C. Match reliability weight**
- \( r \in [0,1] \) scales updates by signal quality: minutes played / 30, plus reductions for remake/early surrenders and known low‑signal queues (Normals).

**Recommended half‑lives**
- Metrics: \(HL=6\) matches; Domain scores: \(HL=8\); Overall: \(HL=10\).  
- Convert to EWMA coefficient \( \alpha = 1 - 2^{-1/HL} \).

---

## 4) Domain scoring (per match → smoothed domain score)

For domain \(k\), use a **role‑aware linear blend** of standardized sub‑metrics \(z_m\):

\[
D_k^{inst} = \sum_{m \in \mathcal{M}_k} w_{k,m} \cdot \text{clip}(z_m, -3, 3)
\]

Map to 0–100: \( S_k^{inst} = 50 + 10 \cdot D_k^{inst} \) (so ±1σ ≈ ±10 points).

**Example weight templates** (tweakable JSON config):

- **Laning (Top/Mid/ADC)**  
  GD@10: .35, XPD@10: .25, CSD@10: .25, early deaths: –.15, plates: .10.
- **Jungle Objectives**  
  Early herald/dragon presence: .30, overall objective participation: .30, KP pre‑14: .20, invades/secured scuttle: .10, early deaths: –.10.
- **Support Vision**  
  Vision/min: .35, wards killed: .20, objective vision timing: .15, KP: .15, deaths alone: –.15.

**Per‑match smoothing update** (EWMA with reliability \(r\)):

\[
S_{k}^{new} = S_{k}^{prev} + r \cdot \alpha_k \cdot (S_{k}^{inst} - S_{k}^{prev})
\]

Where \( \alpha_k \) from half‑life. Start all domains at 50 on first 3 matches (warmup).

---

## 5) Overall GIS (stable, role‑aware)

Compute an **instant overall** as weighted deviation from 50, then smooth:

\[
GIS^{inst} = 50 + \sum_k W_k \cdot (S_k^{inst} - 50),\quad \sum_k W_k = 1
\]

- \(W_k\) = role + queue weights (config). E.g., Support: Vision .28, Objectives .20, Laning .14, Damage .12, Macro .10, Discipline .08, Economy .08.
- Smooth with \(HL=10\) and reliability \(r\):

\[
GIS^{new} = GIS^{prev} + r \cdot \alpha_{GIS} \cdot (GIS^{inst} - GIS^{prev})
\]

**Outlier damping**  
Wins/losses with extreme stomps can spike metrics. Before mapping, **Huberize** each standardized metric at ±2.5σ and clamp the per‑match overall delta to ±6 points.

---

## 6) Achilles heel + secondary issues (clear focus, no flip‑flop)

Define **domain deficits** over the recent window \(T\) (e.g., last 8 ranked SR matches, EWMA‑weighted):

\[
\bar{\Delta}_k = \text{EWMA}_T \left( S_k^{inst} - 50 \right)
\]

- **Primary Achilles heel** = domain with the **lowest** \( \bar{\Delta}_k \) that also satisfies:
  - (a) Gap magnitude ≥ 4 points below 0, **and**
  - (b) Beats current Achilles heel by ≥ 2 points for at least **3 consecutive** matches (hysteresis to prevent thrash).
- **Secondary issues** = next two domains with \( \bar{\Delta}_k \le -2 \) ordered by magnitude.

**Targeted prescriptions**
- Each domain has 3–5 actionable “recipes” keyed to which sub‑metric drags most.  
  Example: Laning → “CS/M below baseline by 0.9; aim for +12 CS by 15 min,” “early deaths ≥2 before 10, tighten wave control.”

**Copy generation (dashboard)**
- “Biggest blocker: **Objectives**. Your objective participation is **–6.3** vs baseline; improve dragon/herald presence in 10–20m.”  
- “Also slipping: **Vision** (–3.2), **Economy** (–2.6).”

---

## 7) Queue & champion guardrails (score integrity)

- Only include **SR 5v5** queues in GIS by default. Others → “sandbox impact” box, not counted.
- Adjust expectations using **champion mastery** deciles: if mastery is low on a champ, cap per‑match negative impact to –3 for that match to avoid punishing practice. *(Inventory pages 1–2.)*
- Patch boundaries: on major patch change (gameVersion), temporarily widen the Huber threshold to ±3σ for 3 matches.

---

## 8) Outputs for UI

- **Dashboard**:  
  - Big number: **GIS 0–100** (+/– delta vs last 5).  
  - “**Your biggest blocker**” (one sentence), plus “**Recently also**” (1–3 chips).  
  - Trend sparkline (overall + your role).
- **Matches list**: badges reflect domains that most affected that match’s inst score (e.g., “High DPM”, “Early Obj Low”).
- **Match drawer**: show domain contribution bars to that match’s **inst** GIS.

---

## 9) Data model additions

- `score_overall (player_id, queue, role, value, updated_at)` – smoothed GIS per context.
- `score_domain (player_id, queue, role, domain, value, updated_at)` – smoothed domain score.
- `inst_contrib (match_id, puuid, domain, inst_score, z_metrics jsonb)` – for drill‑down & badges.
- `norm_state (player_id, queue, role, metric, ewma_mean, ewma_var)` – personal baselines.

Indexes: `(player_id, queue, role)`, `(match_id, puuid)`, GIN on `z_metrics`.

---

## 10) Services & jobs

- **Compute pipeline** (after persisting match + timeline):
  1. Extract features → standardize vs personal baselines.  
  2. Compute domain inst scores → update smoothed domain scores.  
  3. Compute overall inst → update smoothed GIS.  
  4. Recompute Achilles/secondary determinations (hysteresis rules).
- **Backfill** on first run: 20–40 recent matches; seed baselines with rolling medians from the first 5 to avoid cold‑start spikes.

---

## 11) Pseudocode (server)

```py
def update_scores_for_match(player, match):
    ctx = context_key(match.queue, match.role)  # role from teamPosition
    feats = extract_features(match)             # from match + timeline
    z = standardize(feats, load_baselines(player, ctx))
    inst_domains = {
        d: map_to_100(weighted_sum(z, domain_weights[player.role][d]))
        for d in DOMAINS
    }
    inst_overall = 50 + sum(W[player.role][d]*(inst_domains[d]-50) for d in DOMAINS)
    r = reliability(match)                      # minutes/30, queue filter, remake guards

    # Smooth domain scores
    for d in DOMAINS:
        S_prev = load_domain_score(player, ctx, d, default=50)
        S_new = S_prev + r * alpha_domain * (inst_domains[d] - S_prev)
        save_domain_score(player, ctx, d, S_new)

    # Smooth overall
    GIS_prev = load_overall(player, ctx, default=50)
    GIS_new = GIS_prev + r * alpha_overall * (inst_overall - GIS_prev)
    save_overall(player, ctx, GIS_new)

    # Update Achilles + side issues with hysteresis
    update_focus_recommendations(player, ctx)
```

*`extract_features`* reads `match-v5` info & `timeline` (frames/events). *(Inventory pages 4–5.)*

---

## 12) Role weight presets (starter values)

- **Top**: Laning .30, Economy .20, Damage .15, Macro .15, Objectives .10, Vision .05, Discipline .05
- **Jungle**: Objectives .30, Macro .20, Laning .10, Economy .10, Damage .10, Vision .10, Discipline .10
- **Mid**: Laning .28, Damage .20, Economy .18, Macro .14, Objectives .10, Vision .05, Discipline .05
- **ADC**: Economy .25, Damage .22, Laning .22, Objectives .12, Macro .09, Vision .05, Discipline .05
- **Support**: Vision .28, Objectives .20, Macro .14, Laning .14, Damage .12, Economy .06, Discipline .06

These are config‑driven; you can tune them after collecting a few weeks of data.

---

## 13) Achievements & Challenges (nice‑to‑have)

- Pull `lol-challenges-v1` player‑data to show **“progress deltas”** that correlate with your focus areas (e.g., vision challenge going up while Vision domain deficit narrows). *(Inventory pages 3–4.)*  
- Treat these as supporting evidence; **do not** let them drive GIS to avoid bias toward grindable challenges.

---

## 14) Endpoint wiring checklist (quick)

- **History**: `GET /lol/match/v5/matches/by-puuid/{puuid}/ids …`, `GET /lol/match/v5/matches/{matchId}`, `GET /lol/match/v5/matches/{matchId}/timeline`. *(Inventory pages 4–5.)*
- **Rank context**: `GET /lol/league/v4/entries/by-puuid/{encryptedPUUID}`. *(Page 3.)*
- **Mastery**: `GET /lol/champion-mastery/v4/champion-masteries/by-puuid/{encryptedPUUID}`. *(Pages 1–2.)*
- **Identity**: `GET /riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}`. *(Page 1.)*
- **Live (opt)**: `GET /lol/spectator/v5/active-games/by-summoner/{encryptedPUUID}`. *(Page 5.)*

---

## 15) Anti‑thrash & trustworthiness rules

- **Hysteresis** for Achilles heel (needs 3 consecutive matches and 2‑point advantage to switch).  
- **Clamping** of per‑match overall delta to ±6 points.  
- **Queue gating** (ranked SR only by default).  
- **Confidence ribbon**: show a thin band around GIS reflecting recent variance; when the band is wide, copy says “insufficient signal to change focus.”

---

## 16) What the user sees

- Dashboard headline:  
  - **“Biggest blocker: Vision”** (example) – one sentence that links to the drawer with charts.  
  - **“Also slipping: Economy, Discipline.”** 1–3 chips.  
  - GIS number with ±5‑match trend; a small **“Why?”** pill opens the domain contribution bars for the past 5 matches.
- Matches tab: a clean list; clicking opens the drawer with domain contributions for that match and the metric mini‑charts.

---

## 17) Why this won’t tell you something different every match

- Everything is **standardized to your personal baseline** and **smoothed** with half‑lives (6–10 matches).  
- There’s **hysteresis** before the top recommendation switches.  
- Outliers are **Huber‑downweighted** and **clamped**.  
- Non‑ranked and non‑SR matches don’t perturb the number unless you opt in.

---

### Optional next steps I can generate on request

1) A `weights.json` starter for each role (domains → metrics → weights).  
2) A `scores.sql` migration (Postgres/SQLite) for the four tables in §9.  
3) A `compute_scores.py` (or TypeScript) module that plugs into your current ingest and updates GIS + domains after each match.



---

## 18) Calibration & Confidence Gating (UI & Scoring)

**Why**: Prevent noisy recommendations from tiny samples and keep the dashboard stable.

### A) Staged calibration
- **Stage 0 – Collecting (≤4 ranked SR matches in this role/queue)**
  - Hide numeric GIS; show a neutral “Calibrating” chip.
  - Show per‑match drill‑downs, but **suppress Achilles/secondary**.
  - Seed baselines with rolling median of the first 5 matches (when available).

- **Stage 1 – Provisional (5–7 matches)**
  - Show GIS with a **wide confidence band** and a “Calibrating” chip.
  - Continue to **suppress Achilles**; you may show soft guidance chips (e.g., “Vision trending down”) but label them “provisional”.

- **Stage 2 – Stable (≥8 matches)**
  - Show GIS normally; band width computed from last‑5 inst variance.
  - Enable **Achilles** + **secondary** issues *only if* confidence rules are satisfied (below).

> Sampling is **per (queue, role)** context; other contexts maintain their own counters and stages.

### B) Confidence rules (same as §15 but formalized)
- **GIS visibility**: `n ≥ 5`.
- **Achilles eligibility**:
  - `n ≥ 8` ranked SR matches in the context, **and**
  - Confidence band width ≤ **±6 pts**, **and**
  - EWMA domain deficit ≤ **−4.0**, **and**
  - Primary deficit beats second‑worst by **≥ 2.0** for **3 consecutive matches** (hysteresis).
- **Secondary issues**: `n ≥ 8` and EWMA deficit ≤ **−2.0`.
- **Queue gating**: Only SR 5v5 ranked contribute by default.
- **Patch guard**: On gameVersion change, temporarily widen Huber clamp to ±3σ for 3 matches; keep Achilles suppressed during this window unless `n ≥ 12`.

### C) Config knobs (JSON)
```json
{
  "minMatchesForGIS": 5,
  "minMatchesForFocus": 8,
  "minPrimaryGap": -4.0,
  "minPrimaryLead": 2.0,
  "hysteresisMatches": 3,
  "maxBandForFocus": 6.0,
  "secondaryGap": -2.0
}
```

### D) Reliability & smoothing during calibration
- Maintain the EWMA baselines throughout; during Stage 0–1 use `r = min(1, minutes/30) * 0.7` (slightly conservative).
- Clamp per‑match overall delta to **±6** points; Huber loss on each standardized metric at **±2.5σ**.

### E) UI behavior
- Dashboard card copy examples:
  - Stage 0: “**Calibrating** — play ~5 ranked games in this role to unlock your score.”
  - Stage 1: “**Calibrating** — your score is provisional; we’ll lock focus after ~8 games.”
  - Stage 2: “**Biggest blocker: Vision** … (Achilles and secondaries appear).”
- Progress text: `3/8 games toward stable focus`.

### F) Pseudocode (gate + render)
```ts
const n = ctx.sampleCount; // ranked SR matches for (queue, role)
const bandWidth = band(last5InstOverall); // pts
const stage = n <= 4 ? 0 : (n <= 7 ? 1 : 2);

const showGIS = n >= cfg.minMatchesForGIS;
const showCalibrating = stage < 2 || bandWidth > cfg.maxBandForFocus;

const primary = pickPrimary(deficitsEWMA);
const primaryLead = deficitsEWMA[primary] - deficitsEWMA[secondWorst(deficitsEWMA)];
const hysteresisOK = streak(primary, matches=cfg.hysteresisMatches, lead=cfg.minPrimaryLead);

const achillesEligible = (
  n >= cfg.minMatchesForFocus &&
  bandWidth <= cfg.maxBandForFocus &&
  deficitsEWMA[primary] <= cfg.minPrimaryGap &&
  hysteresisOK
);

render({
  stage,
  GIS: showGIS ? overall : null,
  calibrating: showCalibrating,
  achilles: achillesEligible ? primary : null,
  secondary: achillesEligible ? pickSecondaries(deficitsEWMA, cfg.secondaryGap, 2) : []
});
```

