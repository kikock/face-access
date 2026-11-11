<template>
  <div class="events-view">
    <el-card shadow="never">
      <div class="header-toolbar">
        <div>
          <span class="header-title">人脸识别日志记录</span>
          <span class="header-sub">（共 {{ total }} 条记录）</span>
        </div>
        <div class="actions">
          <el-button icon="Refresh" circle @click="loadEvents" />
          <el-button
            type="danger"
            plain
            icon="Delete"
            :loading="clearing"
            @click="handleClearAll"
          >
            一键清理所有记录
          </el-button>
        </div>
      </div>

      <el-table
        v-loading="loading"
        :data="events"
        style="width: 100%; margin-top: 16px;"
      >
        <el-table-column prop="id" label="记录ID" width="90" />
        <el-table-column prop="created_at" label="识别时间" width="200">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="person_name" label="姓名" width="130" />
        <el-table-column prop="person_no" label="工号/标识" width="140" />
        <el-table-column prop="result" label="识别结论" width="120">
          <template #default="{ row }">
            <el-tag :type="row.result === 'granted' ? 'success' : 'danger'">
              {{ row.result === 'granted' ? '比对命中' : '未知人员' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="score" label="相似度得分" width="120">
          <template #default="{ row }">
            <el-tag type="success">{{ row.score ? row.score.toFixed(1) : '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="现场抓拍证据" width="140">
          <template #default="{ row }">
            <el-image
              v-if="row.snapshot_path"
              style="width: 52px; height: 52px; border-radius: 4px;"
              :src="`/api/v1/snapshots/${row.snapshot_path}`"
              :preview-src-list="[`/api/v1/snapshots/${row.snapshot_path}`]"
              :preview-teleported="true"
              fit="cover"
            />
            <span v-else style="color: #9ca3af; font-size: 13px;">无抓拍图</span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="判定说明" min-width="180" />
      </el-table>

      <!-- 分页栏 -->
      <div class="pagination-box">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadEvents"
          @current-change="loadEvents"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

const events = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const clearing = ref(false)

const loadEvents = async () => {
  loading.value = true
  try {
    const res: any = await api.get('/events', {
      params: {
        page: page.value,
        page_size: pageSize.value,
      },
    })
    events.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

const handleClearAll = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要清空所有人脸识别历史记录和本地抓拍图片吗？该操作不可撤销！',
      '清空确认',
      {
        confirmButtonText: '确定清空',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    clearing.value = true
    const res: any = await api.delete('/events/clear')
    ElMessage.success(res.message || '清理完成')
    page.value = 1
    loadEvents()
  } catch (err) {
    // 取消或错误
  } finally {
    clearing.value = false
  }
}

const formatTime = (timeStr: string) => {
  if (!timeStr) return '-'
  return timeStr.replace('T', ' ').split('.')[0]
}

onMounted(() => {
  loadEvents()
})
</script>

<style scoped>
.header-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-title {
  font-weight: 600;
  font-size: 16px;
  color: #1f2937;
}
.header-sub {
  color: #9ca3af;
  font-size: 13px;
}
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.pagination-box {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
