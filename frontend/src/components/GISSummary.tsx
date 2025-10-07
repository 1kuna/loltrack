import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useSegmentParams, toQuery } from '../shared/FilterBar'

type GisSummary = {
  overall: number
  domains: Record<string, number>
  delta5: number
  confidence_band?: number
  focus: { primary: string|null, secondary: string[], deficits: Record<string, number>, advice?: string|null }
}

export default function GISSummary(){
  const [data, setData] = useState<GisSummary|null>(null)
  const [err, setErr] = useState<any>(null)
  const { seg } = useSegmentParams()
  useEffect(()=>{
    let active = true
    const qs = toQuery(seg)
    api<GisSummary>(`/gis/summary${qs}`).then(d=>{ if(active) setData(d) }).catch(e=>{ if(active) setErr(e) })
    return () => { active = false }
  }, [seg.queue, seg.role])
  if (err) return <div className="card text-red-400 text-sm">{String(err?.message||err)}</div>
  return (
    <div className="card p-4 flex items-center justify-between">
      <div className="flex items-center gap-6">
        <div>
          <div className="text-xs text-slate-400">Overall Improvement</div>
          <div className="text-3xl font-bold">
            {data?.gis_visible ? Math.round(data.overall) : '—'}
            {(data && data.calibration_stage < 2) && <span className="ml-2 text-xs text-amber-400 align-middle">Calibrating</span>}
          </div>
          <div className="text-xs text-slate-400">Δ last 5: <span className={twDelta(data?.delta5)}>{fmtDelta(data?.delta5)}</span></div>
          <div className="text-xs text-slate-500">Confidence: {bandLabel(data?.confidence_band)}</div>
          {/* Simple confidence ribbon */}
          <div className="mt-1 h-1 w-40 bg-slate-800 rounded relative overflow-hidden">
            <div className="absolute left-1/2 top-0 bottom-0 w-px bg-slate-600" />
            <div className="absolute top-0 bottom-0 bg-cyan-400/20 transition-all duration-200 ease-out" style={{ left: `${50 - Math.min(50, (data?.confidence_band||0)*5)}%`, width: `${Math.min(100, (data?.confidence_band||0)*10)}%` }} />
          </div>
        </div>
        <div className="hidden md:block w-px h-12 bg-slate-700" />
        <div>
          <div className="text-xs text-slate-400">Your biggest blocker</div>
          <div className="text-sm">{(data?.achilles_eligible && data?.focus?.primary) ? cap(data.focus.primary) : '—'}</div>
          {(data?.achilles_eligible && data?.focus?.advice) && <div className="text-xs text-slate-400 mt-1">{data.focus.advice}</div>}
          <div className="text-xs text-slate-400 mt-1">Also slipping:</div>
          <div className="flex gap-2 flex-wrap mt-1">
            {((data?.secondary_eligible && data?.focus?.secondary)||[]).map((d, i)=> (
              <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-200">{cap(d)}</span>
            ))}
            {(!data?.secondary_eligible || !data?.focus?.secondary || data.focus.secondary.length===0) && (<span className="text-[10px] text-slate-500">None</span>)}
          </div>
        </div>
      </div>
      <div className="text-xs text-slate-400">
        <span className="opacity-80">Domains: </span>
        {Object.entries(data?.domains||{}).map(([k,v]) => (
          <span key={k} className="mr-2">{cap(k)} <span className={twDelta(v-50)}>{fmtDelta(v-50)}</span></span>
        ))}
      </div>
    </div>
  )
}

function cap(s?: string|null){ return (s||'').slice(0,1).toUpperCase() + (s||'').slice(1) }
function fmtDelta(n?: number){ if(n==null) return '—'; const r = Math.round(n*10)/10; return (r>=0?'+':'') + r }
function twDelta(n?: number){ if(n==null) return ''; return n>0? 'text-green-400' : n<0? 'text-red-400' : '' }
function bandLabel(n?: number){ if(n==null) return '—'; if(n<=2) return 'narrow'; if(n<=5) return 'moderate'; return 'wide' }
