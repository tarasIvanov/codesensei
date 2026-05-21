export type RepoStatus = 'ready' | 'indexing' | 'failed'

export interface RepoEntry {
  repo_id: string
  source: string
  source_kind: 'https' | 'local'
  default_branch: string | null
  indexed_at: string | null
  chunk_count: number
  embedding_provider: string | null
  embedding_model: string | null
  status: RepoStatus
  last_error: string | null
  codesensei_ignore_patterns?: string[] | null
  embedding_token_count?: number | null
}

export interface CreateIndexBody {
  source: string
  default_branch?: string | null
}

export interface CreateIndexResult {
  repo_id: string
  job_id?: string
  chunk_count?: number
  indexed_at?: string
  mode: 'sync' | 'async'
}

export type RepoErrorCategory =
  | 'invalid_input'
  | 'payload_too_large'
  | 'already_indexing'
  | 'clone_failed'
  | 'embedding_failed'
  | 'embedding_dimension_mismatch'
  | 'embedding_mismatch'
  | 'delete_during_index'
  | 'queue_unavailable'
  | 'not_found'
  | 'internal'

export class RepoApiError extends Error {
  category: RepoErrorCategory
  retryable: boolean

  constructor(category: RepoErrorCategory, message: string, retryable: boolean) {
    super(message)
    this.category = category
    this.retryable = retryable
  }
}

const FALLBACK_REPO_MSG: Record<RepoErrorCategory, string> = {
  invalid_input: 'The submitted repository source is not accepted.',
  payload_too_large:
    'The repository is too large for the per-repo chunk cap (5,000). Pick a smaller source or split it.',
  already_indexing:
    'This source is already being indexed. Wait until the current pass finishes.',
  clone_failed:
    'Could not clone the repository. Check the URL, network, and that the repo is public.',
  embedding_failed: 'The embedding provider failed during indexing. Retry later.',
  embedding_dimension_mismatch:
    'The embedding provider returned vectors with an unexpected dimension. Re-index after changing the model.',
  embedding_mismatch:
    'The repository was indexed with a different embedding provider/model than the active one.',
  delete_during_index: 'Cannot delete a repository while indexing is in progress.',
  queue_unavailable: 'The background job queue is unreachable. Try again later.',
  not_found: 'No repository with that id.',
  internal: 'Unexpected server error.',
}

async function _raise(resp: Response): Promise<never> {
  let category: RepoErrorCategory = 'internal'
  let message = FALLBACK_REPO_MSG.internal
  let retryable = false
  try {
    const parsed = (await resp.json()) as {
      error?: { category?: RepoErrorCategory; message?: string; retryable?: boolean }
    }
    if (parsed?.error?.category) {
      category = parsed.error.category
      message = parsed.error.message || FALLBACK_REPO_MSG[category] || message
      retryable = Boolean(parsed.error.retryable)
    }
  } catch {
    // not JSON
  }
  throw new RepoApiError(category, message, retryable)
}

export async function listRepos(): Promise<RepoEntry[]> {
  const resp = await fetch('/api/repos')
  if (!resp.ok) {
    return _raise(resp)
  }
  const body = (await resp.json()) as { repos: RepoEntry[] }
  return body.repos
}

export async function createIndex(body: CreateIndexBody): Promise<CreateIndexResult> {
  const resp = await fetch('/api/index', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source: body.source,
      default_branch: body.default_branch ?? null,
    }),
  })
  if (!resp.ok) {
    return _raise(resp)
  }
  return (await resp.json()) as CreateIndexResult
}

export async function deleteRepo(repoId: string): Promise<void> {
  const resp = await fetch(`/api/repos/${encodeURIComponent(repoId)}`, {
    method: 'DELETE',
  })
  if (!resp.ok && resp.status !== 204) {
    return _raise(resp)
  }
}

export interface JobLookup {
  job_id: string
  status: 'pending' | 'in_progress' | 'complete' | 'not_found'
  submitted_at?: string
  completed_at?: string
  result?: unknown
}

export async function pollJob(jobId: string): Promise<JobLookup> {
  const resp = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`)
  if (resp.status === 404) {
    return { job_id: jobId, status: 'not_found' }
  }
  if (!resp.ok) {
    await _raise(resp)
  }
  return (await resp.json()) as JobLookup
}
