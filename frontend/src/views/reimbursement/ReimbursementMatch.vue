<template>
  <div class="page-container reimbursement-page">
    <div class="page-header"><h1 class="page-title">报销单匹配</h1></div>
    <div class="upload-band">
      <el-upload
        drag accept=".pdf" :show-file-list="false" :limit="1"
        :before-upload="beforeUpload" :http-request="submitUpload" :disabled="uploading"
        ref="uploadRef"
      >
        <el-icon><UploadFilled /></el-icon>
        <span>{{ uploading ? '正在上传报销单' : '上传 PDF 报销单' }}</span>
      </el-upload>
      <el-button :icon="Refresh" :loading="loadingJobs" @click="loadJobs(false)">刷新</el-button>
    </div>
    <el-alert v-if="uploadError" :title="uploadError" type="error" :closable="false" class="notice" />
    <div class="workspace">
      <aside class="history">
        <h2>识别记录</h2>
        <el-empty v-if="!jobs.length" description="暂无报销单" :image-size="60" />
        <button
          v-for="job in jobs" :key="job.id" type="button" class="history-item"
          :class="{ active: selectedJob?.id === job.id }" @click="selectJob(job)"
        >
          <span class="history-name">{{ job.filename }}</span>
          <span class="history-meta">
            <el-tag size="small" :type="jobStatusType(job.status)">{{ jobStatusText(job.status) }}</el-tag>
            <span>{{ job.status === 'processing' ? `${job.completed_pages}/${job.page_count} 页` : `${job.numbers.length} 个票号` }}</span>
          </span>
          <time>{{ formatTime(job.created_at) }}</time>
        </button>
        <h2 class="history-section-title">已入库报销单</h2>
        <button
          v-for="report in reports" :key="report.id" type="button" class="history-item"
          :class="{ active: persistedReport?.id === report.id }" @click="selectReport(report.id)"
        >
          <span class="history-name">{{ report.name }}</span>
          <span class="history-meta"><el-tag size="small" type="success">已入库</el-tag><span>{{ report.invoice_count }} 张发票</span></span>
          <time>{{ formatTime(report.created_at) }}</time>
        </button>
      </aside>
      <section class="results" v-loading="matching">
        <div v-if="persistedReport && showReport" class="report-panel">
          <div class="result-heading">
            <div>
              <h2>{{ persistedReport.name }}</h2>
              <p class="muted">{{ persistedReport.invoice_count }} 张发票 · {{ amount(persistedReport.total_amount) }}</p>
            </div>
            <div class="report-actions">
              <el-button :icon="Download" @click="downloadReport">下载报销单</el-button>
              <el-button type="danger" plain :icon="Delete" @click="removeReport">删除报销单</el-button>
              <el-button type="primary" plain @click="openAddInvoice">添加发票</el-button>
            </div>
          </div>
          <div class="report-toolbar">
            <span>已选择 {{ selectedReportInvoices.length }} / {{ persistedReport.invoices.length }} 张</span>
            <el-button :disabled="!persistedReport.invoices.length" @click="invertReportSelection">反选</el-button>
            <el-select v-model="batchStatus" :disabled="updatingStatus" clearable placeholder="批量报销状态" style="width: 170px">
              <el-option label="未报销" value="unreimbursed" />
              <el-option label="已报销" value="reimbursed" />
              <el-option label="需换开" value="needs_reissue" />
              <el-option label="被打回" value="rejected" />
              <el-option label="报销中" value="processing" />
              <el-option label="疑似红冲" value="suspected_red_offset" />
            </el-select>
            <el-button type="primary" :loading="updatingStatus" :disabled="!batchStatus || !selectedReportInvoices.length" @click="applyBatchStatus">修改选中状态</el-button>
          </div>
          <div class="amount-toolbar">
            <el-input v-model="targetAmount" placeholder="财务实际到账金额" clearable style="width: 210px" />
            <el-button :loading="solvingAmount" @click="findAmountSolution">寻找精确组合</el-button>
            <span v-if="amountMessage" class="muted">{{ amountMessage }}</span>
          </div>
          <el-table
            ref="reportTable" :data="persistedReport.invoices" border stripe row-key="id"
            @select="handleReportSelect" @select-all="handleReportSelectAll"
          >
            <el-table-column type="selection" width="48" reserve-selection />
            <el-table-column prop="invoice_num" label="发票号码" width="220" />
            <el-table-column prop="seller_name" label="销售方" min-width="180" show-overflow-tooltip />
            <el-table-column label="开票日期" width="120"><template #default="{ row }">{{ row.invoice_date?.slice(0, 10) || '-' }}</template></el-table-column>
            <el-table-column label="金额" width="110" align="right"><template #default="{ row }">{{ amount(row.amount_in_figures ?? row.total_amount) }}</template></el-table-column>
            <el-table-column label="报销状态" width="110"><template #default="{ row }"><el-tag :type="getReimbursementStatusType(row.reimbursement_status)">{{ reimbursementStatusText(row.reimbursement_status) }}</el-tag></template></el-table-column>
            <el-table-column label="操作" width="80"><template #default="{ row }"><el-button link type="danger" @click="removeReportInvoice(row.id)">移除</el-button></template></el-table-column>
          </el-table>
        </div>
        <el-empty v-else-if="!selectedJob" description="尚未选择报销单" />
        <template v-else>
          <div class="result-heading">
            <h2>{{ selectedJob.filename }}</h2>
            <el-tooltip content="删除识别记录" placement="top">
              <el-button
                :icon="Delete" text type="danger" aria-label="删除识别记录"
                :disabled="isActive(selectedJob)" @click="removeJob(selectedJob)"
              />
            </el-tooltip>
          </div>
          <el-alert v-if="selectedJob.status === 'failed'" type="error" :title="selectedJob.error_message || '识别失败'" :closable="false" />
          <div v-else-if="isActive(selectedJob)" class="progress-state">
            <el-tag type="warning">{{ jobStatusText(selectedJob.status) }}</el-tag>
            <el-progress :percentage="progress" :stroke-width="8" />
            <span>{{ selectedJob.completed_pages }} / {{ selectedJob.page_count }} 页</span>
          </div>
          <template v-else>
            <div class="result-toolbar">
              <el-radio-group v-model="view" size="small">
                <el-radio-button label="all">全部 {{ rows.length }}</el-radio-button>
                <el-radio-button label="matched">已找到 {{ counts.matched }}</el-radio-button>
                <el-radio-button label="not_found">未找到 {{ counts.not_found }}</el-radio-button>
                <el-radio-button label="review">待核对 {{ counts.review }}</el-radio-button>
              </el-radio-group>
              <el-button :icon="Refresh" :loading="matching" :disabled="!rows.length" @click="rematch">重新匹配</el-button>
              <el-button type="success" :disabled="!canSaveReport" @click="saveReport">报销单入库</el-button>
            </div>
            <el-empty v-if="!rows.length" description="未识别到发票号码" />
            <el-table v-else :data="visibleRows" border row-key="key" class="match-table" max-height="650">
              <el-table-column label="发票号码" width="236">
                <template #default="{ row }">
                  <el-input v-model="row.input" maxlength="20" inputmode="numeric" aria-label="发票号码" @keyup.enter="rematch" />
                  <span v-if="row.input.trim() !== row.number.invoice_num" class="original-number">原识别：{{ row.number.invoice_num }}</span>
                </template>
              </el-table-column>
              <el-table-column label="来源" width="100">
                <template #default="{ row }">
                  <span>第 {{ row.number.pages.join(', ') }} 页</span>
                  <el-tag size="small" :type="needsReview(row) ? 'warning' : 'info'">
                    {{ row.input.trim() !== row.number.invoice_num ? '手动更正' : row.number.source === 'text' ? '文字层' : 'OCR' }}
                  </el-tag>
                  <span v-if="row.number.occurrences > 1" class="occurrences">出现 {{ row.number.occurrences }} 次</span>
                </template>
              </el-table-column>
              <el-table-column label="匹配结果" width="120">
                <template #default="{ row }">
                  <el-tag :type="matchStatusType(currentStatus(row))">{{ matchStatusText(currentStatus(row)) }}</el-tag>
                  <span v-if="needsReview(row)" class="low-confidence">识别待核对</span>
                </template>
              </el-table-column>
              <el-table-column label="销售方 / 文件名" min-width="210">
                <template #default="{ row }">
                  <div v-for="invoice in currentInvoices(row)" :key="invoice.id" class="invoice-info">
                    <span>{{ invoice.seller_name || invoice.original_filename }}</span>
                    <el-button link type="primary" @click="router.push(`/invoices/${invoice.id}`)">查看发票</el-button>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="开票日期" width="115">
                <template #default="{ row }"><div v-for="invoice in currentInvoices(row)" :key="invoice.id">{{ invoice.invoice_date?.slice(0, 10) || '-' }}</div></template>
              </el-table-column>
              <el-table-column label="金额" width="100" align="right">
                <template #default="{ row }"><div v-for="invoice in currentInvoices(row)" :key="invoice.id">{{ amount(invoice.amount_in_figures ?? invoice.total_amount) }}</div></template>
              </el-table-column>
            </el-table>
          </template>
        </template>
      </section>
    </div>
    <el-dialog v-model="addDialogVisible" title="从发票库添加" width="520px">
      <el-input v-model="addNumber" placeholder="输入完整发票号码" clearable @keyup.enter="searchAddInvoices" />
      <el-button class="search-add-button" :loading="searchingAdd" @click="searchAddInvoices">查找</el-button>
      <el-radio-group v-model="addInvoiceId" class="add-choices">
        <el-radio v-for="invoice in addCandidates" :key="invoice.id" :label="invoice.id">
          {{ invoice.invoice_num }} · {{ invoice.seller_name || invoice.original_filename }} · {{ amount(invoice.amount_in_figures ?? invoice.total_amount) }}
        </el-radio>
      </el-radio-group>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!addInvoiceId" @click="confirmAddInvoice">加入报销单</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox, type TagProps, type UploadInstance, type UploadProps, type UploadRequestOptions } from 'element-plus'
