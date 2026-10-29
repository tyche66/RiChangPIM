/** Proposal / Quotation / Share domain types. */

// ============ Proposal ============

export interface ProjectSpace {
  id: string
  project_id: string
  parent_id: string | null
  space_type: 'floor' | 'room' | 'zone' | 'other'
  space_name: string
  level: number
  sort: number
  create_time: string | null
}

export interface ProductSnapshot {
  product_no: string | null
  product_name: string | null
  category_name: string | null
  material: string | null
  colors: string | null
  material_description: string | null
  specification: string | null
  face_price: number | null
}

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
  // Track C：空间归属、材质说明与服务端生成的产品快照
  project_space_id?: string | null
  floor_label?: string | null
  space_label?: string | null
  material_desc?: string | null
  product_snapshot?: ProductSnapshot | null
  category_name?: string | null
  material?: string | null
  colors?: string | null
  material_description?: string | null
  specification?: string | null
}

export interface Proposal {
  id: string
  proposal_no: string
  proposal_name: string
  customer_name: string | null
  customer_id?: string | null
  project_id?: string | null
  creator_id: string
  status: 'draft' | 'confirmed'
  ai_polished: boolean
  ai_polish_content?: string | null
  ai_polish_at?: string | null
  ai_polish_model?: string | null
  total_face_value: number
  create_time: string
  items: ProposalItem[]
  /** Track D：方案平面图（媒体库绑定，详情接口随方案返回） */
  floor_plans?: ProposalFloorPlan[]
}

/**
 * 方案平面图：图片本体在媒体库，本结构只是绑定关系 + 展示名。
 * `image_url` 是后端签发的短时地址（15 分钟），不要缓存到 localStorage。
 */
export interface ProposalFloorPlan {
  id: string
  proposal_id: string
  project_id: string | null
  attachment_id: string
  name: string
  floor_label?: string | null
  space_label?: string | null
  sort: number
  file_name?: string | null
  file_type?: string | null
  file_size?: number | null
  image_url: string
  create_time?: string | null
}

/**
 * 新增方案对话框里的平面图暂存项：方案还没创建，因此没有绑定 id。
 * 创建成功后由 `proposalFloorPlanApi.batchCreate` 一次性绑定。
 */
export interface FloorPlanDraft {
  id?: string
  attachment_id: string
  name: string
  image_url?: string | null
  sort?: number
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
  // Track C：空间归属、材质说明与服务端生成的产品快照
  project_space_id?: string | null
  floor_label?: string | null
  space_label?: string | null
  material_desc?: string | null
  material_description?: string | null
  colors?: string | null
  specification?: string | null
  product_snapshot?: ProductSnapshot | null
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
  // Track C：空间位置与产品事实
  project_space_id?: string | null
  floor_label?: string | null
  space_label?: string | null
  material_desc?: string | null
  material?: string | null
  colors?: string | null
  material_description?: string | null
  specification?: string | null
  category_name?: string | null
  product_snapshot?: ProductSnapshot | null
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
  project_space_id?: string | null
  floor_label?: string | null
  space_label?: string | null
  material_desc?: string | null
}

export interface ProposalCreateRequest {
  proposal_name: string
  customer_name?: string | null
  customer_id?: string | null
  project_id?: string | null
  creator_id: string
  items: ProposalItemRequest[]
}

export interface ProposalUpdateRequest {
  proposal_name?: string
  customer_name?: string | null
  customer_id?: string | null
  project_id?: string | null
  items?: ProposalItemRequest[]
}

export interface QuotationItemRequest {
  product_id: string
  quantity: number
  unit_price: number
  tax_rate: number
  // Track C：从方案预填时一并带上空间归属与材质说明
  project_space_id?: string | null
  floor_label?: string | null
  space_label?: string | null
  material_desc?: string | null
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
