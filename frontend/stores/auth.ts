import { defineStore } from 'pinia'
import type { User } from '~/types/auth'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: User | null
}

const ACCESS_TOKEN_KEY = 'tp_access_token'
const REFRESH_TOKEN_KEY = 'tp_refresh_token'
const USER_KEY = 'tp_user'

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    accessToken: null,
    refreshToken: null,
    user: null,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.accessToken && state.user),
    isAdmin: (state) => state.user?.role === 'ADMIN',
  },
  actions: {
    hydrate() {
      if (!process.client) return
      this.accessToken = localStorage.getItem(ACCESS_TOKEN_KEY)
      this.refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
      const rawUser = localStorage.getItem(USER_KEY)
      this.user = rawUser ? (JSON.parse(rawUser) as User) : null
    },
    setSession(accessToken: string, refreshToken: string, user: User) {
      this.accessToken = accessToken
      this.refreshToken = refreshToken
      this.user = user
      if (!process.client) return
      localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
      localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    },
    clearSession() {
      this.accessToken = null
      this.refreshToken = null
      this.user = null
      if (!process.client) return
      localStorage.removeItem(ACCESS_TOKEN_KEY)
      localStorage.removeItem(REFRESH_TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    },
  },
})
