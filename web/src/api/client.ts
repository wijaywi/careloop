export type ApiCase = {
  id: string
  status: string
  stage: string
  owner_id: string
}

export type ApiHealth = {
  status: string
  service: string
}

export type ApiCaseSummary = {
  id: string
  title: string
  status: string
  stage: string
  owner_id: string
  patient_id: string
}

export type ApiCaseList = {
  items: ApiCaseSummary[]
  count: number
}

export type ApiEvidence = {
  id: string
  case_id: string
  kind: string
  summary: string
  recorded_by: string
  recorded_at: string
}

export type ApiConsent = {
  consent_id?: string
  id?: string
  case_id: string
  scope: string
  granted: boolean
  recorded_by?: string
  recorded_at: string
}

export type ApiAppointment = {
  id?: string
  appointment_id?: string
  case_id: string
  scheduled_for: string
  created_by?: string
  created_at?: string
}

export type ApiEscalation = {
  id: string
  case_id: string
  reason: string
  target_role: string
  level: number
  created_at: string
}

export type ApiHandoff = {
  id: string
  case_id: string
  from_user: string
  to_user: string
  note?: string
  status?: string
  created_at?: string
}

export type ApiTransportEvent = {
  loop_id: string
  event_type: string
  timestamp: string
  reporter_org: string
  owner_next: string
  due_at: string
  evidence_ref?: string
}

export type ApiCaseDetail = {
  id: string
  title: string
  loop_id: string
  patient_id: string
  owner_id: string
  owner_next: string
  status: string
  stage: string
  urgency: string
  high_risk: boolean
  closure_code: string | null
  closure_basis: string | null
  reporter_org: string
  evidence_refs: string[]
  authorization_id: string | null
  created_at: string
  opened_at: string
  due_at: string
  closed_at: string | null
  events: ApiTransportEvent[]
  consents: ApiConsent[]
  evidence: ApiEvidence[]
  escalations: ApiEscalation[]
  handoffs: ApiHandoff[]
  appointments: ApiAppointment[]
}

export type ApiFhirBundle = {
  resourceType: string
  type: string
  label: string
  conformance_tested: boolean
  entry: { resource: Record<string, unknown> }[]
}

export type ApiAuditItem = {
  id: number
  case_id: string
  actor_id: string
  action: string
  payload: Record<string, unknown>
  created_at: string
}

export type ApiAuditList = {
  items: ApiAuditItem[]
  count?: number
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api'

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(body.error ?? `CareLoop API request failed (${response.status})`)
  }
  return body as T
}

export const careLoopApi = {
  health(): Promise<ApiHealth> {
    return request<ApiHealth>('/health')
  },

  seedDemo(): Promise<Record<string, unknown>> {
    return request('/demo/seed', {
      method: 'POST',
      body: JSON.stringify({ seed: 20261019, case_count: 12 }),
    })
  },

  listCases(actorId: string): Promise<ApiCaseList> {
    return request<ApiCaseList>(`/cases?actor_id=${encodeURIComponent(actorId)}`)
  },

  getCase(caseId: string, actorId: string): Promise<ApiCaseDetail> {
    return request<ApiCaseDetail>(`/cases/${encodeURIComponent(caseId)}`, { headers: { 'X-Actor-ID': actorId } })
  },

  listAudit(actorId: string, caseId?: string): Promise<ApiAuditList> {
    const path = caseId ? `/cases/${encodeURIComponent(caseId)}/audit` : `/audit`
    return request<ApiAuditList>(path, { headers: { 'X-Actor-ID': actorId } })
  },

  fhirExport(caseId: string, actorId: string): Promise<ApiFhirBundle> {
    return request<ApiFhirBundle>(`/cases/${encodeURIComponent(caseId)}/fhir`, { headers: { 'X-Actor-ID': actorId } })
  },

  createCase(input: { id: string; patient_id: string; title: string; owner_id: string; urgency?: string }, actorId: string): Promise<ApiCaseSummary> {
    return request<ApiCaseSummary>('/cases', {
      method: 'POST',
      headers: { 'X-Actor-ID': actorId },
      body: JSON.stringify(input),
    })
  },

  action<T = ApiCase>(caseId: string, actorId: string, action: string, payload: Record<string, unknown> = {}): Promise<T> {
    return request<T>(`/cases/${encodeURIComponent(caseId)}/actions`, {
      method: 'POST',
      headers: { 'X-Actor-ID': actorId },
      body: JSON.stringify({ action, payload }),
    })
  },
}
