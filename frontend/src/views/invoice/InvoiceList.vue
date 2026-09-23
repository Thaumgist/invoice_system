<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">发票列表</h1>
      <div class="page-header-actions">
        <el-button @click="fetchInvoices" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button type="primary" @click="$router.push('/invoices/upload')">
          <el-icon><UploadFilled /></el-icon>
          上传发票
        </el-button>
      </div>
    </div>
    
    <!-- 筛选表单 -->
      <el-card class="filter-form">
      <template #header>
        <span class="card-header-title section-title">筛选条件</span>
      </template>
      <div @keydown.capture.enter="handleFilterEnter">
      <el-form
        :model="filters"
        :inline="false"
        size="default"
        @submit.prevent="handleSearch"
      >
        <el-form-item label="商品名称" class="full-width-item">
          <el-input
            v-model="filters.commodity_name"
            clearable
            placeholder="输入商品或服务名称"
          />
        </el-form-item>

        <el-row :gutter="32" class="more-filters-row">
          <el-col :span="6">
            <el-form-item label="精确金额">
              <el-input
                v-model="filters.amount_exact"
                inputmode="decimal"
                clearable
                placeholder="例如 60.10"
                @input="sanitizeAmountInput('amount_exact')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="最低金额">
              <el-input
                v-model="filters.amount_min"
                inputmode="decimal"
                clearable
                :disabled="hasExactAmountFilter"
                placeholder="例如 10.00"
                @input="sanitizeAmountInput('amount_min')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="最高金额">
              <el-input
                v-model="filters.amount_max"
                inputmode="decimal"
                clearable
                :disabled="hasExactAmountFilter"
                placeholder="例如 99.99"
                @input="sanitizeAmountInput('amount_max')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="报销状态">
              <el-select
                v-model="filters.reimbursement_status"
                placeholder="请选择状态"
                clearable
                style="width: 100%"
                @visible-change="setDropdownOpen('reimbursement_status', $event)"
              >
                <el-option label="未报销" value="unreimbursed" />
                <el-option label="已报销" value="reimbursed" />
                <el-option label="需换开" value="needs_reissue" />
                <el-option label="报销中" value="processing" />
                <el-option label="疑似红冲" value="suspected_red_offset" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="32" class="more-filters-row">
          <el-col :span="8">
            <el-form-item label="发票类型">
              <el-select
                v-model="filters.service_types"
                multiple
                collapse-tags
                filterable
                clearable
                placeholder="选择类型"
                style="width: 100%"
                @visible-change="setDropdownOpen('service_types', $event)"
              >
                <el-option
                  v-for="t in filterOptions.service_types"
                  :key="t"
                  :label="t"
                  :value="t"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 更多筛选项 -->
        <template v-if="showMoreFilters">
          <el-form-item label="销售方" class="full-width-item">
            <el-select-v2
              v-model="filters.seller_names"
              multiple
              collapse-tags
              filterable
              clearable
              placeholder="选择销售方"
              :options="sellerOptions"
              style="width: 100%"
              @visible-change="setDropdownOpen('seller_names', $event)"
            />
          </el-form-item>

          <el-form-item label="购方" class="full-width-item">
            <el-select-v2
              v-model="filters.purchaser_names"
              multiple
              collapse-tags
              filterable
              clearable
              placeholder="选择购方"
              :options="purchaserOptions"
              style="width: 100%"
              @visible-change="setDropdownOpen('purchaser_names', $event)"
            />
          </el-form-item>

          <el-row :gutter="32" class="more-filters-row">
            <el-col :span="8">
              <el-form-item label="OCR状态">
                <el-select
                  v-model="filters.ocr_status"
                  placeholder="请选择OCR状态"
                  clearable
                  style="width: 100%"
                  @visible-change="setDropdownOpen('ocr_status', $event)"
                >
                  <el-option label="全部" value="" />
                  <el-option label="待处理" value="pending" />
                  <el-option label="识别中" value="processing" />
                  <el-option label="成功" value="success" />
                  <el-option label="失败" value="failed" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="包含重复">
                <el-switch v-model="filters.include_duplicates" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>
        
        <el-form-item class="filter-action-bar">
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleClearSearch">清空搜索</el-button>
          <el-button @click="showDuplicateManager">去重管理</el-button>
          <el-button type="text" @click="showMoreFilters = !showMoreFilters">{{ showMoreFilters ? '收起' : '更多' }}</el-button>
        </el-form-item>
      </el-form>
      </div>
    </el-card>
    
    <!-- 发票表格 -->
    <div class="table-container">
      <el-card class="invoice-list-card">
        <template #header>
          <div class="table-header-toolbar">
            <span class="card-header-title section-title">发票列表</span>
            <el-popover
              v-model:visible="columnSettingsVisible"
              placement="bottom-end"
              :width="340"
              trigger="click"
            >
              <template #reference>
                <el-button size="small" plain>
                  <el-icon><Setting /></el-icon>
                  列设置
                </el-button>
              </template>
              <div class="column-settings-panel">
                <div class="column-settings-heading">
                  <span>显示列与顺序</span>
                  <el-button link type="primary" size="small" @click="resetColumnSettings">
                    恢复默认
                  </el-button>
                </div>
                <div
                  v-for="(column, index) in columnSettings"
                  :key="column.key"
                  class="column-settings-row"
                >
                <el-checkbox
                    v-model="column.visible"
                    :disabled="column.visible && visibleInvoiceColumns.length === 1"
                    @change="persistColumnSettings"
                  >
                    {{ column.label }}
                  </el-checkbox>
                  <span class="column-settings-order">
                    <el-button
                      link
                      size="small"
                      :disabled="index === 0"
                      aria-label="上移列"
                      @click="moveColumn(column.key, -1)"
                    >
                      <el-icon><ArrowUp /></el-icon>
                    </el-button>
                    <el-button
                      link
                      size="small"
                      :disabled="index === columnSettings.length - 1"
                      aria-label="下移列"
                      @click="moveColumn(column.key, 1)"
                    >
                      <el-icon><ArrowDown /></el-icon>
                    </el-button>
                  </span>
                </div>
                <div class="column-settings-fixed">勾选列与“操作”列固定显示</div>
              </div>
            </el-popover>
          </div>
        </template>
        <div v-if="selectedCount" class="selection-summary">
          <div class="selection-summary-text">
            <span>已勾选 {{ selectedCount }} 张</span>
            <span>当前结果中可见 {{ selectedVisibleCount }} 张</span>
            <span>合计金额 {{ formatAmount(selectedTotalAmount) }}</span>
          </div>
          <div class="selection-summary-actions">
            <el-button size="small" type="primary" @click="goToBatchPrint">
              批量打印
            </el-button>
            <el-button size="small" :loading="batchDownloading" @click="downloadSelectedInvoices">
              <el-icon><Download /></el-icon>
              打包下载
            </el-button>
            <el-dropdown
              trigger="click"
              :disabled="batchUpdating"
              @command="(value: string) => batchUpdateReimbursementStatus(value)"
            >
              <el-button size="small" :loading="batchUpdating">
                批量修改报销状态
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="unreimbursed">
                    <el-tag type="info">未报销</el-tag>
                  </el-dropdown-item>
                  <el-dropdown-item command="reimbursed">
                    <el-tag type="success">已报销</el-tag>
                  </el-dropdown-item>
                  <el-dropdown-item command="needs_reissue">
                    <el-tag type="danger">需换开</el-tag>
                  </el-dropdown-item>
                  <el-dropdown-item command="processing">
                    <el-tag type="warning">报销中</el-tag>
                  </el-dropdown-item>
                  <el-dropdown-item command="suspected_red_offset">
                    <el-tag type="danger">疑似红冲</el-tag>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" @click="confirmClearSelection">
              清空选择
            </el-button>
          </div>
        </div>
        <div class="invoice-table-scroll" role="region" aria-label="发票列表，可左右滚动">
          <el-table
            ref="invoiceTableRef"
            v-loading="loading"
            :data="invoices"
            row-key="id"
            stripe
            :fit="false"
            height="100%"
            width="100%"
            @selection-change="handleSelectionChange"
          >
          <el-table-column type="selection" width="55" />
          <el-table-column
            v-for="column in visibleInvoiceColumns"
            :key="column.key"
            :prop="column.prop"
            :label="column.label"
            :width="column.width"
          >
            <template #default="{ row }">
              <template v-if="column.key === 'seller'">
                {{ row.seller_name || '-' }}
              </template>
              <template v-else-if="column.key === 'purchaser'">
                {{ row.purchaser_name || '-' }}
              </template>
              <template v-else-if="column.key === 'commodity'">
                <el-tooltip
                  v-if="getFirstCommodityName(row) !== '-'"
                  :content="getFirstCommodityName(row)"
                  placement="top"
                >
                  <span class="commodity-name">{{ getFirstCommodityName(row) }}</span>
                </el-tooltip>
                <span v-else>-</span>
              </template>
              <template v-else-if="column.key === 'travelTime'">
                <span :class="{ 'train-ticket-time': getTrainTicketTime(row) !== '-' }">
                  {{ getTrainTicketTime(row) }}
                </span>
              </template>
              <template v-else-if="column.key === 'amount'">
                <span :class="{ 'amount': hasValidAmount(row.amount_in_figures) }">
                  {{ formatAmount(row.amount_in_figures) }}
                </span>
              </template>
              <template v-else-if="column.key === 'serviceType'">
                <span v-if="row.service_type">{{ row.service_type }}</span>
                <span v-else>未知</span>
              </template>
              <template v-else-if="column.key === 'reimbursement'">
                <el-dropdown trigger="click" @command="(value: string) => updateReimbursementStatus(row, value)">
                  <el-tag class="status-tag" :type="getReimbursementStatusType(row.reimbursement_status)">
                    {{ getReimbursementStatusText(row.reimbursement_status) }}
                  </el-tag>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="unreimbursed">
                        <el-tag type="info">未报销</el-tag>
                      </el-dropdown-item>
                      <el-dropdown-item command="reimbursed">
                        <el-tag type="success">已报销</el-tag>
                      </el-dropdown-item>
                      <el-dropdown-item command="needs_reissue">
                        <el-tag type="danger">需换开</el-tag>
                      </el-dropdown-item>
                      <el-dropdown-item command="processing">
                        <el-tag type="warning">报销中</el-tag>
                      </el-dropdown-item>
                      <el-dropdown-item command="suspected_red_offset">
                        <el-tag type="danger">疑似红冲</el-tag>
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
              <template v-else-if="column.key === 'invoiceDate'">
                {{ formatDate(row.invoice_date) }}
              </template>
            </template>
          </el-table-column>
        
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link size="small" type="primary" @click="openDetail(row)">
                详情
              </el-button>
              <el-button
                v-if="row.ocr_status === 'failed'"
                link size="small"
                @click="retryOCR(row.id)"
              >
                重试
              </el-button>
              <el-button type="success" link size="small" @click="downloadInvoice(row.id, row.original_filename)">
                下载
              </el-button>
              <el-button type="danger" link size="small" @click="deleteInvoice(row.id)">
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
          </el-table>
        </div>
      
        <div class="pagination-container">
          <el-pagination
            v-model:current-page="pagination.page"
            v-model:page-size="pagination.size"
            :total="pagination.total"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            @size-change="handleSizeChange"
            @current-change="handleCurrentChange"
          />
        </div>
      </el-card>
    </div>
    
    <InvoiceDetailDialog
      v-model="detailDialogVisible"
      :invoice="currentInvoice"
      @saved="fetchInvoices"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { TableInstance, TagProps } from 'element-plus'
