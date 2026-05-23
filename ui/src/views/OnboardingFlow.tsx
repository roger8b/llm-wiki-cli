import { useEffect, useState } from "react"
import {
  Sparkles,
  ShieldCheck,
  Cloud,
  HardDrive,
  Check,
  X,
  Loader2,
  Download,
  ArrowRight,
} from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { ModelTestResult, OllamaStatus } from "@/types"
import { Button } from "@/components/ui/button"

const RECOMMENDED_LOCAL = "qwen2.5:7b"
const CLOUD_PRESETS = [
  { label: "Claude (Anthropic)", model: "anthropic:claude-sonnet-4-5", key: "ANTHROPIC_API_KEY" },
  { label: "GPT-4o (OpenAI)", model: "openai:gpt-4o", key: "OPENAI_API_KEY" },
  { label: "Gemini (Google)", model: "google:gemini-2.0-flash", key: "GOOGLE_API_KEY" },
]

interface Props {
  onDone: () => void
}

export function OnboardingFlow({ onDone }: Props) {
  const [step, setStep] = useState(0)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
      <div className="w-full max-w-[640px] px-8">
        {step === 0 && <Welcome onNext={() => setStep(1)} />}
        {step === 1 && <ModelStep onNext={() => setStep(2)} />}
        {step === 2 && <Done onDone={onDone} />}
        <Dots step={step} total={3} />
      </div>
    </div>
  )
}

function Dots({ step, total }: { step: number; total: number }) {
  return (
    <div className="mt-8 flex justify-center gap-2">
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className={cn(
            "h-1.5 rounded-full transition-all",
            i === step ? "w-6 bg-primary" : "w-1.5 bg-border",
          )}
        />
      ))}
    </div>
  )
}

// ───────────────────────────── Step 0
function Welcome({ onNext }: { onNext: () => void }) {
  return (
    <div className="text-center">
      <div className="mx-auto mb-5 flex size-14 items-center justify-center rounded-2xl bg-primary text-2xl text-primary-foreground">
        ◈
      </div>
      <h1 className="font-display text-2xl font-semibold">Welcome to llm-wiki</h1>
      <p className="mx-auto mt-3 max-w-[460px] text-[14px] leading-relaxed text-muted-foreground">
        A local-first knowledge base your AI keeps tidy. Drop in articles, notes
        or PDFs — the assistant drafts wiki pages, and{" "}
        <strong className="text-foreground">you approve every change</strong>{" "}
        before anything is saved.
      </p>
      <div className="mx-auto mt-6 grid max-w-[480px] grid-cols-3 gap-3 text-[12px] text-muted-foreground">
        <Feature icon={ShieldCheck} label="Nothing saved without your OK" />
        <Feature icon={HardDrive} label="Your data stays on your machine" />
        <Feature icon={Sparkles} label="Works with local or cloud AI" />
      </div>
      <Button onClick={onNext} className="mt-8 gap-1.5">
        Get started <ArrowRight className="size-4" />
      </Button>
    </div>
  )
}

function Feature({ icon: Icon, label }: { icon: typeof ShieldCheck; label: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5 rounded-lg border bg-card p-3">
      <Icon className="size-5 text-primary" />
      <span className="leading-tight">{label}</span>
    </div>
  )
}

