import { useEffect, useState } from "react"
import { Settings as SettingsIcon, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { WorkspaceConfig } from "@/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

const PRESETS = [
  "ollama:qwen2.5:7b",
  "ollama:llama3.2:3b",
  "ollama:gemma4:31b-cloud",
  "anthropic:claude-sonnet-4-5",
  "openai:gpt-4o",
  "google:gemini-2.0-flash",
]

function providerOf(model: string): string {
  const p = model.split(":")[0]
  const map: Record<string, string> = {
    ollama: model.includes("-cloud") ? "Ollama (cloud)" : "Ollama (local)",
    anthropic: "Anthropic — needs ANTHROPIC_API_KEY",
    openai: "OpenAI — needs OPENAI_API_KEY",
    google: "Google — needs GOOGLE_API_KEY",
  }
  return map[p] ?? p
}

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
      {hint && <p className="text-[12px] text-muted-foreground">{hint}</p>}
    </div>
  )
}

export function SettingsView() {
  const [cfg, setCfg] = useState<WorkspaceConfig | null>(null)
  const [draft, setDraft] = useState<WorkspaceConfig | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api
      .getConfig()
      .then((c) => {
        setCfg(c)
        setDraft(c)
      })
      .catch((e) => toast.error((e as Error).message))
  }, [])

  if (!draft || !cfg) {
    return (
      <div className="flex flex-1 items-center justify-center text-[13px] text-muted-foreground">
        Loading…
      </div>
    )
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(cfg)
  const set = <K extends keyof WorkspaceConfig>(
    key: K,
    value: WorkspaceConfig[K],
  ) => setDraft({ ...draft, [key]: value })

  async function save() {
    setSaving(true)
    try {
      const updated = await api.patchConfig(draft!)
      setCfg(updated)
      setDraft(updated)
      toast.success("Settings saved")
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const isOllama = draft.model.startsWith("ollama:")

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-[680px]">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="flex items-center gap-2 font-display text-lg font-semibold">
            <SettingsIcon className="size-5 text-primary" /> Settings
          </h1>
          <Button onClick={save} disabled={!dirty || saving} className="gap-1.5">
            {saving && <Loader2 className="size-4 animate-spin" />}
            Save changes
          </Button>
        </div>

        {/* ── Model ── */}
        <div className="rounded-lg border bg-card p-5">
          <div className="mb-4 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Model
          </div>
          <div className="space-y-4">
            <Field label="Model string" hint={providerOf(draft.model)}>
              <Input
                value={draft.model}
                onChange={(e) => set("model", e.target.value)}
                className="font-mono"
              />
              <div className="flex flex-wrap gap-1.5 pt-1">
                {PRESETS.map((p) => (
                  <button
                    key={p}
                    onClick={() => set("model", p)}
                    className="rounded-full border bg-secondary px-2.5 py-1 font-mono text-[11px] text-muted-foreground hover:border-primary hover:text-foreground"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </Field>

            <Field
              label="Temperature"
              hint="0 = deterministic, higher = more creative. Empty = provider default."
            >
              <Input
                type="number"
                step="0.1"
                min="0"
                max="2"
                value={draft.temperature ?? ""}
                placeholder="default"
                onChange={(e) =>
                  set(
                    "temperature",
                    e.target.value === "" ? null : Number(e.target.value),
                  )
                }
                className="w-32"
              />
            </Field>
          </div>
        </div>

        {/* ── Ollama tuning ── */}
        <div className="mt-4 rounded-lg border bg-card p-5">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Ollama tuning
          </div>
          {!isOllama && (
            <p className="mb-3 text-[12px] text-muted-foreground">
              Applies only to <code>ollama:</code> models. Ignored for hosted
              providers.
            </p>
          )}
          <div className="space-y-4">
            <Field
              label="Context window (num_ctx)"
              hint="Tokens of context. Larger = reads more wiki content, fuller answers (more RAM). Default 8192."
            >
              <Input
                type="number"
                step="1024"
                min="512"
                value={draft.num_ctx}
                onChange={(e) => set("num_ctx", Number(e.target.value))}
                className="w-40"
              />
            </Field>

            <Field
              label="Request timeout (seconds)"
              hint="How long to wait for the model before failing. Cloud models may need more."
            >
              <Input
                type="number"
                step="30"
                min="10"
                value={draft.request_timeout}
                onChange={(e) => set("request_timeout", Number(e.target.value))}
                className="w-32"
              />
            </Field>
          </div>
        </div>

        {/* ── Search ── */}
        <div className="mt-4 rounded-lg border bg-card p-5">
          <div className="mb-4 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Search
          </div>
          <Field
            label="FTS limit"
            hint="Max full-text search results per query."
          >
            <Input
              type="number"
              min="1"
              value={draft.fts_limit}
              onChange={(e) => set("fts_limit", Number(e.target.value))}
              className="w-24"
            />
          </Field>
        </div>

        <p className="mt-4 text-center font-mono text-[11px] text-muted-foreground">
          ~/.wiki/config.yaml
        </p>
      </div>
    </div>
  )
}
