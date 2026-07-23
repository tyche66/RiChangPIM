import api from '@/api/index'

export interface MediaItem {
  id: string
  name: string
  type: 'image' | 'pdf' | 'other'
  mimeType: string
  size: number
  url: string
  thumbnailUrl?: string
  uploadedAt: string
  referencedBy?: string[]
  refCount?: number
  references?: MediaReferences
}

export interface MediaReferences {
  product_images: Array<{
    product_id: string
    product_no: string
    product_name: string
    product_image_id: string
    is_cover: boolean
  }>
  scene_images: Array<{
    scene_image_id: string
    scene_image_name: string
    bound_products: Array<{ product_id: string; product_no: string; product_name: string }>
  }>
  manuals: Array<{
    manual_id: string
    product_id: string
    product_no: string
    product_name: string
    doc_type: string
  }>
}

interface FileItem {
  id: string
  file_name: string
  file_url: string
  preview_url?: string
  file_type: string
  file_size: number
  storage_type: string
  oss_key: string
  create_time: string
  update_time: string
  ref_count: number
}

class MediaService {
  async list(params: { search?: string; type?: string }): Promise<MediaItem[]> {
    const queryParams: Record<string, string> = {}
    if (params.search) queryParams.keyword = params.search
    if (params.type && params.type !== 'all') queryParams.file_type = params.type

    try {
      const resp: any = await api.get('/files', { params: queryParams })
      const data = resp?.data || resp
      if (data?.list) {
        return data.list.map((f: FileItem) => this._toMediaItem(f))
      }
    } catch (err) {
      console.error('[MediaAPI] Failed to load media list:', err)
    }
    return []
  }

  async upload(file: File): Promise<MediaItem> {
    const formData = new FormData()
    formData.append('file', file)
    console.log('[MediaAPI] Uploading file:', file.name, file.type, file.size)
    const resp = await api.post('/files/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    console.log('[MediaAPI] Upload response:', resp)
    // resp is response.data due to axios interceptor
    // Backend returns: { code: 200, data: { attachment_id, file_name, file_url, file_type, file_size } }
    const d = resp?.data?.data || resp?.data
    if (!d || typeof d !== 'object') {
      console.error('[MediaAPI] Unexpected upload response:', resp)
      throw new Error('上传响应格式异常，请查看控制台日志')
    }
    return {
      id: d.attachment_id || d.id,
      name: d.file_name || d.name || file.name,
      type: (d.file_type || d.type || 'image') as 'image' | 'pdf' | 'other',
      mimeType: file.type,
      size: d.file_size || d.size || file.size,
      url: d.preview_url || d.file_url || d.url,
      uploadedAt: d.create_time || d.uploaded_at || new Date().toISOString(),
      referencedBy: [],
      refCount: 0,
    }
  }

  async delete(id: string, config?: { suppressErrorMessage?: boolean }): Promise<void> {
    await api.delete(`/files/${id}`, config)
  }

  async get(id: string, withReferences = false): Promise<MediaItem> {
    const resp: any = await api.get(`/files/${id}`, { params: { with_references: withReferences } })
    const d = resp?.data || resp
    return this._toMediaItem({
      id: d.id,
      file_name: d.file_name,
      file_url: d.preview_url || d.file_url,
      preview_url: d.preview_url,
      file_type: d.file_type,
      file_size: d.file_size,
      storage_type: d.storage_type || 'minio',
      oss_key: d.oss_key || '',
      create_time: d.create_time,
      update_time: d.update_time,
      ref_count: d.ref_count || 0,
      references: d.references,
    } as FileItem & { references?: MediaReferences })
  }

  async replace(id: string, file: File): Promise<MediaItem> {
    const formData = new FormData()
    formData.append('file', file)
    const resp = await api.put(`/files/${id}/replace`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const d = resp?.data?.data || resp?.data || resp
    if (!d || typeof d !== 'object') {
      console.error('[MediaAPI] Unexpected replace response:', resp)
      throw new Error('替换响应格式异常')
    }
    return {
      id: d.attachment_id || d.id || id,
      name: d.file_name || d.name || file.name,
      type: (d.file_type || d.type || 'image') as 'image' | 'pdf' | 'other',
      mimeType: file.type,
      size: d.file_size || d.size || file.size,
      url: d.preview_url || d.file_url || d.url,
      uploadedAt: d.create_time || d.uploaded_at || new Date().toISOString(),
      referencedBy: [],
      refCount: 0,
    }
  }

  private _toMediaItem(f: FileItem & { references?: MediaReferences }): MediaItem {
    const isImage = f.file_type === 'image'
    const isPdf = f.file_type === 'pdf'
    return {
      id: f.id,
      name: f.file_name,
      type: isImage ? 'image' : isPdf ? 'pdf' : 'other',
      mimeType: isImage ? 'image/*' : isPdf ? 'application/pdf' : 'application/octet-stream',
      size: f.file_size,
      url: f.preview_url || f.file_url,
      thumbnailUrl: isImage ? (f.preview_url || f.file_url) : undefined,
      uploadedAt: f.create_time || new Date().toISOString(),
      referencedBy: f.ref_count > 0 ? [`${f.ref_count} 处引用`] : [],
      refCount: f.ref_count || 0,
      references: f.references,
    }
  }
}

export const mediaApi = new MediaService()

export function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

export function formatDate(str: string): string {
  const d = new Date(str)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
