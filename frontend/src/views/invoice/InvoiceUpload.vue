<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">发票上传</h1>
    </div>
    
    <el-card>
      <el-row :gutter="20" class="upload-grid">
        <el-col :xs="24" :md="14" class="upload-col">
          <el-upload
              ref="uploadRef"
              class="upload-surface"
              drag
              multiple
              :action="uploadUrl"
              :headers="uploadHeaders"
              :before-upload="beforeUpload"
              :on-progress="handleProgress"
              :on-success="handleSuccess"
              :on-error="handleError"
              :show-file-list="false"
              :disabled="uploadDisabled"
              accept=".pdf"
            >
              <el-icon class="el-icon--upload">
                <upload-filled />
              </el-icon>
              <div class="el-upload__text">
                将一个或多个 PDF 文件拖到此处，或<em> 点击上传</em>
                <div class="el-upload__tip upload-tips">
                  <el-tag size="small" effect="light">PDF</el-tag>
                  <el-tag size="small" effect="light">可多选</el-tag>
                  <el-tag size="small" effect="light">≤ 10MB</el-tag>
                  <el-tag size="small" effect="light">推荐单页</el-tag>
                </div>
              </div>
          </el-upload>
          <div v-if="uploadStats.total" class="upload-summary">
            <span>本次 {{ uploadStats.total }} 个</span>
            <span>成功 {{ uploadStats.success }} 个</span>
            <span v-if="uploadStats.duplicate">重复 {{ uploadStats.duplicate }} 个</span>
            <span>失败 {{ uploadStats.failed }} 个</span>
            <span v-if="activeUploadCount">上传中 {{ activeUploadCount }} 个</span>
          </div>
        </el-col>
        <el-col :xs="24" :md="10" class="guides-col">
          <div class="guides-pane">
            <div class="guides-card">
              <div class="guides-title">上传须知</div>
              <ul class="guides-list">
                <li>仅支持 PDF 格式，单个文件大小不超过 10MB。</li>
                <li>建议上传清晰、完整的单页发票，以提升识别准确率。</li>
                <li>上传后系统会自动启动 OCR 识别，识别完成后可在列表中查看。</li>
              </ul>
            </div>

            <div v-if="uploadedFiles.length > 0" class="recent-card">
              <div class="guides-title">上传记录</div>
              <div class="upload-list">
                <div
                  v-for="file in uploadedFiles"
                  :key="file.uid"
                  class="upload-item"
                >
                  <div class="file-info">
                    <el-icon><Document /></el-icon>
                    <div class="file-text">
                      <span class="filename">{{ file.filename }}</span>
                      <span v-if="file.message" class="file-message">{{ file.message }}</span>
                    </div>
                  </div>
                  <div class="file-status">
                    <el-tag :type="getStatusType(file.status)">
                      {{ getStatusText(file.status) }}
                    </el-tag>
                  </div>
                  <div class="file-actions">
                    <el-button 
                      v-if="file.id" 
                      size="small" 
                      @click="viewInvoice(file.id)"
                    >
                      查看
                    </el-button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type UploadProps, type UploadRawFile, type TagProps } from 'element-plus'
import { UploadFilled, Document } from '@element-plus/icons-vue'
import { useUserStore } from '../../stores/user'
import { getInvoice } from '../../api/invoice'

const router = useRouter()
const userStore = useUserStore()

interface UploadedFile {
  uid: string
  id?: string
  filename: string
  status: string
  message: string
}

const uploadRef = ref()
const uploadedFiles = ref<UploadedFile[]>([])
const uploadDisabled = ref(false)
const activeUploadCount = ref(0)
const uploadStats = reactive({
  total: 0,
  success: 0,
  duplicate: 0,
  failed: 0
})

const activeUploadUids = new Set<string>()
const completedUploadUids = new Set<string>()
const pollingTimers = new Map<string, ReturnType<typeof setTimeout>>()

const uploadUrl = computed(() => '/api/v1/invoices/upload')
const uploadHeaders = computed(() => ({
  Authorization: `Bearer ${userStore.token}`
}))

const getUploadUid = (file: any) => String(file?.uid ?? file?.raw?.uid ?? file?.name ?? crypto.randomUUID())

const resetUploadBatch = () => {
  activeUploadUids.clear()
  completedUploadUids.clear()
  activeUploadCount.value = 0
  uploadStats.total = 0
  uploadStats.success = 0
  uploadStats.duplicate = 0
  uploadStats.failed = 0
}

const upsertUploadRecord = (file: Partial<UploadedFile> & { uid: string; filename: string }) => {
  const index = uploadedFiles.value.findIndex(item => item.uid === file.uid)
  if (index === -1) {
    uploadedFiles.value.unshift({
      id: file.id,
      uid: file.uid,
      filename: file.filename,
      status: file.status || 'uploading',
      message: file.message || ''
    })
    return
  }

  uploadedFiles.value[index] = {
    ...uploadedFiles.value[index],
    ...file
  }
}

