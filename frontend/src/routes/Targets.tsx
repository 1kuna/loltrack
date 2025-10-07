import { useEffect, useState } from 'react'
import { api, put } from '../lib/api'

export default function Targets() {
  const [cfg, setCfg] = useState<any>(null)
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [targets, setTargets] = useState<any>(null)
  useEffect(() => {
    api('/config').then((c) => { setCfg(c); setWeights(c.metrics?.weights || {}) })
    api('/targets').then(setTargets)
  }, [])
  const update = async () => {
    const next = { ...cfg, metrics: { ...cfg.metrics, weights } }
    await put('/config', next)
    setCfg(next)
  }
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Targets</h1>
      {!cfg && <div className="card animate-pulse h-24"/>}
      {targets?.provisional && <div className="card text-warn">Provisional targets in use (need ≥10 baseline games).</div>}
      {cfg && (
        <div className="card space-y-2">
          <div className="font-semibold">Weights</div>
          {Object.entries(weights).map(([k,v]) => (
            <div key={k} className="flex items-center gap-2">
              <div className="w-40">{k}</div>
              <input className="bg-slate-800 rounded p-1" type="number" step="0.1" value={v} onChange={(e)=>setWeights({ ...weights, [k]: parseFloat(e.target.value) })} />
            </div>
          ))}
          <button className="mt-2 bg-accent text-black px-3 py-1 rounded" onClick={update}>Save</button>
        </div>
      )}
      {targets && (
        <div className="card">
          <div className="font-semibold mb-2">Targets</div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            {Object.entries(targets.by_metric || {}).map(([m, o]:any)=> (
              <div key={m} className="bg-slate-800 rounded p-2">
                <div className="font-semibold">{m}</div>
                <div>Target: {o.target}</div>
                <div>P50: {o.p50 ?? '—'}</div>
                <div>P75: {o.p75 ?? '—'}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
