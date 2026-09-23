<template>
  <div class="invoice-detail">
    <div class="page-header">
      <h1 class="page-title">发票详情</h1>
      <el-button @click="$router.back()">
        <el-icon><ArrowLeft /></el-icon>
        返回
      </el-button>
    </div>
    
    <el-card v-loading="loading">
      <div v-if="invoice">
        <el-descriptions title="发票信息" :column="2" border>
          <el-descriptions-item label="文件名">
            {{ invoice.original_filename }}
          </el-descriptions-item>
          <el-descriptions-item label="发票代码">
            {{ invoice.invoice_code || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="发票号码">
            {{ invoice.invoice_num || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="开票日期">
            {{ invoice.invoice_date ? formatDate(invoice.invoice_date) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="乘车时间">
            {{ getTrainTicketTime(invoice) }}
          </el-descriptions-item>
          <el-descriptions-item label="销售方">
            {{ invoice.seller_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="购买方">
            {{ invoice.purchaser_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="总金额">
            {{ invoice.total_amount ? `¥${invoice.total_amount}` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="消费类型">
            {{ invoice.service_type ? `${invoice.service_type}` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="报销状态">
            <el-tag :type="getReimbursementStatusType(invoice.reimbursement_status)">
              {{ getReimbursementStatusText(invoice.reimbursement_status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="OCR状态">
            <el-tag :type="getOCRStatusType(invoice.ocr_status)">
              {{ getOCRStatusText(invoice.ocr_status) }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="commodityRows.length" class="commodity-section">
          <div class="commodity-title">商品明细</div>
          <el-table :data="commodityRows" size="small" border>
            <el-table-column prop="row" label="行" width="60" />
            <el-table-column prop="name" label="商品名称" min-width="220" show-overflow-tooltip />
            <el-table-column prop="amount" label="金额" width="120" />
            <el-table-column prop="tax_rate" label="税率" width="100" />
            <el-table-column prop="tax" label="税额" width="120" />
          </el-table>
        </div>
      </div>
      
      <div v-else class="empty-state">
        <el-empty description="发票不存在或已被删除" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { useInvoiceStore } from '@/stores/invoice'
import type { Invoice } from '@/types/invoice'

const route = useRoute()
const invoiceStore = useInvoiceStore()

const loading = ref(false)
const invoice = ref<Invoice | null>(null)

import type { TagProps } from 'element-plus'
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
    'suspected_red_offset': '疑似红冲'
  }
  return statusMap[status || 'unreimbursed'] || '未报销'
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

const commodityRows = computed(() => {
  const details = invoice.value?.commodity_details
  if (Array.isArray(details) && details.length) {
    return details.map((item, index) => ({
      row: item?.row || String(index + 1),
      name: item?.name || item?.word || '-',
      amount: item?.amount || '-',
      tax_rate: item?.tax_rate || '-',
      tax: item?.tax || '-'
    }))
  }

  const raw = invoice.value?.ocr_raw_data?.words_result
  const names = raw?.CommodityName
  if (!Array.isArray(names)) return []

  return names.map((item: any, index: number) => ({
    row: String(index + 1),
    name: typeof item === 'string' ? item : item?.word || '-',
    amount: raw?.CommodityAmount?.[index]?.word || '-',
    tax_rate: raw?.CommodityTaxRate?.[index]?.word || '-',
    tax: raw?.CommodityTax?.[index]?.word || '-'
  }))
})

const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleDateString('zh-CN')
}

const fetchInvoiceDetail = async () => {
  const id = route.params.id as string
  if (!id) return
  
  loading.value = true
  try {
    await invoiceStore.fetchInvoice(id)
    invoice.value = invoiceStore.currentInvoice
  } catch (error) {
    console.error('获取发票详情失败:', error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchInvoiceDetail()
})
</script>

<style scoped>
.invoice-detail {
  padding: 20px;
}

.empty-state {
  text-align: center;
  padding: 40px 0;
}

.commodity-section {
  margin-top: 16px;
}

.commodity-title {
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
</style>
