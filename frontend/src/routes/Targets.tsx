import { useEffect, useState } from 'react'
import { api, put } from '../lib/api'
import GlossaryDrawer from '../components/GlossaryDrawer'
import { formatByUnit } from '../lib/format'

export default function Targets() {
  const [cfg, setCfg] = useState<any>(null)
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [goals, setGoals] = useState<any>(null)
  const [overrides, setOverrides] = useState<Record<string, number|undefined>>({})
  useEffect(() => {
    api('/config').then((c) => { setCfg(c); setWeights(c.metrics?.weights || {}) })
    api('/targets').then((t)=>{ setGoals(t); const m = cTargets(t); setOverrides(m) })
    function cTargets(t:any){
      const out: Record<string, number|undefined> = {}
      Object.entries<any>(t.metrics||{}).forEach(([k,v])=>{ if (v.target != null) out[k] = v.target })
      return out
    }
  }, [])
  const saveWeights = async () => {
    const next = { ...cfg, metrics: { ...cfg.metrics, weights } }
    await put('/config', next)
    setCfg(next)
  }
  const saveOverrides = async () => {
    const next = { ...cfg, metrics: { ...cfg.metrics, targets: Object.fromEntries(Object.entries(overrides).map(([k,v])=>[k,{...((cfg?.metrics?.targets||{})[k]||{}), manual_floor: v}])) } }
    await put('/config', next)
    setCfg(next)
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Your goals (auto‑calibrated)</h1>
        <GlossaryDrawer />
      </div>
      {!cfg && <div className="card animate-pulse h-24"/>}
      {goals?.provisional && <div className="card text-amber-400">Using starter goals until we’ve seen 10 matches.</div>}
      {cfg && (
        <div className="card space-y-2">
          <div className="font-semibold">Weights</div>
          {Object.entries(weights).map(([k,v]) => (
            <div key={k} className="flex items-center gap-2">
              <div className="w-40">{k}</div>
              <input className="bg-slate-800 rounded p-1" type="number" step="0.1" value={v} onChange={(e)=>setWeights({ ...weights, [k]: parseFloat(e.target.value) })} />
            </div>
          ))}
          <button className="mt-2 bg-cyan-400 text-black px-3 py-1 rounded" onClick={saveWeights}>Save</button>
        </div>
      )}
      {goals && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Object.entries<any>(goals.metrics || {}).map(([m, o])=> (
            <div key={m} className="card space-y-1">
              <div className="text-[18px] leading-6 font-semibold">{o.name}</div>
              <div className="text-[28px] leading-8">{formatByUnit(o.unit, o.target)}</div>
              <div className="text-[12px] text-slate-400">Typical (P50): {o.p50 != null ? formatByUnit(o.unit, o.p50) : '—'} · Top 25% (P75): {o.p75 != null ? formatByUnit(o.unit, o.p75) : '—'}</div>
              <div className="mt-2 text-sm">
                <label className="mr-2">Manual target</label>
                <input className="bg-slate-800 rounded p-1 w-28" type="number" value={overrides[m] ?? ''} onChange={(e)=>setOverrides({...overrides, [m]: e.target.value===''? undefined : parseFloat(e.target.value)})} />
              </div>
            </div>
          ))}
        </div>
      )}
      {goals && (
        <div>
          <button className="mt-2 bg-cyan-400 text-black px-3 py-1 rounded" onClick={saveOverrides}>Save Overrides</button>
        </div>
      )}
    </div>
  )
}
