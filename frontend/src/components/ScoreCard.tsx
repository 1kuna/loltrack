import MiniBullet from './MiniBullet'
import MiniLine from './MiniLine'
import { formatByUnit, statusFor } from '../lib/format'

type ScoreCardProps = {
  id: 'CS10'|'CS14'|'DL14'|'GD10'|'XPD10'|'CtrlWardsPre14'|'FirstRecall'|'KPEarly',
  title: string,
  subtitle: string,
  windows: { w5: number|null, w10: number|null, d30: number|null },
  target?: number|null,
  unit: 'count'|'gold'|'xp'|'rate'|'time',
  trend: number[]|null,
  status: 'ok'|'warn'|'bad'|'neutral'
}

export default function ScoreCard(p: ScoreCardProps){
  const border = p.status==='ok' ? 'border-ok/70' : p.status==='warn' ? 'border-warn/70' : p.status==='bad' ? 'border-bad/70' : 'border-slate-800'
  return (
    <div className={`card relative overflow-hidden p-6 border-l-4 ${border}`}>
      {/* Header + numbers */}
      <div className="flex flex-col gap-4">
        <div className="min-w-0">
          <div className="text-[18px] leading-6 font-semibold truncate">{p.title || '—'}</div>
          <div className="text-[13px] leading-5 text-slate-400 truncate">{p.subtitle}</div>
        </div>
        <div className={`flex flex-wrap gap-x-10 gap-y-2`}>
          <MetricCol label="last 5" value={formatByUnit(p.unit, p.windows.w5)} status={statusFor(p.unit, p.windows.w5, p.target ?? undefined)} />
          <MetricCol label="last 10" value={formatByUnit(p.unit, p.windows.w10)} status={statusFor(p.unit, p.windows.w10, p.target ?? undefined)} />
          <MetricCol label="30 days" value={formatByUnit(p.unit, p.windows.d30)} status={statusFor(p.unit, p.windows.d30, p.target ?? undefined)} />
        </div>
      </div>
      {/* Viz below */}
      <div className="mt-4 flex items-center gap-4">
        <div className="w-1/3 min-w-[220px]">
          <MiniBullet value={p.windows.w5} target={p.target ?? undefined} unit={p.unit} />
        </div>
        <div className="flex-1">
          <div className="h-8"><MiniLine values={p.trend || undefined} /></div>
        </div>
      </div>
      {/* Footer hint */}
      <div className="mt-2 text-[12px] text-slate-400">
        {p.target != null && (<span>Target {formatByUnit(p.unit, p.target)} · </span>)}
        <span>{hintFor(p.unit, p.id)}</span>
      </div>
    </div>
  )
}

function MetricCol({label, value, status}:{label:string; value:string; status:'ok'|'warn'|'bad'|'neutral'}){
  const color = status==='ok' ? 'text-green-400' : status==='warn' ? 'text-amber-400' : status==='bad' ? 'text-red-400' : 'text-slate-300'
  return (
    <div className="w-[88px] text-center">
      <div className={`text-[22px] leading-7 font-semibold whitespace-nowrap truncate ${color}`}>{value}</div>
      <div className="text-[12px] text-slate-400">{label}</div>
    </div>
  )
}

function hintFor(unit: ScoreCardProps['unit'], id: ScoreCardProps['id']): string {
  if (unit === 'time') return 'Earlier is better'
  // For rates and leads, higher is better
  if (id === 'DL14') return 'Higher is better (no deaths pre-14)'
  if (id === 'KPEarly') return 'Higher is better (share of team kills pre-14)'
  return 'Higher is better'
}

// No extra exports here to keep React Fast Refresh happy.
