<template>
  <div class="share-page">
    <div class="share-brand-header">
      <div class="brand-logo">
        AI-PIM
      </div>
      <div class="brand-subtitle">
        产品信息共享平台
      </div>
    </div>

    <el-card
      v-loading="loading"
      class="share-card"
    >
      <template #header>
        <div class="card-header">
          <span class="card-title">分享预览</span>
          <el-tag
            :type="accessResult === 'success' ? 'success' : 'danger'"
            class="status-tag"
          >
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
        class="password-alert"
      />

      <el-input
        v-if="needPassword && accessResult !== 'success'"
        v-model="passwordInput"
        type="password"
        placeholder="请输入访问密码"
        show-password
        class="password-input"
      >
        <template #append>
          <el-button
            type="primary"
            :loading="loading"
            class="verify-btn"
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
        class="error-alert"
      />

      <!-- Content -->
      <div
        v-if="content"
        class="share-content"
      >
        <!-- Proposal content -->
        <template v-if="shareData.share_type === 'proposal'">
          <div class="content-section">
            <h3 class="section-heading">
              方案信息
            </h3>
            <el-descriptions
              :column="1"
              border
              class="info-descriptions"
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
          </div>

          <div class="content-section">
            <h3 class="section-heading">
              商品列表
            </h3>
            <div class="table-responsive">
              <el-table
                :data="content.items"
                border
                stripe
                class="share-table"
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
                    <span class="price-text">¥{{ row.face_price?.toFixed(2) }}</span>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="quantity"
                  label="数量"
                  width="80"
                  align="center"
                />
              </el-table>
            </div>
          </div>
        </template>

        <!-- Quotation content -->
        <template v-else-if="shareData.share_type === 'quotation'">
          <div class="content-section">
            <h3 class="section-heading">
              报价信息
            </h3>
            <el-descriptions
              :column="1"
              border
              class="info-descriptions"
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
                <span class="total-amount">¥{{ content.total_amount?.toFixed(2) }}</span>
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <div class="content-section">
            <h3 class="section-heading">
              商品明细
            </h3>
            <div class="table-responsive">
              <el-table
                :data="content.items"
                border
                stripe
                class="share-table"
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
                    <span class="price-text">¥{{ row.face_price?.toFixed(2) }}</span>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="unit_price"
                  label="单价"
                >
                  <template #default="{ row }">
                    <span class="price-text">¥{{ row.unit_price?.toFixed(2) }}</span>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="quantity"
                  label="数量"
                  width="80"
                  align="center"
                />
              </el-table>
            </div>
          </div>
        </template>

        <div class="share-footer">
          <el-divider />
          <p class="footer-text">
            访问次数: <strong>{{ shareData.access_count }}</strong>
          </p>
          <p class="footer-brand">
            由 <strong>AI-PIM</strong> 提供技术支持
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
  flex-direction: column;
  align-items: center;
  background: linear-gradient(135deg, #f0f0f0 0%, #e8ecf1 100%);
  padding: 24px 16px 40px;
}

.share-brand-header {
  text-align: center;
  margin-bottom: 24px;
  padding: 20px 0 8px;
}

.brand-logo {
  font-size: 28px;
  font-weight: 700;
  color: rgb(30, 50, 90);
  letter-spacing: 4px;
  margin-bottom: 4px;
}

.brand-subtitle {
  font-size: 13px;
  color: #5E6470;
  letter-spacing: 2px;
  font-weight: 400;
}

.share-card {
  width: 100%;
  max-width: 800px;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 32px;
  border: 1px solid rgba(255, 255, 255, 0.7);
  box-shadow: 0 8px 40px rgba(30, 50, 90, 0.08);
  overflow: hidden;
}

.share-card :deep(.el-card__header) {
  background: rgba(30, 50, 90, 0.04);
  border-bottom: 1px solid rgba(30, 50, 90, 0.08);
  padding: 20px 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 20px;
  font-weight: 600;
  color: rgb(30, 50, 90);
  letter-spacing: 0.5px;
}

.status-tag {
  border-radius: 20px;
}

.share-card :deep(.el-card__body) {
  padding: 24px;
}

.password-alert {
  border-radius: 16px;
  margin-bottom: 16px !important;
}

.password-input {
  margin-bottom: 16px;
  border-radius: 20px;
}

.password-input :deep(.el-input__wrapper) {
  border-radius: 20px;
}

.verify-btn {
  border-radius: 20px;
}

.error-alert {
  border-radius: 16px;
}

.share-content {
  margin-top: 8px;
}

.content-section {
  margin-bottom: 24px;
}

.content-section:last-of-type {
  margin-bottom: 0;
}

.section-heading {
  font-size: 16px;
  font-weight: 600;
  color: rgb(30, 50, 90);
  margin: 0 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 2px solid rgba(30, 50, 90, 0.08);
}

.info-descriptions {
  border-radius: 16px;
  overflow: hidden;
}

.info-descriptions :deep(.el-descriptions__body) {
  border-radius: 16px;
}

.price-text {
  font-weight: 600;
  color: rgb(30, 50, 90);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.total-amount {
  font-size: 20px;
  font-weight: 700;
  color: rgb(30, 50, 90);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.table-responsive {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border-radius: 12px;
}

.share-table {
  min-width: 500px;
  border-radius: 12px;
  overflow: hidden;
}

.share-footer {
  margin-top: 28px;
  text-align: center;
}

.footer-text {
  color: #5E6470;
  font-size: 13px;
  margin: 0 0 4px 0;
}

.footer-brand {
  color: #5E6470;
  font-size: 12px;
  margin: 0;
  opacity: 0.7;
}

/* Mobile optimizations */
@media (max-width: 768px) {
  .share-page {
    padding: 16px 8px 32px;
  }

  .share-brand-header {
    margin-bottom: 16px;
    padding-top: 12px;
  }

  .brand-logo {
    font-size: 24px;
    letter-spacing: 3px;
  }

  .brand-subtitle {
    font-size: 12px;
  }

  .share-card {
    border-radius: 24px;
    width: 95vw;
    max-width: 95vw;
  }

  .share-card :deep(.el-card__header) {
    padding: 16px;
  }

  .share-card :deep(.el-card__body) {
    padding: 16px;
  }

  .card-title {
    font-size: 18px;
  }

  .section-heading {
    font-size: 15px;
  }

  .content-section {
    margin-bottom: 20px;
  }

  .footer-text,
  .footer-brand {
    font-size: 11px;
  }
}

@media (max-width: 380px) {
  .brand-logo {
    font-size: 22px;
  }

  .share-card {
    border-radius: 20px;
  }
}
</style>
