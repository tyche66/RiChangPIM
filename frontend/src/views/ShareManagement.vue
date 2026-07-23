<template>
  <div class="share-management-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>分享管理</span>
        </div>
      </template>

      <div class="table-responsive">
        <el-table
          v-loading="loading"
          :data="shares"
          border
          stripe
        >
          <el-table-column
            prop="id"
            label="分享ID"
            width="240"
          />
          <el-table-column
            label="分享类型"
            width="120"
          >
            <template #default="{ row }">
              <el-tag>{{ row.share_type === 'proposal' ? '方案' : '报价单' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="target_id"
            label="目标ID"
            width="240"
          />
          <el-table-column
            prop="status"
            label="状态"
            width="100"
          >
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : row.status === 'disabled' ? 'danger' : 'info'">
                {{ shareStatusMap[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="create_time"
            label="创建时间"
            width="170"
          >
            <template #default="{ row }">
              {{ formatDate(row.create_time) }}
            </template>
          </el-table-column>
          <el-table-column
            label="操作"
            width="120"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button
                v-if="hasPerm('share:delete') && row.status === 'active'"
                size="small"
                type="danger"
                @click="handleRevoke(row)"
              >
                撤销
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { shareApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'

const authStore = useAuthStore()

function hasPerm(perm: string): boolean {
  return hasPermission(authStore.permissions, perm)
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const shareStatusMap: Record<string, string> = { active: '有效', disabled: '已失效', expired: '已过期' }

const loading = ref(false)
const shares = ref<ShareRecord[]>([])

interface ShareRecord {
  id: string
  share_type: 'proposal' | 'quotation'
  target_id: string
  creator_id: string
  status: 'active' | 'disabled' | 'expired'
  create_time: string | null
}

const fetchShares = async () => {
  loading.value = true
  try {
    const res = await shareApi.list() as { data?: { list: ShareRecord[] } }
    shares.value = res.data?.list || []
  } catch {
    ElMessage.error('加载分享列表失败')
  } finally {
    loading.value = false
  }
}

const handleRevoke = async (row: ShareRecord) => {
  try {
    await ElMessageBox.confirm(`确定撤销该分享链接？`, '确认撤销')
    await shareApi.revoke(row.id)
    ElMessage.success('撤销成功')
    fetchShares()
  } catch (e: any) {
    if (e !== 'cancel') {
      // error handled by interceptor
    }
  }
}

onMounted(fetchShares)
</script>

<style scoped>
.share-management-page {
  min-height: 100vh;
  background: #f0f0f0;
  padding: 24px;
  box-sizing: border-box;
}

.share-management-page :deep(.el-card) {
  background: rgba(255, 255, 255, 0.68);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 4px 32px rgba(30, 50, 90, 0.06);
}

.share-management-page :deep(.el-card__body) {
  padding: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header :deep(span) {
  font-size: 20px;
  font-weight: 600;
  color: rgb(30, 50, 90);
  letter-spacing: 0.3px;
}

.table-responsive {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border-radius: 12px;
}

.table-responsive :deep(.el-table) {
  min-width: 700px;
  border-radius: 12px;
  overflow: hidden;
}

@media (max-width: 768px) {
  .share-management-page {
    padding: 12px;
  }
  .share-management-page :deep(.el-card__body) {
    padding: 16px;
  }
  .card-header :deep(span) {
    font-size: 18px;
  }
}
</style>
