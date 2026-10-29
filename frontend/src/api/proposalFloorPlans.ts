/**
 * 方案平面图 API（Track D）。
 *
 * 图片先走媒体库 `POST /files/upload` 拿 attachment_id，再在这里绑定到方案。
 * 删除绑定只解除关联，不会删除媒体库文件。
 */
import api from '@/api/index'
import type { ApiEnvelope, ProposalFloorPlan } from '@/types/sales'

export interface FloorPlanBindRequest {
  attachment_id: string
  name: string
  sort?: number
  floor_label?: string | null
  space_label?: string | null
}

export interface FloorPlanUpdateRequest {
  name?: string
  sort?: number
  floor_label?: string | null
  space_label?: string | null
}

export const proposalFloorPlanApi = {
  list: (proposalId: string) =>
    api.get(`/proposals/${proposalId}/floor-plans`) as Promise<
      ApiEnvelope<{ list: ProposalFloorPlan[]; total: number; limit: number }>
    >,

  create: (proposalId: string, data: FloorPlanBindRequest) =>
    api.post(`/proposals/${proposalId}/floor-plans`, data) as Promise<
      ApiEnvelope<ProposalFloorPlan>
    >,

  /** 新增方案对话框用：方案创建成功后一次性绑定预选的多张。 */
  batchCreate: (proposalId: string, items: FloorPlanBindRequest[]) =>
    api.post(`/proposals/${proposalId}/floor-plans/batch`, { items }) as Promise<
      ApiEnvelope<{ list: ProposalFloorPlan[]; created: number; total: number }>
    >,

  update: (proposalId: string, floorPlanId: string, data: FloorPlanUpdateRequest) =>
    api.put(`/proposals/${proposalId}/floor-plans/${floorPlanId}`, data) as Promise<
      ApiEnvelope<ProposalFloorPlan>
    >,

  remove: (proposalId: string, floorPlanId: string) =>
    api.delete(`/proposals/${proposalId}/floor-plans/${floorPlanId}`),
}
