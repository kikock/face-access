<template>
  <div class="login-container">
    <el-card class="login-card" shadow="always">
      <div class="title-area">
        <h2>人脸识别服务平台</h2>
        <p>10,000 人脸底库 · 高性能单机服务</p>
      </div>

      <el-form :model="form" :rules="rules" ref="formRef" label-position="top">
        <el-form-item label="管理员账号" prop="username">
          <el-input v-model="form.username" placeholder="请输入管理员用户名" prefix-icon="User" />
        </el-form-item>
        <el-form-item label="登录密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            prefix-icon="Lock"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-button type="primary" class="submit-btn" :loading="loading" @click="handleLogin">
          立即登录
        </el-button>
      </el-form>

      <div class="hint">默认初始账号: admin / admin123456</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api'

const router = useRouter()
const formRef = ref()
const loading = ref(false)

const form = reactive({
  username: 'admin',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const handleLogin = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    loading.value = true
    try {
      const res: any = await api.post('/auth/login', form)
      localStorage.setItem('access_token', res.access_token)
      ElMessage.success('登录成功')
      router.push('/dashboard')
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
}
.login-card {
  width: 400px;
  border-radius: 12px;
  padding: 24px;
}
.title-area {
  text-align: center;
  margin-bottom: 24px;
}
.title-area h2 {
  margin: 0;
  color: #1f2937;
}
.title-area p {
  margin-top: 8px;
  color: #6b7280;
  font-size: 13px;
}
.submit-btn {
  width: 100%;
  margin-top: 16px;
}
.hint {
  margin-top: 16px;
  font-size: 12px;
  color: #9ca3af;
  text-align: center;
}
</style>

