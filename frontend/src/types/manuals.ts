export interface ProductManual {
  id: string
  product_id: string
  attachment_id: string
  doc_type: string
  parsed_content?: string | null
  parse_status: 'pending' | 'processing' | 'parsed' | 'failed' | 'ocr_required'
  parse_error?: string | null
  parser_name?: string | null
  parser_version?: string | null
  page_count?: number | null
  index_status: 'pending' | 'processing' | 'indexed' | 'failed'
  index_error?: string | null
  content_hash?: string | null
  last_indexed_at?: string | null
  create_time: string
  update_time: string
}

export interface ManualListResponse {
  list: ProductManual[]
  total: number
}

export interface RagSource {
  chunk_id: string
  product_manual_id: string
  product_id: string
  chunk_index: number
  chunk_text: string
  score: number
}

export interface RagAnswerResponse {
  answer: string
  sources: RagSource[]
  bounded: boolean
  insufficient_sources: boolean
}
