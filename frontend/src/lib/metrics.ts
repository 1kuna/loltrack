import { formatByUnit } from './format'

export type MetricMode = 'higher_is_better' | 'lower_is_better' | 'earlier_is_better'
export type MetricUnit = 'count' | 'percent' | 'gold' | 'xp' | 'time'
export type MetricStatus = 'ok' | 'warn' | 'bad' | 'neutral'
export type TrendDirection = 'up' | 'down' | 'flat'

export type MetricMeta = {
  unit: MetricUnit
  mode: MetricMode
  glossaryKey?: string
}

export const METRIC_META: Record<string, MetricMeta> = {
  DL14: { unit: 'percent', mode: 'higher_is_better', glossaryKey: 'DL14' },
  CS10: { unit: 'count', mode: 'higher_is_better', glossaryKey: 'CS10' },
  CS14: { unit: 'count', mode: 'higher_is_better', glossaryKey: 'CS14' },
  GD10: { unit: 'gold', mode: 'higher_is_better', glossaryKey: 'GD10' },
  XPD10: { unit: 'xp', mode: 'higher_is_better', glossaryKey: 'XPD10' },
  CtrlWardsPre14: { unit: 'count', mode: 'higher_is_better', glossaryKey: 'CtrlWardsPre14' },
  FirstRecall: { unit: 'time', mode: 'earlier_is_better', glossaryKey: 'FirstRecall' },
  KPEarly: { unit: 'percent', mode: 'higher_is_better', glossaryKey: 'KPEarly' },
}

export const STATUS_THRESHOLDS: Record<'default' | MetricUnit, number> = {
  default: 0.1,
  count: 0.08,
  percent: 0.05,
  gold: 0.1,
  xp: 0.1,
  time: 0.05,
}

const TREND_EPSILON: Record<'default' | MetricUnit, number> = {
  default: 0.04,
  count: 0.06,
  percent: 0.03,
  gold: 0.05,
  xp: 0.05,
  time: 0.015,
}

const MODE_LABEL: Record<MetricMode, string> = {
  higher_is_better: 'Higher is better',
  lower_is_better: 'Lower is better',
  earlier_is_better: 'Earlier is better',
}

export function getModeLabel(mode: MetricMode): string {
  return MODE_LABEL[mode]
}

function toleranceFor(unit: MetricUnit | string): number {
  return STATUS_THRESHOLDS[(unit as MetricUnit)] ?? STATUS_THRESHOLDS.default
}

function trendEpsilonFor(unit: MetricUnit | string): number {
  return TREND_EPSILON[(unit as MetricUnit)] ?? TREND_EPSILON.default
}

export function computeStatus(value: number | null | undefined, target: number | null | undefined, mode: MetricMode, unit: MetricUnit): MetricStatus {
  if (value === null || value === undefined) return 'neutral'
  if (target === null || target === undefined || Number.isNaN(target)) return 'neutral'
  const tolerance = toleranceFor(unit)
  const v = Number(value)
  const t = Number(target)
  if (Number.isNaN(v) || Number.isNaN(t)) return 'neutral'
  if (mode === 'higher_is_better') {
    if (v >= t) return 'ok'
    if (v >= t * (1 - tolerance)) return 'warn'
    return 'bad'
  }
  // lower / earlier is better: hitting target requires v <= t
  if (v <= t) return 'ok'
  if (v <= t * (1 + tolerance)) return 'warn'
  return 'bad'
}

export function computeTrend(value: number | null | undefined, baseline: number | null | undefined, mode: MetricMode, unit: MetricUnit): TrendDirection {
  if (value === null || value === undefined) return 'flat'
  if (baseline === null || baseline === undefined) return 'flat'
  const v = Number(value)
  const b = Number(baseline)
  if (Number.isNaN(v) || Number.isNaN(b)) return 'flat'
  const delta = v - b
  const baselineMagnitude = Math.abs(b) > 1e-6 ? Math.abs(b) : 1
  let normalized = delta / baselineMagnitude
  if (mode !== 'higher_is_better') {
    normalized = -normalized
  }
  const epsilon = trendEpsilonFor(unit)
  if (normalized > epsilon) return 'up'
  if (normalized < -epsilon) return 'down'
  return 'flat'
}

export function trendNarrative(direction: TrendDirection): string {
  if (direction === 'up') return 'improving'
  if (direction === 'down') return 'declining'
  return 'holding steady'
}

export function trendArrow(direction: TrendDirection): string {
  if (direction === 'up') return '▲'
  if (direction === 'down') return '▼'
  return '—'
}

export function goalDeltaPhrase(value: number | null | undefined, target: number | null | undefined, mode: MetricMode, unit: MetricUnit): string {
  if (value === null || value === undefined) return 'Last 5 pending more data.'
  if (target === null || target === undefined || Number.isNaN(target)) return 'Goal not set yet.'
  const status = computeStatus(value, target, mode, unit)
  if (status === 'ok') return 'Last 5 leading vs target.'
  if (status === 'warn') return 'Last 5 near target.'
  return 'Last 5 trailing target.'
}

export function buildMicroCopy(value: number | null | undefined, target: number | null | undefined, mode: MetricMode, unit: MetricUnit): string {
  if (value === null || value === undefined) {
    if (target === null || target === undefined) {
      return 'Goal not set yet — play more matches to calibrate.'
    }
    return `Goal ${formatByUnit(unit, target)} · ${getModeLabel(mode)} · Need more data from upcoming games.`
  }
  if (target === null || target === undefined) {
    return 'Goal not set yet — set a target to unlock tracking.'
  }
  const goalText = `Goal ${formatByUnit(unit, target)}`
  const modeText = getModeLabel(mode)
  const delta = goalDeltaPhrase(value, target, mode, unit)
  return `${goalText} · ${modeText} · ${delta}`
}

export function getMetricMeta(metricId: string, fallback?: MetricMeta): MetricMeta {
  return METRIC_META[metricId] ?? fallback ?? { unit: 'count', mode: 'higher_is_better' }
}
