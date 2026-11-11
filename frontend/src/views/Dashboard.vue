<template>
  <div class="dashboard">
    <!-- 统计指标卡片 -->
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-title">已注册人员总数</div>
          <div class="stat-value text-primary">{{ status.person_count }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-title">底库特征向量数</div>
          <div class="stat-value text-success">{{ status.face_feature_count }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-title">接入识别通道</div>
          <div class="stat-value text-warning">{{ status.device_count }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-title">累计识别记录</div>
          <div class="stat-value text-info">{{ status.access_event_count }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 实时视频流与实时抓拍动态 -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="14">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>实时视频流画面监控</span>
              <el-select
                v-model="selectedDevId"
                placeholder="请选择识别通道"
                style="width: 220px;"
                clearable
              >
                <!-- 显式提供 “请选择 (不进行识别记录)” -->
                <el-option label="-- 请选择 (不进行识别记录) --" :value="null" />
                <el-option
                  v-for="d in devices"
                  :key="d.id"
                  :label="`${d.name} (${d.source_type.toUpperCase()})`"
                  :value="d.id"
                />
              </el-select>
            </div>
          </template>
          <div class="video-container">
            <img
              v-if="selectedDevId"
              :src="`/api/v1/devices/${selectedDevId}/stream`"
              class="video-feed"
              alt="实时视频流"
            />
            <div v-else class="video-placeholder">
              <el-icon size="48"><VideoCamera /></el-icon>
              <p style="margin-top: 12px; font-size: 15px;">当前处于“未选择通道”状态</p>
              <p style="font-size: 13px; color: #9ca3af;">请在上方下拉菜单中选择已配置的通道，启动实时画面与人脸识别</p>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>实时识别动态</span>
              <div style="display: flex; align-items: center; gap: 8px;">
                <el-tag :type="selectedDevId ? 'success' : 'info'" size="small">
                  {{ selectedDevId ? '通道正在实时识别' : '通道待命' }}
                </el-tag>
                <el-tag type="success" size="small">WebSocket 已连接</el-tag>
              </div>
            </div>
          </template>
          <el-timeline style="max-height: 480px; overflow-y: auto; padding-right: 10px;">
            <el-timeline-item
              v-for="e in liveEvents"
              :key="e.event_id || e.id"
              :timestamp="formatTime(e.time || e.created_at)"
              type="primary"
            >
              <div class="event-item">
                <div class="event-desc">
                  <strong>{{ e.person_name }}</strong> ({{ e.person_no }})
                  <el-tag size="small" type="success" style="margin-left: 8px;">
                    匹配分: {{ e.score.toFixed(1) }}
                  </el-tag>
                </div>
                <el-image
                  v-if="e.snapshot || e.snapshot_path"
                  :src="`/api/v1/snapshots/${e.snapshot || e.snapshot_path}`"
                  :preview-src-list="[`/api/v1/snapshots/${e.snapshot || e.snapshot_path}`]"
                  :preview-teleported="true"
                  class="event-snap"
                  fit="cover"
                />
                <span v-else style="font-size: 12px; color: #9ca3af;">[无抓拍图]</span>
              </div>
            </el-timeline-item>
            <div v-if="!liveEvents.length" style="color: #9ca3af; text-align: center; padding: 40px 0;">
              暂无现场识别消息
            </div>
          </el-timeline>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import api from '@/api'

const status = ref<any>({
  person_count: 0,
  face_feature_count: 0,
  device_count: 0,
  access_event_count: 0,
})

const devices = ref<any[]>([])
// 默认值为 null 即 “请选择 (不进行识别记录)”
const selectedDevId = ref<number | null>(null)
const liveEvents = ref<any[]>([])
let ws: WebSocket | null = null

const loadData = async () => {
  status.value = await api.get('/system/status')
  devices.value = await api.get('/devices')
  const res: any = await api.get('/events', { params: { page: 1, page_size: 15 } })
  liveEvents.value = res.items || []
}

const formatTime = (timeStr: string) => {
  if (!timeStr) return '-'
  return timeStr.replace('T', ' ').split('.')[0]
}

const setupWebSocket = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${protocol}//${window.location.host}/ws/events`)
  ws.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data)
      if (data.type === 'access_event') {
        if (selectedDevId.value === null || data.device_id === selectedDevId.value) {
          liveEvents.value.unshift(data)
          if (liveEvents.value.length > 20) {
            liveEvents.value.pop()
          }
          status.value.access_event_count += 1
        }
      }
    } catch (e) {
      console.error('WS 解析错误:', e)
    }
  }
}

onMounted(() => {
  loadData()
  setupWebSocket()
})

onUnmounted(() => {
  if (ws) ws.close()
})
</script>

<style scoped>
.stat-card {
  text-align: center;
}
.stat-title {
  color: #6b7280;
  font-size: 14px;
}
.stat-value {
  font-size: 32px;
  font-weight: bold;
  margin-top: 8px;
}
.text-primary { color: #409eff; }
.text-success { color: #67c23a; }
.text-warning { color: #e6a23c; }
.text-info { color: #909399; }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.video-container {
  height: 480px;
  background-color: #000;
  display: flex;
  justify-content: center;
  align-items: center;
  border-radius: 8px;
  overflow: hidden;
}
.video-feed {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
.video-placeholder {
  color: #6b7280;
  text-align: center;
}
.event-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.event-snap {
  width: 60px;
  height: 60px;
  border-radius: 4px;
  object-fit: cover;
  border: 1px solid #e5e7eb;
}
</style>
