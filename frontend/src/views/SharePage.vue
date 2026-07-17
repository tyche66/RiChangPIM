<template>
  <div class="share-page">
    <el-card
      v-loading="loading"
      class="share-card"
    >
      <template #header>
        <div class="card-header">
          <span>分享预览</span>
          <el-tag :type="accessResult === 'success' ? 'success' : 'danger'">
            {{ accessResult === 'success' ? '有效链接' : '链接失效' }}
          </el-tag>
        </div>
      </template>

      <!-- Password prompt -->
      <el-alert
        v-if="needPassword && accessResult !== 'success'"
        type="warning"
        title="该分享需要访问密码"
        :closable="false"
        style="margin-bottom: 16px;"
      />

      <el-input
        v-if="needPassword && accessResult !== 'success'"
        v-model="passwordInput"
        type="password"
        placeholder="请输入访问密码"
        show-password
        style="margin-bottom: 16px;"
      >
        <template #append>
          <el-button
            type="primary"
            :loading="loading"
            @click="fetchContent"
          >
            验证
          </el-button>
        </template>
      </el-input>

      <!-- Error state -->
      <el-alert
        v-if="accessResult && accessResult !== 'success' && accessResult !== 'denied_password'"
        type="error"
        :title="errorMessage"
        :closable="false"
      />

      <!-- Content -->
      <div
        v-if="content"
        class="share-content"
      >
        <!-- Proposal content -->
        <template v-if="shareData.share_type === 'proposal'">
          <el-descriptions
            :column="1"
            border
            style="margin-bottom: 20px;"
          >
            <el-descriptions-item label="方案名称">
              {{ content.proposal_name }}
            </el-descriptions-item>
            <el-descriptions-item label="客户名称">
              {{ content.customer_name || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="content.status === 'confirmed' ? 'success' : 'info'">
                {{ content.status }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>

          <el-table
            :data="content.items"
            border
            stripe
          >
            <el-table-column
              prop="product_name"
              label="商品名称"
            />
            <el-table-column
              prop="face_price"
              label="面价"
            >
              <template #default="{ row }">
                ¥{{ row.face_price?.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="quantity"
              label="数量"
              width="80"
            />
          </el-table>
        </template>

        <!-- Quotation content -->
        <template v-else-if="shareData.share_type === 'quotation'">
          <el-descriptions
            :column="1"
            border
            style="margin-bottom: 20px;"
          >
            <el-descriptions-item label="报价单号">
              {{ content.quotation_no }}
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="content.status === 'confirmed' ? 'success' : 'info'">
                {{ content.status }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="总金额">
              ¥{{ content.total_amount?.toFixed(2) }}
            </el-descriptions-item>
          </el-descriptions>

          <el-table
            :data="content.items"
            border
            stripe
          >
            <el-table-column
              prop="product_name"
              label="商品名称"
            />
            <el-table-column
              prop="face_price"
              label="面价"
            >
              <template #default="{ row }">
                ¥{{ row.face_price?.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="unit_price"
              label="单价"
            >
              <template #default="{ row }">
                ¥{{ row.unit_price?.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="quantity"
              label="数量"
              width="80"
            />
          </el-table>
        </template>

        <div class="share-footer">
          <el-divider />
          <p class="footer-text">
            访问次数: {{ shareData.access_count }} |
            本页面由 AI-PIM 提供技术支持
          </p>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { shareApi } from '@/api'

const route = useRoute()
const token = route.params.token as string

const loading = ref(false)
const needPassword = ref(false)
const passwordInput = ref('')
const accessResult = ref('')
const errorMessage = ref('分享链接无效或已过期')

const shareData = reactive({
  share_type: '',
  target_id: '',
  access_count: 0,
})
const content = ref<any>(null)

const fetchContent = async () => {
  loading.value = true
  try {
    const res = await shareApi.get(token, passwordInput.value || undefined) as any
    const data = res.data
    shareData.share_type = data.share_type
    shareData.target_id = data.target_id
    shareData.access_count = data.access_count
    content.value = data.content
    accessResult.value = 'success'
    needPassword.value = false
  } catch (e: any) {
    const code = e?.response?.data?.detail?.code
    const msg = e?.response?.data?.detail?.msg
    if (code === 40304) {
      needPassword.value = true
      accessResult.value = 'denied_password'
      errorMessage.value = msg || '访问密码错误'
      ElMessage.error(errorMessage.value)
    } else {
      accessResult.value = 'denied'
      errorMessage.value = msg || '分享链接无效或已过期'
      ElMessage.error(errorMessage.value)
    }
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchContent()
})
</script>

<style scoped>
.share-page {
  min-height: 100vh;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  background: #f5f7fa;
  padding: 40px 20px;
}

.share-card {
  width: 100%;
  max-width: 800px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.share-content {
  margin-top: 16px;
}

.share-footer {
  margin-top: 24px;
  text-align: center;
}

.footer-text {
  color: #909399;
  font-size: 12px;
  margin: 0;
}
</style>
