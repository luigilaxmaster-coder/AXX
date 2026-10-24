//! Snapshot exclusion is temporary and restores each window's recording policy.
use tauri::{AppHandle, Manager, WebviewWindow};
use serde_json::{Value, json};
use std::sync::atomic::{AtomicBool, Ordering};
static BUSY: AtomicBool = AtomicBool::new(false);
pub static ACTIVE: AtomicBool = AtomicBool::new(false);

// A non-blocking lease serializes every change of the main window's capture
// affinity. Unlike a check followed by a write, acquisition is atomic and may
// remain owned across the asynchronous native capture without blocking the UI.
pub struct AffinityLease;
impl AffinityLease {
    pub fn acquire(message: &str) -> Result<Self, String> {
        BUSY.compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .map(|_| Self).map_err(|_| message.to_owned())
    }
}
impl Drop for AffinityLease {
    fn drop(&mut self) { BUSY.store(false, Ordering::Release); }
}

#[tauri::command]
pub fn magic_pen_session(window: WebviewWindow, active: bool) -> Result<(), String> {
    if window.label() != "main" { return Err("Sólo Axx puede activar Magic Pen".into()); }
    ACTIVE.store(active, Ordering::Release);
    Ok(())
}

struct CaptureGuard { windows: Vec<(WebviewWindow, u32)>, _lease: AffinityLease }
impl Drop for CaptureGuard {
    fn drop(&mut self) {
        #[cfg(windows)]
        for (window, affinity) in &self.windows {
            if let Ok(hwnd) = window.hwnd() {
                if unsafe { windows_sys::Win32::UI::WindowsAndMessaging::SetWindowDisplayAffinity(hwnd.0 as _, *affinity) } == 0 {
                    log::error!("Could not restore capture affinity for {}", window.label());
                }
            }
        }
    }
}

#[tauri::command]
pub async fn magic_pen_capture(app: AppHandle, window: WebviewWindow, monitor: String) -> Result<Value, String> {
    if window.label() != "main" { return Err("La captura sólo se inicia desde Axx".into()); }
    let lease = AffinityLease::acquire("Hay una captura o un cambio de grabación en curso")?;
    let mut guard = CaptureGuard { windows: Vec::new(), _lease: lease };
    let position = window.inner_position().map_err(|e| e.to_string())?;
    let scale = window.scale_factor().map_err(|e| e.to_string())?;
    let monitor = if monitor.is_empty() {
        let m = window.current_monitor().map_err(|e| e.to_string())?.ok_or("Pantalla no disponible")?;
        let p = m.position(); let s = m.size();
        format!("{},{},{},{}", p.x, p.y, p.x as i64 + s.width as i64, p.y as i64 + s.height as i64)
    } else { monitor };
    #[cfg(windows)]
    for w in app.webview_windows().into_values() {
        let hwnd = w.hwnd().map_err(|e| e.to_string())?;
        let mut previous = 0;
        unsafe {
            use windows_sys::Win32::UI::WindowsAndMessaging::{GetWindowDisplayAffinity, SetWindowDisplayAffinity};
            if GetWindowDisplayAffinity(hwnd.0 as _, &mut previous) == 0 { return Err("No se pudo comprobar la política de captura".into()); }
            guard.windows.push((w, previous));
            if SetWindowDisplayAffinity(hwnd.0 as _, 0x11) == 0 { return Err("No se pudo excluir Axx de la captura".into()); }
        }
    }
    let connection = app.state::<crate::HostState>().backend.lock().unwrap().clone().ok_or("Backend no disponible")?;
    let result = tauri::async_runtime::spawn_blocking(move || {
        std::thread::sleep(std::time::Duration::from_millis(120));
        crate::request_backend(&connection, "POST", "/axx-api/pen/capture", Some(json!({"monitor":monitor})))
    }).await.map_err(|e| e.to_string())?;
    drop(guard);
    let mut document = result?;
    if window.inner_position().map_err(|e| e.to_string())? != position
        || window.scale_factor().map_err(|e| e.to_string())? != scale {
        return Err("La pantalla cambió durante la captura. Selecciona otra vez.".into());
    }
    document["viewport"] = json!({"x":position.x,"y":position.y,"scale":scale});
    Ok(document)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn affinity_lease_excludes_competing_changes_and_releases_on_error() {
        let first = AffinityLease::acquire("busy").unwrap();
        assert!(AffinityLease::acquire("busy").is_err());
        assert!(std::thread::spawn(|| AffinityLease::acquire("busy").is_err()).join().unwrap());
        drop(first);
        let failed = (|| -> Result<(), String> {
            let _lease = AffinityLease::acquire("busy")?;
            Err("capture failed".into())
        })();
        assert!(failed.is_err());
        assert!(AffinityLease::acquire("busy").is_ok());
    }
}
