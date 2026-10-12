<template>
  <div class="crm-page">
    <el-card
      v-loading="loading"
      class="crm-card"
    >
      <template #header>
        <div class="crm-card__header">
          <div class="crm-detail-head">
            <el-button
              text
              class="crm-link"
              @click="router.back()"
            >
              ← 返回
            </el-button>
            <span class="crm-detail-head__title">{{ project?.name || '项目详情' }}</span>
            <el-tag
              v-if="project"
              :type="stageTagType(project.stage)"
              class="crm-tag"
            >
              {{ labelOf(PROJECT_STAGE_MAP, project.stage) }}
            </el-tag>
            <span
              v-if="project?.code"
              class="crm-mono"
            >{{ project.code }}</span>
          </div>
          <div class="crm-card__actions">
            <el-dropdown
              v-if="hasPerm('project:edit') && project && projectAllowedTransitions(project.stage).length"
              trigger="click"
              @command="(to: string) => handleTransition(to)"
            >
              <el-button class="crm-btn crm-btn--primary">
                变更阶段
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="to in projectAllowedTransitions(project.stage)"
                    :key="to"
                    :command="to"
                  >
                    转为「{{ labelOf(PROJECT_STAGE_MAP, to) }}」
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <!-- 概览 -->
        <el-tab-pane
          label="概览"
          name="overview"
        >
          <el-steps
            :active="stageIndex"
            align-center
            finish-status="success"
            class="stage-steps"
          >
            <el-step
              v-for="stage in PROJECT_STAGE_ORDER"
              :key="stage"
              :title="labelOf(PROJECT_STAGE_MAP, stage)"
            />
          </el-steps>
          <el-descriptions
            :column="2"
            border
            class="crm-section"
          >
            <el-descriptions-item label="客户">
              {{ project?.customer_brief?.name || customerName || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="类型">
              {{ labelOf(PROJECT_TYPE_MAP, project?.project_type) }}
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              {{ labelOf(PROJECT_STATUS_MAP, project?.status) }}
            </el-descriptions-item>
            <el-descriptions-item label="预算">
              {{ project?.budget != null ? `¥${project.budget}` : '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="开始日期">
              {{ project?.start_date || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="结束日期">
              {{ project?.end_date || '—' }}
            </el-descriptions-item>
            <el-descriptions-item
              label="最近活跃"
              :span="2"
            >
              {{ formatBeijingTime(project?.last_activity_at) || '—' }}
            </el-descriptions-item>
            <el-descriptions-item
              label="备注"
              :span="2"
            >
              {{ project?.remark || '—' }}
            </el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>

        <!-- 成员 -->
        <el-tab-pane
          label="成员"
          name="members"
        >
          <div
            v-if="hasPerm('project:member')"
            class="inline-form"
          >
            <el-select
              v-model="memberForm.user_id"
              class="crm-select member-user"
              filterable
              placeholder="选择用户"
            >
              <el-option
                v-for="u in users"
                :key="u.id"
                :label="u.username"
                :value="u.id"
              />
            </el-select>
            <el-select
              v-model="memberForm.member_role"
              class="crm-select channel-select"
            >
              <el-option
                v-for="(label, value) in MEMBER_ROLE_MAP"
                :key="value"
                :label="label"
                :value="value"
              />
            </el-select>
            <el-checkbox v-model="memberForm.is_primary">
              主负责人
            </el-checkbox>
            <el-button
              type="primary"
              class="crm-btn crm-btn--primary"
              :loading="adding"
              @click="addMember"
            >
              添加
            </el-button>
          </div>
          <p
            v-if="!members.length"
            class="crm-empty"
          >
            暂无成员
          </p>
          <el-table
            v-else
            :data="members"
            class="crm-table"
          >
            <el-table-column
              label="成员"
              min-width="140"
            >
              <template #default="{ row }">
                {{ row.username || row.user_id }}
              </template>
            </el-table-column>
            <el-table-column
              label="角色"
              width="120"
            >
              <template #default="{ row }">
                {{ labelOf(MEMBER_ROLE_MAP, row.member_role) }}
              </template>
            </el-table-column>
            <el-table-column
              label="主负责人"
              width="100"
              align="center"
            >
              <template #default="{ row }">
                {{ row.is_primary ? '是' : '否' }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="hasPerm('project:member')"
              label="操作"
              width="100"
              align="center"
            >
              <template #default="{ row }">
                <el-button
                  size="small"
                  text
                  class="crm-link crm-link--danger"
                  @click="removeMember(row)"
                >
                  移除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 图纸 -->
        <el-tab-pane
          label="图纸"
          name="assets"
        >
          <div
            v-if="hasPerm('project:asset')"
            class="crm-uploader"
          >
            <el-select
              v-model="assetForm.category"
              class="crm-select channel-select"
            >
              <el-option
                v-for="(label, value) in ASSET_CATEGORY_MAP"
                :key="value"
                :label="label"
                :value="value"
              />
            </el-select>
            <el-input
              v-model="assetForm.name"
              class="crm-input asset-name-input"
              placeholder="资产名称（同名自动升版本）"
            />
            <el-upload
              :auto-upload="false"
              :limit="1"
              :show-file-list="false"
              accept=".dwg,.dxf,.skp,.psd"
              :on-change="onFileChange"
            >
              <el-button class="crm-btn">
                选择文件（.dwg/.dxf/.skp/.psd）
              </el-button>
            </el-upload>
            <span
              v-if="assetFile"
              class="crm-mono selected-file"
            >{{ assetFile.name }}</span>
            <el-button
              type="primary"
              class="crm-btn crm-btn--primary"
              :loading="adding"
              @click="uploadAsset"
            >
              上传
            </el-button>
          </div>
          <p
            v-if="!assetGroups.length"
            class="crm-empty"
          >
            暂无图纸资产
          </p>
          <el-table
            v-else
            :data="assetGroups"
            class="crm-table"
          >
            <el-table-column
              label="名称"
              min-width="180"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                <span class="crm-asset-name">
                  {{ row.name }}
                  <el-tag
                    size="small"
                    class="crm-tag"
                  >
                    v{{ row.current.version }}
                  </el-tag>
                </span>
              </template>
            </el-table-column>
            <el-table-column
              label="类别"
              width="110"
            >
              <template #default="{ row }">
                {{ labelOf(ASSET_CATEGORY_MAP, row.category) }}
              </template>
            </el-table-column>
            <el-table-column
              label="状态"
              width="100"
              align="center"
            >
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="assetStatusType(row.current.status)"
                  class="crm-tag"
                >
                  {{ labelOf(ASSET_STATUS_MAP, row.current.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              label="更新时间"
              width="170"
            >
              <template #default="{ row }">
                <span class="crm-mono">{{ formatBeijingTime(row.current.update_time) || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="hasPerm('project:asset')"
              label="操作"
              width="220"
              align="center"
            >
              <template #default="{ row }">
                <el-button
                  size="small"
                  text
                  class="crm-link"
                  @click="openHistory(row)"
                >
                  版本历史（{{ row.versions.length }}）
                </el-button>
                <el-button
                  size="small"
                  text
                  class="crm-link"
                  @click="setAssetStatus(row.current, 'approved')"
                >
                  通过
                </el-button>
                <el-button
                  size="small"
                  text
                  class="crm-link crm-link--danger"
                  @click="setAssetStatus(row.current, 'obsolete')"
                >
                  作废
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 方案 -->
        <el-tab-pane
          label="方案"
          name="proposals"
        >
          <p
            v-if="!proposals.length"
            class="crm-empty"
          >
            暂无关联方案
          </p>
          <ul
            v-else
            class="crm-list"
          >
            <li
              v-for="p in proposals"
              :key="p.id"
              class="crm-list-item proposal-item"
            >
              <el-button
                text
                class="crm-link"
                @click="router.push(`/proposals/${p.id}`)"
              >
                {{ p.proposal_name }}
              </el-button>
              <div class="crm-list-item__meta">
                <el-tag
                  size="small"
                  :type="p.status === 'confirmed' ? 'success' : 'info'"
                  class="crm-tag"
                >
                  {{ p.status === 'confirmed' ? '已确认' : '草稿' }}
                </el-tag>
                <span>{{ formatBeijingTime(p.create_time) }}</span>
              </div>
            </li>
          </ul>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 版本历史 -->
    <el-dialog
      v-model="historyVisible"
      title="版本历史"
      width="560px"
      align-center
    >
      <el-table
        :data="historyVersions"
        class="crm-table"
      >
        <el-table-column
          label="版本"
          width="80"
        >
          <template #default="{ row }">
            v{{ row.version }}
          </template>
        </el-table-column>
        <el-table-column
          label="当前"
          width="80"
          align="center"
        >
          <template #default="{ row }">
            {{ row.is_current ? '是' : '否' }}
          </template>
        </el-table-column>
        <el-table-column
          label="状态"
          width="100"
        >
          <template #default="{ row }">
            {{ labelOf(ASSET_STATUS_MAP, row.status) }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间">
          <template #default="{ row }">
            <span class="crm-mono">{{ formatBeijingTime(row.create_time) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile } from 'element-plus'
import { userApi } from '@/api'
import { customerApi } from '@/api/customer'
import {
  projectApi,
  type ProjectAsset,
  type ProjectItem,
  type ProjectMember,
  type ProjectProposalItem,
} from '@/api/project'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'
import {
  ASSET_CATEGORY_MAP,
  ASSET_STATUS_MAP,
  MEMBER_ROLE_MAP,
  PROJECT_STAGE_MAP,
  PROJECT_STAGE_ORDER,
  PROJECT_STATUS_MAP,
  PROJECT_TYPE_MAP,
  labelOf,
  projectAllowedTransitions,
  projectTransitionNeedsReason,
} from '@/constants/crm'
import { formatBeijingTime } from '@/utils/beijingTime'

interface AssetGroup {
  key: string
  name: string
  category: string
  current: ProjectAsset
  versions: ProjectAsset[]
}

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const projectId = computed(() => String(route.params.id))

function hasPerm(perm: string): boolean {
  return hasPermission(authStore.permissions, perm)
}

const loading = ref(false)
const adding = ref(false)
const project = ref<ProjectItem | null>(null)
const customerName = ref('')
const activeTab = ref('overview')

const members = ref<ProjectMember[]>([])
const users = ref<Array<{ id: string; username: string }>>([])
const assets = ref<ProjectAsset[]>([])
const proposals = ref<ProjectProposalItem[]>([])

const memberForm = reactive<{ user_id: string; member_role: string; is_primary: boolean }>({
  user_id: '',
  member_role: 'designer',
  is_primary: false,
})

const assetForm = reactive<{ category: string; name: string }>({ category: 'drawing', name: '' })
const assetFile = ref<File | null>(null)

const historyVisible = ref(false)
const historyVersions = ref<ProjectAsset[]>([])

const stageIndex = computed(() => {
  const idx = PROJECT_STAGE_ORDER.indexOf(project.value?.stage ?? '')
  return idx < 0 ? 0 : idx
})

const assetGroups = computed<AssetGroup[]>(() => {
  const map = new Map<string, AssetGroup>()
  for (const a of assets.value) {
    const key = `${a.category}::${a.name}`
    let group = map.get(key)
    if (!group) {
      group = { key, name: a.name, category: a.category, current: a, versions: [] }
      map.set(key, group)
    }
    group.versions.push(a)
    if (a.is_current) group.current = a
  }
  for (const group of map.values()) {
    group.versions.sort((a, b) => b.version - a.version)
  }
  return Array.from(map.values())
})

function stageTagType(stage: string): 'success' | 'danger' | 'warning' | 'info' {
  if (stage === 'closed') return 'success'
  if (stage === 'cancelled') return 'danger'
  if (stage === 'producing' || stage === 'delivered') return 'warning'
  return 'info'
}

function assetStatusType(status: string): 'success' | 'danger' | 'info' {
  if (status === 'approved') return 'success'
  if (status === 'obsolete') return 'danger'
  return 'info'
}

async function loadProject() {
  loading.value = true
  try {
    project.value = (await projectApi.get(projectId.value)).data
    if (project.value && !project.value.customer_brief && hasPerm('customer:view')) {
      try {
        customerName.value = (await customerApi.get(project.value.customer_id)).data.name
      } catch {
        // 客户不可见（数据范围外）时留空
      }
    }
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

async function loadMembers() {
  if (!hasPerm('project:member')) return
  try {
    members.value = (await projectApi.members(projectId.value)).data.list
  } catch {
    // ignore
  }
}

async function loadUsers() {
  try {
    const res = (await userApi.list({ page: 1, size: 100 })) as {
      data?: { list?: Array<{ id: string; username: string }> } | Array<{ id: string; username: string }>
    }
    const raw = res.data
    users.value = Array.isArray(raw) ? raw : (raw?.list ?? [])
  } catch {
    // ignore
  }
}

async function loadAssets() {
  if (!hasPerm('project:asset')) return
  try {
    assets.value = (await projectApi.assets(projectId.value)).data.list
  } catch {
    // ignore
  }
}

async function loadProposals() {
  try {
    proposals.value = (await projectApi.proposals(projectId.value)).data.list
  } catch {
    // ignore
  }
}

async function handleTransition(to: string) {
  if (!project.value) return
  let reason: string | undefined
  if (projectTransitionNeedsReason(project.value.stage, to)) {
    try {
      const { value } = await ElMessageBox.prompt(
        to === 'cancelled' ? '取消项目需要填写原因' : '回退阶段需要填写原因',
        '阶段变更',
        { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '请输入原因' },
      )
      reason = value
    } catch {
      return
    }
  }
  try {
    project.value = (await projectApi.transitionStage(projectId.value, to, reason)).data
    ElMessage.success('阶段已更新')
  } catch {
    // ignore
  }
}

async function addMember() {
  if (!memberForm.user_id) {
    ElMessage.warning('请选择用户')
    return
  }
  adding.value = true
  try {
    await projectApi.addMember(projectId.value, { ...memberForm })
    memberForm.user_id = ''
    memberForm.is_primary = false
    ElMessage.success('已添加')
    loadMembers()
  } catch {
    // ignore
  } finally {
    adding.value = false
  }
}

async function removeMember(member: ProjectMember) {
  try {
    await ElMessageBox.confirm(`确定移除成员「${member.username || member.user_id}」吗？`, '移除成员', {
      confirmButtonText: '移除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await projectApi.removeMember(projectId.value, member.user_id)
    ElMessage.success('已移除')
    loadMembers()
  } catch {
    // ignore
  }
}

function onFileChange(file: UploadFile) {
  assetFile.value = file.raw ?? null
}

async function uploadAsset() {
  if (!assetFile.value) {
    ElMessage.warning('请选择文件')
    return
  }
  if (!assetForm.name.trim()) {
    ElMessage.warning('请填写资产名称')
    return
  }
  adding.value = true
  try {
    const form = new FormData()
    form.append('file', assetFile.value)
    const upload = await projectApi.uploadFile(form)
    await projectApi.addAsset(projectId.value, {
      attachment_id: upload.data.attachment_id,
      category: assetForm.category,
      name: assetForm.name,
    })
    assetForm.name = ''
    assetFile.value = null
    ElMessage.success('已上传')
    loadAssets()
  } catch {
    // ignore
  } finally {
    adding.value = false
  }
}

async function setAssetStatus(asset: ProjectAsset, status: string) {
  try {
    await projectApi.updateAssetStatus(projectId.value, asset.id, status)
    ElMessage.success('已更新')
    loadAssets()
  } catch {
    // ignore
  }
}

function openHistory(group: AssetGroup) {
  historyVersions.value = group.versions
  historyVisible.value = true
}

onMounted(() => {
  loadProject()
  loadMembers()
  loadAssets()
  loadProposals()
  if (hasPerm('project:member')) loadUsers()
})
</script>

<style scoped>
.stage-steps {
  margin: 8px 0 8px;
}

.inline-form {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.channel-select {
  width: 130px;
  flex: 0 0 auto;
}

.member-user {
  width: 200px;
  flex: 0 0 auto;
}

.asset-name-input {
  width: 260px;
}

.selected-file {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.proposal-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
</style>
