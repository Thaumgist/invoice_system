import type { 
  Invoice, 
  InvoiceFilter, 
  InvoiceListResponse, 
  InvoiceUploadResponse,
  InvoiceUpdate,
  BatchReimbursementStatusUpdate,
  BatchReimbursementStatusUpdateResponse
} from '@/types/invoice'
import api from '@/utils/request'

// 上传发票
export const uploadInvoice = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  
  return api.post<InvoiceUploadResponse>('/invoices/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

// 获取发票列表
export const getInvoices = (params: {
  page?: number
  size?: number
  status?: string
  ocr_status?: string
  seller_name?: string
  purchaser_name?: string
  service_type?: string
  commodity_name?: string
  reimbursement_status?: string
  amount_exact?: number | string
  amount_min?: number | string
  amount_max?: number | string
  // Excel 风格多选
  seller_names?: string[]
  purchaser_names?: string[]
  service_types?: string[]
  include_duplicates?: boolean
  [key: string]: any
}) => {
  const normalizeAmountFilter = (value: unknown) => {
    if (value === '' || value === null || value === undefined) return undefined
    const text = String(value).trim().replace(/，/g, '.')
    const normalizedText = text.startsWith('.') ? `0${text}` : text
    if (!/^\d+(\.\d{0,2})?$/.test(normalizedText)) return undefined
    const [integerPart, decimalPart = ''] = normalizedText.split('.')
    return `${integerPart}.${decimalPart.padEnd(2, '0')}`
  }

  const body: any = {
    page: params.page ?? 1,
    size: params.size ?? 20,
    status: params.status,
    ocr_status: params.ocr_status,
    seller_name: params.seller_name,
    purchaser_name: params.purchaser_name,
    service_type: params.service_type,
    commodity_name: params.commodity_name,
    reimbursement_status: params.reimbursement_status,
    amount_exact: normalizeAmountFilter(params.amount_exact),
    amount_min: normalizeAmountFilter(params.amount_min),
    amount_max: normalizeAmountFilter(params.amount_max),
    seller_names: params.seller_names,
    purchaser_names: params.purchaser_names,
    service_types: params.service_types,
    include_duplicates: params.include_duplicates ?? false
  }
  return api.post<InvoiceListResponse>('/invoices/search', body)
}

// 获取发票筛选器选项
export const getInvoiceFilterOptions = () => {
  return api.get<{
    sellers: string[]
    purchasers: string[]
    service_types: string[]
  }>('/invoices/filters/options')
}

// 获取发票详情
export const getInvoice = (id: string) => {
  return api.get<Invoice>(`/invoices/${id}`)
}

// 下载发票原始文件
export const downloadInvoice = (id: string) => {
  return api.get<Blob>(`/invoices/${id}/download`, {
    responseType: 'blob'
  } as any)
}

// 打包下载多张发票原始文件
export const downloadInvoices = (invoiceIds: string[]) => {
  return api.post<Blob>('/invoices/batch/download', { invoice_ids: invoiceIds }, {
    responseType: 'blob'
  } as any)
}

// 更新发票信息
export const updateInvoice = (id: string, data: InvoiceUpdate) => {
  return api.put<Invoice>(`/invoices/${id}`, data)
}

// 批量更新报销状态
export const batchUpdateReimbursementStatus = (data: BatchReimbursementStatusUpdate) => {
  return api.post<BatchReimbursementStatusUpdateResponse>('/invoices/batch/reimbursement-status', data)
}

// 删除发票
export const deleteInvoice = (id: string) => {
  return api.delete(`/invoices/${id}`)
}

// 重试OCR识别
export const retryOCR = (id: string, data: { force?: boolean } = {}) => {
  return api.post(`/invoices/${id}/retry-ocr`, data)
}

// 添加发票附件
export const addAttachment = (id: string, file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  
  return api.post(`/invoices/${id}/attachments`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}
