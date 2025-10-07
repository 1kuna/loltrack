import { useState } from 'react'

export default function GlossaryDrawer(){
  const [open, setOpen] = useState(false)
  return (
    <>
      <button className="text-slate-300 hover:text-cyan-400 text-sm" onClick={()=>setOpen(true)}>Glossary</button>
      {open && (
        <div className="fixed inset-0 bg-black/50" onClick={()=>setOpen(false)}>
          <div className="absolute right-0 top-0 bottom-0 w-[360px] bg-slate-900 border-l border-slate-800 p-4 space-y-3" onClick={(e)=>e.stopPropagation()}>
            <div className="text-lg font-semibold">Glossary</div>
            <Entry term="Typical (P50)" def="Your median; half your games are above, half below." />
            <Entry term="Top 25% (P75)" def="Mark you hit in your better games." />
            <Entry term="XP lead @10" def="Your XP minus lane opponent's XP at 10:00." />
            <Entry term="Gold lead @10" def="Your gold minus lane opponent's at 10:00." />
            <Entry term="Control wards before 14:00" def="Wards bought/placed before 14:00." />
            <Entry term="First recall time" def="Time of your first intentional recall (mm:ss)." />
          </div>
        </div>
      )}
    </>
  )
}

function Entry({term, def}:{term:string; def:string}){
  return (
    <div>
      <div className="font-semibold">{term}</div>
      <div className="text-sm text-slate-400">{def}</div>
    </div>
  )
}

