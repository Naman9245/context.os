// Thin fetch wrapper for the FastAPI backend. All routes live under /api.

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      // not JSON - keep the status text
    }
    throw new ApiError(res.status, detail)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
}

export type Health = {
  status: string
  version: string
  llm_provider: 'none' | 'gemini' | 'groq'
  llm_model: string | null
  ocr_available: boolean
  watching: boolean
  notifications_available: boolean
  reminder_days: number[]
  library_root: string
  watch_dirs: string[]
}

export type DocType =
  | 'notes'
  | 'slides'
  | 'assignment'
  | 'question_paper'
  | 'lab'
  | 'syllabus'
  | 'notice'
  | 'other'

export type Deadline = {
  id: number
  title: string
  due_at: string | null
  status: 'suggested' | 'todo' | 'done'
}

export type Doc = {
  id: number
  filename: string
  current_path: string
  planned_path: string | null
  destination: string | null
  doc_type: DocType
  subject_id: number | null
  subject: string | null
  subject_color: string | null
  title: string | null
  semester: string | null
  confidence: number
  classified_by: string | null
  extraction: string | null
  error: string | null
  status: 'new' | 'planned' | 'organized' | 'skipped'
  deadlines: Deadline[]
  updated_at: string
}

export type ScanReport = {
  found: number
  new: number
  unchanged: number
  duplicates: { path: string; same_as: string }[]
  errors: { path: string; error: string }[]
  used_llm: number
  llm_errors: number
  deadlines: number
}

export type ScanStatus = {
  running: boolean
  done: number
  total: number
  current: string
  started_at: string | null
  finished_at: string | null
  report: ScanReport | null
  error: string | null
  pending: number
}

export type MoveResult = { batch_id: string; moved: number[]; failed: Record<string, string> }

export type Batch = { batch_id: string; count: number; moved_at: string; undone: boolean }

export type Subject = {
  id: number
  name: string
  code: string | null
  aliases: string[]
  semester: string | null
  color: string | null
  documents: number
}

export type TaskStatus = 'suggested' | 'todo' | 'done' | 'dismissed'

export type Step = { id: number; text: string; done: boolean; written_by: string }

export type Task = {
  id: number
  title: string
  notes: string | null
  subject_id: number | null
  subject: string | null
  subject_color: string | null
  due_at: string | null
  days_left: number | null
  status: TaskStatus
  source: 'manual' | 'chat' | 'extracted'
  document_id: number | null
  document_name: string | null
  steps: Step[]
  completed_at: string | null
}

export type Briefing = {
  name: string
  greeting: string
  lines: { text: string; link: string | null; tone: 'info' | 'warn' | 'good' }[]
  counts: Record<string, number>
}

export type ChatAction = { label: string; ok: boolean; url?: string | null }

export type ChatMessage = {
  id: number
  role: 'user' | 'khushi'
  text: string
  created_at: string
  actions: ChatAction[]
  suggestions: string[]
  by: string | null
  tasks: Task[]
  files: Doc[]
}

export type ChatExchange = { user: ChatMessage; reply: ChatMessage }