import { Delete, Download, Refresh, UploadFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import {
  deleteReimbursement, getReimbursements, matchReimbursement, uploadReimbursement,
  addReportInvoices, createReimbursementReport, deleteReimbursementReport, findReimbursementAmountSolution,
  getReimbursementReport, getReimbursementReports, getReimbursementReportFile, removeReportInvoice as removeReportInvoiceApi,
  type ReimbursementJob, type ReimbursementMatch, type ReimbursementNumber, type ReimbursementReport,
} from '@/api/reimbursement'
import { useInvoiceStore } from '@/stores/invoice'
import type { Invoice, ReimbursementStatus } from '@/types/invoice'
import { getInvoices } from '@/api/invoice'
import { getReimbursementStatusType } from '@/utils/reimbursement'

type TagType = NonNullable<TagProps['type']>
interface MatchRow {
  key: string
  number: ReimbursementNumber
  input: string
  matchedNumber: string
  match?: ReimbursementMatch
}

const router = useRouter()
const invoiceStore = useInvoiceStore()
const jobs = ref<ReimbursementJob[]>([])
const reports = ref<ReimbursementReport[]>([])
const selectedJob = ref<ReimbursementJob | null>(null)
const persistedReport = ref<ReimbursementReport | null>(null)
const showReport = ref(true)
const rows = ref<MatchRow[]>([])
const uploadRef = ref<UploadInstance>()
const loadingJobs = ref(false)
const matching = ref(false)
const uploading = ref(false)
const uploadError = ref('')
const batchStatus = ref<ReimbursementStatus | ''>('')
const updatingStatus = ref(false)
const targetAmount = ref('')
const amountMessage = ref('')
const solvingAmount = ref(false)
const reportTable = ref()
const addDialogVisible = ref(false)
const addNumber = ref('')
const addCandidates = ref<Invoice[]>([])
const addInvoiceId = ref('')
const searchingAdd = ref(false)
const view = ref('all')
let timer: ReturnType<typeof setTimeout> | undefined
let unmounted = false
let matchVersion = 0

const isActive = (job: ReimbursementJob) => ['pending', 'processing'].includes(job.status)
const isCurrent = (row: MatchRow) => !!row.match && row.input.trim() === row.matchedNumber
const currentInvoices = (row: MatchRow) => isCurrent(row) ? row.match?.invoices || [] : []
const currentStatus = (row: MatchRow) => isCurrent(row) ? row.match?.status || 'review' : 'review'
const needsReview = (row: MatchRow) => row.input.trim() === row.number.invoice_num && (
  row.number.source === 'ocr' && (row.number.confidence ?? 0) < 80
)
const counts = computed(() => ({
  matched: rows.value.filter(row => currentStatus(row) === 'matched').length,
  not_found: rows.value.filter(row => currentStatus(row) === 'not_found').length,
  review: rows.value.filter(row => ['ambiguous', 'review'].includes(currentStatus(row)) || needsReview(row)).length,
}))
const visibleRows = computed(() => rows.value.filter(row => view.value === 'all' || (
  view.value === 'review' ? ['ambiguous', 'review'].includes(currentStatus(row)) || needsReview(row) : currentStatus(row) === view.value
)))
const matchedRows = computed(() => rows.value.filter(row => currentStatus(row) === 'matched' && row.match?.invoices?.length === 1))
const canSaveReport = computed(() => !!selectedJob.value && selectedJob.value.status === 'completed' && rows.value.length > 0 && matchedRows.value.length === rows.value.length)
const selectedReportInvoices = computed(() => persistedReport.value?.invoices.filter(invoice => invoiceStore.isSelected(invoice.id)) || [])
const progress = computed(() => selectedJob.value?.page_count ? Math.round(selectedJob.value.completed_pages / selectedJob.value.page_count * 100) : 0)
const formatTime = (value: string) => value.replace('T', ' ').slice(0, 16)
const amount = (value: unknown) => value == null ? '-' : `¥${Number(value).toFixed(2)}`
const reimbursementStatusText = (value?: string) => ({ unreimbursed: '未报销', reimbursed: '已报销', needs_reissue: '需换开', rejected: '被打回', processing: '报销中', suspected_red_offset: '疑似红冲' }[value || 'unreimbursed'] || '未报销')
const asInvoice = (invoice: ReimbursementReport['invoices'][number]) => invoice as unknown as Invoice

const beforeUpload: UploadProps['beforeUpload'] = file => {
  uploadError.value = ''
  if (!file.name.toLowerCase().endsWith('.pdf') || file.size > 10 * 1024 * 1024) {
    uploadError.value = '请上传不超过 10MB 的 PDF 报销单'
    return false
  }
  return true
}

const submitUpload = async (options: UploadRequestOptions) => {
  uploading.value = true
  try {
    const job = (await uploadReimbursement(options.file)).data
    if (unmounted) return
    jobs.value.unshift(job)
    await selectJob(job)
    schedulePolling()
    ElMessage.success('报销单已进入识别队列')
  } catch (error: any) {
    if (!unmounted) uploadError.value = error?.response?.data?.detail || '报销单上传失败'
  } finally {
    uploading.value = false
    uploadRef.value?.clearFiles()
  }
}

const schedulePolling = () => {
  if (timer) clearTimeout(timer)
  if (unmounted || !jobs.value.some(isActive)) return
  timer = setTimeout(() => loadJobs(true), 2000)
}

const loadJobs = async (silent = false) => {
  if (loadingJobs.value || unmounted) return
  loadingJobs.value = true
  try {
    const updated = (await getReimbursements()).data
    if (unmounted) return
    jobs.value = updated
    reports.value = (await getReimbursementReports()).data
    const selected = updated.find(job => job.id === selectedJob.value?.id)
    if (selected) {
      if (selectedJob.value?.status !== selected.status && !isActive(selected)) await selectJob(selected)
      else selectedJob.value = selected
    } else if (selectedJob.value) {
      selectedJob.value = null
      rows.value = []
    }
    if (showReport.value && persistedReport.value) {
      if (!silent && !updatingStatus.value) await selectReport(persistedReport.value.id)
    } else if (!selectedJob.value && updated.length && !silent) await selectJob(updated[0])
  } catch {
    if (!silent) ElMessage.error('识别记录加载失败')
  } finally {
    loadingJobs.value = false
    schedulePolling()
  }
}

const selectReport = async (id: string) => {
  persistedReport.value = (await getReimbursementReport(id)).data
  showReport.value = true
  selectedJob.value = null
  rows.value = []
  await restoreReportSelection()
}

const restoreReportSelection = async () => {
  await nextTick()
  if (!persistedReport.value || !reportTable.value) return
  reportTable.value.clearSelection()
  for (const invoice of persistedReport.value.invoices) {
    if (invoiceStore.isSelected(invoice.id)) reportTable.value.toggleRowSelection(invoice, true)
  }
}

const selectJob = async (job: ReimbursementJob) => {
  matchVersion += 1
  showReport.value = false
  selectedJob.value = job
  rows.value = job.numbers.map(number => ({ key: number.invoice_num, number, input: number.invoice_num, matchedNumber: '' }))
  view.value = 'all'
  matching.value = false
  if (job.status === 'completed' && rows.value.length) await rematch()
}

const rematch = async () => {
  if (!selectedJob.value || selectedJob.value.status !== 'completed') return
  const numbers = rows.value.map(row => row.input.trim())
  if (numbers.some(number => !/^(?:\d{8}|\d{20})$/.test(number))) {
    ElMessage.warning('发票号码须为 8 位或 20 位数字')
    return
  }
  const version = ++matchVersion
  matching.value = true
  try {
    const result = await matchReimbursement(selectedJob.value.id, numbers)
    if (unmounted || version !== matchVersion) return
    const byNumber = new Map(result.data.items.map(item => [item.invoice_num, item]))
    rows.value.forEach((row, index) => {
      row.match = byNumber.get(numbers[index])
      row.matchedNumber = numbers[index]
    })
  } catch (error: any) {
    if (!unmounted && version === matchVersion) ElMessage.error(error?.response?.data?.detail || '票号匹配失败')
  } finally {
    if (version === matchVersion) matching.value = false
  }
}

const removeJob = async (job: ReimbursementJob) => {
  try {
    await ElMessageBox.confirm('只删除这条报销单识别记录，不会删除对应发票。', '删除识别记录', { type: 'warning' })
  } catch { return }
  await deleteReimbursement(job.id)
  jobs.value = jobs.value.filter(item => item.id !== job.id)
  if (selectedJob.value?.id === job.id) {
    matchVersion += 1
    selectedJob.value = null
    rows.value = []
  }
}

const handleReportSelect = (selection: Invoice[]) => {
  if (!persistedReport.value) return
  invoiceStore.syncVisibleSelection(persistedReport.value.invoices.map(asInvoice), selection)
}

const handleReportSelectAll = (selection: Invoice[]) => handleReportSelect(selection)

const invertReportSelection = async () => {
  if (!persistedReport.value) return
  const invoices = persistedReport.value.invoices.map(asInvoice)
  invoiceStore.syncVisibleSelection(invoices, invoices.filter(invoice => !invoiceStore.isSelected(invoice.id)))
  await restoreReportSelection()
}

const saveReport = async () => {
  if (!selectedJob.value || !canSaveReport.value) return
  const items = matchedRows.value.map(row => ({ invoice_id: row.match!.invoices[0].id, invoice_num: row.input.trim() }))
  try {
    persistedReport.value = (await createReimbursementReport({ source_job_id: selectedJob.value.id, name: selectedJob.value.filename, items })).data
    showReport.value = true
    reports.value = [persistedReport.value, ...reports.value.filter(report => report.id !== persistedReport.value?.id)]
    await restoreReportSelection()
    ElMessage.success('报销单已入库')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '报销单入库失败')
  }
}

