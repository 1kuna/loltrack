import { useEffect, useMemo, useState } from 'react'
import { api, put, mapErrorMessage } from '../lib/api'
import GlossaryButton from '../components/GlossaryButton'
import { formatByUnit } from '../lib/format'

export default function Targets() {
  const [cfg, setCfg] = useState<any>(null)
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [goals, setGoals] = useState<any>(null)
  const [overrides, setOverrides] = useState<Record<string, number|undefined>>({})
  const [errors, setErrors] = useState<Record<string, string|undefined>>({})
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState<{ kind: 'success'|'error', msg: string }|null>(null)
  const [lastSavedAt, setLastSavedAt] = useState<Date|null>(null)
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
  // Helpers for input normalization/validation
  const unitOf = useMemo(() => {
    const u: Record<string, string> = {}
    Object.entries<any>(goals?.metrics || {}).forEach(([k,v]) => { u[k] = v.unit })
    return u
  }, [goals])

  function parseRateInput(raw: string): number|undefined {
    if (raw == null) return undefined
    const s = String(raw).trim()
    if (s === '') return undefined
    // Accept forms: 0.65, 65, 65%
    const pct = s.endsWith('%') ? s.slice(0,-1).trim() : s
    const n = Number(pct)
    if (Number.isNaN(n)) return NaN
    // If value > 1 assume percent and convert; if <= 1 assume already fraction
    const frac = n > 1 ? (n / 100) : n
    return frac
  }

  function validateOverrides(inp: Record<string, number|undefined>): { ok: boolean, errs: Record<string, string|undefined>, normalized: Record<string, number|undefined> }{
    const errs: Record<string, string|undefined> = {}
    const norm: Record<string, number|undefined> = {}
    for (const [k, v] of Object.entries(inp)){
      const unit = unitOf[k]
      if (v === undefined || v === null || Number.isNaN(v as any)) { norm[k] = undefined; continue }
      if (unit === 'rate'){
        // Already normalized to fraction in state
        const f = Number(v)
        if (f < 0 || f > 1){ errs[k] = 'Enter 0–100% (e.g., 65 or 0.65)'; continue }
        norm[k] = f
      } else {
        norm[k] = Number(v)
      }
    }
    const ok = Object.values(errs).every((e)=>!e)
    return { ok, errs, normalized: norm }
  }

  const saveOverrides = async () => {
    // Validate before submit
    const { ok, errs, normalized } = validateOverrides(overrides)
    setErrors(errs)
    if (!ok){
      setToast({ kind: 'error', msg: 'Fix invalid inputs before saving.' })
      return
    }
    const next = { ...cfg, metrics: { ...cfg.metrics, targets: Object.fromEntries(Object.entries(normalized).map(([k,v])=>[k,{...((cfg?.metrics?.targets||{})[k]||{}), manual_floor: v}])) } }
    setSaving(true)
    try {
      const saved = await put('/config', next)
      setCfg(saved)
      // Refresh targets to reflect canonical rendering immediately
      try {
        const t = await api('/targets')
        setGoals(t)
        const m: Record<string, number|undefined> = {}
        Object.entries<any>(t.metrics||{}).forEach(([k,v])=>{ if (v.target != null) m[k] = v.target })
        setOverrides(m)
      } catch {}
      setToast({ kind: 'success', msg: 'Saved' })
      setLastSavedAt(new Date())
    } catch (e:any){
      setToast({ kind: 'error', msg: mapErrorMessage(e) })
    } finally {
      setSaving(false)
      // Auto-hide toast after 2s
      setTimeout(()=>setToast(null), 2000)
    }
  }
  async function resetOverrides(){
    setSaving(true)
    try {
      await api('/targets/overrides', { method: 'DELETE' })
      const t = await api('/targets')
      setGoals(t)
      const m: Record<string, number|undefined> = {}
      Object.entries<any>(t.metrics||{}).forEach(([k,v])=>{ if (v.target != null) m[k] = v.target })
      setOverrides(m)
      setToast({ kind: 'success', msg: 'Overrides cleared' })
      setLastSavedAt(new Date())
    } catch(e:any){
      setToast({ kind: 'error', msg: mapErrorMessage(e) })
    } finally {
      setSaving(false)
      setTimeout(()=>setToast(null), 2000)
    }
  }

  async function resetRoleWeightsToDefaults(){
    // Default role domain weights (API-facing schema: Title Case domains)
    const roles = {
      TOP: { Laning: 0.30, Economy: 0.20, Damage: 0.15, Macro: 0.15, Objectives: 0.10, Vision: 0.05, Discipline: 0.05 },
      JUNGLE: { Objectives: 0.30, Macro: 0.20, Laning: 0.10, Economy: 0.10, Damage: 0.10, Vision: 0.10, Discipline: 0.10 },
      MID: { Laning: 0.28, Damage: 0.20, Economy: 0.18, Macro: 0.14, Objectives: 0.10, Vision: 0.05, Discipline: 0.05 },
      ADC: { Economy: 0.25, Damage: 0.22, Laning: 0.22, Objectives: 0.12, Macro: 0.09, Vision: 0.05, Discipline: 0.05 },
      SUPPORT: { Vision: 0.28, Objectives: 0.20, Macro: 0.14, Laning: 0.14, Damage: 0.12, Economy: 0.06, Discipline: 0.06 },
    }
    setSaving(true)
    try {
      await put('/gis/weights', { roles })
      setToast({ kind: 'success', msg: 'Weights reset' })
    } catch (e:any){
      setToast({ kind: 'error', msg: mapErrorMessage(e) })
    } finally {
      setSaving(false)
      setTimeout(()=>setToast(null), 2000)
    }
  }
  function onInputChange(m: string, unit: string, raw: string){
    if (unit === 'rate'){
      const v = parseRateInput(raw)
      if (v === undefined){ setOverrides({ ...overrides, [m]: undefined }); setErrors({ ...errors, [m]: undefined }); return }
      if (Number.isNaN(v)) { setErrors({ ...errors, [m]: 'Enter a number like 65 or 0.65' }); return }
      setOverrides({ ...overrides, [m]: v })
      // Validate on change
      if (v < 0 || v > 1) setErrors({ ...errors, [m]: 'Enter 0–100% (e.g., 65 or 0.65)' })
      else setErrors({ ...errors, [m]: undefined })
    } else {
      const n = raw === '' ? undefined : Number(raw)
      setOverrides({ ...overrides, [m]: (n as any) })
      setErrors({ ...errors, [m]: (raw!=='' && Number.isNaN(n)) ? 'Enter a number' : undefined })
    }
  }

  function lastSavedText(){
    if (!lastSavedAt) return null
    const d = lastSavedAt
    const hh = String(d.getHours()).padStart(2,'0')
    const mm = String(d.getMinutes()).padStart(2,'0')
    return `Last saved ${hh}:${mm}`
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Your goals (auto‑calibrated)</h1>
        <GlossaryButton />
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
          <div className="flex items-center gap-3">
            <button className="mt-2 bg-cyan-400 text-black px-3 py-1 rounded" onClick={saveWeights}>Save</button>
            <button disabled={saving} className={`mt-2 px-3 py-1 rounded ${saving? 'bg-slate-600 text-slate-300' : 'bg-slate-700 text-slate-100 hover:bg-slate-600'}`} onClick={resetRoleWeightsToDefaults}>Reset Weights</button>
          </div>
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
                {o.unit === 'rate' ? (
                  <input
                    className={`bg-slate-800 rounded p-1 w-32 ${errors[m] ? 'outline outline-1 outline-red-500' : ''}`}
                    type="text"
                    placeholder="e.g., 65%"
                    value={overrides[m] != null ? String(overrides[m]) : ''}
                    onChange={(e)=>onInputChange(m, o.unit, e.target.value)}
                    onKeyDown={(e)=>{ if (e.key === 'Enter') saveOverrides() }}
                  />
                ) : (
                  <input
                    className={`bg-slate-800 rounded p-1 w-28 ${errors[m] ? 'outline outline-1 outline-red-500' : ''}`}
                    type="number"
                    value={overrides[m] ?? ''}
                    onChange={(e)=>onInputChange(m, o.unit, e.target.value)}
                    onKeyDown={(e)=>{ if (e.key === 'Enter') saveOverrides() }}
                  />
                )}
                {errors[m] && <div className="text-xs text-red-400 mt-1">{errors[m]}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
      {goals && (
        <div>
          <div className="flex items-center gap-3">
            <button disabled={saving} className={`mt-2 px-3 py-1 rounded ${saving? 'bg-slate-600 text-slate-300' : 'bg-cyan-400 text-black hover:bg-cyan-300'}`} onClick={saveOverrides}>{saving ? 'Saving…' : 'Save Overrides'}</button>
            <div className="text-xs text-slate-400">{lastSavedText()}</div>
            <button disabled={saving} className={`mt-2 px-3 py-1 rounded ${saving? 'bg-slate-600 text-slate-300' : 'bg-slate-700 text-slate-100 hover:bg-slate-600'}`} onClick={resetOverrides}>Reset Overrides</button>
          </div>
        </div>
      )}
      {toast && (
        <div className={`fixed bottom-4 right-4 px-3 py-2 rounded shadow ${toast.kind==='success'?'bg-emerald-500 text-black':'bg-red-500 text-white'}`}>{toast.msg}</div>
      )}
    </div>
  )
}
