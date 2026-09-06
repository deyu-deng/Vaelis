/**
 * Frontend client for North Star HTTP API.
 * FE/BE separation: do not import Python lib; call dashboard plugin routes.
 *
 * Base path: /api/plugins/vaelis-north-star
 * Contract: docs/vaelis/north_star/API.md
 */

export type VaelisArea = 'task' | 'compute' | 'preview' | 'ops'

const BASE = '/api/plugins/vaelis-north-star'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'content-type': 'application/json',
      ...(init?.headers || {})
    }
  })
  if (!res.ok) {
    throw new Error(`vaelis-api ${path} → ${res.status}`)
  }
  return res.json() as Promise<T>
}

export function vaelisHealth() {
  return request<{ ok: boolean; public: string[] }>('/health')
}

export function vaelisBoard() {
  return request<Record<string, unknown>>('/board')
}

export function vaelisTask(body: Record<string, unknown>) {
  return request<Record<string, unknown>>('/task', {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

export function vaelisPreviewList(limit = 50) {
  return request<{ items: unknown[] }>(`/preview?limit=${limit}`)
}

export function vaelisPreview(body: Record<string, unknown>) {
  return request<Record<string, unknown>>('/preview', {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

export function vaelisOps(body: Record<string, unknown>) {
  return request<Record<string, unknown>>('/ops', {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

export function vaelisMorningReport() {
  return request<Record<string, unknown>>('/morning-report')
}