const markUploadStarted = (uid: string, filename: string) => {
  if (activeUploadUids.size === 0 && completedUploadUids.size > 0) {
    resetUploadBatch()
  }

  upsertUploadRecord({
    uid,
    filename,
    status: 'uploading',
    message: '上传中'
  })

  if (!activeUploadUids.has(uid) && !completedUploadUids.has(uid)) {
    activeUploadUids.add(uid)
    activeUploadCount.value = activeUploadUids.size
    uploadStats.total += 1
  }
}

const markUploadFinished = (uid: string, result: 'success' | 'duplicate' | 'failed') => {
  if (activeUploadUids.delete(uid)) {
    activeUploadCount.value = activeUploadUids.size
  }

  if (completedUploadUids.has(uid)) return
  completedUploadUids.add(uid)

  if (result === 'success') {
    uploadStats.success += 1
  } else if (result === 'duplicate') {
    uploadStats.duplicate += 1
  } else {
    uploadStats.failed += 1
  }

  if (activeUploadCount.value === 0 && uploadStats.total > 1) {
    ElMessage.success(`批量上传完成：成功 ${uploadStats.success} 个，重复 ${uploadStats.duplicate} 个，失败 ${uploadStats.failed} 个`)
  }
}

const clearPollingTimer = (uid: string) => {
  const timer = pollingTimers.get(uid)
  if (timer) {
    clearTimeout(timer)
    pollingTimers.delete(uid)
  }
}

const pollInvoiceStatus = (uid: string, invoiceId: string, attempt = 0) => {
  clearPollingTimer(uid)

  const timer = setTimeout(async () => {
    try {
      const response = await getInvoice(invoiceId)
      const invoice = response.data

      if (invoice.ocr_status === 'success') {
        upsertUploadRecord({
          uid,
          id: invoiceId,
          filename: invoice.original_filename,
          status: invoice.status === 'duplicate' ? 'duplicate' : 'completed',
          message: invoice.status === 'duplicate' ? '发票重复，已导入为重复记录' : 'OCR识别完成'
        })
        clearPollingTimer(uid)
        return
      }

      if (invoice.ocr_status === 'failed') {
        upsertUploadRecord({
          uid,
          id: invoiceId,
          filename: invoice.original_filename,
          status: 'failed',
          message: invoice.ocr_error_message || 'OCR识别失败'
        })
        clearPollingTimer(uid)
        return
      }

      upsertUploadRecord({
        uid,
        id: invoiceId,
        filename: invoice.original_filename,
        status: 'processing',
        message: 'OCR识别中'
      })

      if (attempt < 60) {
        pollInvoiceStatus(uid, invoiceId, attempt + 1)
      } else {
        upsertUploadRecord({
          uid,
          id: invoiceId,
          filename: invoice.original_filename,
          status: 'processing',
          message: 'OCR仍在后台处理，可到发票列表查看'
        })
        clearPollingTimer(uid)
      }
    } catch (error) {
      if (attempt < 10) {
        pollInvoiceStatus(uid, invoiceId, attempt + 1)
      } else {
        clearPollingTimer(uid)
      }
    }
  }, attempt === 0 ? 1200 : 2000)

  pollingTimers.set(uid, timer)
}

const beforeUpload: UploadProps['beforeUpload'] = (rawFile: UploadRawFile) => {
  // 检查文件类型
  if (!rawFile.name.toLowerCase().endsWith('.pdf')) {
    ElMessage.error('只能上传PDF文件')
    return false
  }
  
  // 检查文件大小 (10MB)
  if (rawFile.size > 10 * 1024 * 1024) {
    ElMessage.error('文件大小不能超过10MB')
    return false
  }
  
  markUploadStarted(getUploadUid(rawFile), rawFile.name)
  return true
}

const handleProgress: UploadProps['onProgress'] = (_event: any, uploadFile: any) => {
  markUploadStarted(getUploadUid(uploadFile), uploadFile.name)
}

const handleSuccess = (response: any, uploadFile: any) => {
  const uid = getUploadUid(uploadFile)
  upsertUploadRecord({
    uid,
    id: response.id,
    filename: uploadFile.name,
    status: response.status || 'processing',
    message: response.message || '上传成功，正在进行OCR识别'
  })
  markUploadFinished(uid, 'success')
  pollInvoiceStatus(uid, response.id)

  if (uploadStats.total === 1) {
    ElMessage.success('发票上传成功，正在进行OCR识别')
  }
}

