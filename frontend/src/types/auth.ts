export interface LoginRequest {
  username: string
  password: string
}

export interface TokenData {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface LoginResponse {
  code: number
  data: TokenData
}

export interface UserResponse {
  id: string
  username: string
  email: string | null
  phone: string | null
  status: string
  role_id: string
  last_login_time: string | null
  create_time: string
}

export interface JwtPayload {
  sub: string
  role_code: string
  perms: string[]
  exp?: number
  type?: string
}

export interface AuthState {
  user: UserResponse | null
  permissions: string[]
  roleCode: string | null
  accessToken: string | null
  refreshToken: string | null
}

export interface RefreshResponse {
  code: number
  data: TokenData
}
