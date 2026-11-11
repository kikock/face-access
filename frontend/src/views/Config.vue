<template>
  <div class="config-view">
    <el-tabs v-model="activeTab">
      <!-- 识别算法与质检门限 -->
      <el-tab-pane label="算法与质检参数" name="algorithm">
        <el-card shadow="never">
          <div class="card-desc">配置人脸检测灵敏度、比对通过阈值、活体眨眼防伪及照片质量过滤标准，修改后即时热生效，无需重启服务。</div>

          <el-form :model="form" label-width="180px" style="max-width: 720px; margin-top: 20px;">
            <el-divider content-position="left">识别与命中决策</el-divider>
            <el-form-item label="默认比对通过阈值">
              <el-slider v-model="form.default_recog_threshold" :min="50" :max="95" show-input />
              <span class="field-hint">对应余弦相似度换算分 (0~100)。推荐 75.0 分（对应原模型余弦 0.50）。</span>
            </el-form-item>
            <el-form-item label="连续确认命中帧数">
              <el-input-number v-model="form.default_continuous_frames" :min="1" :max="10" />
              <span class="field-hint">连续 N 帧识别同一人且活体通过方可判定命中，抗误识别抖动。</span>
            </el-form-item>
            <el-form-item label="同人防重复识别冷却 (秒)">
              <el-input-number v-model="form.person_cooldown_seconds" :min="1" :max="60" />
              <span class="field-hint">同一人员识别成功后在此时间内不再重复产生高频抓拍事件。</span>
            </el-form-item>

            <el-divider content-position="left">人脸检测与活体防伪</el-divider>
            <el-form-item label="目标检测置信度阈值">
              <el-slider v-model="form.det_threshold" :min="0.3" :max="0.9" :step="0.05" show-input />
              <span class="field-hint">人脸定位正类分数门限，值越高漏检率上升但误检率下降。</span>
            </el-form-item>
            <el-form-item label="NMS 重叠抑制 IoU">
              <el-slider v-model="form.nms_iou_threshold" :min="0.1" :max="0.6" :step="0.05" show-input />
            </el-form-item>
            <el-form-item label="静默单目活体总开关">
              <el-switch
                v-model="form.liveness_silent_enabled"
                active-text="已开启 (防照片/屏幕翻拍)"
                inactive-text="已关闭"
              />
              <span class="field-hint">关闭后将跳过 MiniFASNetV2 静默单目防伪校验，仅执行人脸识别或眨眼检测。</span>
            </el-form-item>
            <el-form-item label="活体校验策略模式">
              <el-select v-model="form.liveness_mode" style="width: 280px;">
                <el-option label="静默单目活体 (无感秒过，推荐)" value="silent" />
                <el-option label="动作眨眼活体 (EAR 闭眼/睁眼)" value="blink" />
                <el-option label="静默 + 眨眼双重校验 (最高安全)" value="both" />
              </el-select>
            </el-form-item>
            <el-form-item label="静默活体通过阈值">
              <el-slider v-model="form.liveness_silent_threshold" :min="0.5" :max="0.98" :step="0.02" show-input />
              <span class="field-hint">真人概率得分高于此阈值方判定为真实活体，默认 0.80。</span>
            </el-form-item>
            <el-form-item label="活体闭眼 EAR 门限">
              <el-slider v-model="form.liveness_ear_threshold" :min="0.15" :max="0.30" :step="0.01" show-input />
              <span class="field-hint">眼部纵横比 EAR 小于此值认定为闭眼瞬间，默认 0.22。</span>
            </el-form-item>

            <el-divider content-position="left">人脸照片入库质检门限</el-divider>
            <el-form-item label="最小人脸分辨率 (像素)">
              <el-input-number v-model="form.min_face_size" :min="40" :max="200" :step="10" />
              <span class="field-hint">入库照片人脸宽/高小于该像素时自动拦截，保障底库质量。</span>
            </el-form-item>
            <el-form-item label="最大允许偏航角 (Yaw)">
              <el-input-number v-model="form.max_yaw" :min="15" :max="60" />
              <span class="field-hint">绝对值超过此角度 (度) 的侧脸照片将被自动拒绝。</span>
            </el-form-item>
            <el-form-item label="最大允许俯仰角 (Pitch)">
              <el-input-number v-model="form.max_pitch" :min="15" :max="60" />
              <span class="field-hint">绝对值超过此角度的仰头或低头照片将被拦截。</span>
            </el-form-item>
            <el-form-item label="最小清晰度指标 (Laplacian)">
              <el-input-number v-model="form.min_blur_score" :min="10" :max="100" />
              <span class="field-hint">图像拉普拉斯方差小于此值认定为模糊，默认 30.0。</span>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="saving" @click="saveSettings">
                保存并即时热生效
              </el-button>
              <el-button @click="loadSettings">重置为当前服务端值</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- 模型版本与在线升级 -->
      <el-tab-pane label="模型版本与热升级" name="model_upgrade">
        <el-card shadow="never">
          <div class="card-desc">查看当前加载的各级神经网络架构与哈希指纹，并支持在线上传替换新版 ONNX 模型权重。</div>

          <el-descriptions title="当前部署模型清单" :column="2" border style="margin-top: 16px;">
            <el-descriptions-item label="主模型版本标识">
              <el-tag type="success">{{ modelInfo.model_version || 'fp-irn50-v1' }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="ONNX Opset 兼容标准">Opset {{ modelInfo.opset || 13 }}</el-descriptions-item>
            <el-descriptions-item label="目标人脸检测器">detector.onnx (SSD-Slim 320)</el-descriptions-item>
            <el-descriptions-item label="关键点解算器">landmark.onnx (MobileFaceNet 68点)</el-descriptions-item>
            <el-descriptions-item label="特征向量提取器">feature.onnx (IRN50 256维)</el-descriptions-item>
            <el-descriptions-item label="静默活体防伪器">liveness.onnx (MiniFASNetV2 80x80)</el-descriptions-item>
            <el-descriptions-item label="推理硬件驱动">{{ systemStatus.inference_engine || 'ONNX Runtime (CPU)' }}</el-descriptions-item>
          </el-descriptions>

          <div style="margin-top: 30px;">
            <h3>在线模型热升级</h3>
            <el-alert
              title="特别提醒：若上传升级【人脸特征提取模型 (feature.onnx)】，系统在加载新模型后将自动将底库中所有人员照片全量重新提取特征并刷新内存检索库，以确保向量空间对齐。"
              type="warning"
              show-icon
              :closable="false"
              style="margin-bottom: 16px;"
            />

            <el-form label-width="140px" style="max-width: 600px;">
              <el-form-item label="升级目标网络" required>
                <el-select v-model="upgradeType">
                  <el-option label="特征提取模型 (feature.onnx)" value="feature" />
                  <el-option label="目标检测模型 (detector.onnx)" value="detector" />
                  <el-option label="关键点模型 (landmark.onnx)" value="landmark" />
                  <el-option label="静默活体模型 (liveness.onnx)" value="liveness" />
                </el-select>
              </el-form-item>
              <el-form-item label="新模型版本号">
                <el-input v-model="newModelVersion" placeholder="例如：fp-irn50-v2" />
              </el-form-item>
              <el-form-item label="新 ONNX 文件" required>
                <input type="file" accept=".onnx" @change="onModelFileChange" />
              </el-form-item>
              <el-form-item>
                <el-button type="danger" :loading="upgrading" @click="submitUpgrade">
                  开始验证并上传升级
                </el-button>
              </el-form-item>
            </el-form>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

const activeTab = ref('algorithm')
const saving = ref(false)
const upgrading = ref(false)

const form = reactive({
  det_threshold: 0.6,
  nms_iou_threshold: 0.3,
  default_recog_threshold: 75.0,
  default_continuous_frames: 3,
  liveness_ear_threshold: 0.22,
  liveness_silent_enabled: true,
  liveness_silent_threshold: 0.80,
  liveness_mode: 'silent',
  min_face_size: 60,
  max_yaw: 40.0,
  max_pitch: 35.0,
  max_roll: 35.0,
  min_blur_score: 30.0,
  person_cooldown_seconds: 5,
})

const modelInfo = ref<any>({})
const systemStatus = ref<any>({})
const upgradeType = ref('feature')
const newModelVersion = ref('')
const selectedModelFile = ref<File | null>(null)

const loadSettings = async () => {
  const data: any = await api.get('/settings/recognition')
  Object.assign(form, data)
}

const loadModelInfo = async () => {
  modelInfo.value = await api.get('/models/info')
  systemStatus.value = await api.get('/system/status')
}

const saveSettings = async () => {
  saving.value = true
  try {
    await api.put('/settings/recognition', form)
    window.dispatchEvent(new CustomEvent('system-status-updated'))
    ElMessage.success('配置已保存并即时热生效')
  } finally {
    saving.value = false
  }
}

const onModelFileChange = (e: any) => {
  selectedModelFile.value = e.target.files[0]
}

const submitUpgrade = async () => {
  if (!selectedModelFile.value) {
    ElMessage.warning('请选择需要上传的 .onnx 模型文件')
    return
  }
  await ElMessageBox.confirm(
    `确定上传并热升级模型 [${upgradeType.value}] 吗？系统将自动重载推理引擎。`,
    '模型升级确认',
    {
      confirmButtonText: '确定升级',
      cancelButtonText: '取消',
      type: 'warning',
    }
  )

  upgrading.value = true
  const fd = new FormData()
  fd.append('model_type', upgradeType.value)
  fd.append('model_version', newModelVersion.value)
  fd.append('file', selectedModelFile.value)

  try {
    const res: any = await api.post('/models/upgrade', fd)
    ElMessage.success(
      `${res.message}！` + (res.reindexed_faces ? `（底库已自动重新提取 ${res.reindexed_faces} 张特征）` : '')
    )
    loadModelInfo()
  } finally {
    upgrading.value = false
  }
}

onMounted(() => {
  loadSettings()
  loadModelInfo()
})
</script>

<style scoped>
.card-desc {
  color: #6b7280;
  font-size: 13px;
  margin-bottom: 12px;
}
.field-hint {
  display: block;
  font-size: 12px;
  color: #9ca3af;
  line-height: 1.4;
  margin-top: 4px;
}
</style>

