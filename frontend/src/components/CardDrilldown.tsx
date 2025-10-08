import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip as LineTooltip,
  ReferenceLine,
  BarChart,
  Bar,
} from 'recharts'
import StatusChip from './StatusChip'
import ProgressRibbon from './ProgressRibbon'
import GlossaryButton from './GlossaryButton'
import { formatByUnit } from '../lib/format'
import { api } from '../lib/api'
import { track } from '../lib/analytics'
import { usePrefersReducedMotion } from '../lib/hooks'
import {
  buildMicroCopy,
  computeStatus,
  getModeLabel,
  goalDeltaPhrase,
  MetricMode,
  MetricStatus,
  MetricUnit,
  TrendDirection,
  trendNarrative,
  trendArrow,
} from '../lib/metrics'
import MetricPills from './MetricPills'

type MatchRow = {
  match_id: string
  game_creation_ms: number
  role?: string | null
  champion_id?: number | null
  result?: 'Win' | 'Lose'
  cs10?: number | null
  cs14?: number | null
  gd10?: number | null
  xpd10?: number | null
  dl14?: number | null
  ctrl_wards_pre14?: number | null
  first_recall_s?: number | null
  kp_early?: number | null
}

type DrilldownMatch = {
  id: string
  label: string
  createdAt: Date
  role?: string | null
  championId?: number | null
  result?: 'Win' | 'Lose'
  value: number | null
}

type CardDrilldownProps = {
  open: boolean
  onClose: () => void
  metricId: string
  title: string
  unit: MetricUnit
  mode: MetricMode
  status: MetricStatus
  trend: TrendDirection
  value: number | null
  target?: number | null
  windows: { w5: number | null; w10: number | null; d30: number | null }
  series?: number[]
  glossaryKey?: string
  filtersQuery?: string
}

type TabKey = 'overview' | 'history' | 'distribution' | 'coaching'

const TAB_LABELS: Record<TabKey, string> = {
  overview: 'Overview',
  history: 'History',
  distribution: 'Distribution',
  coaching: 'Coaching',
}

