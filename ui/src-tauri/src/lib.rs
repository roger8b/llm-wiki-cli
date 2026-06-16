// llm-wiki desktop shell.
//
// Boots the Python FastAPI backend (a PyInstaller onedir bundle shipped as a
// Tauri resource) on a dynamic port, waits for `/api/health` to return 200, then
// opens a WebView pointing at it. The backend serves both the SPA and the /api
// routes on the same origin, so the React app's "/api" base works unchanged.

use std::collections::HashMap;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder, WindowEvent, Wry};
use tauri_plugin_autostart::ManagerExt;
use tauri_plugin_clipboard_manager::ClipboardExt;
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};
use tauri_plugin_notification::NotificationExt;

/// Holds the running backend process so we can kill it on exit.
struct Backend(Mutex<Option<Child>>);

/// Session state needed to rebuild/refocus the main window from the tray without
/// spawning a second backend (same port/token), plus the desktop preferences the
/// Rust shell acts on (#204).
struct AppSession {
    url: String,
    token: String,
    brain: String,
    port: u16,
    /// When false, closing the window quits (legacy behavior).
    run_in_background: AtomicBool,
    /// Tray menu item showing the running-job count; updated by the poll thread.
    jobs_item: Mutex<Option<MenuItem<Wry>>>,
    /// Last seen `{job_id: status}` snapshot for transition detection (#205).
    prev_jobs: Mutex<HashMap<i64, String>>,
    /// Route to navigate to when the window is next opened (set when a
    /// notification fires; consumed by `open_main_window`). (#205)
    pending_route: Mutex<Option<String>>,
}

/// A native notification to fire on a job state transition (#205). Pure data so
/// the detection logic is unit-testable without a live backend.
#[derive(Debug, PartialEq)]
struct JobNote {
    title: String,
    body: String,
    /// SPA route to open on click (e.g. "/review", "/jobs").
    route: String,
}

/// Ask the OS for a free TCP port by binding to :0 and reading it back.
fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .expect("no free port")
        .local_addr()
        .unwrap()
        .port()
}

/// Block until the backend answers `GET /api/health` with HTTP 200 (or we give up).
///
/// A bare TCP check returns as soon as uvicorn binds the port, which can be well
/// before FastAPI finishes wiring routes — opening the WebView then races a backend
/// that 404s the SPA. The health probe is served before any brain is loaded, so it
/// flips to ready at the exact moment the backend can serve requests.
fn wait_for_http_ready(port: u16, timeout: Duration) -> bool {
    let addr = format!("127.0.0.1:{port}");
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if http_health_ok(&addr) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(150));
    }
    false
}

/// One `GET /api/health` attempt over a short-lived connection. Returns true on 200.
fn http_health_ok(addr: &str) -> bool {
    let sock = match addr.parse() {
        Ok(s) => s,
        Err(_) => return false,
    };
    let Ok(mut stream) = TcpStream::connect_timeout(&sock, Duration::from_millis(300)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let req = format!(
        "GET /api/health HTTP/1.1\r\nHost: {addr}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 64];
    let Ok(n) = stream.read(&mut buf) else {
        return false;
    };
    buf.get(..n)
        .and_then(|b| std::str::from_utf8(b).ok())
        .is_some_and(|s| s.starts_with("HTTP/1.1 200") || s.starts_with("HTTP/1.0 200"))
}

/// Minimal authenticated `GET` over a short-lived connection, returning the body
/// (everything after the blank line). Used by the lightweight tray job poll so we
/// avoid pulling in a full HTTP client just for one call every 15s.
fn http_get_body(port: u16, path: &str, token: &str) -> Option<String> {
    let addr = format!("127.0.0.1:{port}");
    let sock = addr.parse().ok()?;
    let mut stream = TcpStream::connect_timeout(&sock, Duration::from_millis(500)).ok()?;
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let req = format!(
        "GET {path} HTTP/1.1\r\nHost: {addr}\r\nX-Wiki-Token: {token}\r\nConnection: close\r\n\r\n"
    );
    stream.write_all(req.as_bytes()).ok()?;
    let mut raw = String::new();
    stream.read_to_string(&mut raw).ok()?;
    let idx = raw.find("\r\n\r\n")?;
    Some(raw[idx + 4..].to_string())
}

/// Count jobs currently `running` from a `GET /api/jobs` body. Pure so it can be
/// unit-tested without a live backend.
fn count_running_jobs(body: &str) -> usize {
    let Ok(serde_json::Value::Array(items)) = serde_json::from_str::<serde_json::Value>(body) else {
        return 0;
    };
    items
        .iter()
        .filter(|j| j.get("status").and_then(|s| s.as_str()) == Some("running"))
        .count()
}

/// Parse the `pid` out of a `server.lock` JSON body (`{"pid": N, "port": M}`).
fn parse_lock_pid(body: &str) -> Option<u32> {
    let v: serde_json::Value = serde_json::from_str(body).ok()?;
    v.get("pid")?.as_u64().map(|p| p as u32)
}

/// True if `pid` is currently a `wiki-backend` process (guards against reusing a
/// recycled pid that now belongs to something innocent).
fn pid_is_backend(pid: u32) -> bool {
    Command::new("ps")
        .args(["-p", &pid.to_string(), "-o", "comm="])
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).contains("wiki-backend"))
        .unwrap_or(false)
}

