import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'

type Overview = {
  k: number; d: number; a: number; kda: number; kp: number
  dpm: number; gpm: number; csm: number
  gd10: number; gd15: number; xpd10: number; xpd15: number
  dmgObj: number; dmgTurrets: number; dmgToChamps: number; dmgTaken: number
  visionPerMin: number; wardsPlaced: number; wardsKilled: number
  items: { id: number; t: number }[]
  mythicAtS?: number | null
  twoItemAtS?: number | null
  objParticipation?: number
  roamDistancePre14?: number
  runes?: { primary: number; sub: number; shards: number[] }
}
type Series = { minutes: number[]; goldDiff: number[]; xpDiff: number[]; cs: number[] }
type Events = { elite: any[]; buildings: any[]; kills: any[]; wards: any[]; items: any[] }
type AdvResponse = { overview: Overview, series: Series, events: Events }
type GisMatch = { domains: Record<string, number>, overall_inst: number, z: Record<string, Record<string, number>>, debug?: Record<string, { inputs: number, metrics: string[], value: number }> }

export default function MatchDrawer({ matchId, onClose }: { matchId: string, onClose: () => void }){
  const [data, setData] = useState<AdvResponse | null>(null)
  const [err, setErr] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [advanced, setAdvanced] = useState<boolean>(() => {
    try { return localStorage.getItem('lt:advanced') === '1' } catch { return false }
  })
  const [open, setOpen] = useState<{[k:string]:boolean}>(()=>{
    try { return JSON.parse(localStorage.getItem('lt:md-open')||'{}') } catch { return { overview: true } }
  })
  useEffect(()=>{ try { localStorage.setItem('lt:advanced', advanced ? '1':'0') } catch {} }, [advanced])
  useEffect(()=>{ try { localStorage.setItem('lt:md-open', JSON.stringify(open)) } catch {} }, [open])
  useEffect(()=>{
    setLoading(true)
    api<AdvResponse>(`/match/${matchId}/advanced`).then((d)=>{ setData(d); setLoading(false) }).catch((e)=>{ setErr(e); setLoading(false) })
  }, [matchId])
  const [gis, setGis] = useState<GisMatch|null>(null)
  const [gisLoading, setGisLoading] = useState(false)
  const [gisErr, setGisErr] = useState<string|null>(null)
  const [showDiag, setShowDiag] = useState(false)
  useEffect(()=>{
    fetchGis(false)
  }, [matchId])
  async function fetchGis(recompute: boolean){
    setGisLoading(true)
    setGisErr(null)
    api<GisMatch>(`/gis/match/${matchId}${recompute ? '?recompute=1' : ''}`)
      .then(setGis)
      .catch((e)=>{ setGisErr(String(e?.message||e)) })
      .finally(()=> setGisLoading(false))
  }
  const kdaColor = useMemo(()=>{
    const kda = data?.overview.kda || 0
    if (kda >= 4) return 'text-emerald-300'
    if (kda >= 2) return 'text-sky-300'
    return 'text-slate-300'
  }, [data])
  return (
    <div className="fixed inset-0 bg-black/50 flex items-stretch justify-end z-50" onClick={onClose}>
      <div className="w-full sm:w-[720px] bg-slate-950 p-4 border-l border-slate-800 overflow-y-auto" onClick={(e)=>e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xl font-semibold">Match Details</h2>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1 text-xs text-slate-300">
              <input type="checkbox" className="accent-cyan-400" checked={advanced} onChange={(e)=>setAdvanced(e.target.checked)} />
              Advanced
            </label>
            <button className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700" onClick={onClose}>Close</button>
          </div>
        </div>
        {loading && <div className="card animate-pulse h-24" />}
        {err && <div className="card text-red-400">{String(err?.message||err)}</div>}
        {data && (
          <div className="space-y-4">
            <section className="card p-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                <Metric label="K/D/A" value={<span className={kdaColor}>{data.overview.k}/{data.overview.d}/{data.overview.a}</span>} sub={`${data.overview.kda.toFixed(2)} KDA · ${data.overview.kp.toFixed(1)}% KP`} />
                <Metric label="DPM · GPM" value={`${Math.round(data.overview.dpm)} · ${Math.round(data.overview.gpm)}`} sub={`${data.overview.csm.toFixed(2)} CS/m`} />
                <Metric label="Gold Diff" value={`${fmtSign(data.overview.gd10)} · ${fmtSign(data.overview.gd15)}`} sub={`@10 · @15`} />
                <Metric label="XP Diff" value={`${fmtSign(data.overview.xpd10)} · ${fmtSign(data.overview.xpd15)}`} sub={`@10 · @15`} />
                {data.overview.runes && (
                  <div>
                    <div className="text-slate-400 text-xs">Runes</div>
                    <div className="flex items-center gap-2">
                      <img className="w-6 h-6" src={`/assets/rune-style/${data.overview.runes.primary}.png`} />
                      <img className="w-6 h-6" src={`/assets/rune-style/${data.overview.runes.sub}.png`} />
                    </div>
                    <div className="text-slate-500 text-[10px] mt-1">Shards: {data.overview.runes.shards.join('/')}</div>
                  </div>
                )}
                {advanced && <Metric label="Objective Dmg" value={`${data.overview.dmgObj}`} sub={`Turrets ${data.overview.dmgTurrets}`} />}
                {advanced && <Metric label="Vision" value={`${data.overview.visionPerMin.toFixed(2)}/m`} sub={`W ${data.overview.wardsPlaced} · WK ${data.overview.wardsKilled}`} />}
                {advanced && <Metric label="Obj Part" value={`${(data.overview.objParticipation ?? 0).toFixed(1)}%`} sub={`Team Obj Contrib`} />}
                {advanced && <Metric label="Roam ≤14m" value={`${Math.round(data.overview.roamDistancePre14 ?? 0)}`} sub={`Path length`} />}
                {advanced && <Metric label="Ward Clears" value={`${(data.overview as any).wardClearsPre14 ?? 0}`} sub={`≤14m (${(data.overview as any).wardClears ?? 0} total)`} />}
                {advanced && <Metric label="Plates" value={`${(data.overview as any).platesPre14 ?? 0}`} sub={`≤14m`} />}
              </div>
              <div className="flex flex-wrap gap-2 mt-3">
                {topChips(data.overview).map((c,i)=>(
                  <span key={i} className="text-xs px-2 py-1 rounded bg-slate-800 text-slate-200">{c}</span>
                ))}
              </div>
            </section>
            {gis && (
              <section className="card p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-semibold">Domain Contributions</h3>
                  <div className="flex items-center gap-2">
                    {gisErr && <span className="text-xs text-red-400">{gisErr}</span>}
                    <button className="text-xs text-slate-400 hover:text-slate-200" onClick={()=>setShowDiag(v=>!v)}>{showDiag ? 'Hide Diagnostics' : 'Show Diagnostics'}</button>
                    <button disabled={gisLoading} className="text-xs text-slate-400 hover:text-slate-200" onClick={()=>fetchGis(true)}>{gisLoading ? 'Refreshing…' : 'Refresh'}</button>
                  </div>
                </div>
                <div className="space-y-2">
                  {Object.entries(gis.domains).map(([k,v])=> (
                    <DomainBar key={k} label={cap(k)} value={v} />
                  ))}
                </div>
                {showDiag && (
                  <div className="mt-3 text-xs text-slate-400 space-y-1">
                    {Object.keys(gis.domains).map((d)=>{
                      const inputs = (gis.debug?.[d]?.inputs) ?? Object.keys(gis.z?.[d]||{}).length
                      const mets = Object.entries(gis.z?.[d]||{}).map(([m,z]) => `${m}:${z.toFixed(2)}`).join(', ')
                      return (
                        <div key={d}>
                          <span className="text-slate-300">{cap(d)}</span>: inputs {inputs} {mets? `· ${mets}`: '(no inputs)'}
                        </div>
                      )
                    })}
                  </div>
                )}
              </section>
            )}
            <section className="card p-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold">Combat</h3>
                <button className="text-xs text-slate-400" onClick={()=>setOpen(o=>({ ...o, combat: !o.combat }))}>{open.combat ? 'Hide' : 'Show'}</button>
              </div>
              {open.combat && (
                <div className="space-y-2 text-sm">
                  <Bar label="Damage to Champs" value={data.overview.dmgToChamps} max={max4(data.overview)} color="#22d3ee" />
                  <Bar label="Damage to Objectives" value={data.overview.dmgObj} max={max4(data.overview)} color="#a78bfa" />
                  <Bar label="Damage to Turrets" value={data.overview.dmgTurrets} max={max4(data.overview)} color="#f472b6" />
                  <Bar label="Damage Taken" value={data.overview.dmgTaken} max={max4(data.overview)} color="#f87171" />
                </div>
              )}
            </section>
            <section className="card p-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold">Objectives</h3>
                <button className="text-xs text-slate-400" onClick={()=>setOpen(o=>({ ...o, objectives: !o.objectives }))}>{open.objectives ? 'Hide' : 'Show'}</button>
              </div>
              {open.objectives && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                  <ObjectiveCounts events={data.events} />
                </div>
              )}
            </section>
            <section className="card p-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold">Vision</h3>
                <button className="text-xs text-slate-400" onClick={()=>setOpen(o=>({ ...o, vision: !o.vision }))}>{open.vision ? 'Hide' : 'Show'}</button>
              </div>
              {open.vision && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                  <Metric label="Vision/m" value={data.overview.visionPerMin.toFixed(2)} />
                  <Metric label="Wards Placed" value={data.overview.wardsPlaced} />
                  <Metric label="Wards Killed" value={data.overview.wardsKilled} />
                  <Metric label="Ward Events" value={data.events.wards.length} />
                </div>
              )}
            </section>
            <section className="card p-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold">Build</h3>
                <button className="text-xs text-slate-400" onClick={()=>setOpen(o=>({ ...o, build: !o.build }))}>{open.build ? 'Hide' : 'Show'}</button>
              </div>
              {open.build && <div className="flex flex-wrap gap-2 items-center text-xs">
                {data.overview.items.sort((a,b)=>a.t-b.t).slice(0,20).map((it,i)=> (
                  <div key={i} className="flex items-center gap-1">
                    <img className="w-6 h-6 rounded" src={`/assets/item/${it.id}.png`} />
                    <span className="text-slate-300">{fmtTime(it.t)}</span>
                  </div>
                ))}
              </div>}
              {open.build && (
                <div className="text-xs text-slate-400 mt-2">
                  Mythic {data.overview.mythicAtS ? fmtTime(data.overview.mythicAtS) : '—'} · 2-item {data.overview.twoItemAtS ? fmtTime(data.overview.twoItemAtS) : '—'} · Trinket { (data.overview as any).trinketSwapAtS ? fmtTime((data.overview as any).trinketSwapAtS) : '—'}
                </div>
              )}
            </section>
            <section className="card p-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">Timeline</h3>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400">0–20m focus</span>
                  <button className="text-xs text-slate-400" onClick={()=>setOpen(o=>({ ...o, timeline: !o.timeline }))}>{open.timeline ? 'Hide' : 'Show'}</button>
                </div>
              </div>
              {open.timeline && <TimelineMini series={data.series} />}
            </section>
          </div>
        )}
      </div>
    </div>
  )
}

