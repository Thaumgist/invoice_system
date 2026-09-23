import { defineStore } from 'pinia'
import type { Invoice, InvoiceFilter, InvoiceListResponse, InvoiceUpdate, ReimbursementStatus } from '@/types/invoice'
import { 
  getInvoices, 
  getInvoice, 
  updateInvoice, 
  batchUpdateReimbursementStatus,
  deleteInvoice, 
  uploadInvoice, 
  retryOCR 
} from '@/api/invoice'

interface InvoiceState {
  invoices: Invoice[]
  currentInvoice: Invoice | null
  loading: boolean
  filters: InvoiceFilter
  pagination: {
    page: number
    size: number
      total: number
      pages: number
  }
  selectedInvoiceMap: Record<string, Invoice>
}

export const useInvoiceStore = defineStore('invoice', {
  state: (): InvoiceState => ({
    invoices: [],
    currentInvoice: null,
    loading: false,
    filters: {},
    pagination: {
      page: 1,
      size: 20,
      total: 0,
      pages: 0
    },
    selectedInvoiceMap: {}
  }),
  
  getters: {
    filteredInvoices: (state) => state.invoices,
    selectedInvoices: (state) => Object.values(state.selectedInvoiceMap),
    selectedInvoiceIds: (state) => Object.keys(state.selectedInvoiceMap),
    hasSelected: (state) => Object.keys(state.selectedInvoiceMap).length > 0,
    selectedCount: (state) => Object.keys(state.selectedInvoiceMap).length,
    selectedTotalAmount: (state) => Object.values(state.selectedInvoiceMap).reduce((total, invoice) => {
      const amount = invoice.amount_in_figures ?? invoice.total_amount
      const numericAmount = Number(amount)
      return Number.isFinite(numericAmount) ? total + numericAmount : total
    }, 0),
  },
  
  actions: {
    async fetchInvoices(params?: {
      page?: number
      size?: number
      filters?: InvoiceFilter
    }): Promise<void> {
      this.loading = true
      try {
        const { page = 1, size = 20, filters = {} } = params || {}
        
        const response = await getInvoices({
          page,
          size,
          ...filters,
          include_duplicates: (filters as any).include_duplicates ?? false,
        })
        
        const data: InvoiceListResponse = response.data
        
        this.invoices = data.items
        for (const invoice of data.items) {
          if (this.selectedInvoiceMap[invoice.id]) {
            this.selectedInvoiceMap[invoice.id] = invoice
          }
        }
        this.pagination = {
          page: data.page,
          size: data.size,
          total: data.total,
          pages: data.pages
        }
        this.filters = filters
      } catch (error) {
        console.error('获取发票列表失败:', error)
      } finally {
        this.loading = false
      }
    },
    
    async fetchInvoice(id: string): Promise<void> {
      try {
        const response = await getInvoice(id)
        this.currentInvoice = response.data
      } catch (error) {
        console.error('获取发票详情失败:', error)
      }
    },
    
    async uploadInvoice(file: File): Promise<boolean> {
      try {
        const response = await uploadInvoice(file)
        await this.fetchInvoices()
        return true
      } catch (error) {
        console.error('上传发票失败:', error)
        return false
      }
    },
    
    async updateInvoice(id: string, data: InvoiceUpdate): Promise<boolean> {
      try {
        const response = await updateInvoice(id, data)
        
        // 更新本地状态
        const index = this.invoices.findIndex(invoice => invoice.id === id)
        if (index !== -1) {
          this.invoices[index] = response.data
        }
        
        if (this.currentInvoice?.id === id) {
          this.currentInvoice = response.data
        }

        if (this.selectedInvoiceMap[id]) {
          this.selectedInvoiceMap[id] = response.data
        }
        
        return true
      } catch (error) {
        console.error('更新发票失败:', error)
        return false
      }
    },

    async batchUpdateReimbursementStatus(invoiceIds: string[], reimbursementStatus: ReimbursementStatus): Promise<number | null> {
      try {
        const response = await batchUpdateReimbursementStatus({
          invoice_ids: invoiceIds,
          reimbursement_status: reimbursementStatus
        })

        const invoiceIdSet = new Set(invoiceIds)
        this.invoices = this.invoices.map(invoice => (
          invoiceIdSet.has(invoice.id)
            ? { ...invoice, reimbursement_status: reimbursementStatus }
            : invoice
        ))

        if (this.currentInvoice && invoiceIdSet.has(this.currentInvoice.id)) {
          this.currentInvoice = {
            ...this.currentInvoice,
            reimbursement_status: reimbursementStatus
          }
        }

        for (const invoiceId of invoiceIds) {
          const selectedInvoice = this.selectedInvoiceMap[invoiceId]
          if (!selectedInvoice) continue
          this.selectedInvoiceMap[invoiceId] = {
            ...selectedInvoice,
            reimbursement_status: reimbursementStatus
          }
        }

        return response.data.updated_count
      } catch (error) {
        console.error('批量更新报销状态失败:', error)
        return null
      }
    },
    
    async deleteInvoice(id: string): Promise<boolean> {
      try {
        await deleteInvoice(id)
        
        // 从本地状态中移除
        this.invoices = this.invoices.filter(invoice => invoice.id !== id)
        delete this.selectedInvoiceMap[id]
        
        if (this.currentInvoice?.id === id) {
          this.currentInvoice = null
        }
        
        return true
      } catch (error) {
        console.error('删除发票失败:', error)
        return false
      }
    },
    
    async retryOCR(id: string, force: boolean = false): Promise<boolean> {
      try {
        await retryOCR(id, { force })
        
        // 更新发票状态
        const invoice = this.invoices.find(inv => inv.id === id)
        if (invoice) {
          invoice.ocr_status = 'pending'
          invoice.ocr_error_message = undefined
        }

        if (this.selectedInvoiceMap[id]) {
          this.selectedInvoiceMap[id] = {
            ...this.selectedInvoiceMap[id],
            ocr_status: 'pending',
            ocr_error_message: undefined
          }
        }
        
        return true
      } catch (error) {
        console.error('重试OCR失败:', error)
        return false
      }
    },
    
    setFilters(filters: InvoiceFilter): void {
      this.filters = { ...filters }
    },
    
    syncVisibleSelection(visibleInvoices: Invoice[], selectedVisibleInvoices: Invoice[]): void {
      const visibleIdSet = new Set(visibleInvoices.map(invoice => invoice.id))
      const selectedVisibleInvoiceMap = new Map(
        selectedVisibleInvoices.map(invoice => [invoice.id, invoice] as const)
      )

      for (const invoiceId of visibleIdSet) {
        if (!selectedVisibleInvoiceMap.has(invoiceId)) {
          delete this.selectedInvoiceMap[invoiceId]
        }
      }

      for (const invoice of selectedVisibleInvoices) {
        this.selectedInvoiceMap[invoice.id] = invoice
      }
    },

    setInvoiceSelected(invoice: Invoice, selected: boolean): void {
      if (selected) {
        this.selectedInvoiceMap[invoice.id] = invoice
        return
      }

      delete this.selectedInvoiceMap[invoice.id]
    },
    
    clearSelection(): void {
      this.selectedInvoiceMap = {}
    },
    
    isSelected(id: string): boolean {
      return Boolean(this.selectedInvoiceMap[id])
    }
  }
})
