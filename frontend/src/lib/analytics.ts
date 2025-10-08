type AnalyticsPayload = Record<string, unknown>

declare global {
  interface Window {
    analytics?: {
      track?: (event: string, payload?: AnalyticsPayload) => void
    }
  }
}

export function track(event: string, payload?: AnalyticsPayload) {
  try {
    if (typeof window !== 'undefined' && window.analytics?.track) {
      window.analytics.track(event, payload)
    } else if (process.env.NODE_ENV === 'development') {
      // eslint-disable-next-line no-console
      console.debug('[analytics]', event, payload ?? {})
    }
  } catch (err) {
    if (process.env.NODE_ENV === 'development') {
      // eslint-disable-next-line no-console
      console.debug('[analytics:error]', err)
    }
  }
}
