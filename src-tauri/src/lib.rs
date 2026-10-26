use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet},
    fs,
    io::Read,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::{AppHandle, Emitter, Manager, State};
mod resident;
mod system_media;
mod capture;
mod magic_pen;
mod realtime_chat;

const MAX_MESSAGE: usize = 8 * 1024 * 1024;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}
impl Rect {
    fn valid(self) -> bool {
        [self.x, self.y, self.width, self.height]
            .iter()
            .all(|v| v.is_finite())
            && self.width > 0.0
            && self.height > 0.0
    }
    fn contains(self, x: f64, y: f64) -> bool {
        x >= self.x && x <= self.x + self.width && y >= self.y && y <= self.y + self.height
    }
}

#[derive(Clone)]
struct BackendConnection {
    port: u16,
    token: String,
    instance_id: String,
}

#[allow(dead_code)]
struct PixelMask {
    bounds: Rect,
    cols: usize,
    rows: usize,
    bits: Vec<bool>,
}
impl PixelMask {
    fn contains(&self, x: f64, y: f64) -> bool {
        let padded = Rect {
            x: self.bounds.x - 2.0,
            y: self.bounds.y - 2.0,
            width: self.bounds.width + 4.0,
            height: self.bounds.height + 4.0,
        };
        if !padded.contains(x, y) {
            return false;
        }
        let clamped_x = x.clamp(self.bounds.x, self.bounds.x + self.bounds.width);
        let clamped_y = y.clamp(self.bounds.y, self.bounds.y + self.bounds.height);
        let column = (((clamped_x - self.bounds.x) / self.bounds.width * self.cols as f64).floor()
            as usize)
            .min(self.cols - 1);
        let row = (((clamped_y - self.bounds.y) / self.bounds.height * self.rows as f64).floor() as usize)
            .min(self.rows - 1);
        // One sample of tolerance keeps the moving edge reachable between hit map updates.
        for r in row.saturating_sub(1)..=(row + 1).min(self.rows - 1) {
            for c in column.saturating_sub(1)..=(column + 1).min(self.cols - 1) {
                if self.bits[r * self.cols + c] {
                    return true;
                }
            }
        }
        false
    }
}

#[derive(Default)]
pub struct HostState {
    resident: Mutex<resident::Geometry>,
    desktop_error: Mutex<Option<String>>,
    frontend_active: AtomicBool,
    follow: AtomicBool,
    quitting: AtomicBool,
    layout_changing: AtomicBool,
    active_operations: std::sync::atomic::AtomicUsize,
    pub timer_task: Mutex<Option<Value>>,
    pub is_ignoring_cursor: Mutex<bool>,
    pub interactive_regions: Mutex<Vec<Rect>>,
    avatar_mask: Mutex<Option<PixelMask>>,
    pub backend_child: Mutex<Option<Child>>,
    backend: Mutex<Option<BackendConnection>>,
    backend_error: Mutex<Option<String>>,
    shortcut_error: Mutex<Option<String>>,
    remote_voice_shortcut_error: Mutex<Option<String>>,
    active_requests: Mutex<HashSet<String>>,
    realtime_cancellations: Mutex<HashMap<String, Arc<AtomicBool>>>,
    data_dir: Mutex<PathBuf>,
    preferences_dirty: AtomicBool,
    runtime_revision: std::sync::atomic::AtomicU64,
    runtime_committed: Mutex<u64>,
    stopping: AtomicBool,
    #[cfg(windows)]
    job: Mutex<Option<WinHandle>>,
    #[cfg(windows)]
    instance: Mutex<Option<WinHandle>>,
    #[cfg(windows)]
    summon_event: Mutex<Option<WinHandle>>,
}

