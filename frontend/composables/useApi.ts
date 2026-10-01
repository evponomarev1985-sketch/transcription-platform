import { useAuthStore } from '~/stores/auth'

export function useApi() {
  const config = useRuntimeConfig()
  const auth = useAuthStore()

  async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers)
    headers.set('Content-Type', 'application/json')
    if (auth.accessToken) {
      headers.set('Authorization', `Bearer ${auth.accessToken}`)
    }

    const response = await fetch(`${config.public.apiBase}${path}`, {
      ...options,
      headers,
    })

    if (response.status === 401 && auth.refreshToken) {
      const refreshed = await refreshToken()
      if (refreshed) {
        return apiFetch<T>(path, options)
      }
    }

    if (!response.ok) {
      let detail = response.statusText
      try {
        const data = await response.json()
        detail = data?.detail || detail
      } catch {
        // ignore parse errors
      }
      throw new Error(detail)
    }

    if (response.status === 204) {
      return {} as T
    }
    return (await response.json()) as T
  }

  async function refreshToken(): Promise<boolean> {
    if (!auth.refreshToken) return false
    try {
      const response = await fetch(`${config.public.apiBase}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: auth.refreshToken }),
      })
      if (!response.ok) {
        auth.clearSession()
        return false
      }
      const data = await response.json()
      auth.setSession(data.access_token, data.refresh_token, data.user)
      return true
    } catch {
      auth.clearSession()
      return false
    }
  }

  return { apiFetch }
}