import { ArrowDown, ArrowUp, Download, Refresh, Setting, UploadFilled } from '@element-plus/icons-vue'
import { useInvoiceStore } from '../../stores/invoice'
import {
  downloadInvoice as apiDownloadInvoice,
  downloadInvoices as apiDownloadInvoices,
  getInvoiceFilterOptions,
} from '../../api/invoice'
import InvoiceDetailDialog from '../../components/InvoiceDetailDialog.vue'
import type { Invoice, InvoiceFilter, ReimbursementStatus } from '../../types/invoice'

const router = useRouter()
const invoiceStore = useInvoiceStore()

const loading = ref(false)
const batchUpdating = ref(false)
const batchDownloading = ref(false)
const showMoreFilters = ref(false)
const columnSettingsVisible = ref(false)
const invoiceTableRef = ref<TableInstance>()
const isSyncingTableSelection = ref(false)

type InvoiceColumnKey =
  | 'seller'
  | 'purchaser'
  | 'commodity'
  | 'travelTime'
  | 'amount'
  | 'serviceType'
  | 'reimbursement'
  | 'invoiceDate'

type InvoiceColumnSetting = {
  key: InvoiceColumnKey
  label: string
  prop?: string
  width: number
  visible: boolean
}

const COLUMN_SETTINGS_STORAGE_KEY = 'invoice-list-column-settings'

