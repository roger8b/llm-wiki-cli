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
  history_id?: number
}

export interface AskHistoryItem {
  id: number
  question: string
  answer: string
  citations: Citation[]
  change_request_id?: string | null
  created_at: string
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

export type ProviderName = "anthropic" | "openai" | "google"

export interface ProviderStatus {
  base_url: string | null
  model: string | null
  has_key: boolean
}

export type ProvidersMap = Record<ProviderName, ProviderStatus>

export interface ProviderPatch {
  base_url?: string | null
  model?: string | null
  api_key?: string
}

// Brain configuration

export type BrainIcon =
  | "brain"           // 🧠 default
  | "book"            // 📖 documentation
  | "code"            // 💻 development
  | "briefcase"       // 💼 work
  | "flask"           // 🔬 research
  | "lightbulb"       // 💡 ideas
  | "rocket"          // 🚀 project
  | "folder"          // 📁 generic

export interface BrainConfig {
  name: string
  path: string
  icon?: BrainIcon
}

export interface RegisteredBrain extends BrainConfig {
  id: string
  createdAt: string
  /** False when the brain's folder is missing/moved on disk. */
  valid?: boolean
  db_size?: number
}

export interface BrainSettings {
  brains: RegisteredBrain[]
  activeBrainId: string | null
}

export interface Job {
  id: number
  type: string
  status: "queued" | "running" | "done" | "error"
  payload?: string | null
  result?: string | null
  error?: string | null
  created_at: string
  completed_at?: string | null
}
