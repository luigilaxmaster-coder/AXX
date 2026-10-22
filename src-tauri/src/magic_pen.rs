//! Snapshot exclusion is temporary and restores each window's recording policy.
use tauri::{AppHandle, Manager, WebviewWindow};
use serde_json::{Value, json};
use std::sync::atomic::{AtomicBool, Ordering};
pub static BUSY: AtomicBool = AtomicBool::new(false);
pub static ACTIVE: AtomicBool = AtomicBool::new(false);

#[tauri::command]
pub fn magic_pen_session(window: WebviewWindow, active: bool) -> Result<(), String> {
    if window.label() != "main" { return Err("Sólo Axx puede activar Magic Pen".into()); }
    ACTIVE.store(active, Ordering::Release);
    Ok(())
}

struct CaptureGuard(Vec<(WebviewWindow, u32)>);
impl Drop for CaptureGuard {
    fn drop(&mut self) {
        #[cfg(windows)]
        for (window, affinity) in &self.0 {
            if let Ok(hwnd) = window.hwnd() {
                if unsafe { windows_sys::Win32::UI::WindowsAndMessaging::SetWindowDisplayAffinity(hwnd.0 as _, *affinity) } == 0 {
                    log::error!("Could not restore capture affinity for {}", window.label());
                }
            }
        }
        BUSY.store(false, Ordering::Release);
    }
}

#[tauri::command]
pub async fn magic_pen_capture(app: AppHandle, window: WebviewWindow, monitor: String) -> Result<Value, String> {
    if window.label() != "main" { return Err("La captura sólo se inicia desde Axx".into()); }
    if BUSY.swap(true, Ordering::AcqRel) { return Err("Hay una captura en curso".into()); }
    let mut guard = CaptureGuard(Vec::new());
    #[cfg(windows)]
    for w in app.webview_windows().into_values() {
        let hwnd = w.hwnd().map_err(|e| e.to_string())?;
        let mut previous = 0;
        unsafe {
            use windows_sys::Win32::UI::WindowsAndMessaging::{GetWindowDisplayAffinity, SetWindowDisplayAffinity};
            if GetWindowDisplayAffinity(hwnd.0 as _, &mut previous) == 0 { return Err("No se pudo comprobar la política de captura".into()); }
            guard.0.push((w, previous));
            if SetWindowDisplayAffinity(hwnd.0 as _, 0x11) == 0 { return Err("No se pudo excluir Axx de la captura".into()); }
        }
    }
    let connection = app.state::<crate::HostState>().backend.lock().unwrap().clone().ok_or("Backend no disponible")?;
    let result = tauri::async_runtime::spawn_blocking(move || {
        std::thread::sleep(std::time::Duration::from_millis(120));
        crate::request_backend(&connection, "POST", "/axx-api/pen/capture", Some(json!({"monitor":monitor})))
    }).await.map_err(|e| e.to_string())?;
    drop(guard);
    result
}