const defaultColumnSettings = (): InvoiceColumnSetting[] => [
  { key: 'seller', label: '销售方', prop: 'seller_name', width: 200, visible: true },
  { key: 'purchaser', label: '购方', prop: 'purchaser_name', width: 200, visible: true },
  { key: 'commodity', label: '商品名称', width: 220, visible: true },
  { key: 'travelTime', label: '乘车时间', width: 140, visible: true },
  { key: 'amount', label: '金额', prop: 'total_amount', width: 120, visible: true },
  { key: 'serviceType', label: '消费类型', prop: 'service_type', width: 120, visible: true },
  { key: 'reimbursement', label: '报销状态', width: 120, visible: true },
  { key: 'invoiceDate', label: '开票日期', prop: 'created_at', width: 120, visible: true },
]

const columnSettings = ref<InvoiceColumnSetting[]>(defaultColumnSettings())
const visibleInvoiceColumns = computed(() => columnSettings.value.filter(column => column.visible))

const persistColumnSettings = () => {
  localStorage.setItem(
    COLUMN_SETTINGS_STORAGE_KEY,
    JSON.stringify(columnSettings.value.map(({ key, visible }) => ({ key, visible })))
  )
}

const loadColumnSettings = () => {
  const defaults = defaultColumnSettings()
  try {
    const stored = JSON.parse(localStorage.getItem(COLUMN_SETTINGS_STORAGE_KEY) || 'null')
    if (!Array.isArray(stored)) return

    // 旧版本曾保存过发票“状态”列，迁移时直接丢弃，避免旧配置继续污染列设置。
    const migratedStored = stored.filter(item => item?.key !== 'status')

    const visibility = new Map(
      migratedStored
        .filter(item => item && typeof item.key === 'string')
        .map(item => [item.key, item.visible !== false])
    )
    const storedOrder = migratedStored
      .map(item => item?.key)
      .filter((key): key is InvoiceColumnKey => defaults.some(column => column.key === key))
    const order = [...new Set([...storedOrder, ...defaults.map(column => column.key)])]

    columnSettings.value = order.map(key => {
      const column = defaults.find(item => item.key === key)!
      return { ...column, visible: visibility.get(key) ?? column.visible }
    })
    persistColumnSettings()
  } catch {
    columnSettings.value = defaults
  }
}

