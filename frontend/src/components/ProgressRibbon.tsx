type ProgressMode = 'higher_is_better' | 'lower_is_better' | 'earlier_is_better'

type ProgressRibbonProps = {
  value: number | null | undefined
  target?: number | null | undefined
  mode: ProgressMode
  confidence?: number | null | undefined
}

function clamp01(n: number) {
  if (Number.isNaN(n)) return 0
  if (n < 0) return 0
  if (n > 1) return 1
  return n
}

function computeProgress(value: number | null | undefined, target: number | null | undefined, mode: ProgressMode) {
  if (value === null || value === undefined) return 0
  if (target === null || target === undefined || target === 0) {
    return 0
  }
  const v = Number(value)
  const t = Number(target)
  if (Number.isNaN(v) || Number.isNaN(t)) return 0
  if (mode === 'higher_is_better') {
    return clamp01(v / t)
  }
  if (mode === 'lower_is_better') {
    return clamp01(t / (v || Number.EPSILON))
  }
  // earlier_is_better: smaller times better
  return clamp01(t / (v || Number.EPSILON))
}

export default function ProgressRibbon({ value, target, mode, confidence }: ProgressRibbonProps) {
  const progress = computeProgress(value, target, mode)
  const pct = `${Math.round(progress * 100)}%`
  const barOpacity = confidence == null ? 1 : (0.3 + clamp01(Number(confidence)) * 0.7)
  return (
    <div
      className="ribbon-track"
      role="progressbar"
      aria-valuenow={Math.round(progress * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className="center-tick" aria-hidden />
      <div
        className="ribbon-fill"
        style={{ width: pct, opacity: barOpacity }}
      />
    </div>
  )
}

export { clamp01, computeProgress }
