import { useEffect, useState } from 'react'
import { api, post } from '../lib/api'

type Match = { match_id: string, queue_id: number, game_creation_ms: number, game_duration_s: number, role?: string, champion_id?: number }

export default function Matches() {
  const [rows, setRows] = useState<Match[]>([])
  const [err, setErr] = useState<string|null>(null)
  const load = () => api<Match[]>('/matches?limit=25').then(setRows).catch(e => setErr(String(e)))
  useEffect(() => { load() }, [])
  const [syncing, setSyncing] = useState(false)
  const startSync = async () => {
    setSyncing(true)
    try{
      const r = await post<{task_id:string}>('/sync/bootstrap', {})
      const id = r.task_id
      const int = setInterval(async ()=>{
        const st = await api<{phase:string;progress:number;detail?:string}>(`/sync/status?id=${id}`)
        if (st.phase==='done' || st.phase==='error') { clearInterval(int); setSyncing(false); load() }
      }, 1000)
    }catch(e){ setSyncing(false) }
  }
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Matches</h1>
      {err && <div className="card text-bad">{err}</div>}
      {rows.length===0 && (
        <div className="card">
          <div className="mb-2">No matches yet.</div>
          <button className="bg-accent text-black px-3 py-1 rounded disabled:opacity-50" disabled={syncing} onClick={startSync}>Sync last 14 days</button>
        </div>
      )}
      <div className="grid gap-2">
        {rows.map((m) => (
          <div key={m.match_id} className="card flex items-center justify-between text-sm">
            <div>{m.match_id}</div>
            <div>{new Date(m.game_creation_ms).toLocaleString()}</div>
            <div>{Math.round(m.game_duration_s/60)}m</div>
            <div>{m.role || '-'}</div>
            <div>Q{m.queue_id}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