const resetColumnSettings = () => {
  columnSettings.value = defaultColumnSettings()
  persistColumnSettings()
}

const moveColumn = (key: InvoiceColumnKey, direction: -1 | 1) => {
  const index = columnSettings.value.findIndex(column => column.key === key)
  const targetIndex = index + direction
  if (index < 0 || targetIndex < 0 || targetIndex >= columnSettings.value.length) return

  const nextSettings = [...columnSettings.value]
  const [movedColumn] = nextSettings.splice(index, 1)
  nextSettings.splice(targetIndex, 0, movedColumn)
  columnSettings.value = nextSettings
  persistColumnSettings()
}

type InvoiceListFilters = InvoiceFilter & {
  include_duplicates?: boolean
  seller_names?: string[]
  purchaser_names?: string[]
  service_types?: string[]
}

const createDefaultFilters = (): InvoiceListFilters => ({
  ocr_status: '',
  commodity_name: '',
  reimbursement_status: '',
  amount_exact: undefined,
  amount_min: undefined,
  amount_max: undefined,
  seller_names: [],
  purchaser_names: [],
  service_types: [],
  include_duplicates: false,
})

const filters = reactive<InvoiceListFilters>(createDefaultFilters())
const filterOptions = reactive({
  sellers: [] as string[],
  purchasers: [] as string[],
  service_types: [] as string[],
})

