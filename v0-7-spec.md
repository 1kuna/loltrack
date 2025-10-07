# LoL Web Dashboard — Spec v1.2 (UI Polish, UX Gating, Plain‑English)

> Goal: fix cramped headers, uninformative charts, and confusing labels; stop 500s on Sync; make settings/onboarding fool‑proof; present **plain‑English** metrics with human‑readable units. This is a new spec (separate from v1.0/1.1) that replaces the Dashboard/Targets layouts and tightens API/UX contracts.

---

## 0) Quick Copy‑Paste for the Coding Agent
```
PR SCOPE (v1.2):
1) UI
- Replace current metric cards with new "ScoreCard" component (title, subtitle, 3 windows, target delta, micro chart).
- Use plain-English labels & units: 
  CS10 → "CS by 10:00" (count)
  CS14 → "CS by 14:00" (count)
  DL14 → "No deaths until 14:00" (rate)
  GD10 → "Gold lead @10" (± gold)
  XPD10 → "XP lead @10" (± XP)
  CtrlWardsPre14 → "Control wards before 14:00" (count)
  FirstRecall → "First recall time" (mm:ss)
- Redesign Targets page as "Goals" with human copy: P50="Typical"; P75="Top 25%"; add info tooltips.
- Charts: replace tiny sparklines with bullet charts (target band + current) and 8‑point mini-line (EWMA). Keep max 2 hues.

2) UX GATING
- Settings flow: Step 1 = Riot API key (validate), Step 2 = Riot ID (resolve PUUID). Disable Step 2 until Step 1 is green.
- Show inline validation errors and success toasts. Health pills stay visible.

3) MATCHES SYNC 500
- Backend must validate prerequisites (key + puuid). If missing → 400 with code MISSING_PREREQ.
- Wrap ingest in try/catch, return structured errors; never leak 500 to UI. Add /api/sync/bootstrap guardrails and progress.
- Frontend: show error toast with mapped human message; offer "Fix in Settings" CTA.

4) DATA FORMAT & UNITS
- Times as mm:ss; deltas with ±; whole numbers for counts; 1 decimal for rates/percentages where needed.
- Cap absurd values (e.g., GD10 > 2000) and mark as outlier.

5) EMPTY/ERROR STATES
- Dashboard/Goals/Matches: skeleton ≤600ms → data or empty card with helpful text + CTA.
- Live: states = Waiting / Live / Ended.

6) ACCESSIBILITY & LAYOUT
- Use 12‑column responsive grid; consistent spacing (8/12/16/24). Headings 18–20px; subtitles 12–13px. Avoid cramped titles.

7) ACCEPTANCE
- No more infinite loaders; no 500 surfaced to user; onboarding enforces key→id order; Dashboard shows meaningful charts; Targets reads like English.
```

---

## 1) Information Architecture Changes
- **Targets** → rename to **Goals** in nav and copy.
- Global top bar adds **segment filters**: Queue (default 420), Role, Champion, Patch. Persist to URL query.
- Add a compact **legend/help** button that opens a glossary drawer.

---

## 2) Visual Design Tokens
- Typeface: system UI; sizes—`h1: 28/32`, `cardTitle: 18/24`, `subTitle: 13/18`, `body: 14/20`, `caption: 12/16`.
- Spacing scale: 8/12/16/24/32.
- Colors (dark): `accent: cyan-400`, `ok: green-500`, `warn: amber-500`, `bad: red-500`, `ink: slate-200`, `muted: slate-400`, `surface: slate-900`, `panel: slate-850`.
- Elevation: subtle shadow on hover; rounded-2xl; borders `slate-800`.

---

