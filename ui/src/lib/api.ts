// Typed fetch client for the FastAPI backend.
// In dev, Vite proxies /api → http://localhost:8000 (see vite.config.ts).
// In prod, the SPA is served by the same FastAPI process, so /api maps back.

import type {
  ChangeRequest,
  Graph,
  LintFinding,
  PageDetail,
  PageMeta,
  QueryResult,
  SearchResult,
  Source,
  WorkspaceConfig,
} from "@/types"

// All endpoints live under /api (both dev and prod) so SPA client routes
// like /sources and /graph never collide with API routes.
// Dev: Vite proxies /api → http://localhost:8000. Prod: same-origin FastAPI.
const BASE = "/api"

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  })
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
  applyChangeRequest: (id: string, commit = false) =>
    request<{ id: string; status: string }>(
      `/change-requests/${id}/apply`,
      { method: "POST", body: JSON.stringify({ commit }) },
    ),
  rejectChangeRequest: (id: string) =>
    request<{ id: string; status: string }>(
      `/change-requests/${id}/reject`,
      { method: "POST" },
    ),

  // ── sources ──
  listSources: () => request<Source[]>("/sources"),
  ingestSource: (path: string) =>
    request<{ change_request_id: string; files_changed: number }>(
      "/sources/ingest",
      { method: "POST", body: JSON.stringify({ path }) },
    ),
  uploadSource: async (file: File): Promise<Source> => {
    const form = new FormData()
    form.append("file", file)
    const res = await fetch(`${BASE}/sources/upload`, {
      method: "POST",
      body: form, // let the browser set the multipart boundary
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
  listPages: () => request<PageMeta[]>("/wiki/pages"),
  getPage: (path: string) => request<PageDetail>(`/wiki/pages/${path}`),

  // ── query ──
  ask: (question: string, saveAsPage = false) =>
    request<QueryResult>("/query", {
      method: "POST",
      body: JSON.stringify({ question, save_as_page: saveAsPage }),
    }),

  // ── lint ──
  lint: (semantic = false) =>
    request<{ findings: LintFinding[] }>("/lint", {
      method: "POST",
      body: JSON.stringify({ semantic }),
    }),
  maintain: (semantic = false) =>
    request<{
      change_request_id: string | null
      files_changed: number
      findings: number
    }>("/maintain", {
      method: "POST",
      body: JSON.stringify({ semantic }),
    }),

  // ── search / graph ──
  search: (q: string) =>
    request<SearchResult[]>(`/search?q=${encodeURIComponent(q)}`),
  graph: () => request<Graph>("/graph"),

  // ── config (added in Fase 1) ──
  getConfig: () => request<WorkspaceConfig>("/config"),
  patchConfig: (patch: Partial<WorkspaceConfig>) =>
    request<WorkspaceConfig>("/config", {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
}

export { ApiError }
