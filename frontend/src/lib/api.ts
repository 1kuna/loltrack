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
  if (!res.ok) throw new Error(`${res.status}`)
  const json = await res.json()
  if (json && json.ok) return json.data as T
  const err = json?.error || { code: 'UNKNOWN', message: 'Unknown error' }
  throw Object.assign(new Error(err.message), { code: err.code, details: err.details })
}

export async function post<T=any>(path: string, body: any): Promise<T> {
  return api(path, { method: 'POST', body: JSON.stringify(body) })
}

export async function put<T=any>(path: string, body: any): Promise<T> {
  return api(path, { method: 'PUT', body: JSON.stringify(body) })
}