function Metric({ label, value, sub }: { label: string, value: any, sub?: string }){
  return (
    <div>
      <div className="text-slate-400 text-xs">{label}</div>
      <div className="text-slate-100 text-base">{value}</div>
      {sub && <div className="text-slate-500 text-xs">{sub}</div>}
    </div>
  )
}

function fmtSign(n: number){ if(n==null) return '—'; const s = n>=0?'+':'−'; return `${s}${Math.abs(Math.round(n))}` }
function fmtTime(s: number){ if(!s) return '—'; const m = Math.floor(s/60), ss = s%60; return `${m}:${String(ss).padStart(2,'0')}` }

function TimelineMini({ series }: { series: Series }){
  const [m, setM] = useState(series.minutes[series.minutes.length-1] || 0)
  useEffect(()=>{ setM(series.minutes[series.minutes.length-1] || 0) }, [series])
  const i = Math.max(0, Math.min(series.minutes.length-1, series.minutes.indexOf(m)))
  const gold = series.goldDiff[i] ?? 0
  const xp = series.xpDiff[i] ?? 0
  return (
    <div className="space-y-2">
      <input type="range" min={0} max={series.minutes[series.minutes.length-1]||0} value={m} onChange={(e)=>setM(Number(e.target.value))} className="w-full" />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
        <Metric label="Gold Diff" value={fmtSign(gold)} sub={`@${m} min`} />
        <Metric label="XP Diff" value={fmtSign(xp)} sub={`@${m} min`} />
        <Metric label="CS" value={`${series.cs[i] ?? 0}`} sub={`@${m} min`} />
      </div>
    </div>
  )
}

