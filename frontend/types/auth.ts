export type UserRole = 'USER' | 'ADMIN'

export interface User {
  id: string
  login: string
  email: string | null
  first_name: string | null
  last_name: string | null
  company_id: string | null
  company_name: string | null
  role: UserRole
  is_active: boolean
  is_blocked: boolean
  marketing_consent: boolean
  created_at: string
}

export interface AuthTokensResponse {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  expires_in_seconds: number
  user: User
}
