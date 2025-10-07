export function fmtCount(n: number|null|undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return Math.round(n).toString()
}

export function fmtDiff(n: number|null|undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  const sign = n >= 0 ? '+' : '−'
  const v = Math.abs(Math.round(n))
  return `${sign}${v.toLocaleString()}`
}

export function fmtXP(n: number|null|undefined): string { return fmtDiff(n) }
export function fmtGold(n: number|null|undefined): string { return fmtDiff(n) }

export function fmtRate(frac: number|null|undefined): string {
  if (frac === null || frac === undefined || Number.isNaN(frac)) return '—'
  return `${(frac * 100).toFixed(1)}%`
}

export function fmtTime(seconds: number|null|undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '—'
  const s = Math.max(0, Math.round(seconds))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${String(m).padStart(2,'0')}:${String(r).padStart(2,'0')}`
}

export function formatByUnit(unit: string, value: number|null|undefined): string {
  switch(unit){
    case 'count': return fmtCount(value)
    case 'gold': return fmtGold(value)
    case 'xp': return fmtXP(value)
    case 'rate': return fmtRate(value ?? 0)
    case 'time': return fmtTime(value)
    default: return fmtCount(value)
  }
}

export function statusFor(unit: string, value: number|null|undefined, target?: number|null): 'ok'|'warn'|'bad'|'neutral' {
  if (value === null || value === undefined || target === null || target === undefined) return 'neutral'
  const v = value
  const t = target
  const within10 = Math.abs((v - t) / (t || 1)) <= 0.10
  if (unit === 'time') {
    if (v <= t) return 'ok'
    if (within10) return 'warn'
    return 'bad'
  }
  if (v >= t) return 'ok'
  if (within10) return 'warn'
  return 'bad'
}

