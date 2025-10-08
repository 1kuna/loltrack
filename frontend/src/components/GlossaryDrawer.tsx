import { useEffect, useMemo, useRef } from 'react'
import { createPortal } from 'react-dom'
import { getGlossaryEntries, resolveGlossaryEntry } from '../lib/glossary'

type GlossaryDrawerProps = {
  open: boolean
  onClose: () => void
  anchor?: string | null
}

type EntryRefs = Record<string, HTMLDivElement | null>

export default function GlossaryDrawer({ open, onClose, anchor }: GlossaryDrawerProps) {
  const entries = useMemo(() => getGlossaryEntries(), [])
  const active = anchor ? resolveGlossaryEntry(anchor)?.key ?? null : null
  const refs = useRef<EntryRefs>({})

  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  useEffect(() => {
    if (!open || !active) return
    const node = refs.current[active]
    if (node) {
      node.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [open, active])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-40 flex"
      onClick={onClose}
      aria-hidden={!open}
    >
      <div className="flex-1 bg-black/50" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Glossary"
        className="relative w-full max-w-sm bg-slate-950/95 border-l border-slate-800/80 shadow-2xl overflow-y-auto focus:outline-none"
        onClick={(e) => e.stopPropagation()}
        tabIndex={-1}
      >
        <header className="sticky top-0 z-10 bg-slate-950/95 backdrop-blur px-5 py-4 border-b border-slate-800/60 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Glossary</h2>
          <button
            onClick={onClose}
            className="text-sm text-slate-400 hover:text-slate-200"
          >
            Close
          </button>
        </header>
        <div className="px-5 py-4 space-y-4">
          {entries.map((entry) => {
            const resolvedKey = entry.key
            const highlighted = resolvedKey === active
            return (
              <div
                key={resolvedKey}
                ref={(el) => { refs.current[resolvedKey] = el }}
                className={`rounded-lg border px-4 py-3 transition-colors ${
                  highlighted
                    ? 'border-sky-500/60 bg-sky-500/10'
                    : 'border-slate-800/60 bg-slate-900/40'
                }`}
              >
                <div className="font-semibold text-sm text-slate-100">{entry.term}</div>
                <div className="text-sm text-slate-400 mt-1 leading-relaxed">
                  {entry.definition}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>,
    document.body,
  )
}
