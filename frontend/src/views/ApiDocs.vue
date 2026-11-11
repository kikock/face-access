<template>
  <div class="api-docs-view">
    <el-card shadow="never">
      <div class="header-info">
        <h2>人脸识别服务平台 - 开放 API 接口调用指南</h2>
        <p>提供标准的 RESTful HTTP 接口、全双工 WebSocket 推送以及详尽的高并发性能基准说明，便于第三方考勤、门禁、安防系统与智能硬件快速对接集成。</p>
      </div>

      <el-tabs v-model="activeTab" style="margin-top: 20px;">
        <!-- 概览与通用规范 -->
        <el-tab-pane label="接口规范与鉴权" name="overview">
          <el-descriptions title="通用调用环境" :column="2" border>
            <el-descriptions-item label="服务基准地址">http://localhost:8000/api/v1</el-descriptions-item>
            <el-descriptions-item label="数据交互格式">JSON / multipart/form-data</el-descriptions-item>
            <el-descriptions-item label="在线 Swagger 调试">
              <el-link type="primary" href="http://localhost:8000/docs" target="_blank">
                打开 Swagger UI (/docs)
              </el-link>
            </el-descriptions-item>
            <el-descriptions-item label="在线 ReDoc">
              <el-link type="primary" href="http://localhost:8000/redoc" target="_blank">
                打开 ReDoc (/redoc)
              </el-link>
            </el-descriptions-item>
          </el-descriptions>

          <div class="section-box">
            <h3>鉴权方式</h3>
            <p>管理与档案维护类接口需在 HTTP 请求头携带 Bearer Token：</p>
            <pre><code>Authorization: Bearer &lt;access_token&gt;</code></pre>
            <p>调用 <code>POST /api/v1/auth/login</code> 获取 Token，默认初始管理账号为 <code>admin / admin123456</code>。</p>
          </div>
        </el-tab-pane>

        <!-- 并发性能与规格说明（新增） -->
        <el-tab-pane label="系统并发性能指标说明" name="performance">
          <div class="perf-header">
            <h3>人脸识别并发能力与吞吐量基准</h3>
            <p style="color: #6b7280; font-size: 13px;">本数据由平台内置基准测试脚本在 10,000 人脸特征底库规模下实测得出，包含 x86 CPU 与 RK3588 NPU 双架构对比。</p>
          </div>

          <el-descriptions :column="2" border style="margin-top: 16px;">
            <el-descriptions-item label="10,000 底库纯向量检索耗时">
              <el-tag type="success" effect="dark">0.22 毫秒 / 次</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="1:N 纯特征点积理论 QPS">
              <el-tag type="success">4,400,000+ QPS</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="x86 (CPU 推理) 单路端到端耗时">约 80 ~ 300 ms (取决于 CPU 核心数与图像尺寸)</el-descriptions-item>
            <el-descriptions-item label="x86 (CPU 推理) 推荐并发并发路数">1 ~ 4 路实时视频流</el-descriptions-item>
            <el-descriptions-item label="RK3588 (NPU 6TOPS) 单张端到端耗时">
              <el-tag type="primary">15 ~ 35 毫秒 (INT8 量化)</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="RK3588 (NPU 6TOPS) 推荐并发路数">
              <el-tag type="primary">4 ~ 8 路 1080P 实时视频并发抓拍</el-tag>
            </el-descriptions-item>
          </el-descriptions>

          <div class="section-box">
            <h4>并发瓶颈与优化建议</h4>
            <el-timeline style="margin-top: 16px;">
              <el-timeline-item timestamp="阶段一：图像解码与目标检测 (SSD)" type="warning">
                耗时约占 25%~30%。大分辨率图片建议前端或边缘抓拍机提前 Resize 缩放至 640x480 以内再上传，可降低 60% 解码耗时。
              </el-timeline-item>
              <el-timeline-item timestamp="阶段二：IRN50 特征向量提取 (50层残差)" type="danger">
                计算瓶颈所在，耗时约占 60%~70%。在 x86 CPU 上单次计算需数十毫秒；迁移至 <strong>RK3588 NPU</strong> 后将通过硬件加速压降至 15ms 以内，性能提升 6~10 倍。
              </el-timeline-item>
              <el-timeline-item timestamp="阶段三：1:N 向量底库相似度检索" type="success">
                耗时仅 <strong>0.22ms</strong>（1 万人脸特征在连续内存矩阵内做点积乘法，读写锁隔离），完全不会构成并发瓶颈。即使底库扩展至 5 万人，检索延迟仍在 1ms 以内。
              </el-timeline-item>
            </el-timeline>
          </div>
        </el-tab-pane>

        <!-- 核心识别接口 -->
        <el-tab-pane label="人脸识别与比对" name="recognition">
          <div class="api-item">
            <el-tag type="success" effect="dark">POST</el-tag>
            <span class="api-path">/api/v1/recognize/search</span>
            <span class="api-desc">1:N 底库快速检索（单图查人）</span>
          </div>
          <p><strong>功能：</strong>上传待识别照片，系统自动检测人脸、质量评估，并在 1 万人脸底库中执行高并发余弦相似度检索，返回 Top-K 命中人员及得分。</p>
          <div class="code-block">
            <strong>cURL 示例：</strong>
            <pre><code>curl -X POST "http://localhost:8000/api/v1/recognize/search" \
  -F "file=@capture.jpg" \
  -F "threshold=75.0" \
  -F "top_k=3"</code></pre>
          </div>
          <div class="code-block">
            <strong>响应示例：</strong>
            <pre><code>[
  {
    "person_id": 101,
    "person_no": "P1001",
    "name": "张工",
    "department": "研发部",
    "score": 84.65,
    "cosine": 0.693
  }
]</code></pre>
          </div>

          <el-divider />

          <div class="api-item">
            <el-tag type="success" effect="dark">POST</el-tag>
            <span class="api-path">/api/v1/recognize/compare</span>
            <span class="api-desc">1:1 双人人脸两两比对</span>
          </div>
          <p><strong>功能：</strong>输入两张照片，比对两张人脸是否属于同一人，返回相似度评分（0~100）。</p>
          <div class="code-block">
            <strong>cURL 示例：</strong>
            <pre><code>curl -X POST "http://localhost:8000/api/v1/recognize/compare" \
  -F "file1=@photoA.jpg" \
  -F "file2=@photoB.jpg"</code></pre>
          </div>
        </el-tab-pane>

        <!-- 人员底库接口 -->
        <el-tab-pane label="底库档案与人脸录入" name="persons">
          <el-table :data="personApis" border size="small">
            <el-table-column prop="method" label="请求方式" width="100">
              <template #default="{ row }">
                <el-tag :type="row.method === 'GET' ? 'primary' : (row.method === 'POST' ? 'success' : 'danger')">
                  {{ row.method }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="path" label="接口路径" width="280" />
            <el-table-column prop="desc" label="功能说明" />
          </el-table>

          <div class="code-block" style="margin-top: 16px;">
            <strong>人脸录入与追加接口说明（POST /api/v1/persons/{id}/faces）：</strong>
            <pre><code>curl -X POST "http://localhost:8000/api/v1/persons/1/faces" \
  -H "Authorization: Bearer &lt;token&gt;" \
  -F "file=@person_face.jpg"</code></pre>
            <p>系统自动进行人脸尺寸检测（≥60px）、偏航/俯仰角度质检（≤40°）、模糊度检测与特征提取，并自动动态注册进内存检索底库，支持同一个人追加多张照片。</p>
          </div>
        </el-tab-pane>

        <!-- WebSocket 实时事件 -->
        <el-tab-pane label="WebSocket 实时事件推送" name="websocket">
          <div class="api-item">
            <el-tag type="warning" effect="dark">WS</el-tag>
            <span class="api-path">/ws/events</span>
            <span class="api-desc">实时通行与识别抓拍事件流</span>
          </div>
          <p>客户端建立 WebSocket 长连接，当有现场视频抓拍识别成功时，服务端会即时广播推送事件载荷：</p>
          <div class="code-block">
            <strong>推送 JSON 格式：</strong>
            <pre><code>{
  "type": "access_event",
  "event_id": 1052,
  "device_id": 1,
  "person_id": 101,
  "person_name": "张工",
  "person_no": "P1001",
  "score": 86.2,
  "snapshot": "snap_dev1_171000000.jpg",
  "time": "2026-11-10 10:30:15"
}</code></pre>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const activeTab = ref('overview')

const personApis = [
  { method: 'GET', path: '/api/v1/persons', desc: '查询人员列表与名下所有人脸照片' },
  { method: 'POST', path: '/api/v1/persons', desc: '新增人员档案（工号、姓名、部门）' },
  { method: 'DELETE', path: '/api/v1/persons/{id}', desc: '删除人员及其名下所有人脸特征' },
  { method: 'POST', path: '/api/v1/persons/{id}/faces', desc: '上传追加人脸照片并生成特征向量（支持单人多照）' },
  { method: 'DELETE', path: '/api/v1/faces/{face_id}', desc: '删除单张人脸照片记录' },
]
</script>

<style scoped>
.header-info h2 {
  margin: 0;
  color: #1f2937;
}
.header-info p {
  color: #6b7280;
  margin-top: 8px;
}
.section-box {
  margin-top: 20px;
}
.api-item {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.api-path {
  font-family: monospace;
  font-size: 16px;
  font-weight: bold;
}
.api-desc {
  color: #6b7280;
}
.code-block {
  background-color: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px;
  margin-top: 10px;
}
.code-block pre {
  margin: 8px 0 0 0;
  font-family: Consolas, Monaco, "Courier New", monospace;
  font-size: 13px;
  color: #374151;
}
</style>
