# Objective
Make every dashboard metric card deliver the same *clarity + momentum* as the top “Calibrating” block: one obvious headline status, subtle motion, and a short English narrative—while keeping deeper details one click away.

---

## Scope (MVP)
- Refactor **Score cards on Dashboard** only (no Targets/Matches pages in this PR).
- New shared components: `StatusChip`, `ProgressRibbon`, `MetricPills`, `CardDrilldown` (drawer), `GlossaryButton`.
- Keep current data contracts; compute status/progress client‑side from existing windows/targets.

Out of scope (nice‑to‑have follow‑up): per‑metric insights, A/B copy tests, custom themes.

---

## Success Criteria
1) Each card has **one lead KPI** with a **status chip** (On track / Near / Behind) and an **arrow** (up / flat / down) indicating *trend vs baseline*.
2) A thin **progress ribbon** shows percent to goal with a center tick; animates on mount/update.
3) **English micro‑copy** at the bottom states what’s happening in one line.
4) **Secondary windows** (last 10 / 30d) are small, quiet pills to the side.
5) Clicking a card opens a **drilldown drawer** with charts and details.
6) Jargon has an in‑UI **glossary** (global button + per‑card `?`).

---

## Card Anatomy (apply to every metric)
```
┌──────────────────────────────────────────────────────────────┐
│  Title        [?]                               ⋯ menu       │
│  64  ▲  (On track)   |  10: 51   30d: 48                     │  ← KPI + Trend + Status + quiet pills
│  ──────────────▮────────┊──────────────                       │  ← ProgressRibbon (% to goal, center tick)
│  sparkline (faint)                                        ↗  │  ← Tiny sparkline, low contrast
│  Goal 85 · Higher is better · Last 5 leading vs target        │  ← Narrative micro‑copy (1 line)
└──────────────────────────────────────────────────────────────┘
```

**Hierarchy rules**
- KPI font: `text-3xl font-bold` (mobile `text-2xl`).
- Status chip: 10px text, rounded pill, semantic color (ok/warn/bad).
- Trend arrow: ▲ / ▼ / — (or lucide `trending-up`, `trending-down`, `minus`).
- Secondary pills: `text-xs text-slate-400`.
- Ribbon height 6px, with a subtle width transition (180–240ms).

---

## Components

### 1) `<StatusChip status>`
- `status ∈ {ok, warn, bad}`
- Colors from tokens (see **Design Tokens**):
  - ok: `text-emerald-400 bg-emerald-950/50 ring-emerald-500/20`
  - warn: `text-amber-400 bg-amber-950/50 ring-amber-500/20`
  - bad: `text-rose-400 bg-rose-950/50 ring-rose-500/20`
- Copy: `On track`, `Near`, `Behind` (override allowed via prop).

### 2) `<ProgressRibbon value target mode>`
- `mode ∈ {higher_is_better, lower_is_better, earlier_is_better}`.
- Computes `progress = clamp01(value/target)`; for `earlier_is_better`, use `progress = clamp01(target/value)`.
- Renders a track with a center tick; fills to `progress * 100%` with `transition-[width] duration-200`.
- Optional `confidence` can modulate bar glow `opacity`.

### 3) `<MetricPills windows>`
- Shows *last 10* and *30d* values as faint inline pills: `10: 51 · 30d: 48`.

