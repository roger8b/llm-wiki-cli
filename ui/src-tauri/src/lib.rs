// llm-wiki desktop shell.
//
// Boots the Python FastAPI backend (a PyInstaller onedir bundle shipped as a
// Tauri resource) on a dynamic port, waits for `/api/health` to return 200, then
// opens a WebView pointing at it. The backend serves both the SPA and the /api
// routes on the same origin, so the React app's "/api" base works unchanged.

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

/// Holds the running backend process so we can kill it on exit.
struct Backend(Mutex<Option<Child>>);

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // Single instance MUST be registered first (plugin docs): a second
        // launch focuses the existing window instead of spawning a 2nd backend.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.show();
                let _ = win.unminimize();
                let _ = win.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .manage(Backend(Mutex::new(None)))
        .setup(|app| {
            let port = free_port();
            let brain = default_brain();
            let token = gen_token();
            eprintln!("[llm-wiki] Using port={port}, brain={brain}");

            // Reap orphaned backends from a prior crash/force-quit before spawning.
            kill_stray_backends(&brain);

            // Spawn the FastAPI backend (PyInstaller onedir exe). The token goes
            // via env (not argv) so it doesn't leak in `ps`.
            let exe = resolve_backend_exe(&app.handle());
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

            // Wait for readiness, then open the window pointing at the backend.
            let url = format!("http://127.0.0.1:{port}");
            let handle = app.handle().clone();
            let win_token = token.clone();
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
                let t2 = Instant::now();
                WebviewWindowBuilder::new(
                    &handle,
                    "main",
                    WebviewUrl::External(url.parse().unwrap()),
                )
                .title("llm-wiki")
                .inner_size(1280.0, 860.0)
                .min_inner_size(900.0, 600.0)
                // Expose the per-session token to the SPA before any page script
                // runs. {win_token:?} emits a safely-quoted JS string literal.
                .initialization_script(&format!("window.__WIKI_TOKEN__ = {win_token:?};"))
                .build()
                .expect("failed to build window");
                eprintln!(
                    "[llm-wiki] WebviewWindowBuilder::new() took {:.1}s",
                    t2.elapsed().as_secs_f32()
                );
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri app")
        .run(|app, event| {
            // Stop the backend gracefully when the app exits (SIGTERM → wait →
            // SIGKILL) so uvicorn runs shutdown and the worker marks job state
            // instead of dying mid-job (#203).
            if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
                if let Some(mut child) = app.state::<Backend>().0.lock().unwrap().take() {
                    graceful_stop(&mut child);
                }
            }
        });
}