/** Thin typed wrappers over the REST API. Every failure surfaces as ApiError so the UI
 * can show `message` and never a raw stack. */
import type {
  ApiErrorBody,
  Channel,
  DatasetInfo,
  ErrorCode,
  Health,
  Turn,
  VoiceSession,
} from './types'

export class ApiError extends Error {
  readonly code: ErrorCode
  readonly details: string[]

  constructor(body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.code = body.code
    this.details = body.details ?? []
  }
}

/** Anything that isn't a well-formed ApiError still has to reach the user as a sentence. */
function fallbackError(code: ErrorCode, message: string): ApiError {
  return new ApiError({ code, message, details: [] })
}

function isApiErrorBody(body: unknown): body is ApiErrorBody {
  return (
    typeof body === 'object' &&
    body !== null &&
    typeof (body as ApiErrorBody).code === 'string' &&
    typeof (body as ApiErrorBody).message === 'string'
  )
}

async function request<T>(path: string, init?: RequestInit): Promise<T | null> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw fallbackError('not_found', "Can't reach Beacon. Is the backend running?")
  }

  if (res.status === 204) return null

  const body: unknown = await res.json().catch(() => null)
  if (!res.ok) {
    throw isApiErrorBody(body)
      ? new ApiError(body)
      : fallbackError('invalid_request', `Request failed (${res.status})`)
  }
  return body as T
}

async function requireBody<T>(path: string, init?: RequestInit): Promise<T> {
  const body = await request<T>(path, init)
  if (body === null) throw fallbackError('not_found', 'The server returned an empty response')
  return body
}

export function getHealth(): Promise<Health> {
  return requireBody<Health>('/api/health')
}

export function postQuery(
  text: string,
  channel: Channel,
  discreet: boolean
): Promise<Turn> {
  return requireBody<Turn>('/api/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, channel, discreet }),
  })
}

/** 204 means no turns yet — a normal state, not an error. */
export function getLatestTurn(): Promise<Turn | null> {
  return request<Turn>('/api/turns/latest')
}

export function getDataset(): Promise<DatasetInfo> {
  return requireBody<DatasetInfo>('/api/dataset')
}

export function uploadDataset(file: File): Promise<DatasetInfo> {
  const form = new FormData()
  form.append('file', file)
  return requireBody<DatasetInfo>('/api/dataset/upload', { method: 'POST', body: form })
}

export function resetDataset(): Promise<DatasetInfo> {
  return requireBody<DatasetInfo>('/api/dataset/reset', { method: 'POST' })
}

export function getVoiceSession(): Promise<VoiceSession> {
  return requireBody<VoiceSession>('/api/voice/session')
}

/** Turn any thrown value into a sentence safe to put in front of the user. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error && err.message) return err.message
  return 'Something went wrong'
}