// 为虚拟化选择器准备 options 数组
const sellerOptions = computed(() => filterOptions.sellers.map(name => ({ label: name, value: name })))
const purchaserOptions = computed(() => filterOptions.purchasers.map(name => ({ label: name, value: name })))

const fetchFilterOptions = async () => {
  try {
    const resp = await getInvoiceFilterOptions()
    filterOptions.sellers = resp.data.sellers || []
    filterOptions.purchasers = resp.data.purchasers || []
    filterOptions.service_types = resp.data.service_types || []
  } catch (e) {
    // 忽略错误，保持空选项
  }
}

const pagination = reactive({
  page: 1,
  size: 20,
  total: 0
})

const invoices = computed(() => invoiceStore.invoices)
const selectedInvoiceIds = computed(() => invoiceStore.selectedInvoiceIds)
const selectedCount = computed(() => invoiceStore.selectedCount)
const selectedTotalAmount = computed(() => invoiceStore.selectedTotalAmount)
const selectedVisibleCount = computed(() => (
  invoices.value.filter(invoice => invoiceStore.isSelected(invoice.id)).length
))
const hasAmountFilterValue = (value: unknown) => value !== '' && value !== null && value !== undefined
const hasExactAmountFilter = computed(() => hasAmountFilterValue(filters.amount_exact))

type AmountFilterField = 'amount_exact' | 'amount_min' | 'amount_max'
type DropdownFilterField =
  | 'reimbursement_status'
  | 'service_types'
  | 'seller_names'
  | 'purchaser_names'
  | 'ocr_status'

let amountSearchTimer: ReturnType<typeof setTimeout> | undefined
const openFilterDropdowns = reactive<Record<DropdownFilterField, boolean>>({
  reimbursement_status: false,
  service_types: false,
  seller_names: false,
  purchaser_names: false,
  ocr_status: false,
})

const amountFilterFields: AmountFilterField[] = ['amount_exact', 'amount_min', 'amount_max']
const isAnyFilterDropdownOpen = computed(() => Object.values(openFilterDropdowns).some(Boolean))

const isAmountFilterReady = (value: unknown) => {
  if (!hasAmountFilterValue(value)) return true
  const text = String(value).trim().replace(/，/g, '.')
  return /^\d+(\.\d{1,2})?$/.test(text) && !text.endsWith('.')
}

const clearAmountSearchTimer = () => {
  if (!amountSearchTimer) return
  clearTimeout(amountSearchTimer)
  amountSearchTimer = undefined
}

const runSearchFromFirstPage = () => {
  pagination.page = 1
  fetchInvoices()
}

const scheduleAmountSearch = () => {
  clearAmountSearchTimer()
  if (!amountFilterFields.every(field => isAmountFilterReady(filters[field]))) return

  amountSearchTimer = setTimeout(() => {
    amountSearchTimer = undefined
    runSearchFromFirstPage()
  }, 450)
}

const sanitizeAmountInput = (field: AmountFilterField) => {
  const rawValue = filters[field]
  if (rawValue === null || rawValue === undefined) {
    scheduleAmountSearch()
    return
  }

  const text = String(rawValue)
    .replace(/，/g, '.')
    .replace(/[^\d.]/g, '')

  const firstDotIndex = text.indexOf('.')
  if (firstDotIndex === -1) {
    filters[field] = text
    scheduleAmountSearch()
    return
  }

  const integerPart = text.slice(0, firstDotIndex) || '0'
  const decimalPart = text.slice(firstDotIndex + 1).replace(/\./g, '').slice(0, 2)
  filters[field] = `${integerPart}.${decimalPart}`
  scheduleAmountSearch()
}

const setDropdownOpen = (field: DropdownFilterField, visible: boolean) => {
  openFilterDropdowns[field] = visible
}

