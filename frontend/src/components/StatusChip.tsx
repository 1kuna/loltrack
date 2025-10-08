type Status = 'ok' | 'warn' | 'bad' | 'neutral'

type StatusChipProps = {
  status: Status
  label?: string
  className?: string
}

const LABELS: Record<Status, string> = {
  ok: 'On track',
  warn: 'Near',
  bad: 'Behind',
  neutral: 'Near',
}

const STYLES: Record<Status, string> = {
  ok: 'text-emerald-400 bg-emerald-950/50 ring-emerald-500/20',
  warn: 'text-amber-400 bg-amber-950/50 ring-amber-500/20',
  bad: 'text-rose-400 bg-rose-950/50 ring-rose-500/20',
  neutral: 'text-slate-300 bg-slate-800/60 ring-slate-400/10',
}

export default function StatusChip({ status, label, className }: StatusChipProps) {
  const resolvedLabel = label ?? LABELS[status]
  const styles = [STYLES[status] ?? STYLES.warn, 'chip', className].filter(Boolean).join(' ')
  return (
    <span
      className={styles}
      aria-label={`status: ${resolvedLabel.toLowerCase()}`}
    >
      {resolvedLabel}
    </span>
  )
}
