import { useGlossary } from './GlossaryProvider'

type GlossaryButtonProps = {
  anchor?: string | null
  label?: string
  variant?: 'link' | 'icon'
  className?: string
}

export default function GlossaryButton({
  anchor = null,
  label,
  variant = 'link',
  className,
}: GlossaryButtonProps) {
  const glossary = useGlossary()
  const isIcon = variant === 'icon'
  const text = label ?? (isIcon ? '?' : 'Glossary')
  const base = isIcon
    ? 'inline-flex h-6 w-6 items-center justify-center rounded-full border border-slate-700/70 bg-slate-900/80 text-xs font-semibold text-slate-300 hover:border-sky-500/60 hover:text-sky-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60'
    : 'text-sm text-slate-300 hover:text-sky-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60 rounded'
  const cn = [base, className].filter(Boolean).join(' ')
  return (
    <button
      type="button"
      className={cn}
      aria-label={isIcon ? 'Open glossary' : undefined}
      onClick={() => glossary.open(anchor)}
    >
      {text}
    </button>
  )
}
