import { useEffect, useState } from "react"
import {
  Settings as SettingsIcon,
  Loader2,
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
  AgentInfo,
  CliStatus,
  ModelTestResult,
  OllamaStatus,
  ProviderName,
  ProvidersMap,
  SkillsStatus,
} from "@/types"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { BrainSettings } from "@/components/settings/BrainSettings"
import { DesktopSettings } from "@/components/settings/DesktopSettings"
import { IndexHealthCard } from "@/components/shared/IndexHealthCard"
import { useIndexHealthStore } from "@/stores/indexHealth"

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

type Section =
  | "general"
  | "model"
  | "search"
  | "ingestion"
  | "transcription"
  | "security"
  | "tools"

const SECTIONS: { id: Section; label: string }[] = [
  { id: "general", label: "General" },
  { id: "model", label: "Model" },
  { id: "search", label: "Search" },
  { id: "ingestion", label: "Ingestion" },
  { id: "transcription", label: "Transcription" },
  { id: "security", label: "Security" },
  { id: "tools", label: "Tools" },
]

const WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3"]

/** Card section matching the prototype: header (title + desc) over stacked rows. */
function Section({
  title,
  desc,
  danger,
  children,
}: {
  title: string
  desc?: string
  danger?: boolean
  children: React.ReactNode
}) {
  return (
    <div
      className={cn(
        "mb-4 overflow-hidden rounded-lg border bg-card",
        danger && "border-rejected/30",
      )}
    >
      <div
        className={cn(
          "border-b px-4 pb-3 pt-3.5",
          danger ? "bg-rejected/5" : "bg-muted/40",
        )}
      >
        <h3 className={cn("text-[13.5px] font-semibold", danger && "text-rejected")}>{title}</h3>
        {desc && <p className="mt-0.5 text-[12px] text-muted-foreground">{desc}</p>}
      </div>
      <div>{children}</div>
    </div>
  )
}

