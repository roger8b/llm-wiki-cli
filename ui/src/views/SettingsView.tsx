import { useEffect, useState } from "react"
import {
  Settings as SettingsIcon,
  Loader2,
  Terminal,
  Check,
  X,
  AlertTriangle,
  KeyRound,
  Lock,
} from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import type {
  CliStatus,
  ModelTestResult,
  OllamaStatus,
  ProviderName,
  ProvidersMap,
} from "@/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { BrainSettings } from "@/components/settings/BrainSettings"

type Provider = "ollama" | ProviderName

const PROVIDERS: {
  id: Provider
  label: string
  local: boolean
  defaultModel: string
  urlPlaceholder?: string
}[] = [
  { id: "ollama", label: "Ollama", local: true, defaultModel: "llama3.1" },
  { id: "anthropic", label: "Anthropic", local: false, defaultModel: "claude-sonnet-4-5", urlPlaceholder: "https://api.anthropic.com" },
  { id: "openai", label: "OpenAI", local: false, defaultModel: "gpt-4o", urlPlaceholder: "https://api.openai.com/v1" },
  { id: "google", label: "Google", local: false, defaultModel: "gemini-2.0-flash", urlPlaceholder: "(default endpoint)" },
]

function meta(p: Provider) {
  return PROVIDERS.find((x) => x.id === p)!
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
      <Label className="text-[11px]">{label}</Label>
      {children}
      {hint && <p className="text-[12px] text-muted-foreground">{hint}</p>}
    </div>
  )
}

