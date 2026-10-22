//! Resident desktop geometry, tray and supported virtual desktop transfer.
use super::*;
use tauri::{PhysicalPosition, WebviewWindow};

static ACTIVE_PANEL_DRAG: AtomicBool = AtomicBool::new(false);
static STABLE_SURFACE: AtomicBool = AtomicBool::new(false);
static LAST_LAYOUT_INSTANT: Mutex<Option<Instant>> = Mutex::new(None);

#[allow(dead_code)]
pub fn set_panel_drag(active: bool) {
    ACTIVE_PANEL_DRAG.store(active, Ordering::Relaxed);
}

#[allow(dead_code)]
pub fn is_panel_drag_active() -> bool {
    ACTIVE_PANEL_DRAG.load(Ordering::Relaxed)
}

#[derive(Clone, Debug)]
pub struct Geometry {
    pub width: f64,
    pub height: f64,
    pub anchor_x: f64,
    pub anchor_y: f64,
    pub screen_x: f64,
    pub screen_y: f64,
    pub ready: bool,
}
impl Default for Geometry {
    fn default() -> Self {
        Self {
            width: 400.,
            height: 400.,
            anchor_x: 200.,
            anchor_y: 200.,
            screen_x: 0.,
            screen_y: 0.,
            ready: false,
        }
    }
}
#[derive(Clone, Copy, Debug)]
pub struct WorkArea {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
    pub scale: f64,
}
impl WorkArea {
    fn distance(self, x: f64, y: f64) -> f64 {
        let dx = (self.x - x).max(0.).max(x - self.x - self.width);
        let dy = (self.y - y).max(0.).max(y - self.y - self.height);
        dx * dx + dy * dy
    }
}
fn areas(w: &WebviewWindow) -> Vec<WorkArea> {
    w.available_monitors()
        .unwrap_or_default()
        .iter()
        .map(|m| {
            let a = m.work_area();
            WorkArea {
                x: a.position.x as f64,
                y: a.position.y as f64,
                width: a.size.width as f64,
                height: a.size.height as f64,
                scale: m.scale_factor(),
            }
        })
        .collect()
}
fn nearest(w: &WebviewWindow, x: f64, y: f64) -> WorkArea {
    areas(w)
        .into_iter()
        .min_by(|a, b| a.distance(x, y).total_cmp(&b.distance(x, y)))
        .unwrap_or(WorkArea {
            x: 0.,
            y: 0.,
            width: 1920.,
            height: 1080.,
            scale: 1.,
        })
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopStatus {
    width: f64,
    height: f64,
    anchor_x: f64,
    anchor_y: f64,
    screen_x: f64,
    screen_y: f64,
    scale_factor: f64,
    work_width: f64,
    work_height: f64,
    space_left: f64,
    space_right: f64,
    space_above: f64,
    space_below: f64,
    ready: bool,
    virtual_desktop_error: Option<String>,
}
pub fn status(app: &AppHandle) -> Option<DesktopStatus> {
    let w = app.get_webview_window("main")?;
    let state = app.state::<HostState>();
    let g = state.resident.lock().unwrap().clone();
    let a = nearest(&w, g.screen_x, g.screen_y);
    Some(DesktopStatus {
        width: g.width,
        height: g.height,
        anchor_x: g.anchor_x,
        anchor_y: g.anchor_y,
        screen_x: g.screen_x,
        screen_y: g.screen_y,
        scale_factor: a.scale,
        work_width: a.width / a.scale,
        work_height: a.height / a.scale,
        space_left: ((g.screen_x - a.x) / a.scale).max(0.),
        space_right: ((a.x + a.width - g.screen_x) / a.scale).max(0.),
        space_above: ((g.screen_y - a.y) / a.scale).max(0.),
        space_below: ((a.y + a.height - g.screen_y) / a.scale).max(0.),
        ready: g.ready,
        virtual_desktop_error: state.desktop_error.lock().unwrap().clone(),
    })
}
pub fn constrained_origin(g: &Geometry, a: WorkArea) -> (f64, f64) {
    let w = (g.width * a.scale).min(a.width);
    let h = (g.height * a.scale).min(a.height);
    (
        (g.screen_x - g.anchor_x * a.scale).clamp(a.x, a.x + a.width - w),
        (g.screen_y - g.anchor_y * a.scale).clamp(a.y, a.y + a.height - h),
    )
}
fn apply(app: &AppHandle, resize: bool) -> Result<(), String> {
    let w = app
        .get_webview_window("main")
        .ok_or("Resident window unavailable")?;
    let state = app.state::<HostState>();
    let mut g = state.resident.lock().unwrap().clone();
    let a = nearest(&w, g.screen_x, g.screen_y);
    if STABLE_SURFACE.load(Ordering::Relaxed) {
        g.anchor_x = ((g.screen_x - a.x) / a.scale).clamp(0., g.width);
        g.anchor_y = ((g.screen_y - a.y) / a.scale).clamp(0., g.height);
    }
    let (x, y) = constrained_origin(&g, a);
    g.screen_x = x + g.anchor_x * a.scale;
    g.screen_y = y + g.anchor_y * a.scale;
    *state.resident.lock().unwrap() = g.clone();
    state.layout_changing.store(true, Ordering::Relaxed);
    if let Ok(mut guard) = LAST_LAYOUT_INSTANT.lock() {
        *guard = Some(Instant::now());
    }
    let result = (|| {
        #[cfg(windows)]
        {
            use windows_sys::Win32::UI::WindowsAndMessaging::{
                HWND_NOTOPMOST, HWND_TOPMOST, SetWindowPos, SWP_NOACTIVATE, SWP_NOSIZE,
            };
            if let Ok(hwnd) = w.hwnd() {
                let px = x.round() as i32;
                let py = y.round() as i32;
                let pw = (g.width * a.scale).min(a.width).round() as i32;
                let ph = (g.height * a.scale).min(a.height).round() as i32;
                let top = if w.is_always_on_top().unwrap_or(true) {
                    HWND_TOPMOST
                } else {
                    HWND_NOTOPMOST
                };
                unsafe {
                    if resize {
                        SetWindowPos(
                            hwnd.0 as _,
                            top,
                            px,
                            py,
                            pw,
                            ph,
                            SWP_NOACTIVATE,
                        );
                    } else {
                        SetWindowPos(
                            hwnd.0 as _,
                            top,
                            px,
                            py,
                            0,
                            0,
                            SWP_NOACTIVATE | SWP_NOSIZE,
                        );
                    }
                }
            } else {
                if resize {
                    w.set_size(tauri::PhysicalSize::new(
                        (g.width * a.scale).min(a.width).round() as u32,
                        (g.height * a.scale).min(a.height).round() as u32,
                    ))
                    .map_err(|e| e.to_string())?;
                }
                w.set_position(PhysicalPosition::new(x.round() as i32, y.round() as i32))
                    .map_err(|e| e.to_string())?;
            }
        }
        #[cfg(not(windows))]
        {
            if resize {
                w.set_size(tauri::PhysicalSize::new(
                    (g.width * a.scale).min(a.width).round() as u32,
                    (g.height * a.scale).min(a.height).round() as u32,
                ))
                .map_err(|e| e.to_string())?;
            }
            w.set_position(PhysicalPosition::new(x.round() as i32, y.round() as i32))
                .map_err(|e| e.to_string())?;
        }
        Ok(())
    })();
    state.layout_changing.store(false, Ordering::Relaxed);
    if let Ok(mut guard) = LAST_LAYOUT_INSTANT.lock() {
        *guard = Some(Instant::now());
    }
    state.preferences_dirty.store(true, Ordering::Relaxed);
    result

}
#[tauri::command]
pub fn desktop_layout(
    app: AppHandle,
    width: f64,
    height: f64,
    anchor_x: f64,
    anchor_y: f64,
    ready: Option<bool>,
    panel_drag: Option<bool>,
    stable_surface: Option<bool>,
) -> Result<DesktopStatus, String> {
    if let Some(dragging) = panel_drag {
        set_panel_drag(dragging);
    }
    log::info!(
        "resident desktop_layout received width={width} height={height} anchor=({anchor_x},{anchor_y}) ready={ready:?} panel_drag={panel_drag:?}"
    );
    if ![width, height, anchor_x, anchor_y]
        .iter()
        .all(|v| v.is_finite())
        || !(96.0..=4096.0).contains(&width)
        || !(96.0..=4096.0).contains(&height)
        || anchor_x < 0.
        || anchor_y < 0.
        || anchor_x > width
        || anchor_y > height
    {
        return Err("Invalid bounded resident content geometry".into());
    }
    let state = app.state::<HostState>();
    if let Some(stable) = stable_surface {
        STABLE_SURFACE.store(stable, Ordering::Relaxed);
    }
    {
        let mut g = state.resident.lock().unwrap();
        g.width = width;
        g.height = height;
        g.anchor_x = anchor_x;
        g.anchor_y = anchor_y;
        if STABLE_SURFACE.load(Ordering::Relaxed) {
            if let Some(w) = app.get_webview_window("main") {
                let a = nearest(&w, g.screen_x, g.screen_y);
                g.screen_x = a.x + anchor_x * a.scale;
                g.screen_y = a.y + anchor_y * a.scale;
            }
        }
        if ready == Some(true) {
            g.ready = true;
        }
    }
    apply(&app, true)?;
    log::info!("resident desktop_layout geometry applied ready={ready:?}");
    if ready == Some(true) {
        show_passive(&app)?;
        super::write_runtime_snapshot(&app);
    }
    status(&app).ok_or_else(|| "Resident window unavailable".into())
}
#[tauri::command]
pub fn desktop_move_body(app: AppHandle, x: f64, y: f64) -> Result<DesktopStatus, String> {
    if !x.is_finite() || !y.is_finite() {
        return Err("Invalid body position".into());
    }
    {
        let state = app.state::<HostState>();
        let mut g = state.resident.lock().unwrap();
        g.screen_x = x;
        g.screen_y = y;
    }
    apply(&app, false)?;
    status(&app).ok_or_else(|| "Resident window unavailable".into())
}
#[tauri::command]
pub fn desktop_activity(
    app: AppHandle,
    active: bool,
    follow: Option<bool>,
    panel_drag: Option<bool>,
) -> Result<(), String> {
    let state = app.state::<HostState>();
    state.frontend_active.store(active, Ordering::Relaxed);
    if let Some(follow) = follow {
        state.follow.store(follow, Ordering::Relaxed);
    }
    if let Some(dragging) = panel_drag {
        set_panel_drag(dragging);
    }
    Ok(())
}
pub fn show_passive(app: &AppHandle) -> Result<(), String> {
    let w = app
        .get_webview_window("main")
        .ok_or("Resident window unavailable")?;
    if !app.state::<HostState>().resident.lock().unwrap().ready {
        log::info!("resident passive show deferred: frontend first frame not ready");
        return Ok(());
    }
    #[cfg(windows)]
    {
        use windows_sys::Win32::UI::WindowsAndMessaging::*;
        // Keep Tao's VISIBLE flag synchronized. Direct ShowWindow alone leaves
        // it false, so the next cursor/style update hides the HWND again.
        if !w.is_visible().unwrap_or(false) {
            w.set_focusable(false).map_err(|e| e.to_string())?;
            w.show().map_err(|e| e.to_string())?;
        }
        // The controller has its own visibility state, separate from the HWND.
        let webview: &tauri::Webview = w.as_ref();
        webview.show().map_err(|e| e.to_string())?;
        let hwnd = w.hwnd().map_err(|e| e.to_string())?;
        unsafe {
            ShowWindow(hwnd.0 as _, SW_SHOWNOACTIVATE);
            let positioned = SetWindowPos(
                hwnd.0 as _,
                if w.is_always_on_top().unwrap_or(true) {
                    HWND_TOPMOST
                } else {
                    HWND_NOTOPMOST
                },
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            );
            if positioned == 0 {
                let error = std::io::Error::last_os_error();
                log::error!("resident passive show failed: {error}");
                return Err(format!(
                    "Windows could not show Axx without activation: {error}"
                ));
            }
        }
    }
    #[cfg(not(windows))]
    w.show().map_err(|e| e.to_string())?;
    log::info!(
        "resident passive show completed visible={:?} position={:?} size={:?}",
        w.is_visible(),
        w.outer_position(),
        w.inner_size()
    );
    Ok(())
}
pub fn go_home(app: &AppHandle) -> Result<(), String> {
    #[cfg(windows)]
    move_to_foreground_desktop(app);
    let w = app
        .get_webview_window("main")
        .ok_or("Resident window unavailable")?;
    let state = app.state::<HostState>();
    state.follow.store(false, Ordering::Relaxed);
    let mut g = state.resident.lock().unwrap().clone();
    #[cfg(windows)]
    let home_point = cursor().unwrap_or((g.screen_x, g.screen_y));
    #[cfg(not(windows))]
    let home_point = (g.screen_x, g.screen_y);
    let a = nearest(&w, home_point.0, home_point.1);
    let half_w = (g.anchor_x.min(g.width - g.anchor_x) * a.scale).max(48. * a.scale);
    let half_h = (g.anchor_y.min(g.height - g.anchor_y) * a.scale).max(48. * a.scale);
    g.screen_x = a.x + a.width - half_w - 24. * a.scale;
    g.screen_y = a.y + a.height - half_h - 24. * a.scale;
    *state.resident.lock().unwrap() = g;
    apply(app, false)?;
    show_passive(app)?;
    let _ = w.emit("axx-recenter", ());
    Ok(())
}
#[cfg(windows)]
fn cursor() -> Option<(f64, f64)> {
    use windows_sys::Win32::{Foundation::POINT, UI::WindowsAndMessaging::GetCursorPos};
    let mut p = POINT { x: 0, y: 0 };
    (unsafe { GetCursorPos(&mut p) } != 0).then_some((p.x as f64, p.y as f64))
}
pub fn summon(app: &AppHandle, follow: bool) -> Result<(), String> {
    let w = app
        .get_webview_window("main")
        .ok_or("Resident window unavailable")?;
    #[cfg(windows)]
    {
        move_to_foreground_desktop(app);
        if let Some((x, y)) = cursor() {
            let a = nearest(&w, x, y);
            let mut g = app.state::<HostState>().resident.lock().unwrap().clone();
            g.screen_x = x + 100. * a.scale;
            g.screen_y = y - 50. * a.scale;
            *app.state::<HostState>().resident.lock().unwrap() = g;
            apply(app, false)?;
        }
    }
    app.state::<HostState>()
        .follow
        .store(follow, Ordering::Relaxed);
    show_passive(app)?;
    let _ = w.emit("axx-show", json!({"follow":follow}));
    Ok(())
}
pub fn record_move(app: &AppHandle, p: &tauri::PhysicalPosition<i32>) {
    let state = app.state::<HostState>();
    if state.layout_changing.load(Ordering::Relaxed) || is_panel_drag_active() {
        log::debug!("record_move suppressed: active panel drag or layout changing");
        return;
    }
    if let Ok(guard) = LAST_LAYOUT_INSTANT.lock() {
        if let Some(instant) = *guard {
            if instant.elapsed() < Duration::from_millis(300) {
                log::debug!("record_move suppressed: layout change within 300ms");
                return;
            }
        }
    }
    let Some(w) = app.get_webview_window("main") else {
        return;
    };
    let scale = w.scale_factor().unwrap_or(1.);
    let mut g = state.resident.lock().unwrap();
    g.screen_x = p.x as f64 + g.anchor_x * scale;
    g.screen_y = p.y as f64 + g.anchor_y * scale;
    state.preferences_dirty.store(true, Ordering::Relaxed);
}

pub fn recover_display(app: &AppHandle) {
    let state = app.state::<HostState>();
    let mut g = state.resident.lock().unwrap().clone();
    let Some(w) = app.get_webview_window("main") else {
        return;
    };
    let monitors = areas(&w);
    if monitors.is_empty()
        || monitors
            .iter()
            .any(|m| m.distance(g.screen_x, g.screen_y) == 0.)
    {
        return;
    }
    let a = nearest(&w, g.screen_x, g.screen_y);
    g.screen_x = a.x + a.width - ((g.width - g.anchor_x) + 24.) * a.scale;
    g.screen_y = a.y + a.height - ((g.height - g.anchor_y) + 24.) * a.scale;
    *state.resident.lock().unwrap() = g;
    let _ = apply(app, true);
    let _ = w.emit("axx-desktop-layout", status(app));
}
#[derive(Serialize, Deserialize)]
struct Preferences {
    version: u32,
    anchor_screen_x: f64,
    anchor_screen_y: f64,
    always_on_top: bool,
    monitor: Option<String>,
}
pub fn persist(app: &AppHandle) {
    let state = app.state::<HostState>();
    let g = state.resident.lock().unwrap().clone();
    if !g.ready {
        return;
    }
    let Some(w) = app.get_webview_window("main") else {
        return;
    };
    let p = Preferences {
        version: 2,
        anchor_screen_x: g.screen_x,
        anchor_screen_y: g.screen_y,
        always_on_top: w.is_always_on_top().unwrap_or(true),
        monitor: w
            .current_monitor()
            .ok()
            .flatten()
            .and_then(|m| m.name().cloned()),
    };
    let dir = state.data_dir.lock().unwrap().clone();
    if let Ok(bytes) = serde_json::to_vec_pretty(&p) {
        let tmp = dir.join("native-window.tmp");
        if fs::write(&tmp, bytes).is_ok() {
            let _ = fs::rename(tmp, dir.join("native-window.json"));
        }
    }
}
pub fn restore(app: &AppHandle) {
    let state = app.state::<HostState>();
    let path = state.data_dir.lock().unwrap().join("native-window.json");
    let Some(w) = app.get_webview_window("main") else {
        return;
    };
    let monitors = areas(&w);
    let primary = w.primary_monitor().ok().flatten();
    let a = primary
        .as_ref()
        .map(|m| {
            let a = m.work_area();
            WorkArea {
                x: a.position.x as f64,
                y: a.position.y as f64,
                width: a.size.width as f64,
                height: a.size.height as f64,
                scale: m.scale_factor(),
            }
        })
        .unwrap_or(WorkArea {
            x: 0.,
            y: 0.,
            width: 1920.,
            height: 1080.,
            scale: 1.,
        });
    let mut g = Geometry::default();
    g.screen_x = a.x + a.width - 224. * a.scale;
    g.screen_y = a.y + a.height - 224. * a.scale;
    if let Ok(bytes) = fs::read(&path) {
        if let Ok(p) = serde_json::from_slice::<Preferences>(&bytes) {
            if p.version == 2
                && p.anchor_screen_x.is_finite()
                && p.anchor_screen_y.is_finite()
                && monitors
                    .iter()
                    .any(|m| m.distance(p.anchor_screen_x, p.anchor_screen_y) == 0.)
            {
                g.screen_x = p.anchor_screen_x;
                g.screen_y = p.anchor_screen_y;
                let _ = w.set_always_on_top(p.always_on_top);
            }
        } else {
            let backup = path.with_file_name("native-window.before-resident-v2.json");
            if !backup.exists() {
                let _ = fs::copy(&path, backup);
            }
        }
    }
    *state.resident.lock().unwrap() = g;
    let _ = w.set_background_color(Some(tauri::window::Color(0, 0, 0, 0)));
    let _ = w.set_shadow(false);
    let _ = w.set_skip_taskbar(true);
    let _ = w.unmaximize();
    let _ = w.set_maximizable(false);
    let _ = w.hide();
    let _ = apply(app, true);
}
#[cfg(windows)]
pub fn follow_cursor(app: &AppHandle, x: f64, y: f64) {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetAsyncKeyState, VK_LBUTTON};
    let state = app.state::<HostState>();
    if !state.follow.load(Ordering::Relaxed) || unsafe { GetAsyncKeyState(VK_LBUTTON as i32) } < 0 {
        return;
    }
    let mut g = state.resident.lock().unwrap().clone();
    if !g.ready || (!STABLE_SURFACE.load(Ordering::Relaxed) && (g.width > 520. || g.height > 560.)) {
        return;
    }
    let Some(w) = app.get_webview_window("main") else {
        return;
    };
    let a = nearest(&w, x, y);
    let tx = x + 100. * a.scale;
    let ty = y - 50. * a.scale;
    if (g.screen_x - tx).hypot(g.screen_y - ty) < 18. * a.scale {
        return;
    }
    g.screen_x += (tx - g.screen_x) * 0.22;
    g.screen_y += (ty - g.screen_y) * 0.22;
    *state.resident.lock().unwrap() = g;
    let _ = apply(app, false);
    if STABLE_SURFACE.load(Ordering::Relaxed) {
        let _ = w.emit("axx-desktop-layout", status(app));
    }
}
pub fn install_tray(app: &AppHandle) -> tauri::Result<()> {
    use tauri::{
        menu::{Menu, MenuItem, PredefinedMenuItem},
        tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    };
    let show = MenuItem::with_id(app, "resident-show", "Mostrar Axx", true, None::<&str>)?;
    let hide = MenuItem::with_id(app, "resident-hide", "Ocultar Axx", true, None::<&str>)?;
    let home = MenuItem::with_id(app, "resident-home", "Volver a la base", true, None::<&str>)?;
    let settings = MenuItem::with_id(app, "resident-settings", "Ajustes", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "resident-quit", "Salir de Axx", true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let menu = Menu::with_items(app, &[&show, &hide, &home, &settings, &separator, &quit])?;
    let mut builder = TrayIconBuilder::with_id("axx-resident")
        .tooltip("Axx · asistente residente")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, e| match e.id.as_ref() {
            "resident-show" => {
                let _ = summon(app, false);
            }
            "resident-hide" => {
                if let Some(w) = app.get_webview_window("main") {
                    app.state::<HostState>()
                        .follow
                        .store(false, Ordering::Relaxed);
                    let _ = w.hide();
                }
            }
            "resident-home" => {
                let _ = go_home(app);
            }
            "resident-settings" => {
                let _ = show_passive(app);
                if let Some(w) = app.get_webview_window("main") {
                    let _ = w.emit("axx-settings", ());
                }
            }
            "resident-quit" => {
                app.state::<HostState>()
                    .quitting
                    .store(true, Ordering::Relaxed);
                persist(app);
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, e| {
            if matches!(
                e,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                }
            ) {
                let _ = summon(tray.app_handle(), false);
            }
        });
    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }
    builder.build(app)?;
    Ok(())
}
#[cfg(windows)]
pub fn move_to_foreground_desktop(app: &AppHandle) {
    use windows::Win32::{
        Foundation::HWND,
        System::Com::{
            CLSCTX_ALL, COINIT_APARTMENTTHREADED, CoCreateInstance, CoInitializeEx, CoUninitialize,
        },
        UI::Shell::{IVirtualDesktopManager, VirtualDesktopManager},
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::GetForegroundWindow;
    let Some(w) = app.get_webview_window("main") else {
        return;
    };
    let Ok(own) = w.hwnd() else {
        return;
    };
    let foreground = unsafe { GetForegroundWindow() };
    if foreground.is_null() || foreground == own.0 as _ {
        return;
    }
    let initialized = unsafe { CoInitializeEx(None, COINIT_APARTMENTTHREADED) }.is_ok();
    let result = (|| -> windows::core::Result<()> {
        let manager: IVirtualDesktopManager =
            unsafe { CoCreateInstance(&VirtualDesktopManager, None, CLSCTX_ALL) }?;
        let desktop = unsafe { manager.GetWindowDesktopId(HWND(foreground)) }?;
        unsafe { manager.MoveWindowToDesktop(HWND(own.0 as _), &desktop) }?;
        Ok(())
    })();
    if initialized {
        unsafe {
            CoUninitialize();
        }
    }
    *app.state::<HostState>().desktop_error.lock().unwrap()=result.err().map(|e|format!("Windows could not move Axx to the foreground application's desktop: {e}. Permanent all-desktop pinning is not implemented."));
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn expanding_to_left_preserves_global_avatar_anchor() {
        let g = Geometry {
            screen_x: 1100.,
            screen_y: 650.,
            width: 700.,
            height: 400.,
            anchor_x: 500.,
            anchor_y: 200.,
            ready: true,
        };
        let a = WorkArea {
            x: 0.,
            y: 0.,
            width: 1920.,
            height: 1080.,
            scale: 1.,
        };
        let (x, y) = constrained_origin(&g, a);
        assert_eq!(x + g.anchor_x, 1100.);
        assert_eq!(y + g.anchor_y, 650.);
    }
    #[test]
    fn negative_dpi_monitor_clamps_content_inside_workarea() {
        let g = Geometry {
            screen_x: -1700.,
            screen_y: 300.,
            width: 500.,
            height: 400.,
            anchor_x: 200.,
            anchor_y: 200.,
            ready: true,
        };
        let a = WorkArea {
            x: -1920.,
            y: -100.,
            width: 1920.,
            height: 1080.,
            scale: 1.5,
        };
        let (x, y) = constrained_origin(&g, a);
        assert!(x >= a.x);
        assert!(x + 750. <= 0.);
        assert!(y >= -100.);
        assert!(y + 600. <= 980.);
    }
    #[test]
    fn legacy_rectangle_preferences_are_not_resident_v2() {
        let legacy = br#"{"x":20,"y":20,"width":1440,"height":960,"always_on_top":true}"#;
        assert!(serde_json::from_slice::<Preferences>(legacy).is_err());
    }
    #[test]
    fn active_panel_drag_state_toggle() {
        set_panel_drag(false);
        assert!(!is_panel_drag_active());
        set_panel_drag(true);
        assert!(is_panel_drag_active());
        set_panel_drag(false);
        assert!(!is_panel_drag_active());
    }
}
