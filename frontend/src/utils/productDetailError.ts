import axios from 'axios'

export type ProductDetailErrorState =
  | 'not-found'
  | 'forbidden'
  | 'server-error'
  | 'network-error'
  | 'unauthorized'

export function classifyProductDetailError(error: unknown): ProductDetailErrorState {
  if (!axios.isAxiosError(error) || !error.response) return 'network-error'
  if (error.response.status === 404) return 'not-found'
  if (error.response.status === 403) return 'forbidden'
  if (error.response.status === 401) return 'unauthorized'
  return 'server-error'
}
