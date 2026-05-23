// llm-wiki desktop shell.
//
// Boots the Python FastAPI backend (compiled with PyInstaller) as a Tauri
// sidecar on a dynamic port, waits for it to become reachable, then opens a
// WebView pointing at it. The sidecar serves both the SPA and the /api routes
// on the same origin, so the React app's "/api" base works unchanged.

use std::net::{TcpListener, TcpStream};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

/// Holds the running sidecar so we can kill it on exit.
struct Backend(Mutex<Option<CommandChild>>);

/// Ask the OS for a free TCP port by binding to :0 and reading it back.
fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .expect("no free port")
        .local_addr()
        .unwrap()
        .port()
}

/// Block until the backend accepts TCP connections (or we give up).
fn wait_until_ready(port: u16, timeout: Duration) -> bool {
    let addr = format!("127.0.0.1:{port}");
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if TcpStream::connect_timeout(
            &addr.parse().unwrap(),
            Duration::from_millis(300),
        )
        .is_ok()
        {
            // give uvicorn a moment to finish wiring routes
            std::thread::sleep(Duration::from_millis(400));
            return true;
        }
        std::thread::sleep(Duration::from_millis(150));
    }
    false
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

            // Spawn the FastAPI sidecar.
            let sidecar = app
                .shell()
                .sidecar("wiki-backend")
                .expect("sidecar 'wiki-backend' not found")
                .args([
                    "serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    &port.to_string(),
                    "--brain",
                    &brain,
                ]);
            let (_rx, child) = sidecar.spawn().expect("failed to start backend");
            app.state::<Backend>().0.lock().unwrap().replace(child);

            // Wait for readiness, then open the window pointing at the backend.
            let url = format!("http://127.0.0.1:{port}");
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                wait_until_ready(port, Duration::from_secs(30));
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
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri app")
        .run(|app, event| {
            // Kill the sidecar when the app exits so we don't leak a zombie.
            if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
                if let Some(child) = app.state::<Backend>().0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
