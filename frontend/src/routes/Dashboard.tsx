import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import ScoreCard from '../components/ScoreCard'
import { statusFor } from '../lib/format'
import FilterBar, { useSegmentParams, toQuery } from '../shared/FilterBar'

type RollingResp = { windows: any, series: Record<string,{values:number[]}>, summary:any, units: Record<string,string> }
type TargetsResp = { provisional: boolean, metrics: Record<string, { name: string, unit: string, target?: number|null }> }

export default function Dashboard() {
  const [roll, setRoll] = useState<RollingResp|null>(null)
  const [targets, setTargets] = useState<TargetsResp|null>(null)
  const [err, setErr] = useState<any>(null)
  const seg = useSegmentParams()
  useEffect(() => {
    let active = true
    const qs = toQuery(seg)
    Promise.all([
      api<RollingResp>(`/metrics/rolling${qs}`),
      api<TargetsResp>('/targets'),
    ]).then(([r,t])=>{ if(active){ setRoll(r); setTargets(t) } }).catch(e => { if(active) setErr(e) })
    return () => { active = false }
  }, [seg.key])
  const windows = roll?.windows || {}
  const metrics = Object.keys(windows)
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <FilterBar />
      </div>
      {err && <div className="card text-red-400">{String(err?.message||err)}</div>}
      {!roll && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {Array.from({length:6}).map((_,i)=>(<div key={i} className="card animate-pulse h-28"/>))}
        </div>
      )}
      {roll && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 auto-rows-fr">
          {metrics.map((m) => {
            const meta = targets?.metrics?.[m] || { name: m, unit: roll?.units?.[m]||'count', target: undefined }
            const rows = windows[m]
            const c5 = rows?.count?.[5]
            const c10 = rows?.count?.[10]
            const d30row = rows?.days?.[30]
            let w5: number|null = c5?.n >= 5 ? c5?.value ?? null : null
            let w10: number|null = c10?.n >= 10 ? c10?.value ?? null : null
            let d30: number|null = d30row?.n > 0 ? d30row?.value ?? null : null
            // For rate metrics, backend values are 0..100; display expects 0..1
            if (meta.unit === 'rate'){
              w5 = w5 != null ? w5/100.0 : null
              w10 = w10 != null ? w10/100.0 : null
              d30 = d30 != null ? d30/100.0 : null
            }
            const trend = roll?.series?.[m]?.values || null
            const status = statusFor(meta.unit as any, w5, meta.target)
            return (
              <ScoreCard
                key={m as any}
                id={m as any}
                title={meta.name}
                subtitle={'Avg last 5 | last 10 | last 30 days'}
                windows={{ w5, w10, d30 }}
                target={meta.target ?? null}
                unit={meta.unit as any}
                trend={trend}
                status={status}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}
