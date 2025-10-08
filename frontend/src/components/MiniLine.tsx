export default function MiniLine({ values }: { values: number[]|null|undefined }){
  const vals = (values && values.length > 0) ? values : [0,0]
  const vmin = Math.min(...vals)
  const vmax = Math.max(...vals)
  const norm = (v: number) => vmax === vmin ? 0.5 : (v - vmin) / (vmax - vmin)
  // simple EWMA overlay
  const alpha = 0.35
  let s = vals[0]
  const smoothed = [s]
  for (let i=1;i<vals.length;i++){ s = alpha*vals[i] + (1-alpha)*s; smoothed.push(s) }
  const toPoints = (a:number[]) => a.map((v,i)=>`${(i/(a.length-1))*80},${24 - norm(v)*20 - 2}`).join(' ')
  return (
    <div className="w-full h-6 overflow-hidden">
      <svg className="w-full h-6" viewBox="0 0 80 24" preserveAspectRatio="none">
        <polyline fill="none" strokeWidth="1" stroke="currentColor" className="text-slate-600" points={toPoints(vals)} />
        <polyline fill="none" strokeWidth="1.5" stroke="currentColor" className="text-cyan-400" points={toPoints(smoothed)} />
      </svg>
    </div>
  )
}