const applyBatchStatus = async () => {
  if (updatingStatus.value || !persistedReport.value || !batchStatus.value || !selectedReportInvoices.value.length) return
  const report = persistedReport.value
  const status = batchStatus.value
  const ids = selectedReportInvoices.value.map(invoice => invoice.id)
  const selectedIds = new Set(ids)
  updatingStatus.value = true
  try {
    const updatedCount = await invoiceStore.batchUpdateReimbursementStatus(ids, status)
    if (updatedCount === null) return
    report.invoices = report.invoices.map(invoice => selectedIds.has(invoice.id)
      ? { ...invoice, reimbursement_status: status }
      : invoice)
    if (persistedReport.value?.id === report.id) {
      persistedReport.value.invoices = report.invoices
      await restoreReportSelection()
    }
    ElMessage.success(updatedCount ? `已更新 ${updatedCount} 张发票` : '所选发票已是该状态，显示已同步')
  } finally {
    updatingStatus.value = false
  }
}

const openAddInvoice = () => {
  addDialogVisible.value = true
  addNumber.value = ''
  addCandidates.value = []
  addInvoiceId.value = ''
}

const searchAddInvoices = async () => {
  const number = addNumber.value.trim()
  if (!/^(?:\d{8}|\d{20})$/.test(number)) { ElMessage.warning('请输入完整的 8 位或 20 位发票号码'); return }
  searchingAdd.value = true
  try {
    const response = await getInvoices({ invoice_num: number, include_duplicates: true, size: 100 })
    addCandidates.value = response.data.items.filter(invoice => invoice.invoice_num === number && !persistedReport.value?.invoices.some(existing => existing.id === invoice.id))
    addInvoiceId.value = ''
    if (!addCandidates.value.length) ElMessage.info('当前用户的发票库中没有可添加的精确匹配')
  } finally { searchingAdd.value = false }
}

