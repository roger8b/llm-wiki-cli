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

/// Kill stray backend processes left over from a prior run (crash / force-quit).
///
/// Scoped to the desktop brain path so a separately-launched `wiki serve` on a
/// different brain is never touched. Orphaned sidecars compete for CPU/IO and
/// inflate startup from ~9s to 20s+.
fn kill_stray_backends(brain: &str) {
    match Command::new("pkill").args(["-f", brain]).status() {
        Ok(status) => eprintln!("[llm-wiki] pkill stray backends (brain={brain}): {status}"),
        Err(err) => eprintln!("[llm-wiki] pkill unavailable: {err}"),
    }
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(Backend(Mutex::new(None)))
        .setup(|app| {
            let port = free_port();
            let brain = default_brain();
            eprintln!("[llm-wiki] Using port={port}, brain={brain}");

            // Reap orphaned backends from a prior crash/force-quit before spawning.
            kill_stray_backends(&brain);

            // Spawn the FastAPI backend (PyInstaller onedir exe).
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
            // Kill the backend when the app exits so we don't leak a zombie.
            if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
                if let Some(mut child) = app.state::<Backend>().0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}