/// Read a boolean preference from `<brain>/.llmwiki/desktop.json` (written by the
/// backend, #204/#205). Defaults to `default` when missing/unreadable.
fn read_desktop_bool(brain: &str, key: &str, default: bool) -> bool {
    let path = PathBuf::from(brain).join(".llmwiki/desktop.json");
    match std::fs::read_to_string(&path) {
        Ok(body) => serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get(key).and_then(|b| b.as_bool()))
            .unwrap_or(default),
        Err(_) => default,
    }
}

/// Read a string-valued desktop setting (e.g. `notify_granularity`), falling
/// back to `default` when missing/unreadable (#275).
fn read_desktop_str(brain: &str, key: &str, default: &str) -> String {
    let path = PathBuf::from(brain).join(".llmwiki/desktop.json");
    match std::fs::read_to_string(&path) {
        Ok(body) => serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get(key).and_then(|s| s.as_str()).map(String::from))
            .unwrap_or_else(|| default.to_string()),
        Err(_) => default.to_string(),
    }
}

/// Parse a `/api/jobs` body into a `{job_id: status}` map. Pure.
fn jobs_status_map(body: &str) -> HashMap<i64, String> {
    let mut out = HashMap::new();
    if let Ok(serde_json::Value::Array(items)) = serde_json::from_str::<serde_json::Value>(body) {
        for j in items {
            if let (Some(id), Some(status)) = (
                j.get("id").and_then(|v| v.as_i64()),
                j.get("status").and_then(|v| v.as_str()),
            ) {
                out.insert(id, status.to_string());
            }
        }
    }
    out
}

/// Detect job notifications by diffing the previous status snapshot against the
/// current `/api/jobs` body. A notification fires only when a job we previously
/// saw as non-terminal (queued/running) has reached a terminal state — so the
/// first poll (empty `prev`) is silent and a job is never notified twice.
fn detect_notifications(prev: &HashMap<i64, String>, body: &str) -> Vec<JobNote> {
    let mut notes = Vec::new();
    let Ok(serde_json::Value::Array(items)) = serde_json::from_str::<serde_json::Value>(body)
    else {
        return notes;
    };
    for j in items {
        let Some(id) = j.get("id").and_then(|v| v.as_i64()) else {
            continue;
        };
        let status = j.get("status").and_then(|v| v.as_str()).unwrap_or("");
        let terminal = matches!(status, "done" | "error" | "cancelled");
        if !terminal {
            continue;
        }
        match prev.get(&id).map(String::as_str) {
            Some("queued") | Some("running") => {}
            _ => continue, // not seen before, or already terminal last time
        }
        let job_type = j.get("type").and_then(|v| v.as_str()).unwrap_or("job");
        notes.push(build_note(job_type, status, &j));
    }
    notes
}

/// Human label for an ingestion progress step (#275), mirroring the web
/// `IngestionProgress` labels so the tray reads the same as the panel.
fn ingest_progress_label(progress: &str) -> String {
    match progress {
        "extracting" => "reading source".into(),
        "outlining" => "planning concepts".into(),
        "running_agent" => "writing pages".into(),
        "fixing_structural_issues" => "fixing issues".into(),
        "creating_change_request" => "finishing".into(),
        other => other.to_string(), // "chunk 2/4" passes through verbatim
    }
}