const confirmAddInvoice = async () => {
  if (!persistedReport.value || !addInvoiceId.value) return
  persistedReport.value = (await addReportInvoices(persistedReport.value.id, [addInvoiceId.value])).data
  reports.value = reports.value.map(report => report.id === persistedReport.value!.id ? persistedReport.value! : report)
  addDialogVisible.value = false
  await restoreReportSelection()
}

const removeReportInvoice = async (invoiceId: string) => {
  if (!persistedReport.value) return
  persistedReport.value = (await removeReportInvoiceApi(persistedReport.value.id, invoiceId)).data
  delete invoiceStore.selectedInvoiceMap[invoiceId]
  reports.value = reports.value.map(report => report.id === persistedReport.value!.id ? persistedReport.value! : report)
  await restoreReportSelection()
}

const removeReport = async () => {
  if (!persistedReport.value) return
  try { await ElMessageBox.confirm('只删除报销单及其关联关系，不删除其中的发票。', '删除报销单', { type: 'warning' }) } catch { return }
  const id = persistedReport.value.id
  await deleteReimbursementReport(id)
  reports.value = reports.value.filter(report => report.id !== id)
  persistedReport.value = null
}

const downloadReport = async () => {
  if (!persistedReport.value) return
  const response = await getReimbursementReportFile(persistedReport.value.id)
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = persistedReport.value.name
  link.click()
  URL.revokeObjectURL(url)
}

