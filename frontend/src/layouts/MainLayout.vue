<template>
  <el-container class="main-layout">
    <el-aside width="220px">
      <div class="logo">
        AI-PIM
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="#304156"
        text-color="#bfcbd9"
      >
        <el-sub-menu index="products">
          <template #title>
            <el-icon><Document /></el-icon>
            <span>产品管理</span>
          </template>
          <el-menu-item index="/products">
            产品列表
          </el-menu-item>
          <el-menu-item index="/categories">
            分类管理
          </el-menu-item>
          <el-menu-item index="/brands">
            品牌管理
          </el-menu-item>
          <el-menu-item index="/suppliers">
            供应商
          </el-menu-item>
          <el-menu-item index="/tags">
            标签管理
          </el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="sales">
          <template #title>
            <el-icon><DocumentCopy /></el-icon>
            <span>销售管理</span>
          </template>
          <el-menu-item index="/proposals">
            方案管理
          </el-menu-item>
          <el-menu-item index="/quotations">
            报价管理
          </el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="admin">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>系统管理</span>
          </template>
          <el-menu-item index="/users">
            用户管理
          </el-menu-item>
          <el-menu-item index="/roles">
            角色权限
          </el-menu-item>
          <el-menu-item index="/shares">
            分享管理
          </el-menu-item>
          <el-menu-item index="/logs">
            操作日志
          </el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="ai">
          <template #title>
            <el-icon><Cpu /></el-icon>
            <span>AI 功能</span>
          </template>
          <el-menu-item index="/ai-select">
            AI 智能选品
          </el-menu-item>
          <el-menu-item index="/manuals">
            产品知识库
          </el-menu-item>
          <el-menu-item index="/import">
            批量导入
          </el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header>
        <div class="header-content">
          <span>AI 产品信息管理平台</span>
          <el-button
            type="danger"
            size="small"
            @click="handleLogout"
          >
            退出
          </el-button>
        </div>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Document, DocumentCopy, Setting, Cpu } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const activeMenu = computed(() => route.path)

const handleLogout = async () => {
  await authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.main-layout {
  height: 100vh;
}

.el-aside {
  background-color: #304156;
  color: #fff;
}

.logo {
  height: 60px;
  line-height: 60px;
  text-align: center;
  font-size: 20px;
  font-weight: bold;
  color: #fff;
  background-color: #263445;
}

.el-header {
  background-color: #fff;
  border-bottom: 1px solid #e6e6e6;
  display: flex;
  align-items: center;
}

.header-content {
  flex: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.el-main {
  background-color: #f0f2f5;
  padding: 20px;
}
</style>
