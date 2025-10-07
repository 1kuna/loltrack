import { useEffect, useState } from 'react'
import { api, post, mapErrorMessage } from '../lib/api'
import HealthPills from '../components/HealthPills'

export default function Settings() {
  const [health, setHealth] = useState<any>(null)
  const [riotKey, setRiotKey] = useState('')
  const [riotId, setRiotId] = useState('')
  const [keyVerified, setKeyVerified] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState<string>('')

  useEffect(() => {
    const load = () => api('/health').then(setHealth).catch(()=>{})
    load()
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [])
  const [saving, setSaving] = useState(false)
  const saveKey = async () => {
    setSaving(true); setErr('')
    try { const r = await post('/auth/riot-key', {key: riotKey}); setMsg('Key verified'); setKeyVerified(true) }
    catch(e:any){ setErr(mapErrorMessage(e)); setKeyVerified(false) }
    finally { setSaving(false); setTimeout(()=>setMsg(''), 1500) }
  }
  const saveId = async () => {
    setSaving(true); setErr('')
    try { await post('/auth/riot-id', {riot_id: riotId}); setMsg('Riot ID saved') }
    catch(e:any){ setErr(mapErrorMessage(e)) }
    finally { setSaving(false); setTimeout(()=>setMsg(''), 1500) }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Settings</h1>
      <div className="card"><HealthPills health={health} /></div>

      <div className="card space-y-2">
        <div className="font-semibold">Step 1: Riot API Key</div>
        <input className="bg-slate-800 w-full rounded p-2" type="password" value={riotKey} onChange={(e)=>setRiotKey(e.target.value)} placeholder="RGAPI-..." />
        <button className="bg-cyan-400 text-black px-3 py-1 rounded disabled:opacity-50" disabled={saving} onClick={saveKey}>Save & Verify</button>
        {keyVerified && <div className="text-green-400 text-sm">Key verified</div>}
        {err && !keyVerified && <div className="text-red-400 text-sm">{err}</div>}
      </div>
      <div className="card space-y-2 opacity-100">
        <div className="font-semibold">Step 2: Riot ID (GameName#TAG)</div>
        <input className="bg-slate-800 w-full rounded p-2 disabled:opacity-50" type="text" value={riotId} onChange={(e)=>setRiotId(e.target.value)} placeholder="GameName#TAG" disabled={!keyVerified} />
        <button className="bg-cyan-400 text-black px-3 py-1 rounded disabled:opacity-50" disabled={saving || !keyVerified} onClick={saveId}>Save</button>
      </div>
      {msg && <div className="card">{msg}</div>}

      <div className="card">
        <button className="bg-cyan-400 text-black px-3 py-1 rounded" onClick={async()=>{
          try { await post('/sync/bootstrap', {}); setMsg('Sync started') }
          catch(e:any){ setErr(mapErrorMessage(e)) }
        }}>Sync last 14 days</button>
      </div>
    </div>
  )
}
