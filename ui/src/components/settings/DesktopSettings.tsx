import { useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { DesktopConfig } from "@/types"
import { Switch } from "@/components/ui/switch"

/**
 * Desktop-shell preferences (#204). Only meaningful inside the Tauri app — the
 * Rust tray reads these from <brain>/.llmwiki/desktop.json. Harmless in a browser.
 */
/** Tauri bridge invoke (withGlobalTauri); undefined in a plain browser. */
function tauriInvoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> | null {
  const bridge = (globalThis as { __TAURI__?: { core?: { invoke?: Function } } }).__TAURI__
  const invoke = bridge?.core?.invoke
  return invoke ? (invoke(cmd, args) as Promise<T>) : null
}

export function DesktopSettings() {
  const [cfg, setCfg] = useState<DesktopConfig | null>(null)
  const [saving, setSaving] = useState(false)
  // Launch-at-login lives in the OS (Tauri plugin), not the backend config.
  const [autostart, setAutostart] = useState<boolean | null>(null)

  useEffect(() => {
    api.getDesktopConfig().then(setCfg).catch(() => setCfg(null))
    tauriInvoke<boolean>("get_autostart")
      ?.then(setAutostart)
      .catch(() => setAutostart(null))
  }, [])

  async function toggleAutostart(enabled: boolean) {
    const p = tauriInvoke<void>("set_autostart", { enabled })
    if (!p) return
    setSaving(true)
    try {
      await p
      setAutostart(enabled)
    } catch {
      toast.error("Could not change launch-at-login")
    } finally {
      setSaving(false)
    }
  }

  async function update(patch: Partial<DesktopConfig>) {
    setSaving(true)
    try {
      const next = await api.patchDesktopConfig(patch)
      setCfg(next)
    } catch {
      toast.error("Could not save desktop setting")
    } finally {
      setSaving(false)
    }
  }

  if (!cfg) return null

  return (
    <div className="mt-6 rounded-lg border">
      <div className="border-b px-4 py-3">
        <h3 className="text-[13.5px] font-semibold">Desktop app</h3>
        <p className="mt-0.5 text-[12px] text-muted-foreground">
          Applies only to the desktop app, not the browser.
        </p>
      </div>
      <div className="flex items-center gap-4 border-b px-4 py-3 last:border-b-0">
        <div className="flex-1">
          <span className="block text-[13.5px] font-medium">Keep running in background</span>
          <span className="mt-0.5 block text-[12px] text-muted-foreground">
            Closing the window keeps the app in the menu-bar tray so long ingests
            finish. Off = closing the window quits.
          </span>
        </div>
        <Switch
          checked={cfg.run_in_background}
          disabled={saving}
          onCheckedChange={(v) => update({ run_in_background: v })}
        />
      </div>
      <div
        className={
          autostart === null
            ? "flex items-center gap-4 px-4 py-3"
            : "flex items-center gap-4 border-b px-4 py-3"
        }
      >
        <div className="flex-1">
          <span className="block text-[13.5px] font-medium">Notify on jobs</span>
          <span className="mt-0.5 block text-[12px] text-muted-foreground">
            Show a native notification when a background job finishes.
          </span>
        </div>
        <Switch
          checked={cfg.notify_on_jobs}
          disabled={saving}
          onCheckedChange={(v) => update({ notify_on_jobs: v })}
        />
      </div>
      <div className="flex items-center gap-4 border-b px-4 py-3">
        <div className="flex-1">
          <span className="block text-[13.5px] font-medium">Notify when ingestion starts</span>
          <span className="mt-0.5 block text-[12px] text-muted-foreground">
            Also ping when an ingestion begins, not only when it finishes. The
            tray always shows the current step while it runs.
          </span>
        </div>
        <Switch
          checked={cfg.notify_granularity === "all"}
          disabled={saving || !cfg.notify_on_jobs}
          onCheckedChange={(v) => update({ notify_granularity: v ? "all" : "terminal" })}
        />
      </div>
      {autostart !== null && (
        <div className="flex items-center gap-4 px-4 py-3">
          <div className="flex-1">
            <span className="block text-[13.5px] font-medium">Start at login</span>
            <span className="mt-0.5 block text-[12px] text-muted-foreground">
              Launch hidden in the tray when you log in, so the brain is always
              available.
            </span>
          </div>
          <Switch
            checked={autostart}
            disabled={saving}
            onCheckedChange={toggleAutostart}
          />
        </div>
      )}
    </div>
  )
}