function DomainBar({ label, value }: { label: string, value: number }){
  const diff = (value ?? 50) - 50
  const color = diff >= 0 ? 'bg-green-500/70' : 'bg-red-500/70'
  const width = Math.max(0, Math.min(100, Math.abs(diff)))
  return (
    <div>
      <div className="text-xs text-slate-400">{label} <span className={diff>=0?'text-green-300':'text-red-300'}>({formatSigned(diff, 1)})</span></div>
      <div className="h-2 bg-slate-800 rounded relative overflow-hidden">
        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-slate-600" />
        <div className={`${color} h-full`} style={{ width: `${width}%`, marginLeft: diff>=0 ? '50%' : `calc(50% - ${width}%)` }} />
      </div>
    </div>
  )
}
function cap(s: string){ return s.slice(0,1).toUpperCase()+s.slice(1) }

function formatSigned(n: number, decimals=0){
  const sign = n >= 0 ? '+' : '−'
  const abs = Math.abs(n)
  const fixed = abs.toFixed(decimals)
  return `${sign}${fixed}`
}

function topChips(o: Overview): string[] {
  const out: string[] = []
  if (o.dpm >= 600) out.push('High DPM')
  if ((o.objParticipation ?? 0) >= 60) out.push('Objective Beast')
  if (o.visionPerMin >= 1.0) out.push('Vision King')
  return out
}

function ObjectiveCounts({ events }: { events: Events }){
  const drakes = events.elite.filter((e:any)=>e.monsterType==='DRAGON').length
  const heralds = events.elite.filter((e:any)=>e.monsterType==='RIFTHERALD').length
  const barons = events.elite.filter((e:any)=>e.monsterType==='BARON_NASHOR').length
  const towers = events.buildings.filter((e:any)=>e.buildingType==='TOWER_BUILDING').length
  return (
    <>
      <Metric label="Drakes" value={drakes} />
      <Metric label="Heralds" value={heralds} />
      <Metric label="Barons" value={barons} />
      <Metric label="Towers" value={towers} />
    </>
  )
}

function max4(o: Overview){ return Math.max(o.dmgToChamps||0, o.dmgObj||0, o.dmgTurrets||0, o.dmgTaken||0, 1) }
function Bar({ label, value, max, color }: { label: string, value: number, max: number, color: string }){
  const w = Math.max(4, Math.round((value / (max || 1)) * 100))
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-400"><span>{label}</span><span>{value}</span></div>
      <div className="h-2 bg-slate-800 rounded">
        <div className="h-2 rounded" style={{ width: `${w}%`, backgroundColor: color }} />
      </div>
    </div>
  )
}