const syncTableSelection = async () => {
  const table = invoiceTableRef.value
  if (!table) return

  isSyncingTableSelection.value = true
  table.clearSelection()
  for (const invoice of invoices.value) {
    if (invoiceStore.isSelected(invoice.id)) {
      table.toggleRowSelection(invoice, true)
    }
  }
  await nextTick()
  isSyncingTableSelection.value = false
}

type TagType = NonNullable<TagProps['type']>

const getOCRStatusType = (status: string): TagType => {
  const statusMap: Record<string, TagType> = {
    'pending': 'info',
    'processing': 'warning',
    'success': 'success',
    'failed': 'danger'
  }
  return statusMap[status] || 'info'
}

const getOCRStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    'pending': '待处理',
    'processing': '识别中',
    'success': '成功',
    'failed': '失败'
  }
  return statusMap[status] || '未知'
}

const getReimbursementStatusType = (status?: string): TagType => {
  const statusMap: Record<string, TagType> = {
    'unreimbursed': 'info',
    'reimbursed': 'success',
    'needs_reissue': 'danger',
    'processing': 'warning',
    'suspected_red_offset': 'danger'
  }
  return statusMap[status || 'unreimbursed'] || 'info'
}

const getReimbursementStatusText = (status?: string) => {
  const statusMap: Record<string, string> = {
    'unreimbursed': '未报销',
    'reimbursed': '已报销',
    'needs_reissue': '需换开',
    'processing': '报销中',
    'suspected_red_offset': '疑似红冲',
  }
  return statusMap[status || 'unreimbursed'] || '未报销'
}

const getFirstCommodityName = (invoice: Invoice) => {
  const detail = Array.isArray(invoice.commodity_details)
    ? invoice.commodity_details.find(item => item?.name || item?.word)
    : null
  if (detail?.name || detail?.word) {
    return String(detail.name || detail.word)
  }

  const rawNames = invoice.ocr_raw_data?.words_result?.CommodityName
  if (Array.isArray(rawNames)) {
    const first = rawNames.find(item => item?.word || typeof item === 'string')
    if (first) return typeof first === 'string' ? first : String(first.word)
  }

  return '-'
}

const getTrainTicketTime = (invoice: Invoice) => {
  const rawValue = invoice.ocr_raw_data?.words_result
  const raw = rawValue && typeof rawValue === 'object' ? rawValue : {}
  const isTrainTicket = invoice.ocr_raw_data?.ocr_document_type === 'train_ticket'
    || invoice.ocr_raw_data?.baidu_endpoint === 'train_ticket'
    || invoice.invoice_type?.includes('铁路')
    || invoice.invoice_type?.includes('火车票')
    || Boolean(raw.starting_station || raw.destination_station || raw.train_num)
  if (!isTrainTicket) return '-'

  const text = (value: any) => {
    if (value == null) return ''
    if (typeof value === 'string' || typeof value === 'number') return String(value).trim()
    if (typeof value === 'object') return String(value.word || value.words || value.text || '').trim()
    return ''
  }
  const combined = text(raw.TravelDateTime)
  if (combined) return combined
  const date = text(raw.TravelDate || raw.date || invoice.travel_date)
  const time = text(raw.TravelTime || raw.time || raw.Time || invoice.travel_time)
  return [date, time].filter(Boolean).join(' ') || '-'
}

