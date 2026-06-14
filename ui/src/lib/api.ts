// Typed fetch client for the FastAPI backend.
// In dev, Vite proxies /api → http://localhost:8000 (see vite.config.ts).
// In prod, the SPA is served by the same FastAPI process, so /api maps back.

import type {
  AskHistoryItem,
  ChangeRequest,
  CliStatus,
  Graph,
  LintFinding,
  ModelTestResult,
  OllamaStatus,
  OnboardingStatus,
  PageDetail,
  PageMeta,
  ProviderName,
  ProviderPatch,
  ProviderStatus,
  AgentInfo,
  ProvidersMap,
  RegisteredBrain,
  SearchResult,
  SkillsStatus,
  Source,
  SourceContent,
  WorkspaceConfig,
  Job,
} from "@/types"

// All endpoints live under /api (both dev and prod) so SPA client routes
// like /sources and /graph never collide with API routes.
// Dev: Vite proxies /api → http://localhost:8000. Prod: same-origin FastAPI.
const BASE = "/api"

// The desktop shell injects a per-session token (window.__WIKI_TOKEN__) that the
// backend requires on /api/* when WIKI_API_TOKEN is set. In dev / browser there
// is no token and the backend leaves the API open, so this is a no-op there.
function authHeaders(): Record<string, string> {
  const token = (globalThis as { __WIKI_TOKEN__?: string }).__WIKI_TOKEN__
  return token ? { "X-Wiki-Token": token } : {}
}

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const opts: RequestInit = {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...init?.headers,
    },
  }
  // WKWebView (the desktop WebView) reuses keep-alive connections; when the
  // backend has closed an idle one, the reused socket is reset and fetch rejects
  // with a network-level TypeError ("Load failed") before any response. The
  // request never reached the server, so retrying once on a fresh connection is
  // safe and transparent.
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, opts)
  } catch (err) {
    if (err instanceof TypeError) {
      res = await fetch(`${BASE}${path}`, opts)
    } else {
      throw err
    }
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  // ── change requests ──
  listChangeRequests: (status?: string) =>
    request<ChangeRequest[]>(
      `/change-requests${status ? `?status=${encodeURIComponent(status)}` : ""}`,
    ),
  getChangeRequest: (id: string) =>
    request<ChangeRequest>(`/change-requests/${id}`),
  applyChangeRequest: (id: string, commit = false, paths?: string[]) =>
    request<{
      id: string
      status: string
      applied_paths?: string[]
      rejected_paths?: string[]
    }>(`/change-requests/${id}/apply`, {
      method: "POST",
      // Omit `paths` entirely for a full apply (backend treats it as "all").
      body: JSON.stringify(paths ? { commit, paths } : { commit }),
    }),
  rejectChangeRequest: (id: string) =>
    request<{ id: string; status: string }>(
      `/change-requests/${id}/reject`,
      { method: "POST" },
    ),
  updateCrFile: (crId: string, path: string, newContent: string) =>
    request<ChangeRequest>(`/change-requests/${crId}/files`, {
      method: "PATCH",
      body: JSON.stringify({ path, new_content: newContent }),
    }),

  // ── sources ──
  listSources: () => request<Source[]>("/sources"),
  getSourceContent: (path: string) =>
    request<SourceContent>(
      `/sources/content?path=${encodeURIComponent(path)}`,
    ),
  ingestSource: (path: string, force = false) =>
    request<{ job_id: number }>(
      "/sources/ingest",
      { method: "POST", body: JSON.stringify({ path, force }) },
    ),
  ingestSources: (paths: string[], force = false) =>
    request<{ job_ids: number[]; errors: { path: string; detail: string }[] }>(
      "/sources/ingest",
      { method: "POST", body: JSON.stringify({ paths, force }) },
    ),
  uploadSource: async (file: File): Promise<Source> => {
    const form = new FormData()
    form.append("file", file)
    const res = await fetch(`${BASE}/sources/upload`, {
      method: "POST",
      // Only the auth token — no Content-Type, so the browser sets the
      // multipart boundary itself.
      headers: { ...authHeaders() },
      body: form,
    })
    if (!res.ok) {
      let detail = res.statusText
      try {
        detail = (await res.json()).detail ?? detail
      } catch {
        /* keep statusText */
      }
      throw new ApiError(res.status, detail)
    }
    return res.json() as Promise<Source>
  },
  addTextSource: (title: string, content: string) =>
    request<Source>("/sources/text", {
      method: "POST",
      body: JSON.stringify({ title, content }),
    }),

  // ── wiki pages ──
  listPages: (tag?: string) =>
    request<PageMeta[]>(
      tag ? `/wiki/pages?tag=${encodeURIComponent(tag)}` : "/wiki/pages",
    ),
  listTags: () => request<{ tag: string; count: number }[]>("/wiki/tags"),
  getPage: (path: string) => request<PageDetail>(`/wiki/pages/${path}`),
  backlinks: (path: string) =>
    request<{ path: string; backlinks: { path: string; title: string }[] }>(
      `/wiki/backlinks?path=${encodeURIComponent(path)}`,
    ),
  deletePage: (path: string, unlinkBacklinks: boolean) =>
    request<{ change_request_id: string; files_changed: number }>("/wiki/delete", {
      method: "POST",
      body: JSON.stringify({ path, unlink_backlinks: unlinkBacklinks }),
    }),
  proposeEdit: (
    path: string,
    frontmatter: Record<string, unknown>,
    body: string,
    expectNew = false,
  ) =>
    request<{ change_request_id: string; files_changed: number }>(
      `/wiki/pages/${path}/propose-edit`,
      {
        method: "POST",
        body: JSON.stringify({ frontmatter, body, expect_new: expectNew }),
      },
    ),
  listTemplates: () =>
    request<{ type: string; body: string }[]>("/wiki/templates"),

  // ── query ──
  ask: (question: string, saveAsPage = false) =>
    request<{ job_id: number }>("/query", {
      method: "POST",
      body: JSON.stringify({ question, save_as_page: saveAsPage }),
    }),

  // ── ask history + promotion ──
  askHistory: (limit = 50) =>
    request<AskHistoryItem[]>(`/ask/history?limit=${limit}`),
  deleteAskHistory: (id: number) =>
    request<{ status: string }>(`/ask/history/${id}`, { method: "DELETE" }),
  clearAskHistory: () =>
    request<{ status: string }>("/ask/history", { method: "DELETE" }),
  promoteAnswer: (payload: {
    question: string
    answer: string
    title?: string
    history_id?: number
  }) =>
    request<{ change_request_id: string; files_changed: number }>("/ask/promote", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // ── lint ──
  lint: (semantic = false) =>
    request<{ findings?: LintFinding[]; job_id?: number }>("/lint", {
      method: "POST",
      body: JSON.stringify({ semantic }),
    }),
  maintain: (semantic = false) =>
    request<{ job_id: number }>("/maintain", {
      method: "POST",
      body: JSON.stringify({ semantic }),
    }),

  // ── jobs ──
  listJobs: () => request<Job[]>("/jobs"),
  getJob: (id: number) => request<Job>(`/jobs/${id}`),
  /**
   * Subscribe to a job's progress + final result over SSE (fetch + stream, so
   * the X-Wiki-Token header is sent — EventSource can't). Resolves when the
   * stream ends. `onResult` receives the raw job.result string (or null).
   */
  /** Request cooperative cancellation of a running job. */
  cancelJob: (id: number) =>
    request<{ job_id: number; status: string; cancel_requested: boolean }>(
      `/jobs/${id}/cancel`,
      { method: "POST" },
    ),
  streamJob: async (
    id: number,
    h: {
      onStatus?: (status: string) => void
      onProgress?: (step: string) => void
      onResult?: (result: string | null) => void
      onCancelled?: (result: string | null) => void
      onError?: (message: string) => void
    },
  ): Promise<void> => {
    let res: Response
    try {
      res = await fetch(`${BASE}/jobs/${id}/events`, { headers: authHeaders() })
    } catch {
      // network drop (e.g. WebView stale keep-alive) — one retry
      res = await fetch(`${BASE}/jobs/${id}/events`, { headers: authHeaders() })
    }
    if (!res.ok || !res.body) {
      h.onError?.(`stream failed (${res.status})`)
      return
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ""
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let sep: number
      while ((sep = buf.indexOf("\n\n")) !== -1) {
        const frame = buf.slice(0, sep)
        buf = buf.slice(sep + 2)
        let event = "message"
        let data = ""
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim()
          else if (line.startsWith("data:")) data += line.slice(5).trim()
        }
        if (!data) continue
        const payload = JSON.parse(data) as {
          status?: string
          progress?: string
          result?: string | null
          detail?: string
        }
        if (event === "status") h.onStatus?.(payload.status ?? "")
        else if (event === "progress") h.onProgress?.(payload.progress ?? "")
        else if (event === "result") {
          h.onResult?.(payload.result ?? null)
          return
        } else if (event === "cancelled") {
          h.onCancelled?.(payload.result ?? null)
          return
        } else if (event === "error") {
          h.onError?.(payload.detail ?? "Job failed.")
          return
        }
      }
    }
  },

  // ── search / graph ──
  search: (q: string, limit = 20, signal?: AbortSignal) =>
    request<SearchResult[]>(
      `/search?q=${encodeURIComponent(q)}&limit=${limit}`,
      { signal },
    ),
  graph: () => request<Graph>("/graph"),

  // ── brains ──
  listBrains: () => request<RegisteredBrain[]>("/brains"),
  getActiveBrain: () => request<RegisteredBrain | null>("/brains/active"),
  /** Register an EXISTING brain directory. */
  createBrain: (payload: {
    name: string
    path: string
    icon: string
    activate?: boolean
  }) =>
    request<RegisteredBrain>("/brains", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /** Create a NEW brain (scaffold the folder) then register it. */
  initBrain: (payload: {
    name: string
    path: string
    icon: string
    activate?: boolean
  }) =>
    request<RegisteredBrain>("/brains/create", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateBrain: (
    id: string,
    payload: Partial<Pick<RegisteredBrain, "name" | "path" | "icon">>,
  ) =>
    request<RegisteredBrain>(`/brains/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteBrain: (id: string) =>
    request<{ deleted: string; newActiveId: string | null }>(`/brains/${id}`, {
      method: "DELETE",
    }),
  setActiveBrain: (id: string) =>
    request<RegisteredBrain>("/brains/active", {
      method: "POST",
      body: JSON.stringify({ id }),
    }),

  // ── config ──
  getConfig: () => request<WorkspaceConfig>("/config"),
  patchConfig: (patch: Partial<WorkspaceConfig>) =>
    request<WorkspaceConfig>("/config", {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  // ── onboarding / setup ──
  getOnboarding: () => request<OnboardingStatus>("/onboarding"),
  ollamaModels: () => request<OllamaStatus>("/providers/ollama"),
  testModel: (model: string) =>
    request<ModelTestResult>("/config/test", {
      method: "POST",
      body: JSON.stringify({ model }),
    }),
  /** Stream `ollama pull` progress. Calls onEvent for each NDJSON status. */
  pullModel: async (
    model: string,
    onEvent: (e: Record<string, unknown>) => void,
  ): Promise<void> => {
    const res = await fetch(`${BASE}/providers/ollama/pull`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model }),
    })
    if (!res.body) throw new ApiError(res.status, "no stream")
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ""
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split("\n\n")
      buf = lines.pop() ?? ""
      for (const line of lines) {
        const m = /^data: (.*)$/m.exec(line)
        if (m) {
          try {
            onEvent(JSON.parse(m[1]))
          } catch {
            /* ignore malformed */
          }
        }
      }
    }
  },

  // ── remote providers (keys stored in the OS keychain) ──
  getProviders: () => request<ProvidersMap>("/providers"),
  updateProvider: (provider: ProviderName, patch: ProviderPatch) =>
    request<ProviderStatus>(`/providers/${provider}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteProviderKey: (provider: ProviderName) =>
    request<ProviderStatus>(`/providers/${provider}/key`, { method: "DELETE" }),

  // ── CLI tools ──
  cliStatus: () => request<CliStatus>("/cli"),
  cliInstall: () => request<CliStatus>("/cli/install", { method: "POST" }),
  cliUninstall: () => request<CliStatus>("/cli", { method: "DELETE" }),

  // ── agent skills ──
  skillsStatus: () => request<SkillsStatus>("/skills"),
  skillsAgents: () => request<{ agents: AgentInfo[] }>("/skills/agents"),
  installSkills: (opts: {
    agents?: string[]
    agent?: string
    scope?: string
    method?: string
    force?: boolean
  }) =>
    request<{ store: string; results: unknown[] }>("/skills/install", {
      method: "POST",
      body: JSON.stringify(opts),
    }),
  updateSkills: () =>
    request<{ store: string; refreshed: string[] }>("/skills/update", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  removeSkills: (opts: { name?: string; agent?: string; scope?: string } = {}) =>
    request<{ removed: string[] }>("/skills/remove", {
      method: "POST",
      body: JSON.stringify(opts),
    }),
}

export { ApiError }
