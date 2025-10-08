import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { queueName } from '../lib/queues'
import { api } from '../lib/api'

export type Segment = { queue?: number|null, role?: string|null, champion?: number|null, patch?: string|null }

export function useSegmentParams(){
  const [sp, setSp] = useSearchParams()
  const seg: Segment = useMemo(()=>({
    queue: sp.get('queue') ? Number(sp.get('queue')) : -1,
    role: sp.get('role') || undefined,
    champion: sp.get('champion') ? Number(sp.get('champion')) : undefined,
    patch: sp.get('patch') || undefined,
  }), [sp])
  // Key to refetch when any param changes
  const key = `${seg.queue ?? ''}|${seg.role ?? ''}|${seg.champion ?? ''}`
  return { seg, key, sp, setSp }
}

export function toQuery(arg: { seg: Segment } | Segment): string {
  const s: Segment = (arg as any).seg ?? (arg as Segment)
  const params = new URLSearchParams()
  if (s.queue != null && !Number.isNaN(s.queue)) params.set('queue', String(s.queue))
  if (s.role) params.set('role', s.role)
  if (s.champion != null && !Number.isNaN(s.champion)) params.set('champion', String(s.champion))
  if (s.patch) params.set('patch', s.patch)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export default function FilterBar(){
  const { seg, sp, setSp } = useSegmentParams()
  const [champs, setChamps] = useState<{id:number, name:string}[]>([])
  // Ensure the URL has an explicit queue param so data matches the visible selection
  useEffect(()=>{
    if (!sp.get('queue')){
      const next = new URLSearchParams(sp)
      next.set('queue','-1')
      setSp(next, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const [queues, setQueues] = useState<number[]>([])
  const [roles, setRoles] = useState<string[]>([])
  const [patches, setPatches] = useState<string[]>([])
  useEffect(()=>{
    const q = (seg.queue!=null && seg.queue !== -1) ? `?queue=${seg.queue}` : ''
    api<{id:number,name:string}[]>(`/matches/recent-champions${q}`).then(setChamps).catch(()=>{})
    api<{queues:{id:number|null,count:number}[], roles:{id:string,count:number}[], patches:{id:string,count:number}[]}>(`/matches/segments${q}`).then((d)=>{
      setQueues(d.queues.map(x=>x.id!).filter((x)=>x!=null) as number[])
      setRoles(d.roles.map(x=>x.id))
      setPatches(d.patches.map(x=>x.id))
    }).catch(()=>{})
  }, [seg.queue])
  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(sp)
    if (!v) {
      next.delete(k)
    } else {
      next.set(k, v)
    }
    setSp(next, { replace: true })
  }
  return (
    <div className="flex gap-2 items-center text-sm">
      <select className="bg-slate-800 rounded px-2 py-1" value={seg.queue ?? -1} onChange={(e)=>set('queue', e.target.value)}>
        <option value="-1">Any queue</option>
        {queues.map(id => (
          <option key={id} value={id}>{queueName(id)}</option>
        ))}
      </select>
      <select className="bg-slate-800 rounded px-2 py-1" value={seg.role ?? ''} onChange={(e)=>set('role', e.target.value || null)}>
        <option value="">Any role</option>
        {roles.map(r => (<option key={r} value={r}>{r}</option>))}
      </select>
      <select className="bg-slate-800 rounded px-2 py-1" value={seg.champion ?? -1} onChange={(e)=>set('champion', e.target.value === '-1' ? null : e.target.value)}>
        <option value="-1">Any champion</option>
        {champs.map(c => (<option key={c.id} value={c.id}>{c.name}</option>))}
      </select>
      <select className="bg-slate-800 rounded px-2 py-1" value={seg.patch ?? ''} onChange={(e)=>set('patch', e.target.value || null)}>
        <option value="">Any patch</option>
        {patches.map(p => (<option key={p} value={p}>{p}</option>))}
      </select>
      <Presets seg={seg} apply={(s)=>{
        const next = new URLSearchParams()
        if (s.queue != null) next.set('queue', String(s.queue))
        if (s.role) next.set('role', s.role)
        if (s.champion != null) next.set('champion', String(s.champion))
        if (s.patch) next.set('patch', s.patch)
        setSp(next, { replace: true })
      }} />
    </div>
  )
}

function Presets({ seg, apply }: { seg: Segment, apply: (s: Segment)=>void }){
  const [name, setName] = useState('')
  const [presets, setPresets] = useState<{name:string, seg: Segment}[]>(()=>{
    try { return JSON.parse(localStorage.getItem('lt:presets')||'[]') } catch { return [] }
  })
  const save = () => {
    const next = [...presets.filter(p=>p.name!==name), { name, seg }]
    setPresets(next)
    try { localStorage.setItem('lt:presets', JSON.stringify(next)) } catch {}
  }
  const load = (n: string) => {
    const p = presets.find(p=>p.name===n)
    if (p) apply(p.seg)
  }
  const remove = (n: string) => {
    const next = presets.filter(p=>p.name!==n)
    setPresets(next)
    try { localStorage.setItem('lt:presets', JSON.stringify(next)) } catch {}
  }
  return (
    <div className="flex items-center gap-2 text-xs">
      <select className="bg-slate-800 rounded px-2 py-1" onChange={(e)=>load(e.target.value)}>
        <option value="">Presets…</option>
        {presets.map(p => (<option key={p.name} value={p.name}>{p.name}</option>))}
      </select>
      <input className="bg-slate-800 rounded px-2 py-1" placeholder="Save as…" value={name} onChange={(e)=>setName(e.target.value)} />
      <button className="bg-slate-800 rounded px-2 py-1" onClick={save}>Save</button>
      {name && <button className="bg-slate-800 rounded px-2 py-1" onClick={()=>remove(name)}>Delete</button>}
    </div>
  )
}
