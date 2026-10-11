export interface Patient {
  id: string; user_id: string; full_name: string; email: string; date_of_birth: string | null
  gender: string | null; blood_group: string | null; contact_phone: string | null
  emergency_contact: string | null; preferred_language: 'en' | 'ta'; external_ai_consent: boolean
}
export interface Document {
  id: string; original_filename: string; document_type: string; document_date: string | null
  processing_status: string; summary_status: string; index_status: string; error_message: string | null
  revision: number; approved_revision: number | null; created_at: string
}
export interface CandidateObservation {
  id: string; test_name: string; value_numeric: number | null; value_text?: string | null
  unit: string | null; reference_low: number | null; reference_high: number | null
  source_abnormal_flag: string | null; source_text: string; page?: number | null
  confidence?: string; validation_status?: string
}
export interface CandidateMedication {
  id: string; medication_name: string; generic_name: string | null; strength: string | null
  dose_instructions: string | null; route: string | null; frequency: string | null; duration: string | null
  prescription_date: string | null; source_text: string; page?: number | null
}
export interface Candidate {
  document_type: string; document_date: string | null; healthcare_provider: string | null
  practitioner_name: string | null; observations: CandidateObservation[]; medications: CandidateMedication[]
  unreadable_segments: string[]
}
export interface Extraction {
  id: string; document_id: string; revision: number; structured_candidate_data: Candidate
  raw_ocr_text: string; extraction_provider: string; provider_model: string; review_status: string
}
export interface Observation {
  id: string; document_id: string; display_name: string; value_numeric: number | null; value_text: string | null
  unit: string | null; effective_at: string | null; reference_low: number | null; reference_high: number | null
  source_abnormal_flag: string | null
}
export interface Medication extends Omit<CandidateMedication, 'page'> {
  document_id: string; medication_status: string
}
export interface Citation { id: string; document_id: string; revision: number; filename: string; page: number | null; excerpt: string; url: string }
export interface Summary {
  overview: string; key_findings: string[]; citations: Citation[]; safety_disclaimer: string
  provider_model: string; language: string
}
export interface Conversation { id: string; title: string; created_at: string }
export interface Message {
  id: string; role: 'user' | 'assistant'; created_at: string
  data: { question?: string; status?: string; answer?: string; language: string; citations?: Citation[]; provider_model?: string; safety_disclaimer?: string }
}
export interface Trend { test_name: string; unit: string | null; history: { date: string; value: number; source_document_id: string; reference_low?: number | null; reference_high?: number | null }[] }
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}
let csrf = ''
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (options.method && options.method !== 'GET') headers.set('X-CSRF-Token', csrf)
  const result = await fetch('/api/v1' + path, { ...options, headers, credentials: 'same-origin' })
  const body = await result.json().catch(() => ({}))
  if (!result.ok) {
    if (result.status === 401 && path !== '/auth/login' && path !== '/auth/session') window.dispatchEvent(new Event('health-session-expired'))
    const message = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map((item: { msg: string }) => item.msg).join('; ') : 'Request failed. Please try again.'
    throw new ApiError(result.status, message)
  }
  return body as T
}
export const api = {
  async session() {
    try { const data = await request<{ patient: Patient; csrf_token: string }>('/auth/session'); csrf = data.csrf_token; return data.patient }
    catch (error) { if (error instanceof ApiError && error.status === 401) return null; throw error }
  },
  async login(email: string, password: string) {
    const data = await request<{ patient: Patient; csrf_token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
    csrf = data.csrf_token; return data.patient
  },
  async register(full_name: string, email: string, password: string, confirm_password: string) {
    const data = await request<{ patient: Patient; csrf_token: string }>('/auth/register', { method: 'POST', body: JSON.stringify({ full_name, email, password, confirm_password }) })
    csrf = data.csrf_token; return data.patient
  },
  logout: () => request('/auth/logout', { method: 'POST' }),
  profile: (data: Partial<Patient>) => request<Patient>('/patient/me', { method: 'PATCH', body: JSON.stringify(data) }),
  documents: (offset = 0) => request<Document[]>('/documents?limit=50&offset=' + offset),
  async upload(file: File) { const form = new FormData(); form.append('file', file); return request<Document>('/documents', { method: 'POST', body: form }) },
  remove: (id: string) => request('/documents/' + id, { method: 'DELETE' }),
  retry: (id: string) => request('/documents/' + id + '/process', { method: 'POST' }),
  index: (id: string) => request('/documents/' + id + '/index', { method: 'POST' }),
  extraction: (id: string) => request<Extraction>('/documents/' + id + '/extraction'),
  edit: (id: string, revision: number, data: Candidate) => request<Extraction>('/documents/' + id + '/extraction', { method: 'PATCH', body: JSON.stringify({ revision, structured_candidate_data: data }) }),
  confirm: (id: string, revision: number, observation_ids: string[], medication_ids: string[], active_medications: string[]) => request('/documents/' + id + '/confirm', { method: 'POST', body: JSON.stringify({ revision, observation_ids, medication_ids, active_medications }) }),
  summary: (id: string, language: string) => request<Summary>('/documents/' + id + '/summary?lang=' + language),
  generate: (id: string) => request('/documents/' + id + '/summary', { method: 'POST' }),
  observations: () => request<Observation[]>('/observations'),
  medications: () => request<Medication[]>('/medications'),
  medication: (id: string, medication_status: string) => request('/medications/' + id, { method: 'PATCH', body: JSON.stringify({ medication_status }) }),
  trends: () => request<Trend[]>('/observations/trends'),
  conversations: () => request<Conversation[]>('/rag/conversations'),
  conversation: () => request<Conversation>('/rag/conversations', { method: 'POST', body: JSON.stringify({ title: 'Health records' }) }),
  messages: (id: string) => request<Message[]>('/rag/conversations/' + id + '/messages'),
  ask: (id: string, question: string, language: string) => request<Message>('/rag/conversations/' + id + '/messages', { method: 'POST', body: JSON.stringify({ question, language }) }),
}
