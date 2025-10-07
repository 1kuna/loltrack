import { useEffect, useRef, useState } from 'react'
import { connectLive } from '../lib/ws'
import { api } from '../lib/api'

export default function Live() {
  const [state, setState] = useState<any>(null)
  const [ended, setEnded] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  useEffect(() => {
    let active = true
    api<{status:string, in_game:boolean}>(`/live/status`).then((d)=>{
      if (!active) return
      if (!d.in_game) {
        setEnded(true)
        setState(null)
        return
      }
      const ws = connectLive((d) => { if (d?.event==='live_end') setEnded(true); else setState(d) })
      wsRef.current = ws
    }).catch(()=>{ setEnded(true) })
    return () => { active = false; wsRef.current?.close() }
  }, [])
  const early = state?.early
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Live Game</h1>
      {!state && !ended && <div className="card">Checking live status…</div>}
      {ended && <div className="card">Not in a live game.</div>}
      {state?.event === 'waiting' && <div className="card">Waiting for match...</div>}
      {early && (
        <div className="grid grid-cols-2 gap-4">
          <div className="card space-y-2">
            <div>DL14: <span className={early.dl14_on_track ? 'text-ok' : 'text-bad'}>{early.dl14_on_track ? '✓ on track' : '✗ failed'}</span></div>
            <div>CS@10 pace: {early.cs10_eta}</div>
            <div>CS now: {early.cs}</div>
          </div>
          <div className="card">
            <div>Game Time: {Math.floor((state.gameTime||0)/60)}:{String(Math.floor((state.gameTime||0)%60)).padStart(2,'0')}</div>
          </div>
        </div>
      )}
    </div>
  )
}
