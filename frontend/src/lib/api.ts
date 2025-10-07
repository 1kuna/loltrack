const BASE = (import.meta as any).env?.VITE_API_BASE || ''

export async function api<T=any>(path: string, init?: RequestInit): Promise<T> {
  const url = (path.startsWith('/api') ? path : `/api${path}`)
  const res = await fetch(`${BASE}${url}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  let json: any = null
  try {
    json = await res.json()
  } catch {}

  if (json && typeof json.ok === 'boolean') {
    if (json.ok) return json.data as T
    const err = json.error || { code: 'UNKNOWN', message: 'Unknown error' }
    throw Object.assign(new Error(err.message), { code: err.code, details: err.details, status: res.status })
  }
  if (!res.ok) {
    throw Object.assign(new Error(`HTTP ${res.status}`), { code: 'HTTP_ERROR', status: res.status })
  }
  return json as T
}

export async function post<T=any>(path: string, body: any): Promise<T> {
  return api(path, { method: 'POST', body: JSON.stringify(body) })
}

export async function put<T=any>(path: string, body: any): Promise<T> {
  return api(path, { method: 'PUT', body: JSON.stringify(body) })
}

export function mapErrorMessage(e: any): string {
  const code = e?.code || 'UNKNOWN'
  switch (code) {
    case 'MISSING_PREREQ':
      return 'Add your Riot API key and Riot ID in Settings first.'
    case 'RIOT_429':
      return 'Riot API rate-limited. Try again later.'
    case 'INGEST_ERROR':
      return 'We couldn’t process some matches. We’ll keep the ones that worked.'
    case 'RIOT_DOWN':
      return 'Riot API is unavailable right now.'
    case 'INVALID_INPUT':
      return e?.message || 'Invalid input.'
    default:
      return e?.message || 'Something went wrong.'
  }
}
