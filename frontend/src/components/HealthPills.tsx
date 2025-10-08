function Pill({label, state}:{label:string; state:'ok'|'warn'|'bad'}){
  const color = state==='ok'?'bg-green-500': state==='warn'?'bg-amber-500':'bg-red-500'
  return <span className={`px-2 py-0.5 rounded text-black text-xs ${color}`}>{label}</span>
}

export default function HealthPills({health}:{health:any}){
  return (
    <div className="flex gap-3 items-center">
      <div className="font-semibold">Health</div>
      <Pill label="DB" state={health?.db?.ok? 'ok':'bad'} />
      <Pill label="Live" state={health?.live_client?.status==='up'? 'ok':'bad'} />
      <Pill label="Riot" state={(health?.riot_api?.status||'down')==='ok'? 'ok':'warn'} />
      <Pill label="DDragon" state={health?.ddragon?.assets_cached? 'ok':'warn'} />
    </div>
  )
}

