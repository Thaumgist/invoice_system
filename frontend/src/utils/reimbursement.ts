import type { TagProps } from 'element-plus'

const reimbursementStatusTypes: Record<string, NonNullable<TagProps['type']>> = {
  unreimbursed: 'info',
  reimbursed: 'success',
  needs_reissue: 'danger',
  rejected: 'danger',
  processing: 'warning',
  suspected_red_offset: 'danger',
}

export const getReimbursementStatusType = (status?: string) => (
  reimbursementStatusTypes[status || 'unreimbursed'] || 'info'
)
