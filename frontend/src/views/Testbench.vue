<template>
  <div class="testbench-view">
    <el-row :gutter="20">
      <!-- 1:1 比对测试 -->
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>人脸 1:1 两图两两比对</span>
              <el-tag type="info">身份验证模式</el-tag>
            </div>
          </template>

          <div class="compare-inputs">
            <div class="file-box">
              <p>照片 A</p>
              <input type="file" accept="image/*" @change="onFile1Change" />
            </div>
            <div class="file-box">
              <p>照片 B</p>
              <input type="file" accept="image/*" @change="onFile2Change" />
            </div>
          </div>

          <el-button
            type="primary"
            style="margin-top: 16px; width: 100%;"
            :loading="comparing"
            @click="runCompare"
          >
            开始 1:1 比对分析
          </el-button>

          <div v-if="compareResult" class="result-box">
            <el-result
              :icon="compareResult.same_person ? 'success' : 'error'"
              :title="compareResult.same_person ? '判定为同一人' : '非同一人'"
              :sub-title="`相似度评分: ${compareResult.similarity_score} 分 (余弦值: ${compareResult.cosine})`"
            />
          </div>
        </el-card>
      </el-col>

      <!-- 1:N 检索测试 -->
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>人脸 1:N 底库全量搜索</span>
              <el-tag type="warning">底库快速鉴权</el-tag>
            </div>
          </template>

          <div class="file-box">
            <p>查询输入照片</p>
            <input type="file" accept="image/*" @change="onSearchFileChange" />
          </div>

          <div style="margin-top: 16px;">
            <span>相似度门限: </span>
            <el-slider v-model="searchThreshold" :min="50" :max="95" show-input />
          </div>

          <el-button
            type="success"
            style="margin-top: 16px; width: 100%;"
            :loading="searching"
            @click="runSearch"
          >
            在底库中执行 1:N 检索
          </el-button>

          <div v-if="searchResults" style="margin-top: 20px;">
            <p style="font-weight: 600;">Top 匹配结果：</p>
            <el-table :data="searchResults" border size="small">
              <el-table-column prop="person_no" label="工号" width="100" />
              <el-table-column prop="name" label="姓名" width="100" />
              <el-table-column prop="department" label="部门" />
              <el-table-column prop="score" label="相似度得分">
                <template #default="{ row }">
                  <el-tag type="success">{{ row.score.toFixed(1) }}</el-tag>
                </template>
              </el-table-column>
            </el-table>
            <p v-if="!searchResults.length" style="color: #9ca3af; text-align: center; margin-top: 10px;">
              未命中达到阈值的人员（查无此人/陌生人）
            </p>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const file1 = ref<File | null>(null)
const file2 = ref<File | null>(null)
const searchFile = ref<File | null>(null)
const comparing = ref(false)
const searching = ref(false)
const searchThreshold = ref(70)
const compareResult = ref<any>(null)
const searchResults = ref<any>(null)

const onFile1Change = (e: any) => {
  file1.value = e.target.files[0]
}
const onFile2Change = (e: any) => {
  file2.value = e.target.files[0]
}
const onSearchFileChange = (e: any) => {
  searchFile.value = e.target.files[0]
}

const runCompare = async () => {
  if (!file1.value || !file2.value) {
    ElMessage.warning('请选择两张照片进行比对')
    return
  }
  comparing.value = true
  const fd = new FormData()
  fd.append('file1', file1.value)
  fd.append('file2', file2.value)
  try {
    compareResult.value = await api.post('/recognize/compare', fd)
  } finally {
    comparing.value = false
  }
}

const runSearch = async () => {
  if (!searchFile.value) {
    ElMessage.warning('请选择待检索人脸照片')
    return
  }
  searching.value = true
  const fd = new FormData()
  fd.append('file', searchFile.value)
  fd.append('threshold', searchThreshold.value.toString())
  try {
    searchResults.value = await api.post('/recognize/search', fd)
  } finally {
    searching.value = false
  }
}
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.compare-inputs {
  display: flex;
  gap: 16px;
}
.file-box {
  flex: 1;
  background-color: #f9fafb;
  padding: 12px;
  border-radius: 6px;
  border: 1px dashed #d1d5db;
}
.file-box p {
  margin: 0 0 8px 0;
  font-weight: 500;
  color: #374151;
}
.result-box {
  margin-top: 16px;
}
</style>

