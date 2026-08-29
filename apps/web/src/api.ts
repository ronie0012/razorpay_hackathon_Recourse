import type { Analysis, AuditEvent, CaseDetail, CaseSummary, EvaluationReport, SurgeryResult } from './types'

const json = async <T>(response: Response): Promise<T> => {
  const payload = await response.json()
  if (!response.ok) throw new Error(payload?.error?.message ?? `API request failed (${response.status})`)
  return payload as T
}

export const api = {
  listCases: (): Promise<CaseSummary[]> => fetch('/api/v1/cases').then(json<CaseSummary[]>),
  resetDemo: (): Promise<{ case_ids: string[]; count: number; mode_label: string }> => fetch('/api/v1/demo/reset', { method: 'POST' }).then(json<{ case_ids: string[]; count: number; mode_label: string }>),
  caseDetail: (id: string): Promise<CaseDetail> => fetch(`/api/v1/cases/${id}`).then(json<CaseDetail>),
  analyze: (id: string): Promise<Analysis> => fetch(`/api/v1/cases/${id}/analyze`, { method: 'POST' }).then(json<Analysis>),
  execute: (id: string): Promise<{ executed: boolean; reason: string; error?: string; state?: string; mode_label?: string }> => fetch(`/api/v1/cases/${id}/execute`, { method: 'POST' }).then(json<{ executed: boolean; reason: string; error?: string; state?: string; mode_label?: string }>),
  audit: (id: string): Promise<AuditEvent[]> => fetch(`/api/v1/cases/${id}/audit`).then(json<AuditEvent[]>),
  surgery: (id: string, mutations: Record<string, unknown>): Promise<SurgeryResult> => fetch(`/api/v1/cases/${id}/surgery`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(mutations),
  }).then(json<SurgeryResult>),
  evaluation: (): Promise<EvaluationReport> => fetch('/api/v1/evaluation').then(json<EvaluationReport>),
}