/// The tray "jobs" line. When an ingest job is running, surface its live step
/// ("Ingesting: chunk 2/4") so background progress is visible without opening
/// the window (#275). Otherwise fall back to a plain running count.
fn tray_jobs_label(body: &str) -> String {
    let n = count_running_jobs(body);
    if n == 0 {
        return "No jobs running".into();
    }
    let items = match serde_json::from_str::<serde_json::Value>(body) {
        Ok(serde_json::Value::Array(items)) => items,
        _ => return format!("Jobs running: {n}"),
    };
    // Prefer the ingest job's step, since that's the slow, user-watched one.
    let ingest_step = items.iter().find_map(|j| {
        let running = j.get("status").and_then(|v| v.as_str()) == Some("running");
        let ingest = j.get("type").and_then(|v| v.as_str()) == Some("ingest");
        if running && ingest {
            j.get("progress")
                .and_then(|v| v.as_str())
                .filter(|s| !s.is_empty())
                .map(ingest_progress_label)
        } else {
            None
        }
    });
    match ingest_step {
        Some(step) => format!("Ingesting: {step}"),
        None => format!("Jobs running: {n}"),
    }
}

/// Notifications for jobs that have just *started* (queued/none -> running),
/// fired only when the user opted into "all" transitions (#275). Terminal
/// notifications are always handled by `detect_notifications`.
fn detect_start_notifications(prev: &HashMap<i64, String>, body: &str) -> Vec<JobNote> {
    let mut notes = Vec::new();
    let Ok(serde_json::Value::Array(items)) = serde_json::from_str::<serde_json::Value>(body)
    else {
        return notes;
    };
    for j in items {
        let Some(id) = j.get("id").and_then(|v| v.as_i64()) else {
            continue;
        };
        if j.get("status").and_then(|v| v.as_str()) != Some("running") {
            continue;
        }
        // Only the queued->running (or first-seen-as-running) edge, once.
        if prev.get(&id).map(String::as_str) == Some("running") {
            continue; // already running last poll
        }
        if j.get("type").and_then(|v| v.as_str()) != Some("ingest") {
            continue; // ingestion is the long job worth a start ping
        }
        notes.push(JobNote {
            title: "Ingestion started".into(),
            body: "Reading the source and updating the wiki".into(),
            route: "/jobs".into(),
        });
    }
    notes
}

/// Build the user-facing notification for one terminal transition.
fn build_note(job_type: &str, status: &str, job: &serde_json::Value) -> JobNote {
    let is_ingest = job_type == "ingest";
    match status {
        "done" => {
            // Ingest results carry a CR id to review; route there.
            let result = job
                .get("result")
                .and_then(|r| r.as_str())
                .and_then(|s| serde_json::from_str::<serde_json::Value>(s).ok());
            let cr = result
                .as_ref()
                .and_then(|v| v.get("cr").and_then(|c| c.as_str()).map(String::from));
            // A "phantom" ingest: the agent wrote nothing (empty CR / note set).
            // Surface it as a distinct notification, not a misleading "ready".
            let empty = result.as_ref().is_some_and(|v| {
                v.get("note").is_some()
                    || v.get("files").and_then(|f| f.as_i64()) == Some(0)
                    || v.get("skipped").and_then(|s| s.as_bool()) == Some(true)
            });
            if is_ingest {
                if empty {
                    return JobNote {
                        title: "Ingestion finished — no pages written".into(),
                        body: "The agent proposed no changes for this source".into(),
                        route: "/jobs".into(),
                    };
                }
                let body = match cr {
                    Some(cr) => format!("{cr} ready to review"),
                    None => "Change request ready to review".to_string(),
                };
                JobNote { title: "Ingestion finished".into(), body, route: "/review".into() }
            } else {
                JobNote {
                    title: "Job finished".into(),
                    body: format!("{job_type} completed"),
                    route: "/jobs".into(),
                }
            }
        }
        "error" => {
            let first_line = job
                .get("error")
                .and_then(|e| e.as_str())
                .map(|e| e.lines().next().unwrap_or("").to_string())
                .filter(|s| !s.is_empty())
                .unwrap_or_else(|| "See Jobs for details".to_string());
            let title = if is_ingest { "Ingestion failed" } else { "Job failed" };
            JobNote { title: title.into(), body: first_line, route: "/jobs".into() }
        }
        _ => JobNote {
            title: "Job cancelled".into(),
            body: format!("{job_type} was cancelled"),
            route: "/jobs".into(),
        },
    }
}

