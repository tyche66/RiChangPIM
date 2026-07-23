/** Proposal / Quotation / Share domain types. */

// ============ Proposal ============

export interface ProposalItem {
  id?: string
  product_id: string
  quantity: number
  remark?: string
  /** Enriched display fields (not sent to server). */
  product_name?: string
  product_no?: string
  face_price?: number | null
  stock_status?: string | null
  cover_image_url?: string | null
  line_total?: number
  /** Image load error flag (UI only). */
  _imgError?: boolean
}

export interface Proposal {
  id: string
  proposal_no: string
  proposal_name: string
  customer_name: string | null
  creator_id: string
  status: 'draft' | 'confirmed'
  ai_polished: boolean
  ai_polish_content?: string | null
  ai_polish_at?: string | null
  ai_polish_model?: string | null
  total_face_value: number
  create_time: string
  items: ProposalItem[]
}

// ============ Quotation ============

export interface QuotationItem {
  id?: string
  product_id: string
  quantity: number
  unit_price: number
  tax_rate: number
  subtotal: number
  /** Enriched display fields (not sent to server). */
  product_name?: string
  product_no?: string
  face_price?: number | null
  cover_image_url?: string | null
}

export interface Quotation {
  id: string
  quotation_no: string
  proposal_id: string
  proposal_no?: string
  proposal_name?: string
  creator_id: string
  valid_until: string | null
  total_amount: number
  subtotal: number
  tax_rate: number
  discount: number
  status: 'draft' | 'confirmed'
  create_time: string
  update_time: string
  items: QuotationItem[]
}

// ============ Product option (for item picker) ============

export interface ProductOption {
  id: string
  product_name: string
  product_no: string
  face_price: number | null
  stock_status?: string | null
  cover_image_url?: string | null
}

// ============ Share result ============

export interface ShareResult {
  share_id: string
  share_url: string
  token: string
  expire_time: string | null
  max_access_count: number | null
}

export interface ShareForm {
  share_type: 'proposal' | 'quotation'
  target_id: string
  creator_id?: string
  password: string
  expire_hours: number
  max_access_count: number
}

// ============ Share content (from backend share endpoint) ============

export interface ShareProductItem {
  product_id: string
  product_name: string
  product_no?: string
  face_price: number | null
  quantity: number
  cover_image_url?: string | null
  scene_images?: { id: string; name: string; image_url?: string | null; sort: number }[]
  // Quotation-only fields
  unit_price?: number
  tax_rate?: number
  subtotal?: number
  _imgError?: boolean
}

export interface ShareProposalContent {
  proposal_no: string
  proposal_name: string
  customer_name: string | null
  status: 'draft' | 'confirmed'
  total_face_value: number
  items: ShareProductItem[]
}

export interface ShareQuotationContent {
  quotation_no: string
  status: 'draft' | 'confirmed'
  total_amount: number
  items: ShareProductItem[]
}

export type ShareContent = ShareProposalContent | ShareQuotationContent

export interface ApiEnvelope<T> {
  code: number
  data: T
  msg?: string
}

export interface Paginated<T> {
  list: T[]
  total: number
  page: number
  size: number
}

export interface ProductListItem {
  id: string
  product_name: string
  product_no: string
  face_price: number | null
  stock_status?: string | null
  status: string
  cover_image_url?: string | null
}

export interface ProposalItemRequest {
  product_id: string
  quantity: number
  remark?: string
}

export interface ProposalCreateRequest {
  proposal_name: string
  customer_name?: string
  creator_id: string
  items: ProposalItemRequest[]
}

export interface ProposalUpdateRequest {
  proposal_name?: string
  customer_name?: string | null
  items?: ProposalItemRequest[]
}

export interface QuotationItemRequest {
  product_id: string
  quantity: number
  unit_price: number
  tax_rate: number
}

export interface QuotationCreateRequest {
  proposal_id: string
  tax_rate: number
  discount: number
  valid_until?: string | null
  items: QuotationItemRequest[]
}

export type QuotationUpdateRequest = Omit<QuotationCreateRequest, 'proposal_id'>

export interface ShareCreateRequest {
  share_type: 'proposal' | 'quotation'
  target_id: string
  password?: string
  expire_hours?: number
  max_access_count?: number
}

// ============ Proposal token (from Products selection to Proposals) ============

export interface ProposalToken {
  /** Comma-separated product IDs (no UUIDs in URL). */
  productIds: string[]
  /** Full ProductOption data for enriched display. */
  options: ProductOption[]
}