### 4) `<MetricCard>` (refactor of existing ScoreCard)
**Props**
```ts
interface MetricCardProps {
  id: string;                             // e.g., "cs@10"
  title: string;                          // e.g., "CS by 10:00"
  unit: 'count'|'percent'|'gold'|'xp'|'time';
  mode: 'higher_is_better'|'lower_is_better'|'earlier_is_better';
  windows: { w5: number; w10: number; d30: number }; // already available
  target?: number | null;                 // target if defined
  baseline?: 'w10'|'d30';                 // trend baseline (default 'w10')
  glossaryKey?: string;                   // for tooltip / drawer help
  spark?: Array<number>;                  // small recent series for sparkline
}
```
**Render**
- Row 1: `title` + `?` button → opens Glossary at `glossaryKey` anchor.
- Row 2: **KPI** (windows.w5), **Trend arrow** (vs baseline), **StatusChip**.
- Row 2 right: `<MetricPills windows>`.
- Row 3: `<ProgressRibbon value={w5} target={target} mode={mode} />`.
- Row 4: **Micro‑copy** (see rules below).
- Card is clickable → opens `<CardDrilldown metricId=id>`.

### 5) `<CardDrilldown>` (right drawer)
- **Header**: Big KPI, status chip, trend arrow, short blurb.
- **Tabs**: `Overview`, `History`, `Distribution`, `Coaching`.
  - *Overview*: goal vs actual, progress ribbon, last‑N table, quick tips.
  - *History*: line chart (last 30/60), moving average toggle.
  - *Distribution*: histogram or box plot with percentiles (P50/P75); tooltips in English.
  - *Coaching*: 2–3 actionable suggestions pulled from your heuristics.
- **Footer**: “View Glossary” and “Copy link to metric”.

### 6) `GlossaryButton` (global + per‑card)
- Top‑right button on the page opens the Glossary drawer.
- Per‑card `?` opens to specific anchor.

---

## Status, Trend, and Copy Logic

### Status (color)
```ts
function statusFor(value: number, target?: number|null, mode: Mode): 'ok'|'warn'|'bad' {
  if (target == null || target === 0) return 'warn';
  const pct = mode==='earlier_is_better' ? target/value : value/target;
  if (pct >= 1.0) return 'ok';
  if (pct >= 0.85) return 'warn';
  return 'bad';
}
```
*(Thresholds are tunables via config; start at 100%/85%.)*

### Trend Arrow (direction)
- Compute baseline = `w10` (fallback `d30`).
- `delta = w5 - baseline` (invert sign if `earlier_is_better`).
- If `|delta| < epsilon` (e.g., < 2% of target or unit‑specific small), show **flat**; else ▲ if improving, ▼ if worsening.

### Micro‑copy (one line)
- Template per mode:
  - **higher_is_better**: `Last 5: {v} vs goal {t}. {Ahead|Close|Behind} — {short action}.`
  - **earlier_is_better**: `Last 5: {mm:ss} vs goal {mm:ss}. {Ahead|Close|Behind} — {short action}.`
- Example (Gold lead @10): `Last 5: +632 vs goal +150. Ahead — keep early plates.`

### Units & Formatting
- `percent`: `toFixed(0)%` (no deaths until 14 → use success rate 0–100%).
- `time`: `mm:ss`.
- `gold/xp/count`: locale `toLocaleString`.

---

## Drilldown Charts (MVP)
- **History**: Line chart of last 30 matches; show goal line.
- **Distribution**: Box plot with P50/P75; hover shows English labels (e.g., `Median (P50)`, `Top quartile`).
- **Overview table**: last 10 rows (match id | value | outcome | lane/champ) with colorized value by status.

Charting library: keep current (Recharts). Disable animations on reduce-motion.

---

## Design Tokens (Tailwind)
```css
/* tailwind.css */
@layer components {
  .chip { @apply text-[10px] leading-4 px-1.5 py-0.5 rounded-2xl ring-1; }
  .kpi  { @apply text-3xl font-bold; }
  .pill { @apply text-xs text-slate-400; }
  .ribbon-track { @apply h-1.5 rounded bg-slate-800/80 relative; }
  .ribbon-fill  { @apply absolute inset-y-0 left-0 rounded bg-sky-400/80 transition-[width] duration-200; }
  .center-tick   { @apply absolute inset-y-0 left-1/2 w-px bg-slate-600/40; }
}
```

---