const findAmountSolution = async () => {
  if (!persistedReport.value || !targetAmount.value.trim()) return
  solvingAmount.value = true
  amountMessage.value = ''
  try {
    const result = (await findReimbursementAmountSolution(persistedReport.value.id, targetAmount.value.trim())).data.solution
    if (!result) { amountMessage.value = '没有找到金额完全相等的组合'; return }
    reportTable.value?.clearSelection()
    for (const invoice of persistedReport.value.invoices) {
      const selected = result.invoice_ids.includes(invoice.id)
      reportTable.value?.toggleRowSelection(invoice, selected)
      invoiceStore.setInvoiceSelected(asInvoice(invoice), selected)
    }
    amountMessage.value = `已找到 ${result.invoice_count} 张发票，合计 ${amount(result.total_amount)}`
  } catch (error: any) {
    amountMessage.value = error?.response?.data?.detail || '金额组合计算失败'
  } finally { solvingAmount.value = false }
}

const jobStatusType = (status: string): TagType => ({ pending: 'info', processing: 'warning', completed: 'success', failed: 'danger' }[status] || 'info') as TagType
const jobStatusText = (status: string) => ({ pending: '排队中', processing: '识别中', completed: '已完成', failed: '失败' }[status] || '未知')
const matchStatusType = (status: string): TagType => ({ matched: 'success', not_found: 'info', ambiguous: 'warning', review: 'warning' }[status] || 'info') as TagType
const matchStatusText = (status: string) => ({ matched: '已找到', not_found: '未找到', ambiguous: '多个候选', review: '待重新匹配' }[status] || '未知')

