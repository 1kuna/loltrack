import { useEffect, useState } from 'react'
import { api, post } from '../lib/api'

export default function Settings() {
  const [health, setHealth] = useState<any>(null)
  const [riotKey, setRiotKey] = useState('')
  const [riotId, setRiotId] = useState('')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    const load = () => api('/health').then(setHealth).catch(()=>{})
    load()
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [])
  const [saving, setSaving] = useState(false)
  const saveKey = async () => { setSaving(true); try { await post('/auth/riot-key', {key: riotKey}); setMsg('Saved key') } finally { setSaving(false); setTimeout(()=>setMsg(''), 1500) } }
  const saveId = async () => { setSaving(true); try { await post('/auth/riot-id', {riot_id: riotId}); setMsg('Saved Riot ID') } finally { setSaving(false); setTimeout(()=>setMsg(''), 1500) } }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Settings</h1>
      <div className="card flex gap-3 items-center">
        <div className="font-semibold">Health</div>
        <Pill label="DB" state={health?.db?.ok? 'ok':'bad'} />
        <Pill label="Live" state={health?.live_client?.status==='up'? 'ok':'bad'} />
        <Pill label="Riot" state={(health?.riot_api?.status||'down')==='ok'? 'ok':'warn'} />
        <Pill label="DDragon" state={health?.ddragon?.assets_cached? 'ok':'warn'} />
      </div>
      <div className="card space-y-2">
        <div className="font-semibold">Riot API Key</div>
        <input className="bg-slate-800 w-full rounded p-2" type="password" value={riotKey} onChange={(e)=>setRiotKey(e.target.value)} placeholder="RGAPI-..." />
        <button className="bg-accent text-black px-3 py-1 rounded disabled:opacity-50" disabled={saving} onClick={saveKey}>Save Key</button>
      </div>
      <div className="card space-y-2">
        <div className="font-semibold">Riot ID</div>
        <input className="bg-slate-800 w-full rounded p-2" type="text" value={riotId} onChange={(e)=>setRiotId(e.target.value)} placeholder="GameName#TAG" />
        <button className="bg-accent text-black px-3 py-1 rounded disabled:opacity-50" disabled={saving} onClick={saveId}>Save Riot ID</button>
      </div>
      {msg && <div className="card">{msg}</div>}

      <div className="card">
        <button className="bg-accent text-black px-3 py-1 rounded" onClick={async()=>{
          const r = await post('/sync/bootstrap', {})
          setMsg('Sync started')
        }}>Sync last 14 days</button>
      </div>
    </div>
  )
}

function Pill({label, state}:{label:string; state:'ok'|'warn'|'bad'}){
  const color = state==='ok'?'bg-ok': state==='warn'?'bg-warn':'bg-bad'
  return <span className={`px-2 py-0.5 rounded text-black text-xs ${color}`}>{label}</span>
}
