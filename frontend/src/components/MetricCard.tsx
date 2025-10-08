import { useEffect, useMemo, useRef, type KeyboardEvent } from 'react'
import { MoreHorizontal } from 'lucide-react'
import MiniLine from './MiniLine'
import StatusChip from './StatusChip'
import ProgressRibbon from './ProgressRibbon'
import MetricPills from './MetricPills'
import GlossaryButton from './GlossaryButton'
import { formatByUnit } from '../lib/format'
import { buildMicroCopy, computeStatus, computeTrend, trendNarrative, trendArrow, type MetricMode, type MetricUnit } from '../lib/metrics'
import { track } from '../lib/analytics'

export interface MetricCardProps {
  id: string
  title: string
  unit: MetricUnit
  mode: MetricMode
  windows: { w5: number | null; w10: number | null; d30: number | null }
  target?: number | null
  baseline?: 'w10' | 'd30'
  glossaryKey?: string
  spark?: Array<number>
  onOpen?: (id: string) => void
}

export default function MetricCard({
  id,
  title,
  unit,
  mode,
  windows,
  target = null,
  baseline = 'w10',
  glossaryKey,
  spark,
  onOpen,
}: MetricCardProps) {
  const ref = useRef<HTMLDivElement | null>(null)
  const hasTrackedView = useRef(false)
  const kpiValue = windows.w5
  const kpiText = formatByUnit(unit, kpiValue)
  const status = computeStatus(kpiValue, target, mode, unit)
  const baselineValue = windows[baseline]
  const trend = computeTrend(kpiValue, baselineValue, mode, unit)
  const trendIcon = trendArrow(trend)
  const trendText = trendNarrative(trend)
  const microCopy = buildMicroCopy(kpiValue, target, mode, unit)

  useEffect(() => {
    const el = ref.current
    if (!el || hasTrackedView.current) return
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !hasTrackedView.current) {
            hasTrackedView.current = true
            track('dashboard_card_view', { metric_id: id })
          }
        })
      },
      { threshold: 0.6 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [id])

  const handleOpen = () => {
    track('dashboard_card_click', { metric_id: id })
    onOpen?.(id)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      handleOpen()
    }
  }

  const pillsFormatter = useMemo(() => (value: number | null | undefined) => formatByUnit(unit, value), [unit])

  return (
    <div
      ref={ref}
      role="button"
      tabIndex={0}
      onClick={handleOpen}
      onKeyDown={onKeyDown}
      className="card group flex h-full cursor-pointer flex-col gap-4 p-6 transition ring-1 ring-transparent hover:ring-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60"
    >
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-semibold text-slate-200">{title}</h3>
          {glossaryKey && (
            <GlossaryButton
              variant="icon"
              anchor={glossaryKey}
              className="shrink-0"
            />
          )}
        </div>
        <button
          type="button"
          className="text-slate-500 hover:text-slate-200"
          aria-label="More options"
          onClick={(event) => {
            event.stopPropagation()
            // Placeholder for future quick actions
          }}
        >
          <MoreHorizontal size={16} />
        </button>
      </header>
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-wrap items-baseline gap-2">
          <div className="kpi text-2xl sm:text-3xl text-slate-100">{kpiText}</div>
          <div className="flex items-center gap-1 text-sm text-slate-400">
            <span aria-hidden>{trendIcon}</span>
            <span className="sr-only">{`Trend ${trendText}`}</span>
            <span className="hidden sm:inline">({trendText})</span>
          </div>
          <StatusChip status={status} />
        </div>
        <MetricPills windows={windows} format={pillsFormatter} />
      </div>
      <div className="space-y-3 pt-1">
        <ProgressRibbon value={kpiValue} target={target} mode={mode} />
        <div className="flex items-center gap-3 opacity-60">
          {spark && spark.length > 0 ? (
            <div className="w-full">
              <MiniLine values={spark} />
            </div>
          ) : (
            <div className="h-6 w-full rounded bg-slate-800/60" />
          )}
        </div>
        <p className="text-sm leading-relaxed text-slate-400">
          {microCopy}
        </p>
      </div>
    </div>
  )
}
