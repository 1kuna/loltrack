export default function SyncCTA({disabled, onClick}:{disabled?:boolean; onClick:()=>void}){
  return (
    <div className="card">
      <div className="mb-2">No matches yet.</div>
      <button className="bg-cyan-400 text-black px-3 py-1 rounded disabled:opacity-50" disabled={disabled} onClick={onClick}>Sync last 14 days</button>
    </div>
  )
}

