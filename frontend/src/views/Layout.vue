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
          <el-dropdown trigger="click" @command="handleUserCommand">
            <span class="user-dropdown">
              <el-icon><UserFilled /></el-icon>
              <span>{{ currentUsername }}</span>
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="account" icon="Key">
                  修改账号与密码
                </el-dropdown-item>
                <el-dropdown-item command="logout" icon="SwitchButton" divided style="color: #f56c6c;">
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>

    <!-- 修改管理员账号与密码弹窗 -->
    <el-dialog v-model="accountDialogVisible" title="修改登录账号与密码" width="460px">
      <el-form :model="accountForm" label-width="110px">
        <el-form-item label="登录账号" required>
          <el-input v-model="accountForm.new_username" placeholder="至少 3 个字符，例如 admin" />
        </el-form-item>
        <el-form-item label="当前原密码" required>
          <el-input
            v-model="accountForm.old_password"
            type="password"
            show-password
            placeholder="请输入当前登录密码进行验证"
          />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input
            v-model="accountForm.new_password"
            type="password"
            show-password
            placeholder="留空则保持原密码不变（至少 6 位）"
          />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input
            v-model="accountForm.confirm_password"
            type="password"
            show-password
            placeholder="若修改密码请再次输入新密码"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accountDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="accountSaving" @click="submitAccountChange">
          确认修改并重新登录
        </el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api'

const route = useRoute()
const router = useRouter()
const engineLabel = ref('引擎加载中...')
const livenessLoaded = ref(false)
const livenessSilentEnabled = ref(true)
const currentUsername = ref(localStorage.getItem('username') || 'admin')

const accountDialogVisible = ref(false)
const accountSaving = ref(false)
const accountForm = reactive({
  new_username: '',
  old_password: '',
  new_password: '',
  confirm_password: '',
})

const fetchSystemStatus = async () => {
  try {
    const [status, me]: any = await Promise.all([
      api.get('/system/status'),
      api.get('/auth/me').catch(() => null),
    ])
    engineLabel.value = status.inference_engine || 'ONNX Runtime (CPU)'
    livenessLoaded.value = Boolean(status.liveness_model_loaded)
    livenessSilentEnabled.value = status.liveness_silent_enabled !== false
    if (me?.username) {
      currentUsername.value = me.username
      localStorage.setItem('username', me.username)
    }
  } catch {
    engineLabel.value = 'ONNX Runtime (CPU)'
  }
}

const openAccountDialog = () => {
  accountForm.new_username = currentUsername.value
  accountForm.old_password = ''
  accountForm.new_password = ''
  accountForm.confirm_password = ''
  accountDialogVisible.value = true
}

const submitAccountChange = async () => {
  const newUsername = accountForm.new_username.trim()
  if (!newUsername || newUsername.length < 3) {
    ElMessage.warning('新账号长度不能少于 3 个字符')
    return
  }
  if (!accountForm.old_password) {
    ElMessage.warning('请输入当前原密码进行验证')
    return
  }
  if (accountForm.new_password) {
    if (accountForm.new_password.length < 6) {
      ElMessage.warning('新密码长度不能少于 6 个字符')
      return
    }
    if (accountForm.new_password !== accountForm.confirm_password) {
      ElMessage.warning('两次输入的新密码不一致')
      return
    }
  }
  if (newUsername === currentUsername.value && !accountForm.new_password) {
    ElMessage.warning('请修改账号名或输入新密码')
    return
  }

  accountSaving.value = true
  try {
    const res: any = await api.post('/auth/change-password', {
      old_password: accountForm.old_password,
      new_username: newUsername,
      new_password: accountForm.new_password || null,
    })
    ElMessage.success(res.message || '账号与密码修改成功，请使用新凭据重新登录')
    accountDialogVisible.value = false
    localStorage.removeItem('access_token')
    localStorage.setItem('username', res.username || newUsername)
    router.push({ path: '/login', query: { username: res.username || newUsername } })
  } finally {
    accountSaving.value = false
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

const handleUserCommand = (cmd: string) => {
  if (cmd === 'account') {
    openAccountDialog()
  } else if (cmd === 'logout') {
    logout()
  }
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
.user-dropdown {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #374151;
  font-size: 14px;
  font-weight: 500;
  padding: 6px 10px;
  border-radius: 6px;
  transition: background-color 0.2s, color 0.2s;
}
.user-dropdown:hover {
  background-color: #f3f4f6;
  color: #409eff;
}
.main-content {
  padding: 20px;
  overflow-y: auto;
}
</style>