## 3) Dashboard Redesign
### 3.1 ScoreCard Component (replaces current cards)
Props:
```ts
{
  id: 'CS10'|'CS14'|'DL14'|'GD10'|'XPD10'|'CtrlWardsPre14'|'FirstRecall',
  title: string,           // e.g., "CS by 10:00"
  subtitle: string,        // e.g., "Avg over windows"
  windows: { w5: number|null, w10: number|null, d30: number|null },
  target?: number|null,    // target in same unit; for DL14 use rate 0..1
  unit: 'count'|'gold'|'xp'|'rate'|'time',
  trend: number[]|null,    // last 8 values for tiny line
  status: 'ok'|'warn'|'bad'|'neutral'   // computed by compare(value,target)
}
```
Layout:
- Left: **Title** (cardTitle) + subtitle `5g / 10g / 30d` translated to words: "Avg last 5 | last 10 | last 30 days".
- Center: three **large numbers** (`w5`, `w10`, `d30`) with units:
  - `count`: integer (e.g., 66)
  - `gold`/`xp`: `±1,234`
  - `rate`: percentage with 0.0–100.0% (DL14 shows success rate)
  - `time`: `mm:ss`
- Right: **Bullet chart**: target band (thin line), current `w5` marker; small 8‑point trend line under it.
- Footer: small caption: e.g., "Target 65" / "Target 0 deaths until 14:00".

Status rules (defaults):
- `ok`: value ≥ target (or ≥ 0 for leads; ≤ target for FirstRecall if target is a window)
- `warn`: within 10% of target band
- `bad`: below (or above for recall) target by >10%

### 3.2 Grid & Responsiveness
- 12‑col grid; on wide screens: 3 columns; on medium: 2; on narrow: 1.
- Ensure title and numbers never wrap: use `truncate` + tooltips.

---

## 4) Goals (Targets) Page Redesign
- Section header: **Your goals (auto‑calibrated)** with banner if `provisional:true`: "Using starter goals until we’ve seen 10 matches."
- Each goal card:
  - Title in English: "CS by 10:00"
  - **Target** big number; **Typical (P50)** and **Top 25% (P75)** smaller beneath.
  - Info tooltip explaining the metric and why it matters.
  - Optional override input (number/slider) to set manual target; save updates `/api/config`.
- Glossary drawer (question‑mark icon) with entries:
  - **Typical (P50)** = your median; half your games are above, half below.
  - **Top 25% (P75)** = the mark you hit in your better games; we set targets at the higher of P75 or your manual floor.
  - **XP lead @10** = your XP minus lane opponent's XP at 10:00.
  - **Gold lead @10** = your gold minus lane opponent's at 10:00.
  - **Control wards before 14:00** = wards bought/placed before 14:00.
  - **First recall time** = time of your first intentional recall (mm:ss).

---

## 5) Matches Page Fixes
- Empty state with CTA: "Sync last 14 days" (disabled if missing prerequisites). 
- Clicking Sync calls `/api/sync/bootstrap`; if server returns `ok:false`, display mapped message:
  - `MISSING_PREREQ` → "Add your Riot API key and Riot ID in Settings first."
  - `RIOT_429` → "Riot API rate‑limited. Try again in X minutes."
  - `INGEST_ERROR` → "We couldn’t process some matches. We’ll keep the ones that worked."
- Add table columns: Date, Queue, Role, Champ (icon), W/L, Duration, **Early summary**: `CS@10`, `GD@10`, `XPD@10`, `DL14 ✓/✗`.
- Row click opens drawer with mini timelines for CS/Gold/XP (0–14) + ward events.

---

## 6) Settings: Guided Onboarding Flow
- **Step 1: Riot API Key**
  - Input with "Save & Verify" button.
  - On success: green check + text "Key verified".
  - On error: red inline text with example fix.