/** Horizontal label/control row (label left, control right) like the prototype. */
function Row({
  name,
  desc,
  children,
}: {
  name: string
  desc?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-4 border-b px-4 py-3 last:border-b-0">
      <div className="flex-1">
        <span className="block text-[13.5px] font-medium">{name}</span>
        {desc && <span className="mt-0.5 block text-[12px] text-muted-foreground">{desc}</span>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}

export function SettingsView() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [section, setSection] = useState<Section>("general")

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

  // ── new config (#237) ──
  const [embeddingModel, setEmbeddingModel] = useState("")
  const [agentMaxRetries, setAgentMaxRetries] = useState(2)
  const [agentFixRetries, setAgentFixRetries] = useState(1)
  const [chunkThreshold, setChunkThreshold] = useState(24000)
  const [chunkSize, setChunkSize] = useState(16000)
  const [chunkOverlap, setChunkOverlap] = useState(1000)
  const [whisperModel, setWhisperModel] = useState("small")
  const [whisperLanguage, setWhisperLanguage] = useState("")

  // ── reference data ──
  const [providers, setProviders] = useState<ProvidersMap | null>(null)
  const [ollama, setOllama] = useState<OllamaStatus | null>(null)
  const [snapshot, setSnapshot] = useState("")

  // ── cli ──
  const [cli, setCli] = useState<CliStatus | null>(null)
  const [cliBusy, setCliBusy] = useState(false)

  // ── index health (#306) ──
  const indexStatus = useIndexHealthStore((s) => s.status)
  const indexBusy = useIndexHealthStore((s) => s.busy)
  const refreshIndex = useIndexHealthStore((s) => s.refresh)
  const reindex = useIndexHealthStore((s) => s.reindex)
  useEffect(() => {
    refreshIndex()
  }, [refreshIndex])

  // ── skills ──
  const [skills, setSkills] = useState<SkillsStatus | null>(null)
  const [skillsBusy, setSkillsBusy] = useState(false)
  const [skillAgents, setSkillAgents] = useState<AgentInfo[]>([])
  const [selectedAgents, setSelectedAgents] = useState<Set<string>>(new Set())
  const [skillScope, setSkillScope] = useState<"local" | "global" | "both">("global")
  const [skillMethod, setSkillMethod] = useState<"symlink" | "copy">("symlink")

  function snap(s: {
    provider: Provider
    modelName: string
    baseUrl: string
    temperature: number | null
    numCtx: number
    reqTimeout: number
    ftsLimit: number
    embeddingModel: string
    agentMaxRetries: number
    agentFixRetries: number
    chunkThreshold: number
    chunkSize: number
    chunkOverlap: number
    whisperModel: string
    whisperLanguage: string
  }) {
    return JSON.stringify(s)
  }
  function currentSnap() {
    return snap({
      provider,
      modelName,
      baseUrl,
      temperature,
      numCtx,
      reqTimeout,
      ftsLimit,
      embeddingModel,
      agentMaxRetries,
      agentFixRetries,
      chunkThreshold,
      chunkSize,
      chunkOverlap,
      whisperModel,
      whisperLanguage,
    })
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
        // new config (#237), tolerant to older backends that omit them
        const em = cfg.embedding_model ?? ""
        const amr = cfg.agent_max_retries ?? 2
        const afr = cfg.agent_fix_retries ?? 1
        const ct = cfg.chunk_threshold_chars ?? 24000
        const cs = cfg.chunk_size_chars ?? 16000
        const co = cfg.chunk_overlap_chars ?? 1000
        const wm = cfg.whisper_model ?? "small"
        const wl = cfg.whisper_language ?? ""
        setEmbeddingModel(em)
        setAgentMaxRetries(amr)
        setAgentFixRetries(afr)
        setChunkThreshold(ct)
        setChunkSize(cs)
        setChunkOverlap(co)
        setWhisperModel(wm)
        setWhisperLanguage(wl)
        setSnapshot(
          snap({
            provider: p,
            modelName: mn || meta(p).defaultModel,
            baseUrl: bu,
            temperature: cfg.temperature,
            numCtx: cfg.num_ctx,
            reqTimeout: cfg.request_timeout,
            ftsLimit: cfg.fts_limit,
            embeddingModel: em,
            agentMaxRetries: amr,
            agentFixRetries: afr,
            chunkThreshold: ct,
            chunkSize: cs,
            chunkOverlap: co,
            whisperModel: wm,
            whisperLanguage: wl,
          }),
        )
      } finally {
        setLoading(false)
      }
    }
    load()
    api.cliStatus().then(setCli).catch(() => {})
    api.skillsStatus().then(setSkills).catch(() => {})
    api
      .skillsAgents()
      .then((r) => {
        setSkillAgents(r.agents)
        setSelectedAgents(new Set(r.agents.filter((a) => a.detected).map((a) => a.name)))
      })
      .catch(() => {})
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
        // #237 — empty strings map to null (disabled / autodetect)
        embedding_model: embeddingModel.trim() || null,
        agent_max_retries: agentMaxRetries,
        agent_fix_retries: agentFixRetries,
        chunk_threshold_chars: chunkThreshold,
        chunk_size_chars: chunkSize,
        chunk_overlap_chars: chunkOverlap,
        whisper_model: whisperModel,
        whisper_language: whisperLanguage.trim() || null,
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

  function discard() {
    try {
      const s = JSON.parse(snapshot)
      setProvider(s.provider)
      setModelName(s.modelName)
      setBaseUrl(s.baseUrl)
      setTemperature(s.temperature)
      setNumCtx(s.numCtx)
      setReqTimeout(s.reqTimeout)
      setFtsLimit(s.ftsLimit)
      setEmbeddingModel(s.embeddingModel)
      setAgentMaxRetries(s.agentMaxRetries)
      setAgentFixRetries(s.agentFixRetries)
      setChunkThreshold(s.chunkThreshold)
      setChunkSize(s.chunkSize)
      setChunkOverlap(s.chunkOverlap)
      setWhisperModel(s.whisperModel)
      setWhisperLanguage(s.whisperLanguage)
      setTest(null)
    } catch {
      /* snapshot malformed — nothing to restore */
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

  async function installSkills() {
    setSkillsBusy(true)
    try {
      await api.installSkills({
        agents: [...selectedAgents],
        scope: skillScope,
        method: skillMethod,
      })
      setSkills(await api.skillsStatus())
      toast.success("Skills installed")
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSkillsBusy(false)
    }
  }
  async function removeSkills() {
    setSkillsBusy(true)
    try {
      await api.removeSkills({})
      setSkills(await api.skillsStatus())
      toast("Skills removed")
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSkillsBusy(false)
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
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto px-9 py-7">
        <div className="mx-auto max-w-[820px]">
          <h1 className="mb-7 flex items-center gap-2 font-display text-xl font-semibold tracking-[-0.3px]">
            <SettingsIcon className="size-5 text-primary" /> Settings
          </h1>

          <div className="flex gap-8">
            {/* ── section nav ── */}
            <nav className="flex w-40 shrink-0 flex-col gap-0.5">
              {SECTIONS.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setSection(s.id)}
                  className={cn(
                    "rounded-md px-2.5 py-2 text-left text-[13px] transition-colors",
                    section === s.id
                      ? "bg-card font-medium text-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground",
                  )}
                >
                  {s.label}
                </button>
              ))}
            </nav>

            {/* ── content ── */}
            <div className="min-w-0 flex-1 max-w-[600px]">
              {/* ── General ── */}
              {section === "general" && (
                <>
                  <div className="mb-5 text-[20px] font-semibold tracking-[-0.3px]">General</div>
                  {/* Index health (#306): surfaces drift and lets the user
                      trigger a reindex without leaving Settings. */}
                  <div className="mb-4">
                    <IndexHealthCard
                      status={indexStatus}
                      busy={indexBusy}
                      onReindex={() => reindex()}
                    />
                  </div>
                  <BrainSettings />
                  <DesktopSettings />
                </>
              )}

              {/* ── Model ── */}
              {section === "model" && (
                <>
                  <div className="mb-5 text-[20px] font-semibold tracking-[-0.3px]">Model</div>
                  <Section
                    title="LLM provider"
                    desc="Which model powers ingest, ask, and lint"
                  >
                    <Row name="Provider" desc="Local providers run on your machine; others need an API key.">
                      <div className="inline-flex rounded-md border p-0.5">
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
                    </Row>

                    {isLocal ? (
                      <Row
                        name="Model"
                        desc={ollama?.running ? "Used for wiki generation and Q&A." : "Ollama not detected — start it to list models."}
                      >
                        {ollama?.running && ollama.models.length > 0 ? (
                          <select
                            value={modelName}
                            onChange={(e) => {
                              setModelName(e.target.value)
                              setTest(null)
                            }}
                            className="w-[220px] rounded-md border bg-background px-3 py-2 font-mono text-[13px]"
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
                            className="w-[220px] font-mono"
                            placeholder="llama3.1"
                          />
                        )}
                      </Row>
                    ) : (
                      <>
                        <Row name="Model name" desc="Used for wiki generation and Q&A.">
                          <Input
                            value={modelName}
                            onChange={(e) => {
                              setModelName(e.target.value)
                              setTest(null)
                            }}
                            placeholder={meta(provider).defaultModel}
                            className="w-[220px] font-mono text-[12px]"
                          />
                        </Row>
                        <Row name="API base URL" desc="Leave default for the provider. Set for self-hosted models.">
                          <Input
                            value={baseUrl}
                            onChange={(e) => setBaseUrl(e.target.value)}
                            placeholder={meta(provider).urlPlaceholder}
                            className="w-[240px] font-mono text-[12px]"
                          />
                        </Row>
                      </>
                    )}

                    <Row name="Temperature" desc="0 = deterministic, higher = more creative. Empty = provider default.">
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
                        className="w-20"
                      />
                    </Row>

                    {isLocal && (
                      <>
                        <Row name="Context window" desc="num_ctx — larger reads more, fuller answers (more RAM).">
                          <Input
                            type="number"
                            step="1024"
                            min="512"
                            value={numCtx}
                            onChange={(e) => setNumCtx(Number(e.target.value))}
                            className="w-28"
                          />
                        </Row>
                        <Row name="Request timeout (s)">
                          <Input
                            type="number"
                            step="30"
                            min="10"
                            value={reqTimeout}
                            onChange={(e) => setReqTimeout(Number(e.target.value))}
                            className="w-28"
                          />
                        </Row>
                      </>
                    )}

                    <Row name="Connection" desc={`active: ${modelString}`}>
                      <div className="flex items-center gap-3">
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
                        <Button variant="outline" size="sm" onClick={runTest} disabled={testing} className="gap-1.5">
                          {testing && <Loader2 className="size-4 animate-spin" />}
                          Test connection
                        </Button>
                      </div>
                    </Row>
                  </Section>
                </>
              )}

              {/* ── Search ── */}
              {section === "search" && (
                <>
                  <div className="mb-5 text-[20px] font-semibold tracking-[-0.3px]">Search</div>
                  <Section title="Retrieval" desc="How wiki content is searched and retrieved">
                    <Row name="FTS limit" desc="Max full-text search results per query.">
                      <Input
                        type="number"
                        min="1"
                        value={ftsLimit}
                        onChange={(e) => setFtsLimit(Number(e.target.value))}
                        className="w-24"
                      />
                    </Row>
                    <Row
                      name="Embedding model"
                      desc="provider:model for semantic search (e.g. ollama:nomic-embed-text). Empty = keyword-only. Requires the [semantic] extra in the backend."
                    >
                      <Input
                        value={embeddingModel}
                        onChange={(e) => setEmbeddingModel(e.target.value)}
                        placeholder="ollama:nomic-embed-text"
                        className="w-[240px] font-mono text-[12px]"
                      />
                    </Row>
                  </Section>
                </>
              )}

              {/* ── Ingestion ── */}
              {section === "ingestion" && (
                <>
                  <div className="mb-5 text-[20px] font-semibold tracking-[-0.3px]">Ingestion</div>
                  <Section
                    title="Long-source chunking"
                    desc="Sources longer than the threshold are ingested in multiple passes"
                  >
                    <Row name="Chunk threshold (chars)" desc="Above this length the multi-pass flow kicks in.">
                      <Input
                        type="number"
                        min="0"
                        step="1000"
                        value={chunkThreshold}
                        onChange={(e) => setChunkThreshold(Number(e.target.value))}
                        className="w-28"
                      />
                    </Row>
                    <Row name="Chunk size (chars)" desc="Target size of each pass window.">
                      <Input
                        type="number"
                        min="0"
                        step="1000"
                        value={chunkSize}
                        onChange={(e) => setChunkSize(Number(e.target.value))}
                        className="w-28"
                      />
                    </Row>
                    <Row name="Chunk overlap (chars)" desc="Context carried between consecutive chunks.">
                      <Input
                        type="number"
                        min="0"
                        step="100"
                        value={chunkOverlap}
                        onChange={(e) => setChunkOverlap(Number(e.target.value))}
                        className="w-28"
                      />
                    </Row>
                  </Section>
                  <Section
                    title="Agent retries"
                    desc="How hard the agent tries before giving up"
                  >
                    <Row name="Structural fix passes" desc="Self-correction attempts on lint findings before the CR.">
                      <Input
                        type="number"
                        min="0"
                        value={agentFixRetries}
                        onChange={(e) => setAgentFixRetries(Number(e.target.value))}
                        className="w-20"
                      />
                    </Row>
                    <Row name="Max invoke retries" desc="Total agent.invoke attempts on transient errors (1 = no retry).">
                      <Input
                        type="number"
                        min="1"
                        value={agentMaxRetries}
                        onChange={(e) => setAgentMaxRetries(Number(e.target.value))}
                        className="w-20"
                      />
                    </Row>
                  </Section>
                </>
              )}

              {/* ── Transcription ── */}
              {section === "transcription" && (
                <>
                  <div className="mb-5 text-[20px] font-semibold tracking-[-0.3px]">Transcription</div>
                  <Section
                    title="Audio (faster-whisper)"
                    desc="Offline transcription of audio sources. Requires the [audio] extra in the backend."
                  >
                    <Row name="Whisper model" desc="Larger = more accurate, slower, more memory.">
                      <select
                        value={whisperModel}
                        onChange={(e) => setWhisperModel(e.target.value)}
                        className="w-[160px] rounded-md border bg-background px-3 py-2 font-mono text-[13px]"
                      >
                        {[...new Set([...WHISPER_MODELS, whisperModel])].map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                    </Row>
                    <Row name="Language" desc="ISO code (e.g. en, pt). Empty = autodetect.">
                      <Input
                        value={whisperLanguage}
                        onChange={(e) => setWhisperLanguage(e.target.value)}
                        placeholder="autodetect"
                        className="w-24 font-mono text-[12px]"
                      />
                    </Row>
                  </Section>
                </>
              )}

              {/* ── Security ── */}
              {section === "security" && (
                <>
                  <div className="mb-5 text-[20px] font-semibold tracking-[-0.3px]">Security</div>
                  <Section
                    title="API key"
                    desc="Stored in the OS keychain — never written to config files"
                  >
                    {isLocal ? (
                      <Row name={`${meta(provider).label} key`} desc="Local providers don't need an API key.">
                        <span className="text-[12px] text-muted-foreground">Not required</span>
                      </Row>
                    ) : (
                      <Row
                        name={`${meta(provider).label} key`}
                        desc={hasKey ? "Key stored in keychain — type to replace." : "Paste your key to store it securely."}
                      >
                        <div className="flex items-center gap-2">
                          <Input
                            type="password"
                            value={keyInput}
                            onChange={(e) => setKeyInput(e.target.value)}
                            placeholder={hasKey ? "•••••••••• (stored)" : "paste your key"}
                            className="w-[220px] font-mono text-[12px]"
                          />
                          <Button size="sm" onClick={saveKey} disabled={!keyInput || keyBusy} className="gap-1.5">
                            {keyBusy && <Loader2 className="size-3.5 animate-spin" />}
                            Save
                          </Button>
                          {hasKey && (
                            <Button size="sm" variant="outline" onClick={clearKey} disabled={keyBusy}>
                              Clear
                            </Button>
                          )}
                        </div>
                      </Row>
                    )}
                    <Row name="Storage" desc="Keys live in your OS keychain, scoped to the selected provider.">
                      <span className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                        {hasKey ? (
                          <>
                            <KeyRound className="size-3.5 text-apply" /> stored
                          </>
                        ) : (
                          <>
                            <Lock className="size-3.5" /> keychain
                          </>
                        )}
                      </span>
                    </Row>
                  </Section>
                </>
              )}

              {/* ── Tools ── */}
              {section === "tools" && (
                <>
                  <div className="mb-5 text-[20px] font-semibold tracking-[-0.3px]">Tools</div>

                  <Section
                    title="Command-line tools"
                    desc="Install the wiki command so you (and AI agents) can use it from a terminal"
                  >
                    {cli && (
                      <div className="space-y-3 p-4">
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
                  </Section>

                  <Section
                    title="Agent skills"
                    desc="Install skills from ~/.wiki/skills so your AI agents can use this wiki"
                  >
                    {skills && (
                      <div className="space-y-3 p-4">
                        {/* agents */}
                        <div className="space-y-1">
                          {skillAgents.map((a) => (
                            <label key={a.name} className="flex items-center gap-2 text-[13px]">
                              <Checkbox
                                checked={selectedAgents.has(a.name)}
                                onCheckedChange={(v) =>
                                  setSelectedAgents((prev) => {
                                    const n = new Set(prev)
                                    if (v) n.add(a.name)
                                    else n.delete(a.name)
                                    return n
                                  })
                                }
                              />
                              {a.display}
                              {a.detected && (
                                <span className="text-[11px] text-apply">(detected)</span>
                              )}
                            </label>
                          ))}
                        </div>

                        {/* scope + method toggles */}
                        <div className="flex flex-wrap gap-4 text-[12px]">
                          <div className="flex items-center gap-1">
                            <span className="text-muted-foreground">Scope:</span>
                            {(["local", "global", "both"] as const).map((s) => (
                              <button
                                key={s}
                                onClick={() => setSkillScope(s)}
                                className={cn(
                                  "rounded px-2 py-0.5",
                                  skillScope === s ? "bg-primary text-primary-foreground" : "hover:bg-accent",
                                )}
                              >
                                {s}
                              </button>
                            ))}
                          </div>
                          <div className="flex items-center gap-1">
                            <span className="text-muted-foreground">Method:</span>
                            {(["symlink", "copy"] as const).map((m) => (
                              <button
                                key={m}
                                onClick={() => setSkillMethod(m)}
                                className={cn(
                                  "rounded px-2 py-0.5",
                                  skillMethod === m ? "bg-primary text-primary-foreground" : "hover:bg-accent",
                                )}
                              >
                                {m}
                              </button>
                            ))}
                          </div>
                        </div>

                        {skills.installs.length > 0 && (
                          <p className="text-[11px] text-muted-foreground">
                            Installed in {skills.installs.length} location(s) · {skills.available.length} skills
                            in store
                          </p>
                        )}

                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            onClick={installSkills}
                            disabled={skillsBusy || selectedAgents.size === 0}
                            className="gap-1.5"
                          >
                            {skillsBusy && <Loader2 className="size-4 animate-spin" />}
                            {skills.installs.length > 0 ? "Reinstall / update" : "Install"}
                          </Button>
                          {skills.installs.length > 0 && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={removeSkills}
                              disabled={skillsBusy}
                            >
                              Remove all
                            </Button>
                          )}
                        </div>
                      </div>
                    )}
                  </Section>

                  <p className="mt-4 text-center font-mono text-[11px] text-muted-foreground">
                    ~/.wiki/config.yaml · keys in OS keychain
                  </p>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── sticky save bar ── */}
      <div className="flex items-center gap-3 border-t bg-card px-9 py-3">
        <span
          className={cn(
            "flex-1 text-[12.5px]",
            dirty ? "text-pending" : "text-muted-foreground",
          )}
        >
          {dirty ? "Unsaved changes" : ""}
        </span>
        <Button variant="outline" size="sm" onClick={discard} disabled={!dirty || saving}>
          Discard
        </Button>
        <Button onClick={save} disabled={!dirty || saving} className="gap-1.5">
          {saving && <Loader2 className="size-4 animate-spin" />}
          Save changes
        </Button>
      </div>
    </div>
  )
}
