<template>
  <el-container class="layout-container">
    <el-aside width="240px" class="aside">
      <div class="logo">
        <el-icon size="24" color="#409eff"><VideoCamera /></el-icon>
        <span>人脸识别服务平台</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#1f2937"
        text-color="#9ca3af"
        active-text-color="#ffffff"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataLine /></el-icon>
          <span>实时监控大屏</span>
        </el-menu-item>
        <el-menu-item index="/persons">
          <el-icon><UserFilled /></el-icon>
          <span>人员档案管理</span>
        </el-menu-item>
        <el-menu-item index="/devices">
          <el-icon><VideoCameraFilled /></el-icon>
          <span>识别通道管理</span>
        </el-menu-item>
        <el-menu-item index="/events">
          <el-icon><List /></el-icon>
          <span>识别记录审计</span>
        </el-menu-item>
        <el-menu-item index="/testbench">
          <el-icon><Aim /></el-icon>
          <span>人脸算法测试台</span>
        </el-menu-item>
        <el-menu-item index="/config">
          <el-icon><Setting /></el-icon>
          <span>识别参数与模型</span>
        </el-menu-item>
        <el-menu-item index="/api-docs">
          <el-icon><Document /></el-icon>
          <span>接口调用方式说明</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-title">{{ route.meta.title }}</div>
        <div class="header-right">
          <el-tag type="success" effect="dark" round>{{ engineLabel }}</el-tag>
          <el-tag
            v-if="livenessLoaded"
            :type="livenessSilentEnabled ? 'primary' : 'warning'"
            effect="plain"
            round
          >
            {{ livenessSilentEnabled ? '静默单目活体: 已启用' : '静默单目活体: 已关闭' }}
          </el-tag>
          <el-tag type="info" round>底库上限: 10,000</el-tag>
          <el-button type="danger" link @click="logout">退出登录</el-button>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api'

const route = useRoute()
const router = useRouter()
const engineLabel = ref('引擎加载中...')
const livenessLoaded = ref(false)
const livenessSilentEnabled = ref(true)

const fetchSystemStatus = async () => {
  try {
    const status: any = await api.get('/system/status')
    engineLabel.value = status.inference_engine || 'ONNX Runtime (CPU)'
    livenessLoaded.value = Boolean(status.liveness_model_loaded)
    livenessSilentEnabled.value = status.liveness_silent_enabled !== false
  } catch {
    engineLabel.value = 'ONNX Runtime (CPU)'
  }
}

onMounted(() => {
  fetchSystemStatus()
  window.addEventListener('system-status-updated', fetchSystemStatus)
})

onUnmounted(() => {
  window.removeEventListener('system-status-updated', fetchSystemStatus)
})

const logout = () => {
  localStorage.removeItem('access_token')
  router.push('/login')
}
</script>

<style scoped>
.layout-container {
  height: 100vh;
}
.aside {
  background-color: #1f2937;
  display: flex;
  flex-direction: column;
}
.logo {
  height: 60px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding-left: 20px;
  color: #fff;
  font-size: 16px;
  font-weight: bold;
  border-bottom: 1px solid #374151;
}
.header {
  background-color: #fff;
  height: 60px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  border-bottom: 1px solid #e5e7eb;
}
.header-title {
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.main-content {
  padding: 20px;
  overflow-y: auto;
}
</style>

