type MetricWindow = {
  w5: number | null
  w10: number | null
  d30: number | null
}

type MetricPillsProps = {
  windows: MetricWindow
  format: (value: number | null | undefined) => string
}

function pillLabel(label: string, value: number | null | undefined, format: MetricPillsProps['format']) {
  if (value === null || value === undefined) return `${label}: —`
  return `${label}: ${format(value)}`
}

export default function MetricPills({ windows, format }: MetricPillsProps) {
  const entries = [
    pillLabel('10', windows.w10, format),
    pillLabel('30d', windows.d30, format),
  ]

  return (
    <div className="flex items-center gap-2">
      {entries.map((text) => (
        <span
          key={text}
          className="pill inline-flex items-center rounded-full border border-slate-800/70 bg-slate-900/60 px-2 py-0.5"
        >
          {text}
        </span>
      ))}
    </div>
  )
}
