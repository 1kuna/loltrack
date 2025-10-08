import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import GISSummary from '../components/GISSummary'
import MetricCard from '../components/MetricCard'
import CardDrilldown from '../components/CardDrilldown'
import GlossaryButton from '../components/GlossaryButton'
import FilterBar, { useSegmentParams, toQuery } from '../shared/FilterBar'
import {
  computeStatus,
  computeTrend,
  getMetricMeta,
  type MetricMode,
  type MetricStatus,
  type MetricUnit,
} from '../lib/metrics'

type RollingResp = {
  windows: Record<string, any>
  series: Record<string, { values: number[] }>
  summary: any
  units: Record<string, string>
}

type TargetsResp = {
  provisional: boolean
  metrics: Record<string, {
    name: string
    unit: string
    target?: number | null
    progress_ratio?: number | null
  }>
  weights?: Record<string, number>
}

type MetricCardData = {
  id: string
  title: string
  unit: MetricUnit
  mode: MetricMode
  windows: { w5: number | null; w10: number | null; d30: number | null }
  target: number | null
  baseline: 'w10' | 'd30'
  spark: number[]
  series: number[]
  glossaryKey?: string
}

export default function Dashboard() {
  const [roll, setRoll] = useState<RollingResp | null>(null)
  const [targets, setTargets] = useState<TargetsResp | null>(null)
  const [err, setErr] = useState<any>(null)
  const { seg, key } = useSegmentParams()
  const [activeMetricId, setActiveMetricId] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const qs = toQuery({ seg })
    Promise.all([
      api<RollingResp>(`/metrics/rolling${qs}`),
      api<TargetsResp>('/targets'),
    ])
      .then(([r, t]) => {
        if (active) {
          setRoll(r)
          setTargets(t)
        }
      })
      .catch((e) => {
        if (active) setErr(e)
      })
    return () => { active = false }
  }, [seg, key])

  const filtersQuery = useMemo(() => toQuery({ seg }), [seg])
  const windows = roll?.windows ?? {}
  const metrics = Object.keys(windows)

  const cards: MetricCardData[] = useMemo(() => {
    return metrics
      .map((metricId) => {
        const metaFromTarget = targets?.metrics?.[metricId]
        const defaults = getMetricMeta(metricId)
        const unit = normalizeUnit(metaFromTarget?.unit ?? roll?.units?.[metricId] ?? defaults.unit)
        const mode = defaults.mode
        const rows = windows[metricId]
        const c5 = rows?.count?.[5]
        const c10 = rows?.count?.[10]
        const d30row = rows?.days?.[30]

        let w5: number | null = c5?.n >= 5 ? c5?.value ?? null : null
        let w10: number | null = c10?.n >= 10 ? c10?.value ?? null : null
        let d30: number | null = d30row?.n > 0 ? d30row?.value ?? null : null

        w5 = normalizeValue(unit, w5)
        w10 = normalizeValue(unit, w10)
        d30 = normalizeValue(unit, d30)

        const sparkRaw = roll?.series?.[metricId]?.values ?? []
        const spark = sparkRaw.map((v) => normalizeValue(unit, v)).filter((v): v is number => v != null)
        const series = spark

        const rawTarget = metaFromTarget?.target ?? null
        const displayTarget = (targets?.provisional && (!rawTarget || rawTarget === 0)) ? null : (rawTarget ?? null)

        return {
          id: metricId,
          title: metaFromTarget?.name ?? metricId,
          unit,
          mode,
          windows: { w5, w10, d30 },
          target: displayTarget,
          baseline: 'w10',
          spark,
          series,
          glossaryKey: defaults.glossaryKey ?? metricId,
        } satisfies MetricCardData
      })
  }, [metrics, targets, roll?.series, roll?.units, windows])

  const activeCard = useMemo(
    () => (activeMetricId ? cards.find((c) => c.id === activeMetricId) ?? null : null),
    [activeMetricId, cards],
  )

  const activeStatus: MetricStatus = useMemo(() => {
    if (!activeCard) return 'neutral'
    return computeStatus(activeCard.windows.w5, activeCard.target, activeCard.mode, activeCard.unit)
  }, [activeCard])

  const activeTrend = useMemo(() => {
    if (!activeCard) return 'flat'
    const baselineValue = activeCard.baseline === 'w10' ? activeCard.windows.w10 : activeCard.windows.d30
    return computeTrend(activeCard.windows.w5, baselineValue, activeCard.mode, activeCard.unit)
  }, [activeCard])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex items-center gap-3">
          {renderGoalProgress(targets)}
          <GlossaryButton />
          <FilterBar />
        </div>
      </div>
      <GISSummary />
      {err && <div className="card text-rose-400">{String(err?.message || err)}</div>}
      {!roll && (
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="card h-28 animate-pulse" />
          ))}
        </div>
      )}
      {roll && (
        <div className="grid auto-rows-fr grid-cols-1 gap-8 lg:grid-cols-2">
          {cards.map((card) => (
            <MetricCard
              key={card.id}
              id={card.id}
              title={card.title}
              unit={card.unit}
              mode={card.mode}
              windows={card.windows}
              target={card.target}
              baseline={card.baseline}
              glossaryKey={card.glossaryKey}
              spark={card.spark}
              onOpen={setActiveMetricId}
            />
          ))}
        </div>
      )}
      {activeCard && (
        <CardDrilldown
          open
          onClose={() => setActiveMetricId(null)}
          metricId={activeCard.id}
          title={activeCard.title}
          unit={activeCard.unit}
          mode={activeCard.mode}
          status={activeStatus}
          trend={activeTrend}
          value={activeCard.windows.w5}
          target={activeCard.target}
          windows={activeCard.windows}
          series={activeCard.series}
          glossaryKey={activeCard.glossaryKey}
          filtersQuery={filtersQuery}
        />
      )}
    </div>
  )
}

function renderGoalProgress(targets: TargetsResp | null) {
  if (!targets?.metrics) return null
  const weights: Record<string, number> = targets.weights || {}
  const entries = Object.keys(targets.metrics)
  let sumWeights = 0
  let weighted = 0
  for (const metric of entries) {
    const meta = targets.metrics[metric]
    if (meta.progress_ratio == null) continue
    const w = Number(weights[metric] ?? 1)
    if (w <= 0) continue
    sumWeights += w
    weighted += w * Math.max(0, Math.min(1, Number(meta.progress_ratio)))
  }
  const pct = sumWeights > 0 ? Math.round((weighted / sumWeights) * 100) : null
  if (pct == null) return null
  return (
    <span className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-200">
      Goal Progress: {pct}%
    </span>
  )
}

function normalizeUnit(unit: string): MetricUnit {
  switch (unit) {
    case 'rate':
    case 'percent':
      return 'percent'
    case 'gold':
      return 'gold'
    case 'xp':
      return 'xp'
    case 'time':
      return 'time'
    case 'count':
    default:
      return 'count'
  }
}

function normalizeValue(unit: MetricUnit, value: number | null | undefined): number | null {
  if (value === null || value === undefined) return null
  if (Number.isNaN(value)) return null
  if (unit === 'percent' && Math.abs(value) > 1) {
    return value / 100
  }
  return value
}