## Layout & Responsiveness
- Grid: cards are equal height; use `auto-rows-fr` and `minmax(300px, 1fr)` columns.
- Mobile: stack; KPI `text-2xl`, hide sparkline, keep ribbon and micro‑copy.
- Maintain consistent vertical rhythm (16/12/8 spacing).

---

## Accessibility
- Status chip has `aria-label` (e.g., `status: on track`).
- Arrow has `aria-hidden` with visually hidden text describing trend (`improving/declining/flat`).
- Drawer focus trap, ESC to close, return focus to card.
- Colors pass WCAG AA on dark background.

---

## Analytics (events)
- `dashboard_card_view` `{metric_id}` on mount in viewport.
- `dashboard_card_click` `{metric_id}` when opening drawer.
- `dashboard_drilldown_tab` `{metric_id, tab}`.
- `glossary_open` `{metric_id?}`.

---

## Example: “No deaths until 14:00”
**Props**
- `unit: 'percent'`, `mode: 'higher_is_better'`, `target: 65` (means 65% of games with zero deaths pre‑14).
- Windows: `w5=40`, `w10=20`, `d30=16.7`.

**Render**
- KPI: `40%`  ▼  `Behind`  | `10: 20% · 30d: 17%`
- Ribbon: `progress = 40/65 = 0.615` (fill ~61.5%).
- Micro‑copy: `Last 5: 40% vs goal 65%. Behind — ward river at 2:30 and crash waves before contesting.`
- Click → Drawer with per‑match early deaths list and positioning tips.

---

## Implementation Plan (PR checklist)
1) **Create components**: `StatusChip.tsx`, `ProgressRibbon.tsx`, `MetricPills.tsx`, `CardDrilldown.tsx`, `GlossaryButton.tsx`.
2) **Refactor ScoreCard** to render new anatomy (keep props compatible; migrate styles).
3) **Wire status/trend logic** and unit formatting utilities.
4) **Add Glossary** entry anchors for each metric and mount global button.
5) **Add analytics hooks**.
6) **Responsive QA** and motion‑reduction checks.
7) **Snapshot tests** for status/trend logic; storybook stories for chip/ribbon/card.

---

## Acceptance Tests
- **Visual**: Every card shows exactly one big KPI, one chip, one arrow, one ribbon, and small pills.
- **Motion**: Ribbon animates on value change; honors reduce‑motion.
- **Logic**: Given targets and windows, status and arrow match the rules above (unit tests cover boundaries).
- **Drilldown**: Drawer opens with charts and closes with ESC; focus returns to card.
- **Glossary**: `?` opens to the right term; global button works.

---

## Dev Notes & Hooks
- Reuse existing sparkline code but reduce contrast (`opacity-40`).
- Centralize thresholds (`STATUS_THRESHOLDS`) and epsilon settings per unit.
- If a metric lacks `target`, show ribbon at 0% and chip `Near` (neutral) with copy `Goal not set yet`.
- Time goals (e.g., first recall): treat `earlier_is_better`. Use `mm:ss` parse/format helpers.

---

## Glossary (examples)
- **XPD10** → *XP lead @ 10:00*. Positive is good; +50 means you’re half a wave up.
- **P50** → *Median*. Half your games are above, half below.
- **K/P** → *Kill participation*. `kills+assists ÷ team kills`.

(Ensure these appear in the Glossary drawer used by `?` buttons.)

---

## Future Enhancements (post‑MVP)
- Per‑metric coaching playbooks (condition → tip library).
- Tap‑to‑toggle baseline (w10 ↔ 30d) and trend tooltips.
- Per‑user copy tone (competitive vs casual).
- Save card layout presets.

---

### Hand‑off Summary
Implement the five shared components, refactor the score cards to the new hierarchy, and wire the drawer + glossary. The page should *read like a story*: a bold headline verdict, a small bar of progress, and one sentence that tells the player what to do next—everything else is behind a click.