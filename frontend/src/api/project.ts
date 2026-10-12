/**
 * 项目域 API（HLD §8.3）。
 *
 * 图纸上传是两步：先 POST /files/upload 拿 attachment_id，再
 * POST /projects/{id}/assets 绑定为项目资产（同名自动 +version）。
 */
import api from '@/api'
import type { ApiEnvelope, Paginated } from '@/types/sales'

export interface CustomerBrief {
  customer_no: string | null
  name: string
}

export interface ProjectItem {
  id: string
  customer_id: string
  customer_brief: CustomerBrief | null
  code: string | null
  name: string
  project_type: string
  stage: string
  status: string
  budget: number | null
  start_date: string | null
  end_date: string | null
  remark: string | null
  last_activity_at: string | null
  create_time: string | null
  update_time: string | null
}

export interface ProjectListParams {
  stage?: string
  status?: string
  customer_id?: string
  q?: string
  page?: number
  size?: number
}

export interface ProjectCreateRequest {
  customer_id: string
  name: string
  code?: string | null
  project_type?: string
  budget?: number | null
  start_date?: string | null
  end_date?: string | null
  remark?: string | null
}

export type ProjectUpdateRequest = Partial<Omit<ProjectCreateRequest, 'customer_id'>>

export interface ProjectMember {
  id: string
  project_id: string
  user_id: string
  member_role: string
  is_primary: boolean
  username: string | null
  create_time: string | null
}

export interface ProjectAsset {
  id: string
  project_id: string
  category: string
  name: string
  version: number
  is_current: boolean
  status: string
  attachment_id: string
  remark: string | null
  create_time: string | null
  update_time: string | null
}

export interface ProjectProposalItem {
  id: string
  proposal_no: string | null
  proposal_name: string
  status: string
  total_face_value: number | null
  create_time: string | null
}

export interface FileUploadResult {
  attachment_id: string
  file_name: string
  file_url: string
  preview_url: string | null
  file_type: string
  file_size: number
}

export const projectApi = {
  list: (params?: ProjectListParams) =>
    api.get('/projects', { params }) as Promise<ApiEnvelope<Paginated<ProjectItem>>>,

  get: (id: string) => api.get(`/projects/${id}`) as Promise<ApiEnvelope<ProjectItem>>,

  create: (data: ProjectCreateRequest) =>
    api.post('/projects', data) as Promise<ApiEnvelope<ProjectItem>>,

  update: (id: string, data: ProjectUpdateRequest) =>
    api.put(`/projects/${id}`, data) as Promise<ApiEnvelope<ProjectItem>>,

  remove: (id: string) => api.delete(`/projects/${id}`),

  transitionStage: (id: string, toStage: string, reason?: string) =>
    api.patch(`/projects/${id}/stage`, { to_stage: toStage, reason }) as Promise<
      ApiEnvelope<ProjectItem>
    >,

  members: (id: string) =>
    api.get(`/projects/${id}/members`) as Promise<
      ApiEnvelope<{ list: ProjectMember[]; total: number }>
    >,

  addMember: (
    id: string,
    data: { user_id: string; member_role: string; is_primary?: boolean },
  ) => api.post(`/projects/${id}/members`, data) as Promise<ApiEnvelope<ProjectMember>>,

  removeMember: (id: string, userId: string) => api.delete(`/projects/${id}/members/${userId}`),

  assets: (id: string, category?: string) =>
    api.get(`/projects/${id}/assets`, { params: category ? { category } : {} }) as Promise<
      ApiEnvelope<{ list: ProjectAsset[]; total: number }>
    >,

  addAsset: (
    id: string,
    data: { attachment_id: string; category: string; name: string; remark?: string | null },
  ) => api.post(`/projects/${id}/assets`, data) as Promise<ApiEnvelope<ProjectAsset>>,

  updateAssetStatus: (id: string, assetId: string, status: string) =>
    api.patch(`/projects/${id}/assets/${assetId}`, { status }) as Promise<
      ApiEnvelope<ProjectAsset>
    >,

  proposals: (id: string) =>
    api.get(`/projects/${id}/proposals`) as Promise<
      ApiEnvelope<Paginated<ProjectProposalItem>>
    >,

  uploadFile: (data: FormData) =>
    api.post('/files/upload', data, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }) as Promise<ApiEnvelope<FileUploadResult>>,
}