/// Kill stray backend processes left over from a prior run (crash / force-quit).
///
/// Prefers the precise `<brain>/.llmwiki/server.lock` (pid+port written by the
/// backend, #203): validate the pid is still a `wiki-backend`, SIGTERM then
/// SIGKILL exactly that process, and remove the lock. Falls back to the old
/// broad `pkill -f <brain>` only when no lockfile exists (first migration) so a
/// separately-launched `wiki serve` on another brain is never touched.
fn kill_stray_backends(brain: &str) {
    let lock = PathBuf::from(brain).join(".llmwiki/server.lock");
    if let Ok(body) = std::fs::read_to_string(&lock) {
        if let Some(pid) = parse_lock_pid(&body) {
            if pid_is_backend(pid) {
                let _ = Command::new("kill").args(["-TERM", &pid.to_string()]).status();
                std::thread::sleep(Duration::from_millis(500));
                if pid_is_backend(pid) {
                    let _ = Command::new("kill").args(["-KILL", &pid.to_string()]).status();
                }
                eprintln!("[llm-wiki] killed stray backend pid={pid} via lockfile");
            }
        }
        let _ = std::fs::remove_file(&lock);
        return;
    }
    // Fallback for installs predating the lockfile.
    match Command::new("pkill").args(["-f", brain]).status() {
        Ok(status) => eprintln!("[llm-wiki] pkill stray backends (brain={brain}): {status}"),
        Err(err) => eprintln!("[llm-wiki] pkill unavailable: {err}"),
    }
}

