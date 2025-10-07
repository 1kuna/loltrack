export default function MiniBullet({ value, target, unit }: { value: number|null|undefined, target?: number|null|undefined, unit: string }){
  if (value === null || value === undefined) return <div className="h-6" />
  // Simple horizontal scale 0..1 based on value vs target band
  const t = target ?? 0
  const max = Math.max(Math.abs(t)*1.5, Math.abs(value)*1.5, 1)
  const center = unit === 'time' ? 0 : 0 // for now baseline at 0
  const pct = Math.max(0, Math.min(1, (value + max) / (2*max)))
  const tpos = Math.max(0, Math.min(1, (t + max) / (2*max)))
  const band = 0.10
  return (
    <div className="relative w-full h-6 overflow-hidden">
      <div className="absolute inset-y-2 left-0 right-0 bg-slate-800 rounded" />
      {target !== null && target !== undefined && (
        <div className="absolute inset-y-1" style={{left: `${(tpos-band/2)*100}%`, width: `${band*100}%`}}>
          <div className="h-full bg-slate-700 rounded opacity-70" />
        </div>
      )}
      {target !== null && target !== undefined && (
        <div className="absolute inset-y-0" style={{left: `${tpos*100}%`, width: 2}}>
          <div className="h-full bg-slate-500" />
        </div>
      )}
      <div className="absolute top-0 bottom-0" style={{left: `${pct*100}%`}}>
        <div className="w-2 h-2 rounded-full bg-cyan-400 translate-x-[-50%] translate-y-[6px]" />
      </div>
    </div>
  )
}
