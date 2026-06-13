import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { useCrStore } from "./crs"
import { api } from "@/lib/api"
import type { ChangeRequest } from "@/types"

function cr(overrides: Partial<ChangeRequest> = {}): ChangeRequest {
  return {
    id: "CR-2026-0001",
    status: "pending_review",
    summary: "seed",
    files_changed: 1,
    diff_dir: "/tmp/cr",
    created_at: new Date().toISOString(),
    changes: [{ path: "wiki/concepts/rag.md", operation: "update", diff: "", new_content: "old" }],
    ...overrides,
  }
}

describe("useCrStore.updateFile", () => {
  beforeEach(() => {
    useCrStore.setState({ crs: [cr()], selectedId: "CR-2026-0001", editing: true })
  })
  afterEach(() => vi.restoreAllMocks())

  it("replaces the CR with the server response and clears nothing else", async () => {
    const updated = cr({
      edited_by_reviewer: true,
      changes: [{ path: "wiki/concepts/rag.md", operation: "update", diff: "+new", new_content: "new" }],
    })
    const spy = vi.spyOn(api, "updateCrFile").mockResolvedValue(updated)

    await useCrStore.getState().updateFile("CR-2026-0001", "wiki/concepts/rag.md", "new")

    expect(spy).toHaveBeenCalledWith("CR-2026-0001", "wiki/concepts/rag.md", "new")
    const stored = useCrStore.getState().crs[0]
    expect(stored.edited_by_reviewer).toBe(true)
    expect(stored.changes[0].new_content).toBe("new")
  })

  it("propagates API errors so the caller can toast", async () => {
    vi.spyOn(api, "updateCrFile").mockRejectedValue(new Error("409"))
    await expect(
      useCrStore.getState().updateFile("CR-2026-0001", "wiki/concepts/rag.md", "x"),
    ).rejects.toThrow("409")
  })
})

describe("useCrStore.apply partial (#184)", () => {
  afterEach(() => vi.restoreAllMocks())

  it("passes the selected paths subset to the API", async () => {
    useCrStore.setState({ crs: [cr()], selectedId: "CR-2026-0001", busyId: null })
    const spy = vi
      .spyOn(api, "applyChangeRequest")
      .mockResolvedValue({ id: "CR-2026-0001", status: "applied" })

    await useCrStore.getState().apply("CR-2026-0001", ["wiki/a.md", "wiki/b.md"])

    expect(spy).toHaveBeenCalledWith("CR-2026-0001", false, ["wiki/a.md", "wiki/b.md"])
    expect(useCrStore.getState().crs[0].status).toBe("applied")
  })

  it("omits paths on a full apply", async () => {
    useCrStore.setState({ crs: [cr()], selectedId: "CR-2026-0001", busyId: null })
    const spy = vi
      .spyOn(api, "applyChangeRequest")
      .mockResolvedValue({ id: "CR-2026-0001", status: "applied" })

    await useCrStore.getState().apply("CR-2026-0001")

    expect(spy).toHaveBeenCalledWith("CR-2026-0001", false, undefined)
  })
})

describe("useCrStore edit-mode flags", () => {
  it("setEditing toggles and select resets it", () => {
    useCrStore.setState({ crs: [cr()], editing: true })
    useCrStore.getState().setEditing(false)
    expect(useCrStore.getState().editing).toBe(false)
    useCrStore.getState().setEditing(true)
    useCrStore.getState().select("CR-2026-0001")
    expect(useCrStore.getState().editing).toBe(false)
  })
})