/// Stop the backend child gracefully: SIGTERM, wait up to 5s for a clean exit
/// (so uvicorn/FastAPI run their shutdown and the worker marks state), then
/// SIGKILL as a last resort. Avoids the previous immediate `child.kill()`
/// (SIGKILL) that could leave jobs `running` and risk SQLite corruption.
fn graceful_stop(child: &mut Child) {
    let pid = child.id();
    let _ = Command::new("kill").args(["-TERM", &pid.to_string()]).status();
    let deadline = Instant::now() + Duration::from_secs(5);
    while Instant::now() < deadline {
        if let Ok(Some(_)) = child.try_wait() {
            eprintln!("[llm-wiki] backend exited cleanly on SIGTERM (pid={pid})");
            return;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    eprintln!("[llm-wiki] backend did not exit in 5s — sending SIGKILL (pid={pid})");
    let _ = child.kill();
    let _ = child.wait();
}

/// Set the macOS activation policy. `Accessory` removes the app from the Dock and
/// Cmd-Tab while it lives only in the menubar tray; `Regular` restores it when a
/// window is visible. No-op off macOS.
#[cfg(target_os = "macos")]
fn set_activation(handle: &AppHandle, policy: tauri::ActivationPolicy) {
    let _ = handle.set_activation_policy(policy);
}
#[cfg(not(target_os = "macos"))]
fn set_activation(_handle: &AppHandle, _accessory: bool) {}

#[cfg(target_os = "macos")]
fn show_in_dock(handle: &AppHandle) {
    set_activation(handle, tauri::ActivationPolicy::Regular);
}
#[cfg(target_os = "macos")]
fn hide_from_dock(handle: &AppHandle) {
    set_activation(handle, tauri::ActivationPolicy::Accessory);
}
#[cfg(not(target_os = "macos"))]
fn show_in_dock(_handle: &AppHandle) {}
#[cfg(not(target_os = "macos"))]
fn hide_from_dock(_handle: &AppHandle) {}

/// Show/refocus the main window, recreating it (same session port/token) if it was
/// destroyed. Centralizes window creation so both the initial boot and tray
/// "Open" reuse the identical init script / sizing.
fn open_main_window(handle: &AppHandle) {
    if let Some(win) = handle.get_webview_window("main") {
        let _ = win.show();
        let _ = win.unminimize();
        let _ = win.set_focus();
        show_in_dock(handle);
        navigate_pending(handle, &win);
        return;
    }
    let session = handle.state::<AppSession>();
    let url = session.url.clone();
    let token = session.token.clone();
    let win = WebviewWindowBuilder::new(handle, "main", WebviewUrl::External(url.parse().unwrap()))
        .title("llm-wiki")
        .inner_size(1280.0, 860.0)
        .min_inner_size(900.0, 600.0)
        .initialization_script(format!("window.__WIKI_TOKEN__ = {token:?};"))
        .build()
        .expect("failed to build window");
    show_in_dock(handle);
    navigate_pending(handle, &win);
}

/// If a notification queued a route (#205), navigate the SPA there. The front has
/// no Tauri bridge, so we drive it with `location.assign` — accepted per #205.
fn navigate_pending(handle: &AppHandle, win: &tauri::WebviewWindow) {
    let route = handle
        .state::<AppSession>()
        .pending_route
        .lock()
        .unwrap()
        .take();
    if let Some(route) = route {
        let _ = win.eval(format!("window.location.assign({route:?})"));
    }
}

/// Read the clipboard text, capped so a huge clipboard doesn't bloat the window
/// init script. Empty on failure (quick-capture then opens blank).
fn read_clipboard_text(handle: &AppHandle) -> String {
    let mut text = handle.clipboard().read_text().unwrap_or_default();
    const CAP: usize = 10_000;
    if text.len() > CAP {
        text.truncate(CAP);
    }
    text
}

/// True if the process was launched with `--hidden` (autostart at login starts in
/// the tray with no window, #207). Pure so it's unit-testable.
fn has_hidden_flag(args: &[String]) -> bool {
    args.iter().any(|a| a == "--hidden")
}

/// Enable/disable launch-at-login (#207). Invoked from the SPA via the Tauri
/// bridge (`withGlobalTauri`).
#[tauri::command]
fn set_autostart(app: AppHandle, enabled: bool) -> Result<(), String> {
    let mgr = app.autolaunch();
    if enabled {
        mgr.enable().map_err(|e| e.to_string())
    } else {
        mgr.disable().map_err(|e| e.to_string())
    }
}

/// Read the real OS launch-at-login state so the Settings toggle reflects reality.
#[tauri::command]
fn get_autostart(app: AppHandle) -> Result<bool, String> {
    app.autolaunch().is_enabled().map_err(|e| e.to_string())
}

/// The global quick-capture shortcut: Cmd+Shift+K (Ctrl+Shift+K off macOS).
fn capture_shortcut() -> Shortcut {
    Shortcut::new(Some(Modifiers::SUPER | Modifiers::SHIFT), Code::KeyK)
}

/// Open (or focus) the small always-on-top quick-capture window at `/capture`,
/// prefilled with the clipboard. Works with the main window closed since the
/// backend stays alive in the background (#204/#206).
fn open_capture_window(handle: &AppHandle) {
    if let Some(win) = handle.get_webview_window("capture") {
        let _ = win.show();
        let _ = win.set_focus();
        return;
    }
    let session = handle.state::<AppSession>();
    let token = session.token.clone();
    let url = format!("{}/capture", session.url);
    let clip = read_clipboard_text(handle);
    let init = format!("window.__WIKI_TOKEN__ = {token:?}; window.__WIKI_CAPTURE__ = {clip:?};");
    WebviewWindowBuilder::new(handle, "capture", WebviewUrl::External(url.parse().unwrap()))
        .title("Quick capture")
        .inner_size(520.0, 320.0)
        .always_on_top(true)
        .center()
        .initialization_script(&init)
        .build()
        .expect("failed to build capture window");
    show_in_dock(handle);
}

/// Resolve the PyInstaller onedir backend executable.
///
/// In a bundled `.app` the onedir folder ships under the resource dir as
/// `binaries/wiki-backend/wiki-backend` (with its sibling `_internal/`), since
/// Tauri preserves each resource's path relative to src-tauri. When running the
/// raw `target/release` binary during development, the resource dir doesn't hold
/// it, so fall back to the in-tree `binaries/` folder produced by build_sidecar.sh.
fn resolve_backend_exe(handle: &tauri::AppHandle) -> PathBuf {
    if let Ok(res) = handle.path().resource_dir() {
        // Tauri preserves each resource's path relative to src-tauri, so the
        // glob "binaries/wiki-backend/**/*" lands under <res>/binaries/wiki-backend/.
        for rel in ["binaries/wiki-backend/wiki-backend", "wiki-backend/wiki-backend"] {
            let candidate = res.join(rel);
            if candidate.exists() {
                return candidate;
            }
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("binaries/wiki-backend/wiki-backend")
}

/// Default brain for the desktop app: ~/.wiki/brains/desktop (auto-created by
/// `wiki serve --brain`).
fn default_brain() -> String {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    format!("{home}/.wiki/brains/desktop")
}

/// A random per-session API token. 32 bytes of OS entropy, hex-encoded.
///
/// Passed to the backend via env (WIKI_API_TOKEN) and injected into the WebView
/// so the SPA can authenticate; this keeps other local processes and any
/// browser page from driving the local API.
fn gen_token() -> String {
    use std::io::Read;
    let mut buf = [0u8; 32];
    if let Ok(mut f) = std::fs::File::open("/dev/urandom") {
        if f.read_exact(&mut buf).is_ok() {
            return buf.iter().map(|b| format!("{b:02x}")).collect();
        }
    }
    // Degraded fallback if /dev/urandom is unavailable.
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("{nanos:x}{:x}", std::process::id())
}

/// Background thread: every 15s poll `GET /api/jobs` to (a) refresh the tray's
/// "Jobs running: N" item and (b) fire native notifications on terminal job
/// transitions (#205). Backend down → silent (no regression). Notifications are
/// suppressed when a window is focused, and honor the `notify_on_jobs` toggle.
fn spawn_job_poll(handle: AppHandle) {
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_secs(15));
        let session = handle.state::<AppSession>();

        // Re-read the persisted background pref each tick so the Settings toggle
        // takes effect without an app restart (consumed by hide-on-close).
        let run_bg = read_desktop_bool(&session.brain, "run_in_background", true);
        session.run_in_background.store(run_bg, Ordering::Relaxed);

        let Some(body) = http_get_body(session.port, "/api/jobs?limit=50", &session.token) else {
            continue;
        };

        // Tray job-count item (matters while hidden; cheap to always refresh).
        // Surfaces the live ingest step ("Ingesting: chunk 2/4") when one runs.
        let item = session.jobs_item.lock().unwrap().clone();
        if let Some(item) = item {
            let _ = item.set_text(tray_jobs_label(&body));
        }

        // Notifications on job transitions (#205, #275).
        if read_desktop_bool(&session.brain, "notify_on_jobs", true) {
            let prev = session.prev_jobs.lock().unwrap().clone();
            let mut notes = detect_notifications(&prev, &body);
            // "all" granularity also pings on the start of an ingestion (#275);
            // default "terminal" keeps only the finish/error notifications.
            if read_desktop_str(&session.brain, "notify_granularity", "terminal") == "all" {
                notes.extend(detect_start_notifications(&prev, &body));
            }
            let focused = handle
                .get_webview_window("main")
                .and_then(|w| w.is_focused().ok())
                .unwrap_or(false);
            if !focused {
                for note in notes {
                    *session.pending_route.lock().unwrap() = Some(note.route.clone());
                    let _ = handle
                        .notification()
                        .builder()
                        .title(&note.title)
                        .body(&note.body)
                        .show();
                }
            }
        }
        *session.prev_jobs.lock().unwrap() = jobs_status_map(&body);
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // Single instance MUST be registered first (plugin docs): a second
        // launch focuses the existing window instead of spawning a 2nd backend.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            open_main_window(app);
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        // Autostart at login, launched hidden into the tray (#207).
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--hidden"]),
        ))
        .invoke_handler(tauri::generate_handler![set_autostart, get_autostart])
        // Global shortcut (Cmd/Ctrl+Shift+K) → quick capture. The handler fires
        // for any registered shortcut; we match on the capture combo (#206).
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    if event.state() == ShortcutState::Pressed
                        && shortcut == &capture_shortcut()
                    {
                        open_capture_window(app);
                    }
                })
                .build(),
        )
        .manage(Backend(Mutex::new(None)))
        .setup(|app| {
            let port = free_port();
            let brain = default_brain();
            let token = gen_token();
            let url = format!("http://127.0.0.1:{port}");
            eprintln!("[llm-wiki] Using port={port}, brain={brain}");

            // Persisted desktop preference (#204); default-on for background.
            let run_bg = read_desktop_bool(&brain, "run_in_background", true);
            app.manage(AppSession {
                url: url.clone(),
                token: token.clone(),
                brain: brain.clone(),
                port,
                run_in_background: AtomicBool::new(run_bg),
                jobs_item: Mutex::new(None),
                prev_jobs: Mutex::new(HashMap::new()),
                pending_route: Mutex::new(None),
            });

            // Tray icon + menu (Open / Jobs status / Quit). All tray logic lives
            // on the Rust side; the SPA stays unaware (#204 decision).
            let open_i = MenuItem::with_id(app, "open", "Open llm-wiki", true, None::<&str>)?;
            let jobs_i = MenuItem::with_id(app, "jobs", "No jobs running", false, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let sep1 = PredefinedMenuItem::separator(app)?;
            let sep2 = PredefinedMenuItem::separator(app)?;
            let menu = Menu::with_items(app, &[&open_i, &sep1, &jobs_i, &sep2, &quit_i])?;
            app.state::<AppSession>()
                .jobs_item
                .lock()
                .unwrap()
                .replace(jobs_i.clone());
            let _tray = TrayIconBuilder::with_id("main")
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => open_main_window(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        open_main_window(tray.app_handle());
                    }
                })
                .build(app)?;

            // Reap orphaned backends from a prior crash/force-quit before spawning.
            kill_stray_backends(&brain);

            // Spawn the FastAPI backend (PyInstaller onedir exe). The token goes
            // via env (not argv) so it doesn't leak in `ps`.
            let exe = resolve_backend_exe(app.handle());
            eprintln!("[llm-wiki] backend exe: {}", exe.display());
            let t0 = Instant::now();
            let child = Command::new(&exe)
                .args([
                    "serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    &port.to_string(),
                    "--brain",
                    &brain,
                ])
                .env("WIKI_API_TOKEN", &token)
                .spawn()
                .expect("failed to start backend");
            let child_pid = child.id();
            app.state::<Backend>().0.lock().unwrap().replace(child);
            eprintln!(
                "[llm-wiki] backend spawn took {:.1}s, pid={}",
                t0.elapsed().as_secs_f32(),
                child_pid
            );

            // Autostart launches with `--hidden`: keep the backend + tray alive
            // but don't pop a window in the user's face on login (#207).
            let hidden = has_hidden_flag(&std::env::args().collect::<Vec<_>>());
            if hidden {
                hide_from_dock(app.handle());
            }

            // Wait for readiness, then open the window pointing at the backend
            // (unless we started hidden — then only the tray is live).
            let handle = app.handle().clone();
            let t1 = Instant::now();
            std::thread::spawn(move || {
                let ready = wait_for_http_ready(port, Duration::from_secs(60));
                eprintln!(
                    "[llm-wiki] wait_for_http_ready() took {:.1}s, ready={}, port={}",
                    t1.elapsed().as_secs_f32(),
                    ready,
                    port
                );
                if !ready {
                    eprintln!("[llm-wiki] Backend did not become ready in 60s — aborting");
                    return;
                }
                if !hidden {
                    open_main_window(&handle);
                }
            });

            spawn_job_poll(app.handle().clone());

            // Register the global quick-capture shortcut once (#206).
            if let Err(err) = app.global_shortcut().register(capture_shortcut()) {
                eprintln!("[llm-wiki] could not register quick-capture shortcut: {err}");
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            // Hide-on-close: keep the backend (and any running job) alive in the
            // tray instead of quitting, unless the user opted out (#204).
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() != "main" {
                    return;
                }
                let app = window.app_handle();
                let keep = app
                    .try_state::<AppSession>()
                    .map(|s| s.run_in_background.load(Ordering::Relaxed))
                    .unwrap_or(true);
                if keep {
                    api.prevent_close();
                    let _ = window.hide();
                    hide_from_dock(app);
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri app")
        .run(|app, event| match event {
            // Stop the backend gracefully when the app exits (SIGTERM → wait →
            // SIGKILL) so uvicorn runs shutdown and the worker marks job state
            // instead of dying mid-job (#203).
            RunEvent::ExitRequested { .. } | RunEvent::Exit => {
                if let Some(mut child) = app.state::<Backend>().0.lock().unwrap().take() {
                    graceful_stop(&mut child);
                }
            }
            // Clicking the Dock icon (macOS) when no window is open reopens it.
            #[cfg(target_os = "macos")]
            RunEvent::Reopen { .. } => open_main_window(app),
            _ => {}
        });
}

#[cfg(test)]
mod tests {
    use super::{
        count_running_jobs, detect_notifications, detect_start_notifications,
        ingest_progress_label, jobs_status_map, tray_jobs_label,
    };
    use std::collections::HashMap;

    fn prev(pairs: &[(i64, &str)]) -> HashMap<i64, String> {
        pairs.iter().map(|(k, v)| (*k, v.to_string())).collect()
    }

    #[test]
    fn first_poll_is_silent() {
        let body = r#"[{"id":1,"type":"ingest","status":"done","result":"{\"cr\":\"CR-1\"}"}]"#;
        assert!(detect_notifications(&prev(&[]), body).is_empty());
    }

    #[test]
    fn ingest_done_routes_to_review_with_cr() {
        let body = r#"[{"id":1,"type":"ingest","status":"done","result":"{\"cr\":\"CR-2026-0042\"}"}]"#;
        let notes = detect_notifications(&prev(&[(1, "running")]), body);
        assert_eq!(notes.len(), 1);
        assert_eq!(notes[0].title, "Ingestion finished");
        assert!(notes[0].body.contains("CR-2026-0042"));
        assert_eq!(notes[0].route, "/review");
    }

    #[test]
    fn failed_job_routes_to_jobs_with_error() {
        let body = r#"[{"id":2,"type":"ingest","status":"error","error":"boom: bad pdf\nstacktrace"}]"#;
        let notes = detect_notifications(&prev(&[(2, "running")]), body);
        assert_eq!(notes.len(), 1);
        assert_eq!(notes[0].title, "Ingestion failed");
        assert_eq!(notes[0].body, "boom: bad pdf");
        assert_eq!(notes[0].route, "/jobs");
    }

    #[test]
    fn already_terminal_not_renotified() {
        let body = r#"[{"id":1,"type":"ingest","status":"done","result":"{}"}]"#;
        assert!(detect_notifications(&prev(&[(1, "done")]), body).is_empty());
    }

    #[test]
    fn hidden_flag_detected() {
        use super::has_hidden_flag;
        let s = |v: &[&str]| v.iter().map(|x| x.to_string()).collect::<Vec<_>>();
        assert!(has_hidden_flag(&s(&["app", "--hidden"])));
        assert!(!has_hidden_flag(&s(&["app"])));
        assert!(!has_hidden_flag(&s(&["app", "--other"])));
    }

    #[test]
    fn status_map_parses_ids() {
        let body = r#"[{"id":1,"status":"running"},{"id":2,"status":"done"}]"#;
        let m = jobs_status_map(body);
        assert_eq!(m.get(&1).map(String::as_str), Some("running"));
        assert_eq!(m.get(&2).map(String::as_str), Some("done"));
    }

    #[test]
    fn counts_only_running() {
        let body = r#"[
            {"id": 1, "status": "running"},
            {"id": 2, "status": "done"},
            {"id": 3, "status": "running"},
            {"id": 4, "status": "queued"}
        ]"#;
        assert_eq!(count_running_jobs(body), 2);
    }

    #[test]
    fn handles_empty_and_garbage() {
        assert_eq!(count_running_jobs("[]"), 0);
        assert_eq!(count_running_jobs("not json"), 0);
        assert_eq!(count_running_jobs("{}"), 0);
    }

    // --- #275: native ingestion progress -------------------------------

    #[test]
    fn tray_label_shows_ingest_step() {
        let body = r#"[
            {"id": 1, "type": "ingest", "status": "running", "progress": "chunk 2/4"},
            {"id": 2, "type": "ask", "status": "running"}
        ]"#;
        assert_eq!(tray_jobs_label(body), "Ingesting: chunk 2/4");
    }

    #[test]
    fn tray_label_maps_known_steps() {
        let body = r#"[{"id":1,"type":"ingest","status":"running","progress":"running_agent"}]"#;
        assert_eq!(tray_jobs_label(body), "Ingesting: writing pages");
        assert_eq!(ingest_progress_label("extracting"), "reading source");
    }

    #[test]
    fn tray_label_falls_back_to_count_and_empty() {
        // Running jobs but none is an ingest with progress → plain count.
        let body = r#"[{"id":1,"type":"ask","status":"running"}]"#;
        assert_eq!(tray_jobs_label(body), "Jobs running: 1");
        assert_eq!(tray_jobs_label("[]"), "No jobs running");
        assert_eq!(tray_jobs_label("garbage"), "No jobs running");
    }

    #[test]
    fn start_notification_fires_once_on_queued_to_running() {
        let body = r#"[{"id": 7, "type": "ingest", "status": "running"}]"#;
        // First time we see it running (was queued) → one "started" note.
        let notes = detect_start_notifications(&prev(&[(7, "queued")]), body);
        assert_eq!(notes.len(), 1);
        assert_eq!(notes[0].title, "Ingestion started");
        // Still running next poll → no repeat.
        assert!(detect_start_notifications(&prev(&[(7, "running")]), body).is_empty());
        // Non-ingest jobs don't get a start ping.
        let ask = r#"[{"id": 8, "type": "ask", "status": "running"}]"#;
        assert!(detect_start_notifications(&prev(&[(8, "queued")]), ask).is_empty());
    }

    #[test]
    fn phantom_ingest_done_is_distinct_from_ready() {
        let empty = serde_json::json!({"status": "done"});
        // files: 0 → phantom note, routes to /jobs not /review.
        let body = r#"[{"id": 1, "type": "ingest", "status": "done", "result": "{\"cr\":\"CR-1\",\"files\":0,\"note\":\"none\"}"}]"#;
        let notes = detect_notifications(&prev(&[(1, "running")]), body);
        assert_eq!(notes.len(), 1);
        assert_eq!(notes[0].title, "Ingestion finished — no pages written");
        assert_eq!(notes[0].route, "/jobs");
        let _ = empty;
    }
}