export function SettingsView() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // ── model state ──
  const [provider, setProvider] = useState<Provider>("ollama")
  const [modelName, setModelName] = useState("")
  const [baseUrl, setBaseUrl] = useState("")
  const [keyInput, setKeyInput] = useState("")
  const [keyBusy, setKeyBusy] = useState(false)
  const [temperature, setTemperature] = useState<number | null>(null)
  const [numCtx, setNumCtx] = useState(8192)
  const [reqTimeout, setReqTimeout] = useState(300)
  const [ftsLimit, setFtsLimit] = useState(20)
  const [test, setTest] = useState<ModelTestResult | null>(null)
  const [testing, setTesting] = useState(false)

  // ── reference data ──
  const [providers, setProviders] = useState<ProvidersMap | null>(null)
  const [ollama, setOllama] = useState<OllamaStatus | null>(null)
  const [snapshot, setSnapshot] = useState("")

  // ── cli ──
  const [cli, setCli] = useState<CliStatus | null>(null)
  const [cliBusy, setCliBusy] = useState(false)

  function snap(s: {
    provider: Provider
    modelName: string
    baseUrl: string
    temperature: number | null
    numCtx: number
    reqTimeout: number
    ftsLimit: number
  }) {
    return JSON.stringify(s)
  }
  function currentSnap() {
    return snap({ provider, modelName, baseUrl, temperature, numCtx, reqTimeout, ftsLimit })
  }

  useEffect(() => {
    async function load() {
      try {
        const [cfg, provs, oll] = await Promise.all([
          api.getConfig(),
          api.getProviders().catch(() => null),
          api.ollamaModels().catch(() => null),
        ])
        setProviders(provs)
        setOllama(oll)
        const m = cfg.model.match(/^([^:]+):(.*)$/)
        const prov = m?.[1]
        const name = m?.[2]
        const p = (PROVIDERS.some((x) => x.id === prov) ? prov : "ollama") as Provider
        const mn = name ?? ""
        const bu = !meta(p).local ? (provs?.[p as ProviderName]?.base_url ?? "") : ""
        setProvider(p)
        setModelName(mn || meta(p).defaultModel)
        setBaseUrl(bu)
        setTemperature(cfg.temperature)
        setNumCtx(cfg.num_ctx)
        setReqTimeout(cfg.request_timeout)
        setFtsLimit(cfg.fts_limit)
        setSnapshot(
          snap({
            provider: p,
            modelName: mn || meta(p).defaultModel,
            baseUrl: bu,
            temperature: cfg.temperature,
            numCtx: cfg.num_ctx,
            reqTimeout: cfg.request_timeout,
            ftsLimit: cfg.fts_limit,
          }),
        )
      } finally {
        setLoading(false)
      }
    }
    load()
    api.cliStatus().then(setCli).catch(() => {})
  }, [])

  function switchProvider(p: Provider) {
    setProvider(p)
    setTest(null)
    setKeyInput("")
    if (meta(p).local) {
      setModelName(ollama?.models[0] ?? meta(p).defaultModel)
      setBaseUrl("")
    } else {
      const ps = providers?.[p as ProviderName]
      setModelName(ps?.model ?? meta(p).defaultModel)
      setBaseUrl(ps?.base_url ?? "")
    }
  }

  const modelString = `${provider}:${modelName}`
  const isLocal = meta(provider).local
  const hasKey = !isLocal && (providers?.[provider as ProviderName]?.has_key ?? false)
  const dirty = !loading && currentSnap() !== snapshot

  async function save() {
    setSaving(true)
    try {
      if (!isLocal) {
        await api.updateProvider(provider as ProviderName, {
          base_url: baseUrl || null,
          model: modelName || null,
        })
      }
      const updated = await api.patchConfig({
        model: modelString,
        temperature,
        num_ctx: numCtx,
        request_timeout: reqTimeout,
        fts_limit: ftsLimit,
      })
      // refresh providers (base_url/model may have changed)
      setProviders(await api.getProviders().catch(() => providers))
      setSnapshot(currentSnap())
      void updated
      toast.success("Settings saved")
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function saveKey() {
    if (!keyInput || isLocal) return
    setKeyBusy(true)
    try {
      await api.updateProvider(provider as ProviderName, { api_key: keyInput })
      setProviders(await api.getProviders())
      setKeyInput("")
      toast.success("API key saved to keychain")
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setKeyBusy(false)
    }
  }
  async function clearKey() {
    setKeyBusy(true)
    try {
      await api.deleteProviderKey(provider as ProviderName)
      setProviders(await api.getProviders())
      toast("API key removed")
    } finally {
      setKeyBusy(false)
    }
  }

  async function runTest() {
    setTesting(true)
    setTest(null)
    try {
      setTest(await api.testModel(modelString))
    } finally {
      setTesting(false)
    }
  }

  async function cliInstall() {
    setCliBusy(true)
    try {
      setCli(await api.cliInstall())
      toast.success("CLI installed")
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setCliBusy(false)
    }
  }
  async function cliUninstall() {
    setCliBusy(true)
    try {
      setCli(await api.cliUninstall())
      toast("CLI removed")
    } finally {
      setCliBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center text-[13px] text-muted-foreground">
        Loading…
      </div>
    )
  }

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
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Model
          </div>

          {/* provider selector */}
          <div className="mb-4 inline-flex rounded-md border p-0.5">
            {PROVIDERS.map((p) => (
              <button
                key={p.id}
                onClick={() => switchProvider(p.id)}
                className={cn(
                  "rounded px-3 py-1 text-[12px] font-medium transition-colors",
                  provider === p.id
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="space-y-4">
            {isLocal ? (
              <Field label="Model" hint={ollama?.running ? undefined : "Ollama not detected — start it to list models."}>
                {ollama?.running && ollama.models.length > 0 ? (
                  <select
                    value={modelName}
                    onChange={(e) => {
                      setModelName(e.target.value)
                      setTest(null)
                    }}
                    className="w-full rounded-md border bg-background px-3 py-2 font-mono text-[13px]"
                  >
                    {[...new Set([...ollama.models, modelName])].map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Input
                    value={modelName}
                    onChange={(e) => setModelName(e.target.value)}
                    className="font-mono"
                    placeholder="llama3.1"
                  />
                )}
              </Field>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Base URL">
                    <Input
                      value={baseUrl}
                      onChange={(e) => setBaseUrl(e.target.value)}
                      placeholder={meta(provider).urlPlaceholder}
                      className="font-mono text-[12px]"
                    />
                  </Field>
                  <Field label="Model">
                    <Input
                      value={modelName}
                      onChange={(e) => {
                        setModelName(e.target.value)
                        setTest(null)
                      }}
                      placeholder={meta(provider).defaultModel}
                      className="font-mono text-[12px]"
                    />
                  </Field>
                </div>

                <Field label="API key">
                  <div className="flex items-center gap-2">
                    <Input
                      type="password"
                      value={keyInput}
                      onChange={(e) => setKeyInput(e.target.value)}
                      placeholder={hasKey ? "•••••••••• (stored — type to replace)" : "paste your key"}
                      className="flex-1 font-mono text-[12px]"
                    />
                    <Button size="sm" onClick={saveKey} disabled={!keyInput || keyBusy} className="gap-1.5">
                      {keyBusy && <Loader2 className="size-3.5 animate-spin" />}
                      Save key
                    </Button>
                    {hasKey && (
                      <Button size="sm" variant="outline" onClick={clearKey} disabled={keyBusy}>
                        Clear
                      </Button>
                    )}
                  </div>
                  <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                    {hasKey ? (
                      <>
                        <KeyRound className="size-3.5 text-apply" /> key stored in OS keychain
                      </>
                    ) : (
                      <>
                        <Lock className="size-3.5" /> stored in the OS keychain — never in config files
                      </>
                    )}
                  </p>
                </Field>
              </>
            )}

            {/* shared: temperature */}
            <Field
              label="Temperature"
              hint="0 = deterministic, higher = more creative. Empty = provider default."
            >
              <Input
                type="number"
                step="0.1"
                min="0"
                max="2"
                value={temperature ?? ""}
                placeholder="default"
                onChange={(e) =>
                  setTemperature(e.target.value === "" ? null : Number(e.target.value))
                }
                className="w-32"
              />
            </Field>

            {/* ollama-only tuning */}
            {isLocal && (
              <div className="grid grid-cols-2 gap-3">
                <Field
                  label="Context window (num_ctx)"
                  hint="Larger = reads more, fuller answers (more RAM)."
                >
                  <Input
                    type="number"
                    step="1024"
                    min="512"
                    value={numCtx}
                    onChange={(e) => setNumCtx(Number(e.target.value))}
                  />
                </Field>
                <Field label="Request timeout (s)">
                  <Input
                    type="number"
                    step="30"
                    min="10"
                    value={reqTimeout}
                    onChange={(e) => setReqTimeout(Number(e.target.value))}
                  />
                </Field>
              </div>
            )}

            {/* test + active */}
            <div className="flex items-center gap-3 border-t pt-3">
              <Button variant="outline" size="sm" onClick={runTest} disabled={testing} className="gap-1.5">
                {testing && <Loader2 className="size-4 animate-spin" />}
                Test connection
              </Button>
              {test && (
                <span
                  className={cn(
                    "flex items-center gap-1 text-[12px]",
                    test.ok ? "text-apply" : "text-rejected",
                  )}
                >
                  {test.ok ? <Check className="size-4" /> : <X className="size-4" />}
                  {test.detail}
                </span>
              )}
              <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                active: {modelString}
              </span>
            </div>
          </div>
        </div>

        {/* ── Search ── */}
        <div className="mt-4 rounded-lg border bg-card p-5">
          <div className="mb-4 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Search
          </div>
          <Field label="FTS limit" hint="Max full-text search results per query.">
            <Input
              type="number"
              min="1"
              value={ftsLimit}
              onChange={(e) => setFtsLimit(Number(e.target.value))}
              className="w-24"
            />
          </Field>
        </div>

        {/* ── Brain Configuration ── */}
        <BrainSettings />

        {/* ── Command-line tools ── */}
        <div className="mt-4 rounded-lg border bg-card p-5">
          <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            <Terminal className="size-3.5" /> Command-line tools
          </div>
          <p className="mb-3 text-[12px] text-muted-foreground">
            Install the <code>wiki</code> command so you (and AI agents) can use
            it from a terminal.
          </p>
          {cli && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-[13px]">
                {cli.found_on_path ? (
                  <>
                    <Check className="size-4 text-apply" />
                    <span>
                      Installed — <code>wiki</code> v{cli.version}
                    </span>
                  </>
                ) : (
                  <>
                    <AlertTriangle className="size-4 text-pending" />
                    <span>Not installed</span>
                  </>
                )}
              </div>
              <div className="font-mono text-[11px] text-muted-foreground">{cli.path}</div>
              {cli.installed && !cli.on_path && (
                <div className="rounded-md border border-pending/30 bg-pending/10 px-3 py-2 text-[12px]">
                  <AlertTriangle className="mr-1 inline size-3.5 text-pending" />
                  <code>~/.local/bin</code> isn't on your <code>PATH</code>:
                  <pre className="mt-1 overflow-x-auto rounded bg-muted px-2 py-1 font-mono text-[11px]">
                    export PATH="$HOME/.local/bin:$PATH"
                  </pre>
                </div>
              )}
              <div className="flex gap-2">
                <Button size="sm" onClick={cliInstall} disabled={cliBusy} className="gap-1.5">
                  {cliBusy && <Loader2 className="size-4 animate-spin" />}
                  {cli.installed ? "Reinstall" : "Install"}
                </Button>
                {cli.installed && (
                  <Button size="sm" variant="outline" onClick={cliUninstall} disabled={cliBusy}>
                    Uninstall
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>

        <p className="mt-4 text-center font-mono text-[11px] text-muted-foreground">
          ~/.wiki/config.yaml · keys in OS keychain
        </p>
      </div>
    </div>
  )
}
