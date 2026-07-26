use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::Path;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_SIDECAR: &str = "resumecr7-backend";
const HEALTH_TIMEOUT: Duration = Duration::from_secs(30);
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(200);

#[derive(Default)]
struct BackendState {
    runtime: Mutex<Option<BackendRuntime>>,
}

struct BackendRuntime {
    base_url: String,
    child: CommandChild,
}

#[tauri::command]
fn backend_base_url(state: State<'_, BackendState>) -> Result<String, String> {
    let runtime = state
        .runtime
        .lock()
        .map_err(|_| "backend state lock poisoned".to_string())?;
    runtime
        .as_ref()
        .map(|backend| backend.base_url.clone())
        .ok_or_else(|| "desktop backend is not running".to_string())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState::default())
        .setup(|app| {
            start_backend(app.handle())?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                stop_backend(&window.app_handle());
            }
        })
        .invoke_handler(tauri::generate_handler![backend_base_url])
        .run(tauri::generate_context!())
        .expect("error while running ResumeCR7 desktop app");
}

fn start_backend(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let port = reserve_loopback_port()?;
    let base_url = format!("http://{BACKEND_HOST}:{port}");
    let data_dir = app.path().app_data_dir()?;
    let logs_dir = data_dir.join("logs");
    fs::create_dir_all(&logs_dir)?;

    let port_arg = port.to_string();
    let data_dir_arg = data_dir.to_string_lossy().to_string();
    let (mut events, child) = app
        .shell()
        .sidecar(BACKEND_SIDECAR)?
        .args([
            "--host",
            BACKEND_HOST,
            "--port",
            port_arg.as_str(),
            "--packaged",
            "--data-dir",
            data_dir_arg.as_str(),
        ])
        .env("RESUMECR7_PACKAGED", "true")
        .env("RESUMECR7_DATA_DIR", data_dir_arg.as_str())
        .spawn()?;

    let sidecar_log_path = logs_dir.join("desktop-sidecar.log");
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            let _ = append_sidecar_event(&sidecar_log_path, event);
        }
    });

    if let Err(error) = wait_for_health(port, HEALTH_TIMEOUT) {
        let _ = child.kill();
        return Err(error.into());
    }

    let state = app.state::<BackendState>();
    let mut runtime = state
        .runtime
        .lock()
        .map_err(|_| "backend state lock poisoned")?;
    *runtime = Some(BackendRuntime { base_url, child });
    Ok(())
}

fn stop_backend(app: &AppHandle) {
    let state = app.state::<BackendState>();
    {
        let Ok(mut runtime) = state.runtime.lock() else {
            return;
        };
        if let Some(backend) = runtime.take() {
            let _ = backend.child.kill();
        }
    }
}

fn reserve_loopback_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind((BACKEND_HOST, 0))?;
    Ok(listener.local_addr()?.port())
}

fn wait_for_health(port: u16, timeout: Duration) -> Result<(), String> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if health_check_once(port).unwrap_or(false) {
            return Ok(());
        }
        std::thread::sleep(HEALTH_POLL_INTERVAL);
    }
    Err(format!(
        "desktop backend did not respond to /health within {} seconds",
        timeout.as_secs()
    ))
}

fn health_check_once(port: u16) -> std::io::Result<bool> {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_millis(250))?;
    stream.set_read_timeout(Some(Duration::from_millis(500)))?;
    stream.set_write_timeout(Some(Duration::from_millis(500)))?;
    let request =
        format!("GET /health HTTP/1.1\r\nHost: {BACKEND_HOST}:{port}\r\nConnection: close\r\n\r\n");
    stream.write_all(request.as_bytes())?;

    let mut response = String::new();
    stream.read_to_string(&mut response)?;
    Ok(is_successful_health_response(&response))
}

fn is_successful_health_response(response: &str) -> bool {
    response.starts_with("HTTP/1.1 200") || response.starts_with("HTTP/1.0 200")
}

fn append_sidecar_event(log_path: &Path, event: CommandEvent) -> std::io::Result<()> {
    let mut log = OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_path)?;
    match event {
        CommandEvent::Stdout(line) => write_log_line(&mut log, "stdout", line),
        CommandEvent::Stderr(line) => write_log_line(&mut log, "stderr", line),
        CommandEvent::Error(message) => writeln!(log, "[error] {message}"),
        CommandEvent::Terminated(status) => writeln!(log, "[terminated] {status:?}"),
        _ => Ok(()),
    }
}

fn write_log_line(log: &mut fs::File, stream_name: &str, line: Vec<u8>) -> std::io::Result<()> {
    let text = String::from_utf8_lossy(&line);
    write!(log, "[{stream_name}] {text}")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn successful_health_response_accepts_http_200() {
        assert!(is_successful_health_response(
            "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n\r\n{\"status\":\"ok\"}"
        ));
    }

    #[test]
    fn successful_health_response_rejects_non_200() {
        assert!(!is_successful_health_response(
            "HTTP/1.1 503 Service Unavailable\r\n\r\n"
        ));
    }

    #[test]
    fn reserve_loopback_port_returns_bindable_port() {
        let port = reserve_loopback_port().expect("reserve port");
        let listener = TcpListener::bind((BACKEND_HOST, port)).expect("bind reserved port");
        assert_eq!(listener.local_addr().expect("local address").port(), port);
    }

    #[test]
    fn sidecar_log_path_is_plain_pathbuf() {
        let path = PathBuf::from("/tmp/resumecr7-sidecar.log");
        assert_eq!(path.file_name().unwrap(), "resumecr7-sidecar.log");
    }
}