export default function CardDrilldown({
  open,
  onClose,
  metricId,
  title,
  unit,
  mode,
  status,
  trend,
  value,
  target,
  windows,
  series,
  glossaryKey,
  filtersQuery,
}: CardDrilldownProps) {
  const reduceMotion = usePrefersReducedMotion()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const closeRef = useRef<HTMLButtonElement | null>(null)
  const [tab, setTab] = useState<TabKey>('overview')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [matches, setMatches] = useState<DrilldownMatch[]>([])
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!open) return
    setTab('overview')
    setError(null)
    setCopied(false)
    fetchMatches()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, metricId, filtersQuery])

  useEffect(() => {
    if (!open) return
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      } else if (event.key === 'Tab') {
        const node = containerRef.current
        if (!node) return
        const focusable = node.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        )
        if (focusable.length === 0) return
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first.focus()
        } else if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last.focus()
        }
      }
    }
    const node = containerRef.current
    node?.addEventListener('keydown', handleKey)
    return () => node?.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => closeRef.current?.focus())
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    track('dashboard_drilldown_tab', { metric_id: metricId, tab })
  }, [tab, metricId, open])

  const microCopy = useMemo(() => buildMicroCopy(value, target ?? null, mode, unit), [value, target, mode, unit])

  const trendText = trendNarrative(trend)
  const trendSymbol = trendArrow(trend)

  const tabData = useMemo(() => buildTabData(matches, series, unit, mode, target ?? null), [matches, series, unit, mode, target])

  async function fetchMatches() {
    if (!open) return
    const qs = filtersQuery ? filtersQuery.replace(/^\?/, '') : ''
    const sep = qs ? '&' : ''
    const limit = 40
    const url = `/matches?${qs}${sep}limit=${limit}`
    setLoading(true)
    try {
      const rows = await api<MatchRow[]>(url)
      const mapped = rows.map((row, idx) => toDrilldownMatch(row, idx, metricId, unit))
      setMatches(mapped)
      setLoading(false)
    } catch (err: any) {
      setError(err?.message || 'Unable to load matches.')
      setLoading(false)
    }
  }

  if (!open) return null

  const handleCopyLink = async () => {
    try {
      const url = new URL(window.location.href)
      url.hash = `metric=${metricId}`
      await navigator.clipboard.writeText(url.toString())
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true">
      <div className="flex-1 bg-black/60" onClick={onClose} aria-hidden="true" />
      <div
        ref={containerRef}
        className="relative flex w-full max-w-3xl flex-col bg-slate-950 text-slate-100 shadow-2xl"
      >
        <header className="border-b border-slate-800/80 px-6 py-4">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <span aria-hidden>{trendSymbol}</span>
                <span>{trendText}</span>
                <StatusChip status={status} />
              </div>
              <h2 className="text-2xl font-semibold text-slate-50">{title}</h2>
            </div>
            <div className="flex items-center gap-3">
              {glossaryKey && (
                <GlossaryButton anchor={glossaryKey} />
              )}
              <button
                ref={closeRef}
                type="button"
                className="rounded bg-slate-800 px-3 py-1 text-sm text-slate-200 hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-500/60"
                onClick={onClose}
              >
                Close
              </button>
            </div>
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <div className="flex items-baseline gap-2">
                <div className="kpi text-2xl sm:text-3xl text-slate-100">{formatByUnit(unit, value)}</div>
                {typeof target === 'number' && (
                  <span className="text-sm text-slate-400">Goal {formatByUnit(unit, target)}</span>
                )}
              </div>
              <div className="mt-3">
                <ProgressRibbon value={value} target={target} mode={mode} />
              </div>
              <p className="mt-3 text-sm text-slate-400">{microCopy}</p>
            </div>
            <div className="rounded-lg border border-slate-800/60 bg-slate-900/40 p-3 text-sm text-slate-300">
              <div className="text-xs uppercase tracking-wide text-slate-500">Last windows</div>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <MetricPills windows={windows} format={(v) => formatByUnit(unit, v)} />
              </div>
              <div className="mt-3 space-y-1 text-xs text-slate-400">
                <div>{getModeLabel(mode)}</div>
                <div>{goalDeltaPhrase(windows.w5, target ?? null, mode, unit)}</div>
              </div>
            </div>
          </div>
        </header>
        <nav className="flex border-b border-slate-800/80 px-6">
          {(Object.keys(TAB_LABELS) as TabKey[]).map((key) => (
            <button
              key={key}
              type="button"
              className={`mr-4 border-b-2 pb-2 text-sm transition ${tab === key ? 'border-sky-400 text-sky-200' : 'border-transparent text-slate-400 hover:text-slate-200'}`}
              onClick={() => setTab(key)}
            >
              {TAB_LABELS[key]}
            </button>
          ))}
        </nav>
        <section className="flex-1 overflow-y-auto px-6 py-5">
          {loading && <div className="card h-32 animate-pulse bg-slate-900/60" />}
          {error && (
            <div className="card border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-200">
              {error}
            </div>
          )}
          {!loading && !error && (
            <>
              {tab === 'overview' && (
                <OverviewTab
                  matches={matches}
                  unit={unit}
                  mode={mode}
                  target={target ?? null}
                  metricId={metricId}
                />
              )}
              {tab === 'history' && (
                <HistoryTab
                  matches={matches}
                  series={series}
                  unit={unit}
                  target={target ?? null}
                  reduceMotion={reduceMotion}
                />
              )}
              {tab === 'distribution' && (
                <DistributionTab
                  data={tabData.distribution}
                  unit={unit}
                />
              )}
              {tab === 'coaching' && (
                <CoachingTab
                  suggestions={tabData.suggestions}
                />
              )}
            </>
          )}
        </section>
        <footer className="flex items-center justify-between gap-3 border-t border-slate-800/80 px-6 py-4 text-sm text-slate-400">
          <div className="flex items-center gap-3">
            <GlossaryButton
              anchor={glossaryKey ?? metricId}
              label="View Glossary"
              variant="link"
            />
            <button
              type="button"
              onClick={handleCopyLink}
              className="rounded bg-slate-800 px-2 py-1 text-sm text-slate-200 hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-500/60"
            >
              {copied ? 'Copied!' : 'Copy link to metric'}
            </button>
          </div>
          <div className="text-xs text-slate-500">
            Status chips compare to your current target.
          </div>
        </footer>
      </div>
    </div>
  )
}

