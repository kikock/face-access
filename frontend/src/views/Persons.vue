<template>
  <div class="persons-view">
    <el-card shadow="never">
      <div class="toolbar">
        <el-input
          v-model="searchQuery"
          placeholder="按姓名或工号搜索..."
          prefix-icon="Search"
          style="width: 240px;"
          clearable
        />
        <div class="toolbar-actions">
          <el-button type="success" plain icon="DocumentAdd" @click="openBatchInfoDialog">
            批量导入信息 (CSV)
          </el-button>
          <el-button type="warning" plain icon="Upload" @click="openBatchFacesDialog">
            批量上传人脸照片
          </el-button>
          <el-button type="primary" icon="Plus" @click="openCreateDialog">
            新增人员
          </el-button>
        </div>
      </div>

      <el-table :data="filteredPersons" style="width: 100%; margin-top: 20px;">
        <el-table-column prop="person_no" label="工号/学号" width="140" />
        <el-table-column prop="name" label="姓名" width="140" />
        <el-table-column prop="department" label="部门/班级" width="160" />
        <el-table-column prop="phone" label="联系电话" width="140" />
        <el-table-column label="人脸照片 (支持多张)" min-width="260">
          <template #default="{ row }">
            <div class="face-thumbs">
              <div
                v-for="face in row.faces"
                :key="face.id"
                class="face-item"
              >
                <el-avatar
                  :src="`/api/v1/uploads/${face.image_path}`"
                  shape="square"
                  :size="48"
                />
                <el-icon
                  class="delete-face-btn"
                  title="删除该张人脸照片"
                  @click.stop="handleDeleteFace(face.id)"
                >
                  <CircleCloseFilled />
                </el-icon>
              </div>
              <span v-if="!row.faces.length" class="no-face">暂无人脸</span>
              <el-tag size="small" type="info" style="margin-left: 8px;">
                共 {{ row.faces.length }} 张
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="enabled" label="启用状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'danger'">
              {{ row.enabled ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openUploadFace(row)">
              + 添加人脸照片
            </el-button>
            <el-button size="small" type="warning" link @click="openEditDialog(row)">
              编辑
            </el-button>
            <el-popconfirm title="确定彻底删除该人员及其所有人脸特征吗？" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button size="small" type="danger" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑人员弹窗 -->
    <el-dialog v-model="createVisible" :title="editingPersonId ? '编辑人员档案' : '新增人员档案'" width="500px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="工号/学号" required>
          <el-input v-model="form.person_no" :disabled="Boolean(editingPersonId)" placeholder="唯一标识，例如 P1001" />
        </el-form-item>
        <el-form-item label="姓名" required>
          <el-input v-model="form.name" placeholder="人员姓名" />
        </el-form-item>
        <el-form-item label="部门/组织">
          <el-input v-model="form.department" placeholder="所属部门" />
        </el-form-item>
        <el-form-item label="联系电话">
          <el-input v-model="form.phone" placeholder="电话号码" />
        </el-form-item>
        <el-form-item v-if="editingPersonId" label="启用状态">
          <el-switch v-model="form.enabled" active-text="允许通行" inactive-text="已禁用" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="可选备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">{{ editingPersonId ? '保存修改' : '确认保存' }}</el-button>
      </template>
    </el-dialog>

    <!-- 单张添加人脸弹窗 -->
    <el-dialog
      v-model="uploadVisible"
      :title="`添加人脸照片 - ${currentPerson?.name}`"
      width="460px"
      @closed="resetSingleUpload"
    >
      <div style="margin-bottom: 12px; color: #6b7280; font-size: 13px;">
        提示：支持同一人员登记多张不同角度（如正脸、微仰、微侧）或不同光照下的照片，系统将自动融合特征比对，提高识别通过率。
      </div>
      <el-upload
        ref="singleUploadRef"
        drag
        action=""
        :auto-upload="false"
        :on-change="handleFileChange"
        :on-remove="handleSingleRemove"
        :limit="1"
        accept="image/*"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">将清晰单人人脸图片拖至此处，或<em>点击上传</em></div>
      </el-upload>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitUpload">
          开始检测并追加照片
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量导入人员基本信息 (CSV) 弹窗 -->
    <el-dialog
      v-model="batchInfoVisible"
      title="批量导入人员基本信息 (CSV)"
      width="560px"
      @closed="resetBatchInfo"
    >
      <el-alert
        title="信息与照片分离导入：请先上传 CSV 表格建立人员档案，再通过“批量上传人脸照片”按工号自动关联照片。"
        type="info"
        show-icon
        :closable="false"
        style="margin-bottom: 14px;"
      />
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 13px; color: #4b5563;">支持 UTF-8 / GBK 编码 CSV，若工号已存在将自动更新对应信息。</span>
        <el-button size="small" type="primary" plain @click="downloadTemplate">下载标准 CSV 模板</el-button>
      </div>
      <el-upload
        ref="batchInfoUploadRef"
        drag
        action=""
        :auto-upload="false"
        :on-change="handleBatchInfoChange"
        :on-remove="() => (batchInfoFile = null)"
        :limit="1"
        accept=".csv"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">将人员信息 .csv 文件拖至此处，或<em>点击选择</em></div>
      </el-upload>

      <div v-if="batchInfoResult" style="margin-top: 14px;">
        <el-alert :title="batchInfoResult.message" type="success" show-icon :closable="false" />
        <div v-if="batchInfoResult.errors?.length" style="margin-top: 8px; max-height: 120px; overflow-y: auto; font-size: 12px; color: #b45309;">
          <div v-for="(err, idx) in batchInfoResult.errors" :key="idx">{{ err }}</div>
        </div>
      </div>

      <template #footer>
        <el-button @click="batchInfoVisible = false">关闭</el-button>
        <el-button type="primary" :loading="batchInfoLoading" @click="submitBatchInfo">
          开始导入人员信息
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量上传人脸照片 (多图 / ZIP) 弹窗 -->
    <el-dialog
      v-model="batchFacesVisible"
      title="批量上传人脸照片 (多图 / ZIP 压缩包)"
      width="680px"
      @closed="resetBatchFaces"
    >
      <el-alert
        title="命名匹配规则：请将照片命名为【工号.jpg】或【工号_1.jpg】（如 P1001.jpg、P1001_侧脸.png），无重名时亦可直接用【姓名.jpg】。支持多选图片或直接上传 .zip 压缩包！"
        type="warning"
        show-icon
        :closable="false"
        style="margin-bottom: 14px;"
      />
      <el-upload
        ref="batchFacesUploadRef"
        drag
        multiple
        action=""
        :auto-upload="false"
        :on-change="handleBatchFacesChange"
        :on-remove="handleBatchFacesRemove"
        accept="image/*,.zip"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">拖入多张人脸照片或 .zip 压缩包，或<em>点击多选上传</em></div>
      </el-upload>

      <div v-if="batchFacesResult" style="margin-top: 16px;">
        <div style="margin-bottom: 8px; font-weight: 600;">
          处理完成：总计 {{ batchFacesResult.total }} 张 |
          <span style="color: #16a34a;">成功入库 {{ batchFacesResult.success_count }} 张</span> |
          <span style="color: #dc2626;">失败 {{ batchFacesResult.failed_count }} 张</span>
        </div>
        <el-table :data="batchFacesResult.results" border size="small" max-height="240">
          <el-table-column prop="filename" label="文件名" min-width="140" show-overflow-tooltip />
          <el-table-column prop="matched_person" label="匹配人员" width="130" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
                {{ row.status === 'success' ? '成功' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="quality_score" label="质量分" width="75" />
          <el-table-column prop="reason" label="详情说明" min-width="160" show-overflow-tooltip />
        </el-table>
      </div>

      <template #footer>
        <el-button @click="batchFacesVisible = false">关闭</el-button>
        <el-button type="primary" :loading="batchFacesLoading" @click="submitBatchFaces">
          开始批量检测并入库
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

const persons = ref<any[]>([])
const searchQuery = ref('')
const createVisible = ref(false)
const uploadVisible = ref(false)
const uploading = ref(false)
const currentPerson = ref<any>(null)
const selectedFile = ref<any>(null)
const editingPersonId = ref<number | null>(null)
const singleUploadRef = ref<any>(null)

// 批量导入信息状态
const batchInfoVisible = ref(false)
const batchInfoLoading = ref(false)
const batchInfoFile = ref<File | null>(null)
const batchInfoResult = ref<any>(null)
const batchInfoUploadRef = ref<any>(null)

// 批量上传照片状态
const batchFacesVisible = ref(false)
const batchFacesLoading = ref(false)
const batchFaceFiles = ref<any[]>([])
const batchFacesResult = ref<any>(null)
const batchFacesUploadRef = ref<any>(null)

const form = reactive({
  person_no: '',
  name: '',
  department: '',
  phone: '',
  enabled: true,
  remark: '',
})

const filteredPersons = computed(() => {
  if (!searchQuery.value) return persons.value
  const q = searchQuery.value.toLowerCase()
  return persons.value.filter(
    (p) => p.name.toLowerCase().includes(q) || p.person_no.toLowerCase().includes(q)
  )
})

const loadPersons = async () => {
  persons.value = await api.get('/persons')
}

const openCreateDialog = () => {
  editingPersonId.value = null
  Object.assign(form, { person_no: '', name: '', department: '', phone: '', enabled: true, remark: '' })
  createVisible.value = true
}

const openEditDialog = (row: any) => {
  editingPersonId.value = row.id
  Object.assign(form, {
    person_no: row.person_no,
    name: row.name,
    department: row.department || '',
    phone: row.phone || '',
    enabled: row.enabled,
    remark: row.remark || '',
  })
  createVisible.value = true
}

const submitCreate = async () => {
  if (!form.person_no || !form.name) {
    ElMessage.warning('工号和姓名不能为空')
    return
  }
  if (editingPersonId.value) {
    await api.put(`/persons/${editingPersonId.value}`, {
      name: form.name,
      department: form.department,
      phone: form.phone,
      enabled: form.enabled,
      remark: form.remark,
    })
    ElMessage.success('人员信息修改成功')
  } else {
    await api.post('/persons', {
      person_no: form.person_no,
      name: form.name,
      department: form.department,
      phone: form.phone,
      remark: form.remark,
    })
    ElMessage.success('人员创建成功')
  }
  createVisible.value = false
  loadPersons()
}

const handleDelete = async (id: number) => {
  await api.delete(`/persons/${id}`)
  ElMessage.success('删除成功')
  loadPersons()
}

const handleDeleteFace = async (faceId: number) => {
  try {
    await ElMessageBox.confirm('确定删除该张人脸照片记录吗？', '确认操作', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await api.delete(`/faces/${faceId}`)
    ElMessage.success('人脸照片已删除')
    loadPersons()
  } catch {}
}

// --- 单张添加人脸照片 (彻底解决二次打开残留) ---
const resetSingleUpload = () => {
  selectedFile.value = null
  singleUploadRef.value?.clearFiles()
}

const openUploadFace = async (row: any) => {
  currentPerson.value = row
  selectedFile.value = null
  uploadVisible.value = true
  await nextTick()
  singleUploadRef.value?.clearFiles()
}

const handleFileChange = (file: any) => {
  selectedFile.value = file.raw
}

const handleSingleRemove = () => {
  selectedFile.value = null
}

const submitUpload = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('请选择要上传的人脸照片')
    return
  }
  uploading.value = true
  const formData = new FormData()
  formData.append('file', selectedFile.value)
  try {
    const res: any = await api.post(`/persons/${currentPerson.value.id}/faces`, formData)
    ElMessage.success(`人脸照片追加成功 (质量分: ${res.quality_score.toFixed(1)})`)
    uploadVisible.value = false
    resetSingleUpload()
    loadPersons()
  } finally {
    uploading.value = false
  }
}

// --- 批量导入人员信息 (CSV) ---
const resetBatchInfo = () => {
  batchInfoFile.value = null
  batchInfoUploadRef.value?.clearFiles()
}

const openBatchInfoDialog = async () => {
  batchInfoFile.value = null
  batchInfoResult.value = null
  batchInfoVisible.value = true
  await nextTick()
  batchInfoUploadRef.value?.clearFiles()
}

const handleBatchInfoChange = (file: any) => {
  batchInfoFile.value = file.raw
}

const downloadTemplate = () => {
  window.open('/api/v1/persons/batch-template', '_blank')
}

const submitBatchInfo = async () => {
  if (!batchInfoFile.value) {
    ElMessage.warning('请先选择 .csv 人员信息文件')
    return
  }
  batchInfoLoading.value = true
  const fd = new FormData()
  fd.append('file', batchInfoFile.value)
  try {
    const res: any = await api.post('/persons/batch-info', fd)
    batchInfoResult.value = res
    ElMessage.success(res.message)
    loadPersons()
  } finally {
    batchInfoLoading.value = false
  }
}

// --- 批量上传人脸照片 (多图 / ZIP) ---
const resetBatchFaces = () => {
  batchFaceFiles.value = []
  batchFacesUploadRef.value?.clearFiles()
}

const openBatchFacesDialog = async () => {
  batchFaceFiles.value = []
  batchFacesResult.value = null
  batchFacesVisible.value = true
  await nextTick()
  batchFacesUploadRef.value?.clearFiles()
}

const handleBatchFacesChange = (_file: any, fileList: any[]) => {
  batchFaceFiles.value = fileList
}

const handleBatchFacesRemove = (_file: any, fileList: any[]) => {
  batchFaceFiles.value = fileList
}

const submitBatchFaces = async () => {
  if (!batchFaceFiles.value.length) {
    ElMessage.warning('请先选择至少一张人脸照片或 .zip 压缩包')
    return
  }
  batchFacesLoading.value = true
  const fd = new FormData()
  for (const item of batchFaceFiles.value) {
    if (item.raw) {
      fd.append('files', item.raw)
    }
  }
  try {
    const res: any = await api.post('/persons/batch-faces', fd)
    batchFacesResult.value = res
    ElMessage.success(`批量入库完成: 成功 ${res.success_count} 张，失败 ${res.failed_count} 张`)
    loadPersons()
  } finally {
    batchFacesLoading.value = false
  }
}

onMounted(() => {
  loadPersons()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.toolbar-actions {
  display: flex;
  gap: 10px;
}
.face-thumbs {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.face-item {
  position: relative;
  display: inline-block;
}
.delete-face-btn {
  position: absolute;
  top: -6px;
  right: -6px;
  cursor: pointer;
  color: #f56c6c;
  background-color: #fff;
  border-radius: 50%;
  font-size: 16px;
  display: none;
}
.face-item:hover .delete-face-btn {
  display: block;
}
.no-face {
  color: #9ca3af;
  font-size: 13px;
}
</style>