#[cfg(windows)]
struct WinHandle(isize);
#[cfg(windows)]
impl Drop for WinHandle {
    fn drop(&mut self) {
        unsafe {
            windows_sys::Win32::Foundation::CloseHandle(self.0 as _);
        }
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NativeStatusResponse {
    pub native: bool,
    pub shortcut: String,
    pub shortcut_error: Option<String>,
    pub remote_voice_shortcut: String,
    pub remote_voice_shortcut_error: Option<String>,
    pub always_on_top: bool,
    pub autostart: bool,
    pub timer: Option<Value>,
    pub backend_ready: bool,
    pub backend_error: Option<String>,
    pub backend_instance: Option<String>,
    pub data_directory: String,
    pub desktop: Option<resident::DesktopStatus>,
}

#[tauri::command]
fn native_status(app: AppHandle, state: State<HostState>) -> NativeStatusResponse {
    let backend = state.backend.lock().unwrap().clone();
    NativeStatusResponse {
        native: true,
        shortcut: "Alt+Shift+A".into(),
        shortcut_error: state.shortcut_error.lock().unwrap().clone(),
        remote_voice_shortcut: "Ctrl+Alt+Shift+V".into(),
        remote_voice_shortcut_error: state.remote_voice_shortcut_error.lock().unwrap().clone(),
        always_on_top: app
            .get_webview_window("main")
            .and_then(|w| w.is_always_on_top().ok())
            .unwrap_or(false),
        autostart: false,
        timer: state.timer_task.lock().unwrap().clone(),
        backend_ready: backend.is_some(),
        backend_error: state.backend_error.lock().unwrap().clone(),
        backend_instance: backend.as_ref().map(|b| b.instance_id.clone()),
        data_directory: state.data_dir.lock().unwrap().display().to_string(),
        desktop: resident::status(&app),
    }
}

/// Startup evidence contains no token, request body, or conversation data.
pub fn write_runtime_snapshot(app: &AppHandle) {
    let state = app.state::<HostState>();
    let revision = state.runtime_revision.fetch_add(1, Ordering::SeqCst) + 1;
    let backend = state.backend.lock().unwrap().clone();
    let data_directory = state.data_dir.lock().unwrap().clone();
    let desktop = resident::status(app);
    let visible = app
        .get_webview_window("main")
        .is_some_and(|w| w.is_visible().unwrap_or(false));
    let window_position = app
        .get_webview_window("main")
        .and_then(|w| w.outer_position().ok())
        .map(|p| json!({"x":p.x,"y":p.y}));
    let timestamp = {
        let secs = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        format!("{secs}Z")
    };
    let snapshot = json!({
        "schemaVersion":1,"timestampUtc":timestamp,"version":env!("CARGO_PKG_VERSION"),
        "pid":std::process::id(),"executable":std::env::current_exe().ok().map(|p|p.display().to_string()),
        "backendReady":backend.is_some(),"backendPort":backend.as_ref().map(|b|b.port),
        "backendInstance":backend.as_ref().map(|b|b.instance_id.as_str()),
        "dataDirectory":data_directory.display().to_string(),"windowVisible":visible,"windowPosition":window_position,
        "desktop":desktop
    });
    let result = (|| -> Result<(), Box<dyn std::error::Error>> {
        let dir = data_directory.join("logs");
        fs::create_dir_all(&dir)?;
        let bytes = serde_json::to_vec_pretty(&snapshot)?;
        let mut committed = state.runtime_committed.lock().unwrap();
        if revision <= *committed {
            return Ok(());
        }
        let temp = dir.join(format!("native-runtime-{}.tmp", uuid::Uuid::new_v4()));
        fs::write(&temp, bytes)?;
        if let Err(error) = fs::rename(&temp, dir.join("native-runtime.json")) {
            let _ = fs::remove_file(&temp);
            return Err(error.into());
        }
        *committed = revision;
        Ok(())
    })();
    if let Err(error) = result {
        log::warn!("Cannot save sanitized native startup evidence: {error}");
    }
}

fn validate_route(method: &str, path: &str) -> Result<(), String> {
    if !matches!(method, "GET" | "POST" | "PUT" | "DELETE") {
        return Err("Unsupported backend method".into());
    }
    if !path.starts_with("/axx-api/")
        || path.contains(['\r', '\n', '#', '\\'])
        || path.contains("..")
        || path.len() > 2048
    {
        return Err("Invalid backend path".into());
    }
    Ok(())
}

fn backend_timeout_seconds(path: &str) -> u64 {
    if path == "/axx-api/speech/synthesize" {
        230
    } else if path == "/axx-api/speech/transcribe" {
        95
    } else if path == "/axx-api/status"
        || path == "/axx-api/chat/cancel"
        || path == "/axx-api/actions/cancel"
        || path == "/axx-api/commands/cancel"
    {
        3
    } else if matches!(path, "/axx-api/actions/execute" | "/axx-api/commands/execute" | "/axx-api/learning/propose") {
        150
    } else if matches!(path, "/axx-api/learning/execute" | "/axx-api/learning/resume") {
        1000
    } else {
        73
    }
}

fn request_backend(
    connection: &BackendConnection,
    method: &str,
    path: &str,
    body: Option<Value>,
) -> Result<Value, String> {
    validate_route(method, path)?;
    let client = reqwest::blocking::Client::builder()
        .no_proxy()
        .connect_timeout(Duration::from_secs(3))
        .timeout(Duration::from_secs(backend_timeout_seconds(path)))
        .build()
        .map_err(|_| "Cannot initialize local transport".to_string())?;
    let mut request = client
        .request(
            reqwest::Method::from_bytes(method.as_bytes()).map_err(|_| "Invalid method")?,
            format!("http://127.0.0.1:{}{}", connection.port, path),
        )
        .bearer_auth(&connection.token);
    if let Some(value) = body {
        let encoded = serde_json::to_vec(&value).map_err(|_| "Invalid request JSON")?;
        if encoded.len() > MAX_MESSAGE {
            return Err("Request exceeds 8 MiB".into());
        }
        request = request
            .header("Content-Type", "application/json")
            .body(encoded);
    }
    let response = request.send().map_err(|e| {
        if e.is_timeout() {
            "Local backend timed out"
        } else {
            "Local backend unavailable"
        }
        .to_string()
    })?;
    let status = response.status().as_u16();
    if response
        .content_length()
        .is_some_and(|n| n > MAX_MESSAGE as u64)
    {
        return Err("Backend response exceeds 8 MiB".into());
    }
    let mut bytes = Vec::new();
    response
        .take(MAX_MESSAGE as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "Cannot read backend response")?;
    if bytes.len() > MAX_MESSAGE {
        return Err("Backend response exceeds 8 MiB".into());
    }
    let value: Value = serde_json::from_slice(&bytes)
        .map_err(|_| format!("Backend returned invalid JSON (HTTP {status})"))?;
    if status >= 400 {
        let error = value.get("error");
        let code = error
            .and_then(|v| v.get("code"))
            .and_then(Value::as_str)
            .unwrap_or("BACKEND_ERROR");
        let message = error
            .and_then(|v| v.get("message"))
            .and_then(Value::as_str)
            .or_else(|| error.and_then(Value::as_str))
            .unwrap_or("The local operation was rejected");
        let safe_message: String = message
            .chars()
            .filter(|c| !c.is_control())
            .take(512)
            .collect();
        return Err(format!("{code}: {safe_message} (HTTP {status})"));
    }
    Ok(value)
}

#[tauri::command]
async fn backend_request(
    app: AppHandle,
    method: String,
    path: String,
    mut body: Option<Value>,
) -> Result<Value, String> {
    validate_route(&method, &path)?;
    let state = app.state::<HostState>();
    let connection = state.backend.lock().unwrap().clone().ok_or_else(|| {
        state
            .backend_error
            .lock()
            .unwrap()
            .clone()
            .unwrap_or_else(|| "Backend is starting".into())
    })?;
    let request_id = if method == "POST" && path == "/axx-api/chat" {
        let object = body
            .get_or_insert_with(|| json!({}))
            .as_object_mut()
            .ok_or("Chat body must be an object")?;
        object.insert("stream".into(), json!(false));
        let id = object
            .entry("request_id")
            .or_insert_with(|| json!(uuid::Uuid::new_v4().to_string()))
            .as_str()
            .ok_or("request_id must be a string")?
            .to_string();
        state.active_requests.lock().unwrap().insert(id.clone());
        Some(id)
    } else {
        None
    };
    let operation = method == "POST"
        && matches!(
            path.as_str(),
            "/axx-api/actions/execute" | "/axx-api/recipes/execute" | "/axx-api/speech/transcribe" | "/axx-api/commands/execute"
        );
    if operation {
        state.active_operations.fetch_add(1, Ordering::Relaxed);
    }
    let result = tauri::async_runtime::spawn_blocking(move || {
        request_backend(&connection, &method, &path, body)
    })
    .await
    .map_err(|_| "Local transport worker failed".to_string());
    if let Some(id) = request_id {
        app.state::<HostState>()
            .active_requests
            .lock()
            .unwrap()
            .remove(&id);
    }
    if operation {
        app.state::<HostState>()
            .active_operations
            .fetch_sub(1, Ordering::Relaxed);
    }
    result?
}

fn cancel_active(app: &AppHandle) {
    let state = app.state::<HostState>();
    for cancelled in state.realtime_cancellations.lock().unwrap().values() {
        cancelled.store(true, Ordering::Relaxed);
    }
    let ids: Vec<String> = state
        .active_requests
        .lock()
        .unwrap()
        .iter()
        .cloned()
        .collect();
    let connection = state.backend.lock().unwrap().clone();
    state.follow.store(false, Ordering::Relaxed);
    let _ = app.emit("axx-cancel", ());
    if let Some(connection) = connection {
        // A prepared command may be awaiting approval with no worker in flight.
        let command_connection = connection.clone();
        std::thread::spawn(move || {
            let _ = request_backend(
                &command_connection,
                "POST",
                "/axx-api/commands/cancel",
                Some(json!({})),
            );
        });
        if state.active_operations.load(Ordering::Relaxed) > 0 {
            let connection = connection.clone();
            std::thread::spawn(move || {
                let _ = request_backend(
                    &connection,
                    "POST",
                    "/axx-api/actions/cancel",
                    Some(json!({})),
                );
            });
        }
        for id in ids {
            let connection = connection.clone();
            std::thread::spawn(move || {
                let _ = request_backend(
                    &connection,
                    "POST",
                    "/axx-api/chat/cancel",
                    Some(json!({"request_id":id})),
                );
            });
        }
    }
}

#[tauri::command]
fn window_action(action: String, app: AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or("Axx window unavailable")?;
    match action.as_str() {
        "minimize" => window.minimize(),
        "drag" => {
            app.state::<HostState>()
                .follow
                .store(false, Ordering::Relaxed);
            window.start_dragging()
        }
        "open_panel" => {
            let _ = resident::show_passive(&app);
            window.set_focusable(true).map_err(|e| e.to_string())?;
            window.set_focus()
        }
        "close_panel" => window.set_focusable(false),
        "hide" => window.hide(),
        "show" => return resident::show_passive(&app),
        "recenter" => {
            return resident::go_home(&app);
        }
        "cancel" | "escape" => {
            cancel_active(&app);
            Ok(())
        }
        "quit" => {
            app.state::<HostState>()
                .quitting
                .store(true, Ordering::Relaxed);
            resident::persist(&app);
            app.exit(0);
            Ok(())
        }
        "close" => window.hide(),
        "always-on-top" => window.set_always_on_top(!window.is_always_on_top().unwrap_or(true)),
        _ => return Err("Unknown window action".into()),
    }
    .map_err(|e| e.to_string())
}

#[tauri::command]
fn set_topmost(enabled: bool, app: AppHandle) -> Result<(), String> {
    app.get_webview_window("main")
        .ok_or("Axx window unavailable")?
        .set_always_on_top(enabled)
        .map_err(|e| e.to_string())?;
    persist_window(&app);
    Ok(())
}

#[tauri::command]
fn set_shortcut(shortcut: String) -> Result<(), String> {
    if shortcut.eq_ignore_ascii_case("Alt+Shift+A") {
        Ok(())
    } else {
        Err("This version uses the fixed global shortcut Alt+Shift+A".into())
    }
}

#[tauri::command]
fn set_timer(task: Value, app: AppHandle, state: State<HostState>) -> Result<(), String> {
    if serde_json::to_vec(&task)
        .map_err(|_| "Invalid timer")?
        .len()
        > 16384
    {
        return Err("Timer data too large".into());
    }
    let is_running = task.get("status").and_then(Value::as_str) == Some("running");
    let task_id = task.get("id").and_then(Value::as_str).map(str::to_string);
    let ends_at = task.get("endsAt").and_then(Value::as_f64).map(|v| v as u64);
    *state.timer_task.lock().unwrap() = Some(task);
    if is_running {
        if let (Some(id), Some(target_ms)) = (task_id, ends_at) {
            let app_handle = app.clone();
            std::thread::spawn(move || {
                loop {
                    let st = app_handle.state::<HostState>();
                    if st.stopping.load(Ordering::Relaxed) {
                        return;
                    }
                    let still_active = {
                        let guard = st.timer_task.lock().unwrap();
                        guard.as_ref().is_some_and(|t| {
                            t.get("id").and_then(Value::as_str) == Some(id.as_str())
                                && t.get("status").and_then(Value::as_str) == Some("running")
                                && t.get("endsAt").and_then(Value::as_f64).map(|v| v as u64) == Some(target_ms)
                        })
                    };
                    if !still_active {
                        return;
                    }
                    let now_ms = SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .unwrap_or_default()
                        .as_millis() as u64;
                    if now_ms >= target_ms {
                        let _ = app_handle.emit("axx-timer-due", json!({ "id": id, "endsAt": target_ms }));
                        return;
                    }
                    let wait_ms = (target_ms - now_ms).min(250);
                    std::thread::sleep(Duration::from_millis(wait_ms));
                }
            });
        }
    }
    Ok(())
}

#[tauri::command]
fn hit_map(map: Value, state: State<HostState>) -> Result<(), String> {
    let parse = |r: &Value| -> Option<Rect> {
        let rect = Rect {
            x: r.get("x")?.as_f64()?,
            y: r.get("y")?.as_f64()?,
            width: r.get("width")?.as_f64()?,
            height: r.get("height")?.as_f64()?,
        };
        rect.valid().then_some(rect)
    };
    let mut regions: Vec<Rect> = map
        .get("regions")
        .and_then(Value::as_array)
        .map(|r| r.iter().take(256).filter_map(parse).collect())
        .unwrap_or_default();
    let mask = if let (Some(bounds), Some(cols), Some(rows), Some(bits)) = (
        parse(&map),
        map.get("cols").and_then(Value::as_u64),
        map.get("rows").and_then(Value::as_u64),
        map.get("bits").and_then(Value::as_array),
    ) {
        if (1..=128).contains(&cols)
            && (1..=128).contains(&rows)
            && bits.len() == (cols * rows) as usize
            && bits.iter().all(|b| matches!(b.as_u64(), Some(0 | 1)))
        {
            Some(PixelMask {
                bounds,
                cols: cols as usize,
                rows: rows as usize,
                bits: bits.iter().map(|b| b.as_u64() == Some(1)).collect(),
            })
        } else {
            return Err("Invalid avatar alpha mask".into());
        }
    } else {
        if let Some(rect) = parse(&map) {
            regions.push(rect);
        }
        None
    };
    *state.avatar_mask.lock().unwrap() = mask;
    *state.interactive_regions.lock().unwrap() = regions;
    Ok(())
}

fn data_directory(app: &AppHandle) -> Result<PathBuf, String> {
    let base = std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .or_else(|| app.path().app_local_data_dir().ok())
        .ok_or("No local application data directory")?;
    let path = if base.ends_with("com.axx.desktop") {
        base
    } else {
        base.join("Axx")
    };
    fs::create_dir_all(&path).map_err(|e| format!("Cannot create Axx data directory: {e}"))?;
    Ok(path)
}

fn find_backend(app: &AppHandle) -> Option<PathBuf> {
    let mut paths = Vec::new();
    if let Ok(resource) = app.path().resource_dir() {
        paths.push(resource.join("resources/axx-backend.exe"));
        paths.push(resource.join("axx-backend.exe"));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(base) = exe.parent() {
            paths.push(base.join("resources/axx-backend.exe"));
            paths.push(base.join("axx-backend.exe"));
        }
    }
    #[cfg(debug_assertions)]
    {
        paths.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources/axx-backend.exe"));
    }
    paths.into_iter().find(|p| p.is_file())
}

fn spawn_backend(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<HostState>();
    if state.stopping.load(Ordering::Relaxed) {
        return Err("Axx is shutting down".into());
    }
    let data = state.data_dir.lock().unwrap().clone();
    let ready = data.join(format!("backend-ready-{}.json", std::process::id()));
    let _ = fs::remove_file(&ready);
    let token = format!(
        "{}{}",
        uuid::Uuid::new_v4().simple(),
        uuid::Uuid::new_v4().simple()
    );
    let launch_instance = uuid::Uuid::new_v4().to_string();
    let mut command = if let Some(path) = find_backend(app) {
        Command::new(path)
    } else {
        #[cfg(debug_assertions)]
        {
            let mut c = Command::new("python");
            c.arg(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend/server.py"));
            c
        }
        #[cfg(not(debug_assertions))]
        {
            return Err(
                "Packaged backend executable is missing. Repair the Axx installation.".into(),
            );
        }
    };
    command
        .args(["--host", "127.0.0.1", "--port", "0", "--data-dir"])
        .arg(&data)
        .arg("--ready-file")
        .arg(&ready)
        .env("AXX_HOST_TOKEN", &token)
        .env("AXX_HOST_INSTANCE", &launch_instance)
        .current_dir(&data)
        .stdin(Stdio::null())
        .stdout(Stdio::null());
    let logs = data.join("logs");
    fs::create_dir_all(&logs).map_err(|e| e.to_string())?;
    let stderr = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(logs.join("backend-stderr.log"))
        .map_err(|e| e.to_string())?;
    command.stderr(stderr);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // Suspend until assigned to the job so even bootloader descendants are contained.
        command.creation_flags(0x08000000 | 0x00000004);
    }
    let mut child = command
        .spawn()
        .map_err(|e| format!("Cannot start Axx backend: {e}"))?;
    #[cfg(windows)]
    {
        match bind_child_to_job(&child) {
            Ok(job) => *state.job.lock().unwrap() = Some(job),
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(error);
            }
        }
        if let Err(error) = resume_owned_child(child.id()) {
            state.job.lock().unwrap().take();
            let _ = child.kill();
            let _ = child.wait();
            return Err(error);
        }
    }
    *state.backend_child.lock().unwrap() = Some(child);
    let deadline = Instant::now() + Duration::from_secs(90);
    let result = loop {
        if state.stopping.load(Ordering::Relaxed) {
            break Err("Axx is shutting down".into());
        }
        if Instant::now() >= deadline {
            break Err("Axx backend startup timed out after 90 seconds".into());
        }
        if state
            .backend_child
            .lock()
            .unwrap()
            .as_mut()
            .and_then(|c| c.try_wait().ok().flatten())
            .is_some()
        {
            break Err("Axx backend exited during startup; see backend-stderr.log".into());
        }
        if let Ok(bytes) = fs::read(&ready) {
            if let Ok(value) = serde_json::from_slice::<Value>(&bytes) {
                if value.get("instance_id").and_then(Value::as_str)
                    == Some(launch_instance.as_str())
                {
                    if let (Some(port), Some(instance)) = (
                        value
                            .get("port")
                            .and_then(Value::as_u64)
                            .filter(|p| *p > 0 && *p <= 65535),
                        value.get("instance_id").and_then(Value::as_str),
                    ) {
                        let connection = BackendConnection {
                            port: port as u16,
                            token: token.clone(),
                            instance_id: instance.into(),
                        };
                        if let Ok(status) =
                            request_backend(&connection, "GET", "/axx-api/status", None)
                        {
                            if status.get("instance_id").and_then(Value::as_str)
                                == Some(launch_instance.as_str())
                            {
                                *state.backend.lock().unwrap() = Some(connection);
                                break Ok(());
                            }
                        }
                    }
                }
            }
        }
        std::thread::sleep(Duration::from_millis(100));
    };
    let _ = fs::remove_file(&ready);
    if result.is_err() {
        terminate_backend(&state);
    }
    result
}

#[cfg(windows)]
fn bind_child_to_job(child: &Child) -> Result<WinHandle, String> {
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::System::JobObjects::*;
    unsafe {
        let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if handle.is_null() {
            return Err(format!(
                "Cannot create backend process job: {}",
                std::io::Error::last_os_error()
            ));
        }
        let job = WinHandle(handle as isize);
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        // User-requested application launches may explicitly opt out; sidecar/workers never do.
        info.BasicLimitInformation.LimitFlags =
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_BREAKAWAY_OK;
        if SetInformationJobObject(
            handle,
            JobObjectExtendedLimitInformation,
            &info as *const _ as _,
            std::mem::size_of_val(&info) as u32,
        ) == 0
            || AssignProcessToJobObject(handle, child.as_raw_handle() as _) == 0
        {
            return Err(format!(
                "Cannot contain backend process tree: {}",
                std::io::Error::last_os_error()
            ));
        }
        Ok(job)
    }
}

#[cfg(windows)]
fn resume_owned_child(pid: u32) -> Result<(), String> {
    use windows_sys::Win32::{
        Foundation::INVALID_HANDLE_VALUE,
        System::{Diagnostics::ToolHelp::*, Threading::*},
    };
    unsafe {
        let snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
        if snapshot == INVALID_HANDLE_VALUE {
            return Err("Cannot inspect suspended backend thread".into());
        }
        let _snapshot_guard = WinHandle(snapshot as isize);
        let mut entry: THREADENTRY32 = std::mem::zeroed();
        entry.dwSize = std::mem::size_of::<THREADENTRY32>() as u32;
        let mut found = false;
        let mut present = Thread32First(snapshot, &mut entry);
        while present != 0 {
            if entry.th32OwnerProcessID == pid {
                let thread = OpenThread(THREAD_SUSPEND_RESUME, 0, entry.th32ThreadID);
                if thread.is_null() {
                    return Err("Cannot access owned backend thread".into());
                }
                let _thread_guard = WinHandle(thread as isize);
                if ResumeThread(thread) == u32::MAX {
                    return Err("Cannot resume owned backend thread".into());
                }
                found = true;
            }
            present = Thread32Next(snapshot, &mut entry);
        }
        if found {
            Ok(())
        } else {
            Err("Suspended backend thread is missing".into())
        }
    }
}

fn terminate_backend(state: &HostState) {
    *state.backend.lock().unwrap() = None;
    #[cfg(windows)]
    {
        state.job.lock().unwrap().take();
    }
    if let Some(mut child) = state.backend_child.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn persist_window(app: &AppHandle) {
    resident::persist(app);
}
fn restore_window(app: &AppHandle) {
    resident::restore(app);
}

#[cfg(windows)]
fn start_cursor_hit_test_loop(app: AppHandle) {
    std::thread::spawn(move || {
        use windows_sys::Win32::{
            Foundation::POINT, Graphics::Gdi::ScreenToClient, UI::WindowsAndMessaging::GetCursorPos,
        };
        let mut last_display_check = Instant::now();
        let mut last_x = i32::MIN;
        let mut last_y = i32::MIN;
        loop {
            std::thread::sleep(Duration::from_millis(10));
            let state = app.state::<HostState>();
            if state.stopping.load(Ordering::Relaxed) {
                break;
            }
            if last_display_check.elapsed() > Duration::from_secs(2) {
                resident::recover_display(&app);
                last_display_check = Instant::now();
            }
            let Some(window) = app.get_webview_window("main") else {
                break;
            };
            if !window.is_visible().unwrap_or(false) {
                continue;
            }
            let Ok(hwnd) = window.hwnd() else {
                continue;
            };
            let mut point = POINT { x: 0, y: 0 };
            if unsafe { GetCursorPos(&mut point) } == 0 {
                continue;
            }
            let screen_x = point.x;
            let screen_y = point.y;
            if unsafe { ScreenToClient(hwnd.0 as _, &mut point) } == 0 {
                continue;
            }
            let scale = window
                .current_monitor()
                .ok()
                .flatten()
                .map(|m| m.scale_factor())
                .or_else(|| window.scale_factor().ok())
                .filter(|s| *s > 0.0 && s.is_finite())
                .unwrap_or(1.0);
            let x = point.x as f64 / scale;
            let y = point.y as f64 / scale;
            if point.x != last_x || point.y != last_y {
                let _ = window.emit(
                    "axx-cursor",
                    json!({"x":x,"y":y,"screenX":screen_x,"screenY":screen_y,"scaleFactor":scale}),
                );
                last_x = point.x;
                last_y = point.y;
            }
            let regions = state.interactive_regions.lock().unwrap();
            let mask = state.avatar_mask.lock().unwrap();
            let regions_empty = regions.is_empty();
            let mask_present = mask.is_some();
            let inside = regions.iter().any(|r| r.contains(x, y))
                || mask.as_ref().is_some_and(|m| m.contains(x, y));
            drop(mask);
            drop(regions);

            use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetAsyncKeyState, VK_LBUTTON};
            let lbutton_down = unsafe { GetAsyncKeyState(VK_LBUTTON as i32) } < 0;
            let mut current = state.is_ignoring_cursor.lock().unwrap();
            let ignore = if inside {
                false
            } else if lbutton_down && !*current {
                false
            } else {
                (!regions_empty || mask_present) && !inside
            };

            if *current != ignore && window.set_ignore_cursor_events(ignore).is_ok() {
                *current = ignore;
            }
            resident::follow_cursor(&app, screen_x as f64, screen_y as f64);
        }
    });
}

#[cfg(windows)]
static KEYBOARD_APP: std::sync::OnceLock<AppHandle> = std::sync::OnceLock::new();
#[cfg(windows)]
unsafe extern "system" fn keyboard_hook(code: i32, wparam: usize, lparam: isize) -> isize {
    use windows_sys::Win32::UI::WindowsAndMessaging::*;
    if code >= 0 && wparam == WM_KEYDOWN as usize {
        let event = unsafe { &*(lparam as *const KBDLLHOOKSTRUCT) };
        if event.vkCode == 0x1b {
            if let Some(app) = KEYBOARD_APP.get() {
                if magic_pen::ACTIVE.load(Ordering::Acquire) {
                    let _ = app.emit("axx-pen-escape", ());
                    return unsafe { CallNextHookEx(std::ptr::null_mut(), code, wparam, lparam) };
                }
                let state = app.state::<HostState>();
                if state.frontend_active.load(Ordering::Relaxed)
                    || state.follow.load(Ordering::Relaxed)
                    || state.active_operations.load(Ordering::Relaxed) > 0
                    || !state.active_requests.lock().unwrap().is_empty()
                {
                    cancel_active(app);
                }
            }
        }
    }
    unsafe { CallNextHookEx(std::ptr::null_mut(), code, wparam, lparam) }
}
#[cfg(windows)]
fn start_global_hotkey_thread(app: AppHandle) {
    std::thread::spawn(move || {
        use windows_sys::Win32::UI::{Input::KeyboardAndMouse::*, WindowsAndMessaging::*};
        let _ = KEYBOARD_APP.set(app.clone());
        unsafe {
            let hook =
                SetWindowsHookExW(WH_KEYBOARD_LL, Some(keyboard_hook), std::ptr::null_mut(), 0);
            if RegisterHotKey(
                std::ptr::null_mut(),
                1001,
                MOD_ALT | MOD_SHIFT | MOD_NOREPEAT,
                0x41,
            ) == 0
            {
                *app.state::<HostState>().shortcut_error.lock().unwrap() = Some(format!(
                    "Alt+Shift+A unavailable: {}",
                    std::io::Error::last_os_error()
                ));
            }
            if hook.is_null() {
                log::warn!(
                    "Global Esc hook unavailable: {}",
                    std::io::Error::last_os_error()
                );
            }
            if RegisterHotKey(std::ptr::null_mut(), 1002, MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_NOREPEAT, 0x56) == 0 {
                *app.state::<HostState>().remote_voice_shortcut_error.lock().unwrap() = Some(format!("Ctrl+Alt+Shift+V unavailable: {}", std::io::Error::last_os_error()));
            }
            let mut last = Instant::now() - Duration::from_secs(10);
            let mut msg: MSG = std::mem::zeroed();
            while GetMessageW(&mut msg, std::ptr::null_mut(), 0, 0) > 0 {
                if msg.message == WM_HOTKEY && msg.wParam == 1002 {
                    let _ = app.emit("axx-remote-voice-toggle", ());
                }
                if msg.message == WM_HOTKEY && msg.wParam == 1001 {
                    let now = Instant::now();
                    let double = now.duration_since(last) < Duration::from_millis(450);
                    last = now;
                    if double {
                        let _ = resident::go_home(&app);
                    } else {
                        let _ = resident::summon(&app, true);
                    }
                }
            }
            UnregisterHotKey(std::ptr::null_mut(), 1001);
            UnregisterHotKey(std::ptr::null_mut(), 1002);
            if !hook.is_null() {
                UnhookWindowsHookEx(hook);
            }
        }
    });
}

#[cfg(windows)]
fn acquire_instance() -> Result<Option<WinHandle>, String> {
    use windows_sys::Win32::{
        Foundation::{ERROR_ALREADY_EXISTS, GetLastError},
        System::Threading::{CreateMutexW, EVENT_MODIFY_STATE, OpenEventW, SetEvent},
    };
    let name: Vec<u16> = "Local\\AxxDesktop-com.axx.desktop"
        .encode_utf16()
        .chain(Some(0))
        .collect();
    unsafe {
        let handle = CreateMutexW(std::ptr::null(), 0, name.as_ptr());
        if handle.is_null() {
            return Err("Cannot create Axx instance mutex".into());
        }
        let exists = GetLastError() == ERROR_ALREADY_EXISTS;
        let guard = WinHandle(handle as isize);
        if exists {
            let name: Vec<u16> = "Local\\AxxResidentSummon-com.axx.desktop"
                .encode_utf16()
                .chain(Some(0))
                .collect();
            for _ in 0..10 {
                let event = OpenEventW(EVENT_MODIFY_STATE, 0, name.as_ptr());
                if !event.is_null() {
                    SetEvent(event);
                    drop(WinHandle(event as isize));
                    break;
                }
                std::thread::sleep(Duration::from_millis(30));
            }
            Ok(None)
        } else {
            Ok(Some(guard))
        }
    }
}
#[cfg(windows)]
fn start_instance_listener(app: AppHandle) -> Result<(), String> {
    use windows_sys::Win32::System::Threading::{CreateEventW, WaitForSingleObject};
    let name: Vec<u16> = "Local\\AxxResidentSummon-com.axx.desktop"
        .encode_utf16()
        .chain(Some(0))
        .collect();
    let event = unsafe { CreateEventW(std::ptr::null(), 0, 0, name.as_ptr()) };
    if event.is_null() {
        return Err("Cannot create resident activation event".into());
    }
    let event = event as isize;
    *app.state::<HostState>().summon_event.lock().unwrap() = Some(WinHandle(event));
    std::thread::spawn(move || {
        loop {
            if app.state::<HostState>().stopping.load(Ordering::Relaxed) {
                break;
            }
            if unsafe { WaitForSingleObject(event as _, 300) } == 0 {
                let _ = resident::summon(&app, false);
            }
        }
    });
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let state = HostState::default();
    #[cfg(windows)]
    {
        match acquire_instance() {
            Ok(Some(handle)) => *state.instance.lock().unwrap() = Some(handle),
            Ok(None) => return,
            Err(error) => {
                eprintln!("{error}");
                return;
            }
        }
    }
    let app = tauri::Builder::default()
        .manage(state)
        .plugin(
            tauri_plugin_log::Builder::default()
                // A resident GUI outlives its launcher. Inherited stdout/stderr
                // pipes may already be closed; fern's fallback would panic if
                // both are unavailable. Keep diagnostics in the native log.
                .targets([tauri_plugin_log::Target::new(
                    tauri_plugin_log::TargetKind::LogDir { file_name: None },
                )])
                .level(log::LevelFilter::Info)
                .build(),
        )
        .invoke_handler(tauri::generate_handler![
            native_status,
            system_media::system_media_status,
            system_media::system_media_control,
            capture::capture_select,
            capture::capture_selection_finish,
            capture::capture_cancel_selection,
            capture::capture_halo,
            magic_pen::magic_pen_capture,
            magic_pen::magic_pen_session,
            backend_request,
            realtime_chat::ollama_realtime_chat,
            realtime_chat::ollama_realtime_cancel,
            realtime_chat::ollama_realtime_warmup,
            window_action,
            set_timer,
            hit_map,
            set_topmost,
            set_shortcut,
            resident::desktop_layout,
            resident::desktop_move_body,
            resident::desktop_activity
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            let state = app.state::<HostState>();
            *state.data_dir.lock().unwrap() =
                data_directory(&handle).map_err(std::io::Error::other)?;
            restore_window(&handle);
            resident::install_tray(&handle)?;
            let backend_handle = handle.clone();
            std::thread::spawn(move || {
                if let Err(error) = spawn_backend(&backend_handle) {
                    log::error!("{error}");
                    *backend_handle
                        .state::<HostState>()
                        .backend_error
                        .lock()
                        .unwrap() = Some(error);
                }
                let _ = backend_handle.emit("axx-backend-ready", ());
                write_runtime_snapshot(&backend_handle);
            });
            #[cfg(windows)]
            {
                start_instance_listener(handle.clone()).map_err(std::io::Error::other)?;
                start_cursor_hit_test_loop(handle.clone());
                start_global_hotkey_thread(handle.clone());
            }
            std::thread::spawn(move || {
                loop {
                    std::thread::sleep(Duration::from_millis(400));
                    let state = handle.state::<HostState>();
                    if state.stopping.load(Ordering::Relaxed) {
                        break;
                    }
                    if state.preferences_dirty.swap(false, Ordering::Relaxed) {
                        persist_window(&handle);
                    }
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "capture-selector" && matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                capture::selector_closed();
            }
            // Auxiliary selection/halo windows must never move the resident or stop its backend.
            if window.label() != "main" { return; }
            let state = window.state::<HostState>();
            match event {
                tauri::WindowEvent::Moved(position) => {
                    resident::record_move(window.app_handle(), position);
                    state.preferences_dirty.store(true, Ordering::Relaxed);
                    if magic_pen::ACTIVE.load(Ordering::Acquire) {
                        let _ = window.emit("axx-pen-geometry", json!({"reason":"move"}));
                    }
                }
                tauri::WindowEvent::Resized(_) => {
                    state.preferences_dirty.store(true, Ordering::Relaxed);
                    if magic_pen::ACTIVE.load(Ordering::Acquire) {
                        let _ = window.emit("axx-pen-geometry", json!({"reason":"resize"}));
                    }
                }
                tauri::WindowEvent::ScaleFactorChanged { .. } => {
                    state.preferences_dirty.store(true, Ordering::Relaxed);
                    if magic_pen::ACTIVE.load(Ordering::Acquire) {
                        let _ = window.emit("axx-pen-geometry", json!({"reason":"scale"}));
                    }
                }
                tauri::WindowEvent::CloseRequested { api, .. } => {
                    persist_window(window.app_handle());
                    if !state.quitting.load(Ordering::Relaxed) {
                        api.prevent_close();
                        state.follow.store(false, Ordering::Relaxed);
                        let _ = window.hide();
                    }
                }
                tauri::WindowEvent::Destroyed => {
                    state.stopping.store(true, Ordering::Relaxed);
                    terminate_backend(&state);
                }
                _ => {}
            }
        })
        .build(tauri::generate_context!())
        .expect("Cannot build Axx application");
    app.run(|app, event| {
        if let tauri::RunEvent::Exit = event {
            let state = app.state::<HostState>();
            state.stopping.store(true, Ordering::Relaxed);
            terminate_backend(&state);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn long_actions_fit_worker_deadlines_without_delaying_stop() {
        assert!(backend_timeout_seconds("/axx-api/commands/execute") > 120);
        assert!(backend_timeout_seconds("/axx-api/learning/propose") > 140);
        assert!(backend_timeout_seconds("/axx-api/learning/execute") > 8 * 120);
        assert_eq!(backend_timeout_seconds("/axx-api/commands/cancel"), 3);
        assert_eq!(backend_timeout_seconds("/axx-api/status"), 3);
    }
    #[test]
    fn hit_regions_validate_and_use_logical_coordinates() {
        let r = Rect {
            x: 10.0,
            y: 20.0,
            width: 100.0,
            height: 50.0,
        };
        assert!(r.valid());
        assert!(r.contains(55.0, 35.0));
        assert!(!r.contains(0.0, 0.0));
        assert!(
            !Rect {
                width: f64::NAN,
                ..r
            }
            .valid()
        );
        assert!(!Rect { height: -1.0, ..r }.valid());
    }
    #[test]
    fn local_proxy_rejects_path_escape_and_non_api_routes() {
        assert!(validate_route("GET", "/axx-api/status").is_ok());
        for path in [
            "http://evil/axx-api/status",
            "/axx-api/../secret",
            "/axx-api/status\r\nX: bad",
            "/index.html",
            "/axx-api/\\evil",
        ] {
            assert!(validate_route("POST", path).is_err());
        }
        assert!(validate_route("CONNECT", "/axx-api/status").is_err());
    }
    #[test]
    fn alpha_mask_preserves_transparent_click_through_holes() {
        let mut bits = vec![false; 64];
        bits[4 * 8 + 4] = true;
        let mask = PixelMask {
            bounds: Rect {
                x: 100.0,
                y: 200.0,
                width: 80.0,
                height: 80.0,
            },
            cols: 8,
            rows: 8,
            bits,
        };
        assert!(mask.contains(145.0, 245.0));
        assert!(mask.contains(135.0, 245.0));
        assert!(!mask.contains(105.0, 205.0));
        assert!(!mask.contains(90.0, 245.0));
    }

    #[test]
    fn private_transport_authenticates_and_parses_real_loopback_response() {
        use std::{
            io::{Read, Write},
            net::TcpListener,
        };
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            let mut input = [0; 4096];
            let size = stream.read(&mut input).unwrap();
            let headers = String::from_utf8_lossy(&input[..size]).to_ascii_lowercase();
            assert!(headers.starts_with("get /axx-api/status http/1.1"));
            assert!(headers.contains("authorization: bearer private-session-test"));
            let payload = "{\"instance_id\":\"test-instance\"}";
            write!(stream,"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",payload.len(),payload).unwrap();
        });
        let connection = BackendConnection {
            port,
            token: "private-session-test".into(),
            instance_id: "test-instance".into(),
        };
        let result = request_backend(&connection, "GET", "/axx-api/status", None).unwrap();
        assert_eq!(result["instance_id"], "test-instance");
        server.join().unwrap();
    }

    #[test]
    fn private_transport_rejects_http_errors_instead_of_reporting_json_as_success() {
        use std::{
            io::{Read, Write},
            net::TcpListener,
        };
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            let mut input = [0; 4096];
            stream.read(&mut input).unwrap();
            let payload =
                "{\"error\":{\"code\":\"FORBIDDEN\",\"message\":\"Private session rejected\"}}";
            write!(stream, "HTTP/1.1 403 Forbidden\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}", payload.len(), payload).unwrap();
        });
        let connection = BackendConnection {
            port,
            token: "test-session".into(),
            instance_id: "test".into(),
        };
        let result = request_backend(
            &connection,
            "POST",
            "/axx-api/commands/execute",
            Some(json!({})),
        );
        assert!(result.is_err(), "HTTP 403 must reject the IPC request");
        let error = result.unwrap_err();
        assert!(error.contains("403"));
        assert!(error.contains("Private session rejected"));
        server.join().unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn job_cleanup_terminates_owned_suspended_process() {
        use std::os::windows::process::CommandExt;
        let mut child = Command::new("cmd.exe")
            .args(["/D", "/C", "ping -n 30 127.0.0.1 > NUL"])
            .creation_flags(0x08000000 | 0x00000004)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let job = bind_child_to_job(&child).unwrap();
        resume_owned_child(child.id()).unwrap();
        std::thread::sleep(Duration::from_millis(200));
        assert!(child.try_wait().unwrap().is_none());
        drop(job);
        let deadline = Instant::now() + Duration::from_secs(3);
        loop {
            if child.try_wait().unwrap().is_some() {
                break;
            }
            if Instant::now() >= deadline {
                let _ = child.kill();
                panic!("Owned process survived its job");
            }
            std::thread::sleep(Duration::from_millis(20));
        }
    }

    #[cfg(windows)]
    #[test]
    #[ignore = "Helper invoked only by explicit-breakaway integration test"]
    fn launch_explicit_breakaway_target_helper() {
        use std::os::windows::process::CommandExt;
        let output = std::env::var_os("AXX_TEST_BREAKAWAY_OUTPUT")
            .expect("Parent-owned test output missing");
        let mut target = Command::new("cmd.exe")
            .args(["/D", "/C", "ping -n 60 127.0.0.1 > NUL"])
            .creation_flags(0x08000000 | 0x01000000)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        fs::write(output, target.id().to_string()).unwrap();
        let _ = target.wait();
    }

    #[cfg(windows)]
    #[test]
    fn explicitly_escaped_user_target_survives_owned_job_cleanup() {
        use std::os::windows::process::CommandExt;
        use windows_sys::Win32::System::Threading::{
            OpenProcess, PROCESS_SYNCHRONIZE, WaitForSingleObject,
        };
        let output =
            std::env::temp_dir().join(format!("axx-breakaway-test-{}.pid", uuid::Uuid::new_v4()));
        let mut owned = Command::new(std::env::current_exe().unwrap())
            .args([
                "--ignored",
                "--exact",
                "tests::launch_explicit_breakaway_target_helper",
                "--nocapture",
            ])
            .env("AXX_TEST_BREAKAWAY_OUTPUT", &output)
            .creation_flags(0x08000000 | 0x00000004)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let job = bind_child_to_job(&owned).unwrap();
        resume_owned_child(owned.id()).unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        let escaped_pid = loop {
            if let Ok(text) = fs::read_to_string(&output) {
                if let Ok(pid) = text.parse::<u32>() {
                    break pid;
                }
            }
            if owned.try_wait().unwrap().is_some() || Instant::now() >= deadline {
                drop(job);
                let _ = owned.kill();
                let _ = owned.wait();
                let _ = fs::remove_file(output);
                panic!("Owned helper did not launch explicit breakaway target");
            }
            std::thread::sleep(Duration::from_millis(20));
        };
        let handle = unsafe { OpenProcess(PROCESS_SYNCHRONIZE, 0, escaped_pid) };
        assert!(!handle.is_null());
        let target = WinHandle(handle as isize);
        drop(job);
        let _ = owned.wait();
        // WAIT_TIMEOUT means the deliberately escaped user target is still running.
        let alive = unsafe { WaitForSingleObject(target.0 as _, 150) } == 258;
        // This is a dedicated test-created target. Reap its exact tree after observing survival.
        let cleanup = Command::new("taskkill.exe")
            .args(["/F", "/T", "/PID", &escaped_pid.to_string()])
            .creation_flags(0x08000000)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .unwrap();
        let _ = fs::remove_file(output);
        assert!(alive, "Explicit user target was killed with backend job");
        assert!(
            cleanup.success(),
            "Could not clean up dedicated escaped test target"
        );
        assert_eq!(unsafe { WaitForSingleObject(target.0 as _, 3000) }, 0);
    }
}
