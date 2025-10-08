import { mapErrorMessage } from '../lib/api'

export default function ErrorBanner({ error, cta }: { error: any, cta?: JSX.Element }){
  if (!error) return null
  const msg = mapErrorMessage(error)
  return (
    <div className="card bg-slate-900 border border-red-500/40 text-red-300 flex items-center justify-between">
      <div>{msg}</div>
      {cta}
    </div>
  )
}

