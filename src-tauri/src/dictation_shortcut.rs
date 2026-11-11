use serde::{Deserialize, Serialize};
use std::sync::{
    Mutex,
    atomic::{AtomicBool, AtomicU32, Ordering},
    mpsc,
};
use tauri::{AppHandle, Emitter};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Shortcut {
    key: u32,
    modifiers: u32,
    activation: String,
}
impl Default for Shortcut {
    fn default() -> Self {
        Self {
            key: 0x44,
            modifiers: 7,
            activation: "toggle".into(),
        }
    }
}
impl Shortcut {
    fn valid(&self) -> bool {
        if self.key == 0 && self.modifiers == 0 && self.activation == "disabled" {
            return true;
        }
        (0x41..=0x5a).contains(&self.key)
            && self.modifiers & !7 == 0
            && self.modifiers.count_ones() >= 2
            && ["toggle", "hold"].contains(&self.activation.as_str())
            && !(self.modifiers == 7 && self.key == 0x56)
            && !(self.modifiers == 5 && [0x41, 0x56].contains(&self.key))
    }
}
static THREAD: AtomicU32 = AtomicU32::new(0);
static HOLD_KEY: AtomicU32 = AtomicU32::new(0);
static REGISTERED: AtomicBool = AtomicBool::new(false);
static CURRENT: Mutex<Option<(Shortcut, i32)>> = Mutex::new(None);
type Reply = mpsc::SyncSender<Result<Shortcut, String>>;
static PENDING: Mutex<Option<(Shortcut, Reply)>> = Mutex::new(None);

#[tauri::command]
pub async fn dictation_shortcut(shortcut: Option<Shortcut>) -> Result<serde_json::Value, String> {
    let Some(shortcut) = shortcut else {
        let current = CURRENT.lock().map_err(|_| "Shortcut unavailable")?;
        return Ok(
            serde_json::json!({"shortcut":current.as_ref().map(|(s,_)|s.clone()).unwrap_or_default(),"registered":REGISTERED.load(Ordering::Acquire)}),
        );
    };
    if !shortcut.valid() {
        return Err(
            "Use at least two modifiers and A–Z; existing Axx/Android shortcuts are reserved"
                .into(),
        );
    }
    #[cfg(windows)]
    {
        tauri::async_runtime::spawn_blocking(move || {
            use windows_sys::Win32::UI::WindowsAndMessaging::{PostThreadMessageW, WM_APP};
            let (tx, rx) = mpsc::sync_channel(1);
            {
                let mut pending = PENDING.lock().map_err(|_| "Shortcut unavailable")?;
                if pending.is_some() {
                    return Err("Shortcut update busy".into());
                }
                *pending = Some((shortcut, tx));
            }
            if unsafe { PostThreadMessageW(THREAD.load(Ordering::Acquire), WM_APP + 44, 0, 0) } == 0
            {
                PENDING.lock().unwrap().take();
                return Err("Shortcut thread unavailable".into());
            }
            let applied = rx
                .recv_timeout(std::time::Duration::from_secs(2))
                .map_err(|_| "Shortcut update timed out")??;
                Ok(serde_json::json!({"shortcut":applied,"registered":REGISTERED.load(Ordering::Acquire)}))
        })
        .await
        .map_err(|_| "Shortcut worker failed".to_string())?
    }
    #[cfg(not(windows))]
    {
        Err("Windows required".into())
    }
}

#[cfg(windows)]
pub fn initialize() {
    use windows_sys::Win32::System::Threading::GetCurrentThreadId;
    THREAD.store(unsafe { GetCurrentThreadId() }, Ordering::Release);
    let shortcut = Shortcut::default();
    // Renderer checks its existing command chord before registering a new one.
    REGISTERED.store(false, Ordering::Release);
    *CURRENT.lock().unwrap() = Some((shortcut, 1004));
}

#[cfg(windows)]
pub fn message(app: &AppHandle, message: &windows_sys::Win32::UI::WindowsAndMessaging::MSG) {
    use windows_sys::Win32::UI::{Input::KeyboardAndMouse::*, WindowsAndMessaging::*};
    if message.message == WM_APP + 44 {
        if let Some((shortcut, reply)) = PENDING.lock().unwrap().take() {
            let mut current = CURRENT.lock().unwrap();
            if shortcut.activation == "disabled" {
                if let Some((_, id)) = current.as_ref() {
                    unsafe {
                        UnregisterHotKey(std::ptr::null_mut(), *id);
                    }
                }
                REGISTERED.store(false, Ordering::Release);
                HOLD_KEY.store(0, Ordering::Release);
                *current = Some((shortcut.clone(), 1004));
                let _ = reply.send(Ok(shortcut));
                return;
            }
            if REGISTERED.load(Ordering::Acquire)
                && current.as_ref().is_some_and(|(s, _)| {
                    s.key == shortcut.key && s.modifiers == shortcut.modifiers
                })
            {
                HOLD_KEY.store(
                    if shortcut.activation == "hold" {
                        shortcut.key
                    } else {
                        0
                    },
                    Ordering::Release,
                );
                current.as_mut().unwrap().0 = shortcut.clone();
                let _ = reply.send(Ok(shortcut));
                return;
            }
            let previous = current.as_ref().map_or(1004, |(_, id)| *id);
            let next = if previous == 1004 { 1005 } else { 1004 };
            if unsafe {
                RegisterHotKey(
                    std::ptr::null_mut(),
                    next,
                    shortcut.modifiers | MOD_NOREPEAT,
                    shortcut.key,
                )
            } == 0
            {
                let _ = reply.send(Err("Shortcut occupied; previous shortcut preserved".into()));
            } else {
                unsafe {
                    UnregisterHotKey(std::ptr::null_mut(), previous);
                }
                HOLD_KEY.store(
                    if shortcut.activation == "hold" {
                        shortcut.key
                    } else {
                        0
                    },
                    Ordering::Release,
                );
                REGISTERED.store(true, Ordering::Release);
                *current = Some((shortcut.clone(), next));
                let _ = reply.send(Ok(shortcut));
            }
        }
    }
    if message.message == WM_HOTKEY
        && REGISTERED.load(Ordering::Acquire)
        && [1004, 1005].contains(&message.wParam)
    {
        let hold = HOLD_KEY.load(Ordering::Acquire);
        if hold == 0 {
            let _ = app.emit("axx-dictation-toggle", ());
        } else if unsafe { GetAsyncKeyState(hold as i32) } < 0 {
            let _ = app.emit("axx-dictation-hold-start", ());
        }
    }
}

pub fn released(app: &AppHandle, key: u32) {
    if key == HOLD_KEY.load(Ordering::Acquire) {
        let _ = app.emit("axx-dictation-hold-end", ());
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn reserves_existing_shortcuts_and_requires_deliberate_chords() {
        assert!(Shortcut::default().valid());
        for (key, modifiers) in [(0x56, 7), (0x41, 5), (0x44, 2), (0x20, 3), (0x44, 15)] {
            assert!(
                !Shortcut {
                    key,
                    modifiers,
                    activation: "toggle".into()
                }
                .valid()
            );
        }
    }
}
