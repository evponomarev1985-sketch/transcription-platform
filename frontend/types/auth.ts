export type UserRole = 'USER' | 'ADMIN'

export interface User {
  id: string
  login: string
  email: string | null
  role: UserRole
  is_active: boolean
  is_blocked: boolean
  created_at: string
}

export interface AuthTokensResponse {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  expires_in_seconds: number
  user: User
}
