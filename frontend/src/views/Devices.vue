<template>
  <div class="devices-view">
    <el-card shadow="never">
      <div class="toolbar">
        <div>管理接进系统的人脸识别通道（网络摄像头、USB 摄像头或视频流）</div>
        <el-button type="primary" icon="Plus" @click="openCreateDialog">
          添加识别通道
        </el-button>
      </div>

      <el-table :data="devices" style="width: 100%; margin-top: 20px;">
        <el-table-column prop="id" label="通道ID" width="90" />
        <el-table-column prop="name" label="通道/设备名称" width="180" />
        <el-table-column prop="source_type" label="视频源类型" width="130">
          <template #default="{ row }">
            <el-tag>{{ row.source_type.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source_uri" label="源地址 / 路径 / 索引" min-width="260" />
        <el-table-column prop="threshold" label="相似度比对阈值" width="140" />
        <el-table-column prop="liveness_enabled" label="活体质检" width="120">
          <template #default="{ row }">
            <el-tag :type="row.liveness_enabled ? 'success' : 'info'">
              {{ row.liveness_enabled ? '已开启' : '关闭' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="enabled" label="运行状态" width="110">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" @change="toggleDevice(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openEditDialog(row)">
              编辑
            </el-button>
            <el-popconfirm title="确定删除该识别通道吗？" @confirm="deleteDevice(row.id)">
              <template #reference>
                <el-button size="small" type="danger" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑人脸识别通道' : '添加人脸识别通道'" width="520px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="通道名称" required>
          <el-input v-model="form.name" placeholder="例如：东门人脸抓拍机" />
        </el-form-item>
        <el-form-item label="视频源类型">
          <el-select v-model="form.source_type">
            <el-option label="RTSP 网络视频流" value="rtsp" />
            <el-option label="USB 摄像头" value="usb" />
            <el-option label="本地视频文件 (回放调试)" value="file" />
          </el-select>
        </el-form-item>
        <el-form-item label="视频源 URI">
          <el-input v-model="form.source_uri" placeholder="rtsp://... 或 0 (USB) 或 本地 mp4" />
        </el-form-item>
        <el-form-item label="识别比对阈值">
          <el-slider v-model="form.threshold" :min="50" :max="95" show-input />
        </el-form-item>
        <el-form-item label="活体防伪检测">
          <el-switch v-model="form.liveness_enabled" active-text="开启静默单目活体与质量检测" />
        </el-form-item>
        <el-form-item v-if="editingId" label="启用运行">
          <el-switch v-model="form.enabled" active-text="立即启动视频流分析" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm">{{ editingId ? '保存修改' : '保存接入' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const devices = ref<any[]>([])
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({
  name: '',
  source_type: 'rtsp',
  source_uri: '',
  threshold: 75.0,
  liveness_enabled: true,
  enabled: true,
})

const loadDevices = async () => {
  devices.value = await api.get('/devices')
}

const openCreateDialog = () => {
  editingId.value = null
  Object.assign(form, {
    name: '',
    source_type: 'rtsp',
    source_uri: '',
    threshold: 75.0,
    liveness_enabled: true,
    enabled: true,
  })
  dialogVisible.value = true
}

const openEditDialog = (row: any) => {
  editingId.value = row.id
  Object.assign(form, {
    name: row.name,
    source_type: row.source_type,
    source_uri: row.source_uri || '',
    threshold: row.threshold,
    liveness_enabled: row.liveness_enabled,
    enabled: row.enabled,
  })
  dialogVisible.value = true
}

const submitForm = async () => {
  if (!form.name) {
    ElMessage.warning('请输入通道名称')
    return
  }
  if (editingId.value) {
    await api.put(`/devices/${editingId.value}`, form)
    ElMessage.success('通道配置修改成功并已重新生效')
  } else {
    await api.post('/devices', form)
    ElMessage.success('通道添加成功并已启动')
  }
  dialogVisible.value = false
  loadDevices()
}

const toggleDevice = async (row: any) => {
  await api.put(`/devices/${row.id}`, { enabled: row.enabled })
  ElMessage.info(`通道 [${row.name}] 状态已更新`)
}

const deleteDevice = async (id: number) => {
  await api.delete(`/devices/${id}`)
  ElMessage.success('通道已删除')
  loadDevices()
}

onMounted(() => {
  loadDevices()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