// ───────────────────────────── Step 1: model
function ModelStep({ onNext }: { onNext: () => void }) {
  const [mode, setMode] = useState<"local" | "cloud">("local")
  const [ollama, setOllama] = useState<OllamaStatus | null>(null)
  const [model, setModel] = useState<string>("")
  const [test, setTest] = useState<ModelTestResult | null>(null)
  const [testing, setTesting] = useState(false)
  const [pulling, setPulling] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function refreshOllama() {
    const s = await api.ollamaModels().catch(() => ({ running: false, models: [] }))
    setOllama(s)
    return s
  }
  useEffect(() => {
    refreshOllama().then((s) => {
      if (s.running && s.models.length) setModel(`ollama:${s.models[0]}`)
    })
  }, [])

  async function runTest(m: string) {
    setTesting(true)
    setTest(null)
    try {
      setTest(await api.testModel(m))
    } finally {
      setTesting(false)
    }
  }

  async function pull(name: string) {
    setPulling(name)
    try {
      await api.pullModel(name, (e) => {
        if (typeof e.status === "string") setPulling(`${name} — ${e.status}`)
      })
      await refreshOllama()
      setModel(`ollama:${name}`)
      toast.success(`${name} ready`)
    } catch (e) {
      toast.error(`Pull failed: ${(e as Error).message}`)
    } finally {
      setPulling(null)
    }
  }

  async function save() {
    if (!model) return
    setSaving(true)
    try {
      await api.patchConfig({ model })
      onNext()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const hasRecommended = ollama?.models.some((m) => m.startsWith(RECOMMENDED_LOCAL))

  return (
    <div>
      <h1 className="text-center font-display text-xl font-semibold">
        Choose your AI model
      </h1>
      <p className="mb-5 mt-2 text-center text-[13px] text-muted-foreground">
        You can change this any time in Settings.
      </p>

      <div className="mb-4 flex gap-2">
        <ModeCard
          active={mode === "local"}
          onClick={() => setMode("local")}
          icon={HardDrive}
          title="Private & local"
          desc="Runs on your machine with Ollama. No data leaves your computer."
        />
        <ModeCard
          active={mode === "cloud"}
          onClick={() => setMode("cloud")}
          icon={Cloud}
          title="Best quality"
          desc="Claude, GPT or Gemini. Needs an API key. Faster, smarter."
        />
      </div>

      {mode === "local" ? (
        <div className="rounded-lg border bg-card p-4">
          {ollama === null ? (
            <div className="flex items-center gap-2 text-[13px] text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Detecting Ollama…
            </div>
          ) : !ollama.running ? (
            <div className="text-[13px]">
              <p className="text-rejected">Ollama is not running.</p>
              <p className="mt-1 text-muted-foreground">
                Install it from{" "}
                <a href="https://ollama.com" target="_blank" rel="noreferrer">
                  ollama.com
                </a>
                , start it, then{" "}
                <button className="text-primary underline" onClick={refreshOllama}>
                  re-check
                </button>
                .
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <label className="block text-[12px] font-medium text-muted-foreground">
                Installed models
              </label>
              <select
                value={model}
                onChange={(e) => {
                  setModel(e.target.value)
                  setTest(null)
                }}
                className="w-full rounded-md border bg-background px-3 py-2 text-[13px]"
              >
                {ollama.models.map((m) => (
                  <option key={m} value={`ollama:${m}`}>
                    {m}
                  </option>
                ))}
              </select>
              {!hasRecommended && (
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  disabled={pulling !== null}
                  onClick={() => pull(RECOMMENDED_LOCAL)}
                >
                  {pulling ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Download className="size-4" />
                  )}
                  {pulling ?? `Pull recommended: ${RECOMMENDED_LOCAL} (~4.7 GB)`}
                </Button>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {CLOUD_PRESETS.map((p) => (
            <button
              key={p.model}
              onClick={() => {
                setModel(p.model)
                setTest(null)
              }}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg border bg-card px-4 py-3 text-left transition-colors",
                model === p.model ? "border-primary ring-1 ring-primary" : "hover:bg-accent",
              )}
            >
              <Cloud className="size-5 text-primary" />
              <div className="flex-1">
                <div className="text-[13px] font-medium">{p.label}</div>
                <div className="font-mono text-[11px] text-muted-foreground">
                  {p.model} · needs {p.key}
                </div>
              </div>
              {model === p.model && <Check className="size-4 text-primary" />}
            </button>
          ))}
        </div>
      )}

      {/* test + continue */}
      <div className="mt-4 flex items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          disabled={!model || testing}
          onClick={() => runTest(model)}
          className="gap-1.5"
        >
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
        <Button onClick={save} disabled={!model || saving} className="ml-auto gap-1.5">
          {saving && <Loader2 className="size-4 animate-spin" />}
          Continue <ArrowRight className="size-4" />
        </Button>
      </div>
    </div>
  )
}

function ModeCard({
  active,
  onClick,
  icon: Icon,
  title,
  desc,
}: {
  active: boolean
  onClick: () => void
  icon: typeof Cloud
  title: string
  desc: string
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex-1 rounded-lg border bg-card p-4 text-left transition-colors",
        active ? "border-primary ring-1 ring-primary" : "hover:bg-accent",
      )}
    >
      <Icon className={cn("size-5", active ? "text-primary" : "text-muted-foreground")} />
      <div className="mt-2 text-[13px] font-medium">{title}</div>
      <div className="mt-0.5 text-[12px] leading-snug text-muted-foreground">{desc}</div>
    </button>
  )
}

// ───────────────────────────── Step 2: done
function Done({ onDone }: { onDone: () => void }) {
  const [finishing, setFinishing] = useState(false)
  async function finish() {
    setFinishing(true)
    try {
      await api.patchConfig({ onboarded: true })
      onDone()
    } finally {
      setFinishing(false)
    }
  }
  return (
    <div className="text-center">
      <div className="mx-auto mb-5 flex size-14 items-center justify-center rounded-full bg-apply/15 text-apply">
        <Check className="size-7" />
      </div>
      <h1 className="font-display text-2xl font-semibold">You're all set</h1>
      <p className="mx-auto mt-3 max-w-[440px] text-[14px] leading-relaxed text-muted-foreground">
        Add your first source — an article, a PDF or pasted notes — and the
        assistant will draft wiki pages for you to review.
      </p>
      <Button onClick={finish} disabled={finishing} className="mt-7 gap-1.5">
        {finishing && <Loader2 className="size-4 animate-spin" />}
        Start using llm-wiki <ArrowRight className="size-4" />
      </Button>
    </div>
  )
}