// 格式化日期（仅日期部分）
const formatDate = (dateString: string) => {
  if (!dateString) return '-'
  // 如果是 ISO 字符串，直接截取前 10 位（YYYY-MM-DD）
  if (typeof dateString === 'string' && dateString.includes('T')) {
    return dateString.slice(0, 10)
  }
  // 兜底：解析为日期后按 YYYY-MM-DD 输出
  const date = new Date(dateString)
  if (Number.isNaN(date.getTime())) return '-'
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// 格式化金额
const formatAmount = (amount: any) => {
  if (amount == null || amount === '' || isNaN(amount)) {
    return '-'
  }
  return `¥${Number(amount).toFixed(2)}`
}

// 检查金额是否有效（用于CSS样式）
const hasValidAmount = (amount: any) => {
  return amount != null && amount !== '' && !isNaN(amount)
}

// 获取发票列表
const fetchInvoices = async () => {
  loading.value = true
  try {
    await invoiceStore.fetchInvoices({
      page: pagination.page,
      size: pagination.size,
      filters
    })
    
    pagination.total = invoiceStore.pagination.total
  } catch (error) {
    ElMessage.error('获取发票列表失败')
  } finally {
    loading.value = false
  }
}

// 搜索
const handleSearch = () => {
  clearAmountSearchTimer()
  runSearchFromFirstPage()
}

const handleFilterEnter = (event: KeyboardEvent) => {
  if (event.isComposing) return
  if (isAnyFilterDropdownOpen.value) return
  const target = event.target as HTMLElement | null
  if (target?.tagName.toLowerCase() === 'textarea') return

  event.preventDefault()
  event.stopPropagation()
  event.stopImmediatePropagation?.()
  handleSearch()
}

const handleClearSearch = () => {
  clearAmountSearchTimer()
  Object.assign(filters, createDefaultFilters())
  pagination.page = 1
  fetchInvoices()
}

// 选择变化
const handleSelectionChange = (selection: Invoice[]) => {
  if (isSyncingTableSelection.value) return
  invoiceStore.syncVisibleSelection(invoices.value, selection)
}

// 分页变化
const handleSizeChange = (size: number) => {
  pagination.size = size
  pagination.page = 1
  fetchInvoices()
}

const handleCurrentChange = (page: number) => {
  pagination.page = page
  fetchInvoices()
}

// 详情弹窗
const detailDialogVisible = ref(false)
const currentInvoice = ref<Invoice | null>(null)
const openDetail = (invoice: Invoice) => {
  currentInvoice.value = invoice
  detailDialogVisible.value = true
}

const updateReimbursementStatus = async (invoice: Invoice, reimbursementStatus: string) => {
  if (invoice.reimbursement_status === reimbursementStatus) return

  const previousStatus = invoice.reimbursement_status
  invoice.reimbursement_status = reimbursementStatus as Invoice['reimbursement_status']

  const success = await invoiceStore.updateInvoice(invoice.id, {
    reimbursement_status: invoice.reimbursement_status
  })

  if (success) {
    ElMessage.success('报销状态已更新')
  } else {
    invoice.reimbursement_status = previousStatus
    ElMessage.error('报销状态更新失败')
  }
}

const batchUpdateReimbursementStatus = async (reimbursementStatus: string) => {
  if (!selectedCount.value) return

  const targetStatus = reimbursementStatus as ReimbursementStatus
  const invoiceIds = [...selectedInvoiceIds.value]
  const selectionCount = selectedCount.value

  batchUpdating.value = true
  try {
    const updatedCount = await invoiceStore.batchUpdateReimbursementStatus(invoiceIds, targetStatus)
    if (updatedCount === null) {
      ElMessage.error('批量更新报销状态失败')
      return
    }

    ElMessage.success(`已将 ${selectionCount} 张发票标记为${getReimbursementStatusText(targetStatus)}，实际更新 ${updatedCount} 张`)
  } finally {
    batchUpdating.value = false
  }
}

const confirmClearSelection = async () => {
  if (!selectedCount.value) return

  try {
    await ElMessageBox.confirm(
      `确定清空已勾选的 ${selectedCount.value} 张发票吗？`,
      '清空选择',
      {
        confirmButtonText: '清空',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    invoiceStore.clearSelection()
    ElMessage.success('已清空选择')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('清空选择失败')
    }
  }
}

// 重试OCR
const retryOCR = async (id: string) => {
  try {
    const success = await invoiceStore.retryOCR(id)
    if (success) {
      ElMessage.success('OCR重试已启动')
      fetchInvoices()
    }
  } catch (error) {
    ElMessage.error('重试OCR失败')
  }
}

// 删除发票
const deleteInvoice = async (id: string) => {
  try {
    await ElMessageBox.confirm('确定要删除这张发票吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    const success = await invoiceStore.deleteInvoice(id)
    if (success) {
      ElMessage.success('删除成功')
      fetchInvoices()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

// 显示去重管理器（占位：未实现路由时给予提示或跳转列表自身）
const showDuplicateManager = () => {
  ElMessage.info('去重管理尚未实现，敬请期待')
}

const goToBatchPrint = () => {
  router.push('/print')
}

watch([invoices, selectedInvoiceIds], () => {
  void syncTableSelection()
}, { flush: 'post' })

onMounted(() => {
  loadColumnSettings()
  fetchFilterOptions()
  fetchInvoices()
})

onBeforeUnmount(() => {
  clearAmountSearchTimer()
})


// 下载发票原始文件
const downloadInvoice = async (id: string, filename?: string) => {
  try {
    const response = await apiDownloadInvoice(id)
    const blob = new Blob([response.data], { type: 'application/pdf' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename || `${id}.pdf`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error('下载失败')
  }
}

const downloadSelectedInvoices = async () => {
  if (!selectedCount.value || batchDownloading.value) return

  batchDownloading.value = true
  try {
    const response = await apiDownloadInvoices([...selectedInvoiceIds.value])
    const blob = new Blob([response.data], { type: 'application/zip' })
    const url = window.URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `invoices_${selectedCount.value}_${new Date().toISOString().slice(0, 10)}.zip`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    window.URL.revokeObjectURL(url)
    ElMessage.success(`已打包下载 ${selectedCount.value} 张发票`)
  } catch (error) {
    ElMessage.error('打包下载失败')
  } finally {
    batchDownloading.value = false
  }
}
</script>

 

<style scoped>
.page-container {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 60px);
  height: auto;
  overflow: visible;
}

.filter-form {
  flex: 0 0 auto;
}

.table-container {
  display: flex;
  flex: 0 0 auto;
  min-height: 0;
  min-width: 0;
  overflow: visible;
}

.invoice-list-card {
  display: flex;
  flex: 0 0 auto;
  width: 100%;
  min-width: 0;
  flex-direction: column;
}

.invoice-list-card :deep(.el-card__header) {
  flex: 0 0 auto;
}

.invoice-list-card :deep(.el-card__body) {
  display: flex;
  flex: 0 0 auto;
  min-width: 0;
  flex-direction: column;
  overflow: visible;
}

.filename {
  display: inline-block;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.amount {
  font-weight: 600;
  color: var(--el-color-danger);
}

.full-width-item :deep(.el-form-item__content) {
  width: 100%;
}

.filter-action-bar :deep(.el-form-item__content) {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.selection-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 36px;
  padding: 8px 12px;
  margin-bottom: 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background: var(--el-fill-color-light);
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.selection-summary-text {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
}

.selection-summary-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.table-header-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.column-settings-panel {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.column-settings-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-weight: 600;
}

.column-settings-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 32px;
}

.column-settings-order {
  display: flex;
  align-items: center;
  gap: 2px;
}

.column-settings-fixed {
  padding-top: 6px;
  border-top: 1px solid var(--el-border-color-lighter);
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.invoice-table-scroll {
  flex: 0 0 auto;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  height: 560px;
  overflow: hidden;
}

.invoice-table-scroll :deep(.el-table) {
  width: 100%;
  height: 100%;
}

.invoice-table-scroll :deep(.el-table__body-wrapper) {
  overflow-x: auto;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.invoice-table-scroll :deep(.el-table__header-wrapper) {
  overflow: hidden;
}

.invoice-table-scroll :deep(.el-table__header-wrapper table),
.invoice-table-scroll :deep(.el-table__body-wrapper table) {
  min-width: 1300px;
}

.pagination-container {
  flex: 0 0 auto;
}

.train-ticket-time {
  font-variant-numeric: tabular-nums;
  color: var(--el-color-primary);
}

.commodity-name {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
  white-space: nowrap;
}

.status-tag {
  cursor: pointer;
}

@media (max-width: 768px) {
  .more-filters-row :deep(.el-col) {
    flex: 0 0 100%;
    max-width: 100%;
  }

  .selection-summary {
    align-items: flex-start;
    flex-direction: column;
  }

  .selection-summary-actions {
    width: 100%;
  }

  .invoice-table-scroll {
    margin-right: -16px;
    padding-right: 16px;
  }
}
</style>