const handleError: UploadProps['onError'] = (error: any, uploadFile: any) => {
  const uid = getUploadUid(uploadFile)

  // 优先从响应体读取后端返回
  let resp = uploadFile?.response || error?.response?.data || error?.response
  if (typeof resp === 'string') {
    try {
      resp = JSON.parse(resp)
    } catch {
      // 保留原始字符串
    }
  }
  const detail = (resp && typeof resp === 'object') ? (resp.detail || resp.message) : undefined
  const rawMsg = typeof detail === 'object' ? detail?.message : detail
  
  // 识别409重复
  const isConflict = (error?.status === 409) || (error?.message?.includes?.('409')) || (rawMsg?.includes?.('重复'))
  if (isConflict) {
    // 提取已存在发票ID供跳转
    const existingId = (
      (typeof detail === 'object' && detail?.existing_invoice_id) ||
      resp?.existing_invoice_id ||
      error?.response?.data?.detail?.existing_invoice_id ||
      error?.response?.data?.existing_invoice_id ||
      undefined
    )

    upsertUploadRecord({
      uid,
      id: existingId,
      filename: uploadFile.name,
      status: 'duplicate',
      message: rawMsg || '该发票已存在，无需重复上传'
    })
    markUploadFinished(uid, 'duplicate')
    ElMessage.warning(rawMsg || '该发票已存在，无需重复上传')
    return
  }

  upsertUploadRecord({
    uid,
    filename: uploadFile.name,
    status: 'failed',
    message: rawMsg || '发票上传失败，请重试'
  })
  markUploadFinished(uid, 'failed')
  console.error('上传失败:', error)
  ElMessage.error(rawMsg || '发票上传失败，请重试')
}

type TagType = NonNullable<TagProps['type']>
const getStatusType = (status: string): TagType => {
  const statusMap: Record<string, TagType> = {
    'uploading': 'warning',
    'processing': 'warning',
    'completed': 'success',
    'duplicate': 'warning',
    'failed': 'danger',
    'suspected_red_offset': 'danger',
    'archived': 'info',
    'printed': 'info',
    'submitted': 'primary'
  }
  return statusMap[status] || 'info'
}

const getStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    'uploading': '上传中',
    'processing': 'OCR处理中',
    'completed': '已完成',
    'duplicate': '重复',
    'failed': '失败',
    'suspected_red_offset': '疑似红冲',
    'archived': '已归档',
    'printed': '已打印',
    'submitted': '已提交'
  }
  return statusMap[status] || '未知'
}

const viewInvoice = (id: string) => {
  router.push(`/invoices/${id}`)
}

onBeforeUnmount(() => {
  pollingTimers.forEach(timer => clearTimeout(timer))
  pollingTimers.clear()
})
</script>

<style scoped>
.upload-grid { align-items: flex-start; }


.upload-surface {
  margin-bottom: 8px;
  /* remove outer frame from el-upload root to avoid double borders */
  border: none !important;
  background: transparent;
  box-shadow: none;
}

/* Ensure the drag box aligns visually with the guides card */
.upload-col :deep(.el-upload),
.upload-col :deep(.el-upload-dragger) {
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Drag area visual */

:deep(.el-upload-dragger) {
  width: 100%;
  max-width: 620px;
  height: 320px;
  border-radius: 12px;
  margin: 0 auto;
  background-color: var(--el-fill-color-light);
  border: 1.5px dashed var(--el-border-color);
  box-shadow: 0 2px 8px 0 rgb(0 0 0 / 4%);
  transition: border-color .2s ease, background-color .2s ease, box-shadow .2s ease;
  padding: 20px 24px;
}

/* Subtle emphasis on hover and while dragging */
.upload-surface :deep(.el-upload-dragger:hover),
.upload-surface :deep(.is-dragover .el-upload-dragger) {
  border-color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
  box-shadow: 0 6px 18px 0 rgb(0 0 0 / 8%);
}

/* Accent the upload icon and text slightly */
.upload-surface :deep(.el-icon--upload) {
  color: var(--el-color-primary);
}
.upload-surface :deep(.el-upload__text) {
  color: var(--el-text-color-regular);
}

.upload-tips { display: flex; gap: 8px; justify-content: center; margin-top: 12px; flex-wrap: wrap; }
.muted { color: var(--el-text-color-secondary); margin-top: 6px; }
.upload-summary {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
  color: var(--el-text-color-regular);
  font-size: 14px;
}

.guides-pane { display: flex; flex-direction: column; gap: 16px; }
.guides-card, .recent-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 16px 18px;
}
.guides-title { font-weight: 600; margin-bottom: 10px; color: var(--el-text-color-primary); }
.guides-list { margin: 0; padding-left: 16px; color: var(--el-text-color-regular); }
.guides-list li { margin-bottom: 6px; }

.upload-list { display: flex; flex-direction: column; gap: 8px; }
.upload-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}
.file-info { display: flex; align-items: center; gap: 8px; min-width: 0; }
.file-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.filename { font-size: 14px; color: var(--el-text-color-primary); }
.file-message {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 768px) {
  :deep(.el-upload-dragger) { height: 220px; }
}
</style>
