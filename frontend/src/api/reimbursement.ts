import type { Invoice } from '@/types/invoice'
import api from '@/utils/request'

export interface ReimbursementNumber {
  invoice_num: string
  pages: number[]
  occurrences: number
  confidence?: number | null
  source: 'text' | 'ocr' | 'manual'
}

export interface ReimbursementJob {
  id: string
  filename: string
  status: 'pending' | 'processing' | 'completed' | 'failed' | string
  page_count: number
  completed_pages: number
  numbers: ReimbursementNumber[]
  error_message?: string
  created_at: string
}

export interface ReimbursementMatch {
  invoice_num: string
  status: 'matched' | 'not_found' | 'ambiguous'
  invoices: Pick<Invoice, 'id' | 'original_filename' | 'invoice_num' | 'seller_name' | 'invoice_date' | 'total_amount' | 'amount_in_figures'>[]
}

export interface ReimbursementReportInvoice {
  id: string
  original_filename: string
  invoice_num?: string
  seller_name?: string
  invoice_date?: string
  total_amount?: number
  amount_in_figures?: number
  reimbursement_status?: Invoice['reimbursement_status']
}

export interface ReimbursementReport {
  id: string
  name: string
  source_job_id: string
  file_available: boolean
  invoice_count: number
  total_amount: number
  invoices: ReimbursementReportInvoice[]
  created_at: string
  updated_at: string
}

export interface ReimbursementAmountSolution {
  invoice_ids: string[]
  invoice_nums: string[]
  total_amount: number
  invoice_count: number
}

export const uploadReimbursement = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post<ReimbursementJob>('/reimbursements/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data', 'X-Suppress-Error-Toast': 'true' },
    timeout: 30000,
  })
}

export const getReimbursements = () => api.get<ReimbursementJob[]>('/reimbursements/')
export const getReimbursement = (id: string) => api.get<ReimbursementJob>(`/reimbursements/${id}`)
export const matchReimbursement = (id: string, invoiceNums: string[]) => api.post<{ items: ReimbursementMatch[] }>(
  `/reimbursements/${id}/match`, { invoice_nums: invoiceNums },
  { headers: { 'X-Suppress-Error-Toast': 'true' } },
)
export const deleteReimbursement = (id: string) => api.delete(`/reimbursements/${id}`)
export const createReimbursementReport = (data: { name?: string; source_job_id: string; items: { invoice_id: string; invoice_num: string }[] }) => api.post<ReimbursementReport>('/reimbursements/reports', data)
export const getReimbursementReports = () => api.get<ReimbursementReport[]>('/reimbursements/reports')
export const getReimbursementReport = (id: string) => api.get<ReimbursementReport>(`/reimbursements/reports/${id}`)
export const addReportInvoices = (id: string, invoiceIds: string[]) => api.post<ReimbursementReport>(`/reimbursements/reports/${id}/invoices`, { invoice_ids: invoiceIds })
export const removeReportInvoice = (reportId: string, invoiceId: string) => api.delete<ReimbursementReport>(`/reimbursements/reports/${reportId}/invoices/${invoiceId}`)
export const deleteReimbursementReport = (id: string) => api.delete(`/reimbursements/reports/${id}`)
export const getReimbursementReportFile = (id: string) => api.get<Blob>(`/reimbursements/reports/${id}/file`, { responseType: 'blob' } as any)
export const findReimbursementAmountSolution = (id: string, amount: number | string) => api.post<{ target_amount: number; solution: ReimbursementAmountSolution | null }>(`/reimbursements/reports/${id}/amount-solution`, { amount })