function OverviewTab({ matches, unit, mode, target, metricId }: { matches: DrilldownMatch[]; unit: MetricUnit; mode: MetricMode; target: number | null; metricId: string }) {
  const rows = useMemo(() => matches.slice(0, 10), [matches])
  return (
    <div className="space-y-5">
      <div>
        <div className="text-sm font-semibold text-slate-200">Last 10 matches</div>
        <div className="mt-2 overflow-hidden rounded-lg border border-slate-800/60">
          <table className="min-w-full divide-y divide-slate-800/80 text-sm">
            <thead className="bg-slate-900/50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2 text-left">Match</th>
                <th className="px-3 py-2 text-left">Value</th>
                <th className="px-3 py-2 text-left">Outcome</th>
                <th className="px-3 py-2 text-left">Role/Champ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {rows.map((row) => {
                const status = computeStatus(row.value, target, mode, unit)
                const valueText = formatByUnit(unit, row.value)
                const className = status === 'ok'
                  ? 'text-emerald-300'
                  : status === 'warn'
                    ? 'text-amber-300'
                    : status === 'bad'
                      ? 'text-rose-300'
                      : 'text-slate-300'
                return (
                  <tr key={row.id}>
                    <td className="px-3 py-2 text-xs text-slate-400">{row.label}</td>
                    <td className={`px-3 py-2 font-semibold ${className}`}>{valueText}</td>
                    <td className="px-3 py-2">{row.result ?? '—'}</td>
                    <td className="px-3 py-2 text-xs text-slate-400">
                      {row.role ?? '—'} {row.championId ? `· ${row.championId}` : ''}
                    </td>
                  </tr>
                )
              })}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-4 text-center text-xs text-slate-500">
                    No matches yet — play more games to unlock details.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-slate-800/60 bg-slate-900/40 p-4 text-sm text-slate-300">
          <div className="font-semibold text-slate-200">Baseline</div>
          <p className="mt-1 text-xs text-slate-400">
            We compare your last 5 to the baseline (10-match median) to decide the arrow and chip.
          </p>
          <div className="mt-3 space-y-1 text-xs text-slate-400">
            <div>Mode: {getModeLabel(mode)}</div>
            {typeof target === 'number' ? (
              <div>Target: {formatByUnit(unit, target)}</div>
            ) : (
              <div>No goal set — add a target to track progress.</div>
            )}
          </div>
        </div>
        <div className="rounded-lg border border-slate-800/60 bg-slate-900/40 p-4 text-sm text-slate-300">
          <div className="font-semibold text-slate-200">What to watch</div>
          <ul className="mt-2 list-disc pl-4 text-xs text-slate-400">
            <li>Spot trends over the 10 most recent games.</li>
            <li>Use the tabs to see full history and distribution.</li>
            <li>Coaching tips adapt to your latest status.</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

function HistoryTab({
  matches,
  series,
  unit,
  target,
  reduceMotion,
}: {
  matches: DrilldownMatch[]
  series?: number[]
  unit: MetricUnit
  target: number | null
  reduceMotion: boolean
}) {
  const chronological = useMemo(() => {
    if (matches.length > 0) {
      return [...matches].reverse().map((m, idx) => ({
        index: idx + 1,
        label: m.label,
        value: m.value,
        result: m.result,
      }))
    }
    if (series && series.length > 0) {
      return series.map((v, idx) => ({
        index: idx + 1,
        label: `Game ${idx + 1}`,
        value: v,
      }))
    }
    return []
  }, [matches, series])

  return (
    <div className="space-y-4">
      <div className="text-sm text-slate-300">Last {chronological.length} samples</div>
      <div className="h-64 rounded-lg border border-slate-800/60 bg-slate-900/40 p-2">
        {chronological.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chronological}>
              <CartesianGrid stroke="rgba(148,163,184,0.2)" strokeDasharray="3 3" />
              <XAxis dataKey="index" tickLine={false} axisLine={false} stroke="#94a3b8" />
              <YAxis tickLine={false} axisLine={false} stroke="#94a3b8" tickFormatter={(v) => formatByUnit(unit, v)} />
              <LineTooltip
                content={({ active, payload }) => {
                  if (!active || !payload || payload.length === 0) return null
                  const item = payload[0]
                  return (
                    <div className="rounded bg-slate-900/95 px-3 py-2 text-xs text-slate-200 shadow">
                      <div>{item.payload?.label}</div>
                      <div className="font-semibold text-sky-300">{formatByUnit(unit, item.value as number)}</div>
                      {item.payload?.result && <div className="text-slate-400">{item.payload.result}</div>}
                    </div>
                  )
                }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#38bdf8"
                strokeWidth={2}
                dot={false}
                isAnimationActive={!reduceMotion}
              />
              {typeof target === 'number' && (
                <ReferenceLine y={target} stroke="#f97316" strokeDasharray="4 3" label={{ value: 'Goal', fill: '#f97316', position: 'insideTopRight', fontSize: 12 }} />
              )}
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">No history yet.</div>
        )}
      </div>
    </div>
  )
}

function DistributionTab({ data, unit }: { data: DistributionData; unit: MetricUnit }) {
  return (
    <div className="space-y-4">
      <div className="text-sm text-slate-300">Value distribution (last {data.samples} games)</div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="h-64 rounded-lg border border-slate-800/60 bg-slate-900/40 p-2">
          {data.bins.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.bins}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
                <XAxis dataKey="label" stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" />
                <LineTooltip
                  content={({ active, payload }) => {
                    if (!active || !payload || payload.length === 0) return null
                    const entry = payload[0]?.payload
                    return (
                      <div className="rounded bg-slate-900/95 px-3 py-2 text-xs text-slate-200 shadow">
                        <div>{entry?.label}</div>
                        <div>{entry?.count} matches</div>
                        <div className="text-slate-400">{formatByUnit(unit, entry?.range[0])} - {formatByUnit(unit, entry?.range[1])}</div>
                      </div>
                    )
                  }}
                />
                <Bar dataKey="count" fill="#38bdf8" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-500">Need more matches for a distribution.</div>
          )}
        </div>
        <div className="rounded-lg border border-slate-800/60 bg-slate-900/40 p-4 text-sm text-slate-300">
          <div className="font-semibold text-slate-200">Percentiles</div>
          <dl className="mt-3 space-y-2 text-xs text-slate-400">
            <div className="flex items-center justify-between">
              <dt>P50 (median)</dt>
              <dd className="text-slate-200">{formatByUnit(unit, data.p50)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt>P75 (top quartile)</dt>
              <dd className="text-slate-200">{formatByUnit(unit, data.p75)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt>Range</dt>
              <dd className="text-slate-200">
                {formatByUnit(unit, data.min)} – {formatByUnit(unit, data.max)}
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt>Samples</dt>
              <dd className="text-slate-200">{data.samples}</dd>
            </div>
          </dl>
          <p className="mt-3 text-xs text-slate-500">
            Hover bars to see match counts. Spread shows consistency; a tight cluster near your goal means you’re stabilizing.
          </p>
        </div>
      </div>
    </div>
  )
}

function CoachingTab({ suggestions }: { suggestions: string[] }) {
  return (
    <div className="space-y-4">
      <div className="text-sm text-slate-300">Actionable nudges based on your latest trend.</div>
      <ul className="space-y-3">
        {suggestions.map((item, idx) => (
          <li key={idx} className="rounded-lg border border-slate-800/60 bg-slate-900/40 p-4 text-sm text-slate-200">
            {item}
          </li>
        ))}
        {suggestions.length === 0 && (
          <li className="rounded-lg border border-slate-800/60 bg-slate-900/40 p-4 text-sm text-slate-400">
            Keep stacking games—tips unlock once we have enough data.
          </li>
        )}
      </ul>
    </div>
  )
}

function toDrilldownMatch(row: MatchRow, index: number, metricId: string, unit: MetricUnit): DrilldownMatch {
  const createdAt = new Date(row.game_creation_ms || Date.now())
  const label = createdAt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const rawValue = resolveMetricValue(row, metricId)
  return {
    id: row.match_id ?? `match-${index}`,
    label,
    createdAt,
    role: row.role,
    championId: row.champion_id,
    result: row.result,
    value: normalizeMetricValue(unit, rawValue),
  }
}

function resolveMetricValue(row: MatchRow, metricId: string): number | null {
  switch (metricId) {
    case 'CS10':
      return row.cs10 ?? null
    case 'CS14':
      return row.cs14 ?? null
    case 'GD10':
      return row.gd10 ?? null
    case 'XPD10':
      return row.xpd10 ?? null
    case 'DL14':
      return row.dl14 ?? null
    case 'CtrlWardsPre14':
      return row.ctrl_wards_pre14 ?? null
    case 'FirstRecall':
      return row.first_recall_s ?? null
    case 'KPEarly':
      return row.kp_early ?? null
    default:
      return null
  }
}

function normalizeMetricValue(unit: MetricUnit, value: number | null | undefined): number | null {
  if (value === null || value === undefined) return null
  if (Number.isNaN(value)) return null
  if (unit === 'percent' && Math.abs(value) > 1) {
    return value / 100
  }
  return value
}

type DistributionData = {
  samples: number
  bins: Array<{ label: string; count: number; range: [number, number] }>
  p50: number | null
  p75: number | null
  min: number | null
  max: number | null
  suggestions: string[]
}

function buildTabData(matches: DrilldownMatch[], series: number[] | undefined, unit: MetricUnit, mode: MetricMode, target: number | null) {
  const values = matches.map((m) => m.value).filter((v): v is number => v != null)
  const fallback = series?.filter((v): v is number => v != null)
  const pool = values.length > 0 ? values : (fallback ?? [])
  const distribution = buildDistribution(pool)
  const suggestions = buildSuggestions(mode, target, pool)
  return { distribution, suggestions }
}

function buildDistribution(values: number[]): DistributionData {
  if (!values || values.length === 0) {
    return {
      samples: 0,
      bins: [],
      p50: null,
      p75: null,
      min: null,
      max: null,
      suggestions: [],
    }
  }
  const sorted = [...values].sort((a, b) => a - b)
  const samples = sorted.length
  const min = sorted[0]
  const max = sorted[sorted.length - 1]
  const p50 = percentile(sorted, 0.5)
  const p75 = percentile(sorted, 0.75)
  const bins: Array<{ label: string; count: number; range: [number, number] }> = []
  const bucketCount = Math.min(8, Math.max(4, Math.ceil(Math.sqrt(samples))))
  const range = max - min || 1
  const step = range / bucketCount
  for (let i = 0; i < bucketCount; i += 1) {
    const start = min + i * step
    const end = i === bucketCount - 1 ? max : start + step
    const count = sorted.filter((v) => v >= start && v <= (i === bucketCount - 1 ? end : end)).length
    bins.push({
      label: `${formatSimple(start)}–${formatSimple(end)}`,
      count,
      range: [start, end],
    })
  }
  return {
    samples,
    bins,
    p50,
    p75,
    min,
    max,
    suggestions: [],
  }
}

function formatSimple(n: number) {
  if (Math.abs(n) >= 100) return Math.round(n)
  return Number(n.toFixed(1))
}

function percentile(values: number[], p: number) {
  if (values.length === 0) return null
  const idx = (values.length - 1) * p
  const lower = Math.floor(idx)
  const upper = Math.ceil(idx)
  if (lower === upper) return values[lower]
  const weight = idx - lower
  return values[lower] * (1 - weight) + values[upper] * weight
}

function buildSuggestions(mode: MetricMode, target: number | null, values: number[]): string[] {
  const suggestions: string[] = []
  if (!values || values.length === 0) {
    suggestions.push('Play a few more matches so we can tailor coaching tips for this metric.')
    return suggestions
  }
  const recent = values.slice(-5)
  const avgRecent = recent.reduce((sum, v) => sum + v, 0) / recent.length
  if (target != null) {
    if (mode === 'higher_is_better') {
      if (avgRecent < target) {
        suggestions.push('You’re trailing the goal—review last matches to find where tempo slipped and plan your next openings.')
      } else {
        suggestions.push('You’re beating the goal. Lock in the habits that got you here and push for stretch wins.')
      }
    } else {
      if (avgRecent > target) {
        suggestions.push('Goal is still out of reach—look for one specific habit to trim each game (e.g., secure recall timers or safer pathing).')
      } else {
        suggestions.push('Goal met! Keep reinforcing the routines that keep you ahead of schedule.')
      }
    }
  } else {
    suggestions.push('Set a manual target in Goals to get sharper coaching nudges for this metric.')
  }
  const volatility = Math.max(...recent) - Math.min(...recent)
  if (volatility > (Math.abs(avgRecent) * 0.2 || 1)) {
    suggestions.push('Results are swingy—re-watch the best and worst games to pin down what changes the result.')
  } else {
    suggestions.push('Consistency is improving—gradually raise the bar or add a new focus area once this feels automatic.')
  }
  return suggestions.slice(0, 3)
}
