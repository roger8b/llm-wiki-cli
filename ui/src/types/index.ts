// Domain types — mirror the FastAPI / Pydantic models.

export type PageType =
  | "concept"
  | "entity"
  | "source_summary"
  | "synthesis"
  | "decision"
  | "project"
  | "research"

export type CrStatus = "pending_review" | "applied" | "rejected"

export type FileOperation = "create" | "update" | "delete"

export interface FileChange {
  path: string
  operation: FileOperation
  diff: string
  new_content?: string | null
}

export interface ChangeRequest {
  id: string
  status: CrStatus
  summary: string
  files_changed: number
  diff_dir: string
  created_at: string
  applied_at?: string | null
  changes: FileChange[]
}

export type SourceStatus = "pending" | "processing" | "processed" | "error"

export interface Source {
  id?: number | null
  path: string
  type: string
  title?: string | null
  hash: string
  added_at: string
  processed_at?: string | null
  status: SourceStatus
}

export interface PageMeta {
  path: string
  title: string
  type: PageType
}

export interface PageDetail {
  path: string
  frontmatter: Record<string, unknown>
  body: string
}

export interface Citation {
  page?: string | null
  source?: string | null
  quote?: string | null
}

export interface SuggestedPage {
  path: string
  content: string
}

export interface QueryResult {
  answer: string
  citations: Citation[]
  suggested_page?: SuggestedPage | null
  change_request_id?: string | null
}

export type LintSeverity = "info" | "warn" | "error"

export interface LintFinding {
  kind: string
  severity: LintSeverity
  message: string
  pages: string[]
}

export interface WorkspaceConfig {
  model: string
  fts_limit: number
  num_ctx: number
  temperature: number | null
  request_timeout: number
  onboarded: boolean
}

export interface GraphNode {
  id: string
  title: string
  type: string
}

export interface GraphEdge {
  from: string
  to: string
}

export interface Graph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface SearchResult {
  path: string
  title: string
  rank: number
}

export interface OllamaStatus {
  running: boolean
  models: string[]
}

export interface OnboardingStatus {
  needs_onboarding: boolean
  model: string
  ollama: OllamaStatus
  brains: number
}

export interface ModelTestResult {
  ok: boolean
  detail: string
}

export interface CliStatus {
  installed: boolean
  path: string
  found_on_path: string | null
  on_path: boolean
  version: string
  source: string
}
