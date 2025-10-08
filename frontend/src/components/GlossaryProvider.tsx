import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import GlossaryDrawer from './GlossaryDrawer'
import { track } from '../lib/analytics'

type GlossaryContextValue = {
  open: (anchor?: string | null) => void
  close: () => void
  isOpen: boolean
  anchor: string | null
}

const GlossaryContext = createContext<GlossaryContextValue | null>(null)

type ProviderProps = {
  children: ReactNode
}

export function GlossaryProvider({ children }: ProviderProps) {
  const [state, setState] = useState<{ open: boolean; anchor: string | null }>({ open: false, anchor: null })
  const lastTrigger = useRef<HTMLElement | null>(null)

  const close = useCallback(() => {
    setState({ open: false, anchor: null })
    const el = lastTrigger.current
    if (el && typeof el.focus === 'function') {
      requestAnimationFrame(() => el.focus())
    }
  }, [])

  const open = useCallback((anchor?: string | null) => {
    const active = document.activeElement
    if (active instanceof HTMLElement) {
      lastTrigger.current = active
    } else {
      lastTrigger.current = null
    }
    setState({ open: true, anchor: anchor ?? null })
    track('glossary_open', anchor ? { metric_id: anchor } : undefined)
  }, [])

  const value = useMemo<GlossaryContextValue>(
    () => ({
      open,
      close,
      isOpen: state.open,
      anchor: state.anchor,
    }),
    [open, close, state.open, state.anchor],
  )

  return (
    <GlossaryContext.Provider value={value}>
      {children}
      <GlossaryDrawer open={state.open} anchor={state.anchor} onClose={close} />
    </GlossaryContext.Provider>
  )
}

export function useGlossary() {
  const ctx = useContext(GlossaryContext)
  if (!ctx) throw new Error('useGlossary must be used within a GlossaryProvider')
  return ctx
}