onMounted(() => loadJobs())
onBeforeUnmount(() => {
  unmounted = true
  matchVersion += 1
  if (timer) clearTimeout(timer)
})
</script>

<style scoped>
.reimbursement-page { min-width: 0; }
.upload-band { display: flex; align-items: center; gap: 12px; padding-bottom: 20px; border-bottom: 1px solid var(--el-border-color); }
:deep(.el-upload) { width: min(100%, 460px); }
:deep(.el-upload-dragger) { display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; min-height: 64px; padding: 14px; border-radius: 6px; }
.notice { margin-top: 14px; }
.workspace { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 24px; padding-top: 22px; }
h2 { margin: 0 0 16px; font-size: 16px; overflow-wrap: anywhere; }
.history { border-right: 1px solid var(--el-border-color); padding-right: 16px; min-width: 0; }
.history-item { display: flex; flex-direction: column; gap: 8px; width: 100%; padding: 12px 10px; margin-bottom: 6px; border: 0; border-left: 3px solid transparent; background: transparent; text-align: left; cursor: pointer; color: var(--el-text-color-primary); font-family: inherit; }
.history-item.active { border-left-color: var(--el-color-primary); background: var(--el-fill-color); }
.history-item:hover { background: var(--el-fill-color-light); }
.history-name { overflow-wrap: anywhere; font-size: 14px; }
.history-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; font-size: 12px; }
time, .occurrences, .original-number { color: var(--el-text-color-secondary); font-size: 12px; }
.results { min-width: 0; }
.result-heading, .result-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.result-heading h2 { margin: 0; flex: 1; min-width: 0; }
.progress-state { display: grid; gap: 20px; padding: 24px 0; }
.original-number, .low-confidence, .occurrences { display: block; margin-top: 4px; }
.low-confidence { color: var(--el-color-warning); font-size: 12px; }
.invoice-info { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; overflow-wrap: anywhere; }
.match-table :deep(.cell) { line-height: 24px; }
.search-add-button { margin-top: 12px; }
.add-choices { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; margin-top: 16px; max-height: 220px; overflow: auto; }
@media (max-width: 1100px) { .workspace { grid-template-columns: 210px minmax(0, 1fr); gap: 16px; } }
@media (max-width: 760px) { .workspace { grid-template-columns: minmax(0, 1fr); } .history { border-right: 0; max-height: 230px; overflow: auto; } }
</style>
