import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type WindowRow = { value: number, n: number, trend: number, spark: string }

export default function Dashboard() {
  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState<string|null>(null)
  useEffect(() => {
    const t = setTimeout(()=>{}, 0)
    api('/metrics/rolling').then(setData).catch(e => setErr(String(e)))
    return () => clearTimeout(t)
  }, [])
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      {err && <div className="card text-bad">{err}</div>}
      {!data && (
        <div className="grid grid-cols-3 gap-4">
          {Array.from({length:6}).map((_,i)=>(<div key={i} className="card animate-pulse h-24"/>))}
        </div>
      )}
      {data && (
        <div className="grid grid-cols-3 gap-4">
          {Object.entries<any>(data.windows || {}).map(([metric, rows]) => (
            <div className="card" key={metric}>
              <div className="text-lg font-semibold">{metric}</div>
              <div className="text-sm text-slate-400">5g / 10g / 30d</div>
              <div className="mt-2 grid grid-cols-3 text-center">
                <div>{rows.count?.[5]?.value?.toFixed?.(1) ?? '—'}</div>
                <div>{rows.count?.[10]?.value?.toFixed?.(1) ?? '—'}</div>
                <div>{rows.days?.[30]?.value?.toFixed?.(1) ?? '—'}</div>
              </div>
              <div className="mt-1 text-xs text-slate-400">{rows.count?.[10]?.spark ?? ''}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