- **Step 2: Riot ID (GameName#TAG)**
  - Disabled until Step 1 verified.
  - On save: resolve PUUID and show your region/platform; show green check.
- **Health** panel stays at the top with pills (DB, Live Client, Riot API, DDragon). Update every 10s.
- Add a **Get Started** callout: After both checks are green, offer a button: "Sync last 14 days now".

---

## 7) API & Error Contracts (Additions)
- All endpoints use envelope `{ ok, data?, error? }`.
- New/updated error codes (HTTP 200 with `ok:false` OR appropriate 4xx, but never raw 500):
  - `MISSING_PREREQ` (400): Riot key or PUUID missing
  - `RIOT_429` (429): rate limited (include `retryAfter`)
  - `RIOT_DOWN` (503): upstream outage
  - `INGEST_ERROR` (207): partial success; include counts
  - `INVALID_INPUT` (400)
- `/api/sync/bootstrap` must pre‑validate and fail fast with `MISSING_PREREQ` rather than throwing 500.

---

## 8) Data Formatting Rules (Global)
- **Time**: display `mm:ss` (e.g., `286.5s → 04:46`).
- **Diffs**: prefix with sign and comma grouping: `+766`, `−110`.
- **Counts**: integer.
- **Rates**: `42.8%` (1 decimal). For DL14 show `% of games with 0 deaths by 14:00`.
- **Outliers**: if `|GD10| > 2000` or `|XPD10| > 1500`, mark with a small `Outlier` pill; exclude from EWMA but keep in history.

---

## 9) Charts: From “noise” to “signal”
- **Bullet chart** per card: thin target line at goal value; shaded ±10% band; current `w5` as a dot; x‑axis hidden, y‑axis units subtle.
- **Mini line**: last 8 values with EWMA overlay; no more than 2 lines; no gradients.
- **Matches drawer**: single small area chart per metric (0–14 only) with clear labels.

---

## 10) Component Inventory (Frontend)
- `ScoreCard.tsx` (core dashboard card)
- `GoalCard.tsx` (Targets/Goals)
- `HealthPills.tsx` (Settings)
- `SyncCTA.tsx` (empty state with action)
- `ErrorBanner.tsx` (maps error codes to human text)
- `GlossaryDrawer.tsx`
- `MiniBullet.tsx` and `MiniLine.tsx`

---

## 11) Backend Touches Required
- Ensure `GET /api/targets` returns human names and units metadata:
```json
{ "ok": true, "data": {
  "provisional": true,
  "metrics": {
    "CS10": { "name":"CS by 10:00", "unit":"count", "target":60, "p50":42.5, "p75":50 },
    "DL14": { "name":"No deaths until 14:00", "unit":"rate", "target":0.55, "p50":0.45, "p75":0.55 },
    "FirstRecall": { "name":"First recall time", "unit":"time", "target":273 }
  }
}}
```
- `GET /api/metrics/rolling` returns formatted windows and raw arrays; include `units` per metric.
- `POST /api/sync/bootstrap` pre‑checks key + puuid; if missing, return `{ ok:false, error:{ code:'MISSING_PREREQ', message:'Add your Riot API key and Riot ID in Settings.' } }`.

---

## 12) QA Checklist (Manual)
- [ ] Settings disables Riot ID until key is verified; toasts and inline errors appear.
- [ ] Health shows green DB & DDragon even if Live Client is down; polling doesn’t flicker.
- [ ] Matches empty state appears; 500s replaced with structured error toasts.
- [ ] Dashboard cards show mm:ss for recall; `±` signs for leads; three windows labeled in words.
- [ ] Goals page uses English terms and tooltips; overrides persist.
- [ ] Charts render with 1–2 series, legible, no rainbow; titles never collide.

---

## 13) Definition of Done (User‑visible)
- Dashboard no longer looks cramped; numbers are legible and clearly labeled.
- Charts actually convey whether you’re **on target** (bullet chart) and whether you’re **trending** (mini line).
- Sync never throws a raw 500; user gets a clear next step.
- Targets/Goals read like English; “P50/P75” are shown as “Typical/Top 25%.”
- Settings forces the correct order: **Key → ID → Sync**.

---

## 14) Future (Optional, not required for this PR)
- Light theme, export PNG of dashboard, shareable summary for last session.
- Per‑champion auto‑targets.
