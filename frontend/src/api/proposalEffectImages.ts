/**
 * 方案效果图 API。
 *
 * 图片先走媒体库 `POST /files/upload` 拿 attachment_id，再在这里绑定到方案；
 * 删除绑定只解除关联，不会删除媒体库文件。效果图可绑定方案内产品或空间
 * （相互独立，均可不绑定）。
 */
import api from '@/api/index'
import type { ApiEnvelope, EffectImageDraft, ProposalEffectImage } from '@/types/sales'

export interface EffectImageBindRequest {
  attachment_id: string
  name: string
  sort?: number
  product_id?: string | null
  project_space_id?: string | null
  floor_label?: string | null
  space_label?: string | null
}

export interface EffectImageUpdateRequest {
  name?: string
  sort?: number
  product_id?: string | null
  project_space_id?: string | null
  floor_label?: string | null
  space_label?: string | null
}

export const proposalEffectImageApi = {
  list: (proposalId: string) =>
    api.get(`/proposals/${proposalId}/effect-images`) as Promise<
      ApiEnvelope<{ list: ProposalEffectImage[]; total: number; limit: number }>
    >,

  create: (proposalId: string, data: EffectImageBindRequest) =>
    api.post(`/proposals/${proposalId}/effect-images`, data) as Promise<
      ApiEnvelope<ProposalEffectImage>
    >,

  /** 新增方案用：方案创建成功后一次性绑定预选的多张。 */
  batchCreate: (proposalId: string, items: EffectImageBindRequest[]) =>
    api.post(`/proposals/${proposalId}/effect-images/batch`, { items }) as Promise<
      ApiEnvelope<{ list: ProposalEffectImage[]; created: number; total: number }>
    >,

  update: (proposalId: string, effectImageId: string, data: EffectImageUpdateRequest) =>
    api.put(`/proposals/${proposalId}/effect-images/${effectImageId}`, data) as Promise<
      ApiEnvelope<ProposalEffectImage>
    >,

  remove: (proposalId: string, effectImageId: string) =>
    api.delete(`/proposals/${proposalId}/effect-images/${effectImageId}`),
}

export type { EffectImageDraft }