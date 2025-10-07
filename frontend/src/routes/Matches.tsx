import { useEffect, useState } from 'react'
import { api, post, mapErrorMessage } from '../lib/api'
import { queueName } from '../lib/queues'
import SyncCTA from '../components/SyncCTA'
import MatchDrawer from '../components/MatchDrawer'
import FilterBar, { useSegmentParams, toQuery } from '../shared/FilterBar'

type Match = {
  match_id: string
  queue_id: number
  game_creation_ms: number
  game_duration_s: number
  role?: string
  champion_id?: number
  cs10?: number
  gd10?: number
  xpd10?: number
  dl14?: number
  k?: number
  d?: number
  a?: number
  csm?: number
  dpm?: number
  visionScore?: number
  kp?: number
  result?: 'Win'|'Lose'
  badges?: string[]
}

export default function Matches() {
  const [rows, setRows] = useState<Match[]>([])
  const [err, setErr] = useState<any>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [syncing, setSyncing] = useState(false)
  const [syncErr, setSyncErr] = useState<any>(null)
  const [canSync, setCanSync] = useState<boolean>(true)
  const [openId, setOpenId] = useState<string|null>(null)
  const [offset, setOffset] = useState(0)
  const { seg, key } = useSegmentParams()
  const load = () => {
    const qs = toQuery({ seg })
    const url = `/matches${qs}${qs ? '&' : '?'}limit=25&offset=${offset}`
    setLoading(true)
    return api<Match[]>(url).then((d)=>{ setRows(d); setLoading(false) }).catch(e => { setErr(e); setLoading(false) })
  }
  useEffect(() => {
    load()
    Promise.all([api('/config'), api('/health')]).then(([cfg, h]:any)=>{
      setCanSync(Boolean(cfg?.player?.puuid) && (h?.riot_api?.status==='ok'))
    }).catch(()=>{})
  }, [key, offset])
  const startSync = async () => {
    setSyncing(true)
    setSyncErr(null)
    try{
      const r = await post<{task_id:string}>('/sync/bootstrap', {})
      const id = r.task_id
      const int = setInterval(async ()=>{
        const st = await api<{phase:string;progress:number;detail?:string}>(`/sync/status?id=${id}`)
        if (st.phase==='done' || st.phase==='error') { clearInterval(int); setSyncing(false); load() }
      }, 1000)
    }catch(e){ setSyncing(false); setSyncErr(e) }
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Matches</h1>
        <FilterBar />
      </div>
      {err && <div className="card text-red-400">{String(err?.message||err)}</div>}
      {loading && (
        <div className="card animate-pulse h-24" />
      )}
      {!loading && rows.length===0 && (
        <>
          {syncErr && (
            <div className="card flex items-center justify-between">
              <div className="text-red-300">{mapErrorMessage(syncErr)}</div>
              <a href="/settings" className="text-cyan-400 underline">Fix in Settings</a>
            </div>
          )}
          <SyncCTA disabled={syncing || !canSync} onClick={startSync} />
        </>
      )}
      <div className="grid gap-2">
        <div className="grid grid-cols-8 text-xs text-slate-400 px-1">
          <div>Date</div><div>Queue</div><div>Role</div><div>Champ</div><div>Dur</div><div>Early</div><div>Summary</div><div></div>
        </div>
        {rows.map((m) => (
          <button key={m.match_id} className="card grid grid-cols-8 items-center text-sm gap-2 text-left hover:bg-slate-800/60" onClick={()=>setOpenId(m.match_id)}>
            <div>{new Date(m.game_creation_ms).toLocaleString()}</div>
            <div>{queueName(m.queue_id)}</div>
            <div>{m.role || '-'}</div>
            <div>{m.champion_id ? <img className="w-6 h-6" src={`/assets/champion/${m.champion_id}.png`} /> : '-'}</div>
            <div>{Math.round((m.game_duration_s||0)/60)}m</div>
            <div className="text-xs text-slate-300">CS@10 {m.cs10 ?? '—'} · GD@10 {fmtSign(m.gd10)} · XPD@10 {fmtSign(m.xpd10)} · DL14 {m.dl14 ? '✓' : '✗'}</div>
            <div className="text-xs text-slate-300">{(m.k!=null && m.d!=null && m.a!=null) ? `${m.k}/${m.d}/${m.a}` : ''}{m.kp!=null ? ` · ${m.kp}% KP` : ''}{m.dpm!=null ? ` · ${Math.round(m.dpm)} DPM` : ''}</div>
            <div className="flex gap-1 flex-wrap">
              {(m.badges||[]).slice(0,3).map((b,i)=>(<span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-200">{b}</span>))}
            </div>
          </button>
        ))}
      </div>
      <div className="flex items-center justify-between text-sm text-slate-300">
        <button className="px-2 py-1 rounded bg-slate-800 disabled:opacity-50" disabled={offset<=0} onClick={()=>setOffset(Math.max(0, offset-25))}>Prev</button>
        <div>Page {Math.floor(offset/25)+1}</div>
        <button className="px-2 py-1 rounded bg-slate-800 disabled:opacity-50" disabled={rows.length<25} onClick={()=>setOffset(offset+25)}>Next</button>
      </div>
      {openId && <MatchDrawer matchId={openId} onClose={()=>setOpenId(null)} />}
    </div>
  )
}

function fmtSign(n?: number){ if(n==null) return '—'; const s = n>=0?'+':'−'; return `${s}${Math.abs(Math.round(n))}` }
