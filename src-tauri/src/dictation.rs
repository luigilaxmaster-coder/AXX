//! Deliberate dictation authority, independent of command/Computer Use permissions.
use serde::Deserialize;
use serde_json::{Value, json};
use std::sync::atomic::{AtomicU64, Ordering};

pub static CANCEL: AtomicU64 = AtomicU64::new(0);
pub fn cancel() {
    CANCEL.fetch_add(1, Ordering::SeqCst);
}

#[derive(Deserialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
pub enum Request {
    Start {},
    Stop {},
    Probe {
        session: String,
    },
    Commit {
        session: String,
        target: String,
        sequence: u64,
        text: String,
    },
}

fn valid_text(text: &str) -> bool {
    !text.trim().is_empty() && text.len() <= 8000 && !text.chars().any(char::is_control)
}

fn confirmed(before: &str, after: &str, text: &str) -> bool {
    if after.len() != before.len() + text.len() {
        return false;
    }
    let mut split = before
        .bytes()
        .zip(after.bytes())
        .take_while(|(a, b)| a == b)
        .count();
    while !before.is_char_boundary(split) {
        split -= 1;
    }
    after.get(split..split + text.len()) == Some(text)
        && after.get(split + text.len()..) == Some(&before[split..])
}

#[tauri::command]
pub async fn dictation_control(request: Request) -> Result<Value, String> {
    if matches!(request, Request::Stop {}) {
        cancel();
        return Ok(json!({"state":"OFF"}));
    }
    #[cfg(windows)]
    {
        tauri::async_runtime::spawn_blocking(move || native::send(request))
            .await
            .map_err(|_| "Dictation worker failed".to_string())?
    }
    #[cfg(not(windows))]
    {
        let _ = request;
        Err("Windows UI Automation required".into())
    }
}

#[cfg(windows)]
mod native {
    use super::*;
    use std::{
        sync::{Arc, OnceLock, mpsc},
        time::{Duration, Instant},
    };
    use windows::{
        Win32::{
            Foundation::{CloseHandle, FILETIME, HANDLE},
            Security::{GetTokenInformation, TOKEN_ELEVATION, TOKEN_QUERY, TokenElevation},
            System::{
                Com::{
                    CLSCTX_INPROC_SERVER, COINIT_MULTITHREADED, CoCreateInstance, CoInitializeEx,
                },
                StationsAndDesktops::{
                    CloseDesktop, DESKTOP_CONTROL_FLAGS, DESKTOP_READOBJECTS,
                    GetUserObjectInformationW, OpenInputDesktop, UOI_NAME,
                },
                Threading::{
                    GetProcessTimes, OpenProcess, OpenProcessToken, PROCESS_NAME_WIN32,
                    PROCESS_QUERY_LIMITED_INFORMATION, QueryFullProcessImageNameW,
                },
            },
            UI::{
                Accessibility::*,
                Input::KeyboardAndMouse::*,
                WindowsAndMessaging::{GetForegroundWindow, GetWindowThreadProcessId},
            },
        },
        core::{Ref, implement},
    };

    #[implement(IUIAutomationFocusChangedEventHandler)]
    struct FocusChanged(Arc<AtomicU64>);
    impl IUIAutomationFocusChangedEventHandler_Impl for FocusChanged_Impl {
        fn HandleFocusChangedEvent(
            &self,
            _: Ref<'_, IUIAutomationElement>,
        ) -> windows::core::Result<()> {
            self.0.fetch_add(1, Ordering::SeqCst);
            Ok(())
        }
    }
    struct Target {
        element: IUIAutomationElement,
        hwnd: isize,
        pid: u32,
        started: u64,
        epoch: u64,
        token: String,
    }
    struct Session {
        id: String,
        generation: u64,
        sequence: u64,
        last_status: &'static str,
        target: Option<Target>,
        heartbeat: Instant,
    }
    type Reply = mpsc::SyncSender<Result<Value, String>>;
    static WORKER: OnceLock<mpsc::SyncSender<(Request, Reply)>> = OnceLock::new();

    pub fn send(request: Request) -> Result<Value, String> {
        let worker = WORKER.get_or_init(|| {
            let (tx, rx) = mpsc::sync_channel(4);
            std::thread::spawn(move || run(rx));
            tx
        });
        let (tx, rx) = mpsc::sync_channel(1);
        worker
            .try_send((request, tx))
            .map_err(|_| "Dictation worker busy or unavailable")?;
        rx.recv_timeout(Duration::from_secs(3)).map_err(|_| {
            cancel();
            "UI Automation timed out; dictation cancelled".to_string()
        })?
    }

    fn desktop_available() -> bool {
        unsafe {
            let Ok(desktop) =
                OpenInputDesktop(DESKTOP_CONTROL_FLAGS(0), false, DESKTOP_READOBJECTS)
            else {
                return false;
            };
            let mut name = [0u16; 128];
            let result = GetUserObjectInformationW(
                HANDLE(desktop.0),
                UOI_NAME,
                Some(name.as_mut_ptr().cast()),
                256,
                None,
            );
            let _ = CloseDesktop(desktop);
            result.is_ok()
                && String::from_utf16_lossy(
                    &name[..name.iter().position(|&x| x == 0).unwrap_or(128)],
                )
                .eq_ignore_ascii_case("default")
        }
    }

    fn process_identity(pid: u32) -> Result<u64, String> {
        unsafe {
            let process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid)
                .map_err(|_| "Process inaccessible")?;
            let result = (|| {
                let mut token = HANDLE::default();
                OpenProcessToken(process, TOKEN_QUERY, &mut token)
                    .map_err(|_| "Process token unavailable")?;
                let mut elevation = TOKEN_ELEVATION::default();
                let mut returned = 0;
                let check = GetTokenInformation(
                    token,
                    TokenElevation,
                    Some((&mut elevation as *mut TOKEN_ELEVATION).cast()),
                    std::mem::size_of::<TOKEN_ELEVATION>() as u32,
                    &mut returned,
                );
                let _ = CloseHandle(token);
                if check.is_err() || elevation.TokenIsElevated != 0 {
                    return Err("Elevated process blocked".into());
                }
                let mut path = [0u16; 2048];
                let mut length = path.len() as u32;
                QueryFullProcessImageNameW(
                    process,
                    PROCESS_NAME_WIN32,
                    windows::core::PWSTR(path.as_mut_ptr()),
                    &mut length,
                )
                .map_err(|_| "Process name unavailable")?;
                let path = String::from_utf16_lossy(&path[..length as usize]).to_lowercase();
                if [
                    "cmd.exe",
                    "powershell.exe",
                    "pwsh.exe",
                    "windowsterminal.exe",
                    "conhost.exe",
                    "wsl.exe",
                    "bash.exe",
                ]
                .iter()
                .any(|exe| path.ends_with(&format!("\\{exe}")))
                {
                    return Err("Terminal blocked".into());
                }
                let (mut created, mut exit, mut kernel, mut user) = (
                    FILETIME::default(),
                    FILETIME::default(),
                    FILETIME::default(),
                    FILETIME::default(),
                );
                GetProcessTimes(process, &mut created, &mut exit, &mut kernel, &mut user)
                    .map_err(|_| "Process identity unavailable")?;
                Ok(((created.dwHighDateTime as u64) << 32) | created.dwLowDateTime as u64)
            })();
            let _ = CloseHandle(process);
            result
        }
    }

    fn observe(uia: &IUIAutomation, epoch: u64) -> Result<Target, String> {
        unsafe {
            if !desktop_available() {
                return Err("Windows locked or secure desktop".into());
            }
            let hwnd = GetForegroundWindow();
            if hwnd.0.is_null() {
                return Err("No foreground window".into());
            }
            let mut pid = 0;
            GetWindowThreadProcessId(hwnd, Some(&mut pid));
            let started = process_identity(pid)?;
            let element = uia.GetFocusedElement().map_err(|_| "No UIA focus")?;
            let properties = (|| -> windows::core::Result<bool> {
                Ok(element.CurrentProcessId()? as u32 == pid
                    && element.CurrentIsEnabled()?.as_bool()
                    && !element.CurrentIsPassword()?.as_bool()
                    && !element.CurrentIsOffscreen()?.as_bool()
                    && element.CurrentHasKeyboardFocus()?.as_bool())
            })()
            .unwrap_or(false);
            if !properties {
                return Err("Protected or inactive field".into());
            }
            // Fail closed: selection alone is not proof that a Document is editable.
            let value: IUIAutomationValuePattern = element
                .GetCurrentPatternAs(UIA_ValuePatternId)
                .map_err(|_| "Editable ValuePattern unavailable")?;
            if value.CurrentIsReadOnly().map_or(true, |v| v.as_bool()) {
                return Err("Readonly field".into());
            }
            Ok(Target {
                element,
                hwnd: hwnd.0 as isize,
                pid,
                started,
                epoch,
                token: uuid::Uuid::new_v4().to_string(),
            })
        }
    }

    fn same(uia: &IUIAutomation, a: &Target, b: &Target) -> bool {
        a.hwnd == b.hwnd
            && a.pid == b.pid
            && a.started == b.started
            && a.epoch == b.epoch
            && unsafe {
                uia.CompareElements(&a.element, &b.element)
                    .is_ok_and(|v| v.as_bool())
            }
    }
    fn read(target: &Target) -> Option<String> {
        unsafe {
            let value: IUIAutomationValuePattern = target
                .element
                .GetCurrentPatternAs(UIA_ValuePatternId)
                .ok()?;
            let text = value.CurrentValue().ok()?.to_string();
            (text.len() <= 32768).then_some(text)
        }
    }
    fn insert(
        uia: &IUIAutomation,
        target: &Target,
        text: &str,
        epoch: &AtomicU64,
        generation: u64,
    ) -> &'static str {
        let before = read(target);
        let Ok(current) = observe(uia, epoch.load(Ordering::SeqCst)) else {
            return "blocked";
        };
        if !same(uia, target, &current) || generation != CANCEL.load(Ordering::SeqCst) {
            return "pending";
        }
        let released_by = Instant::now() + Duration::from_millis(300);
        while [VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN]
            .iter()
            .any(|key| unsafe { GetAsyncKeyState(key.0 as i32) } < 0)
        {
            if Instant::now() >= released_by || generation != CANCEL.load(Ordering::SeqCst) {
                return "pending";
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        let Ok(current) = observe(uia, epoch.load(Ordering::SeqCst)) else {
            return "blocked";
        };
        if !same(uia, target, &current) {
            return "pending";
        }
        let mut inputs = Vec::with_capacity(text.encode_utf16().count() * 2);
        for unit in text.encode_utf16() {
            for flags in [KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP] {
                inputs.push(INPUT {
                    r#type: INPUT_KEYBOARD,
                    Anonymous: INPUT_0 {
                        ki: KEYBDINPUT {
                            wScan: unit,
                            dwFlags: flags,
                            ..Default::default()
                        },
                    },
                });
            }
        }
        // Never synthesize Enter, shortcuts, foreground changes, or clipboard writes.
        if epoch.load(Ordering::SeqCst) != target.epoch
            || generation != CANCEL.load(Ordering::SeqCst)
            || unsafe { GetForegroundWindow() }.0 as isize != target.hwnd
        {
            return "pending";
        }
        let sent = unsafe { SendInput(&inputs, std::mem::size_of::<INPUT>() as i32) };
        if sent != inputs.len() as u32 {
            return "uncertain";
        }
        std::thread::sleep(Duration::from_millis(60));
        let Ok(after_target) = observe(uia, epoch.load(Ordering::SeqCst)) else {
            return "uncertain";
        };
        if !same(uia, target, &after_target) {
            return "uncertain";
        }
        match (before, read(&after_target)) {
            (Some(before), Some(after)) if confirmed(&before, &after, text) => "inserted",
            _ => "uncertain",
        }
    }

    fn run(rx: mpsc::Receiver<(Request, Reply)>) {
        unsafe {
            if CoInitializeEx(None, COINIT_MULTITHREADED).is_err() {
                return;
            }
            let Ok(uia): Result<IUIAutomation, _> =
                CoCreateInstance(&CUIAutomation, None, CLSCTX_INPROC_SERVER)
            else {
                return;
            };
            let epoch = Arc::new(AtomicU64::new(0));
            let handler: IUIAutomationFocusChangedEventHandler = FocusChanged(epoch.clone()).into();
            if uia.AddFocusChangedEventHandler(None, &handler).is_err() {
                return;
            }
            let mut active: Option<Session> = None;
            loop {
                if active.as_ref().is_some_and(|s| {
                    s.generation != CANCEL.load(Ordering::SeqCst)
                        || s.heartbeat.elapsed() > Duration::from_secs(3)
                        || !desktop_available()
                }) {
                    active = None;
                    cancel();
                }
                let (request, reply) = match rx.recv_timeout(Duration::from_millis(100)) {
                    Ok(value) => value,
                    Err(mpsc::RecvTimeoutError::Timeout) => continue,
                    Err(_) => break,
                };
                if reply
                    .send(handle(&uia, &epoch, &mut active, request))
                    .is_err()
                {
                    active = None;
                    cancel();
                }
            }
            let _ = uia.RemoveFocusChangedEventHandler(&handler);
        }
    }
    fn handle(
        uia: &IUIAutomation,
        epoch: &AtomicU64,
        active: &mut Option<Session>,
        request: Request,
    ) -> Result<Value, String> {
        if matches!(request, Request::Start {}) {
            cancel();
            let id = uuid::Uuid::new_v4().to_string();
            *active = Some(Session {
                id: id.clone(),
                generation: CANCEL.load(Ordering::SeqCst),
                sequence: 0,
                last_status: "blocked",
                target: None,
                heartbeat: Instant::now(),
            });
            return Ok(json!({"session":id,"state":"ARMED","api_version":1}));
        }
        let session = active.as_mut().ok_or("Dictation is OFF")?;
        if session.generation != CANCEL.load(Ordering::SeqCst) {
            return Err("Dictation cancelled".into());
        }
        match request {
            Request::Probe { session: id } if id == session.id => {
                session.heartbeat = Instant::now();
                match observe(uia, epoch.load(Ordering::SeqCst)) {
                    Ok(mut target) => {
                        if let Some(previous) =
                            session.target.as_ref().filter(|p| same(uia, p, &target))
                        {
                            target.token = previous.token.clone();
                        }
                        let token = target.token.clone();
                        let hwnd = target.hwnd;
                        let pid = target.pid;
                        session.target = Some(target);
                        Ok(json!({"editable":true,"target":token,"hwnd":hwnd,"process_id":pid}))
                    }
                    Err(reason) => {
                        session.target = None;
                        Ok(json!({"editable":false,"reason":reason}))
                    }
                }
            }
            Request::Commit {
                session: id,
                target,
                sequence,
                text,
            } if id == session.id => {
                if sequence == 0 || sequence > 100000 || !valid_text(&text) {
                    return Err("Invalid bounded final segment".into());
                }
                if sequence <= session.sequence {
                    return Ok(
                        json!({"status":if sequence == session.sequence {session.last_status} else {"blocked"},"duplicate":true}),
                    );
                }
                // Consume before sending input: ambiguous effects are never retried.
                session.sequence = sequence;
                session.last_status = match session.target.as_ref().filter(|t| t.token == target) {
                    Some(destination) => insert(uia, destination, &text, epoch, session.generation),
                    None => "pending",
                };
                Ok(json!({"status":session.last_status,"sequence":sequence}))
            }
            _ => Err("Invalid dictation session".into()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn forbids_submit_keys_and_unbounded_segments() {
        for text in ["\n", "hola\r\n", "hola\t", "\u{0}", " "] {
            assert!(!valid_text(text));
        }
        assert!(!valid_text(&"a".repeat(8001)));
        assert!(valid_text("123,45 mg · AXX 🐙"));
    }
    #[test]
    fn requires_exact_readback_without_overwriting_manual_edits() {
        assert!(confirmed("hola mundo", "hola voz mundo", "voz "));
        assert!(confirmed("a", "aa", "a"));
        assert!(confirmed("é", "é 🐙", " 🐙"));
        assert!(!confirmed("manual", "dictado", "dictado"));
    }
    #[test]
    fn rejects_authority_and_unknown_fields() {
        assert!(
            serde_json::from_value::<Request>(json!({"action":"start","approved":true})).is_err()
        );
        assert!(
            serde_json::from_value::<Request>(
                json!({"action":"commit","session":"s","target":"t","sequence":-1,"text":"a"})
            )
            .is_err()
        );
    }

    #[cfg(windows)]
    #[test]
    #[ignore = "Opens an isolated synthetic Win32 Edit fixture; run explicitly on the interactive desktop"]
    fn native_edit_fixture_focus_password_readonly_duplicate_and_cancel() {
        use std::{sync::mpsc, time::Duration};
        use windows_sys::Win32::{
            System::Threading::GetCurrentThreadId, UI::Input::KeyboardAndMouse::SetFocus,
            UI::WindowsAndMessaging::*,
        };
        fn wide(s: &str) -> Vec<u16> {
            s.encode_utf16().chain(Some(0)).collect()
        }
        unsafe extern "system" fn fixture_proc(
            hwnd: windows_sys::Win32::Foundation::HWND,
            msg: u32,
            wp: usize,
            lp: isize,
        ) -> isize {
            if msg == WM_SETFOCUS || msg == WM_ACTIVATE && wp as u16 != WA_INACTIVE as u16 {
                let child = unsafe { GetWindowLongPtrW(hwnd, GWLP_USERDATA) }
                    as windows_sys::Win32::Foundation::HWND;
                if !child.is_null() {
                    unsafe {
                        SetFocus(child);
                    }
                }
                return 0;
            }
            unsafe { DefWindowProcW(hwnd, msg, wp, lp) }
        }
        let (tx, rx) = mpsc::sync_channel(1);
        let fixture = std::thread::spawn(move || unsafe {
            let previous = GetForegroundWindow();
            let name = wide("AxxDictationNativeFixture");
            let instance =
                windows_sys::Win32::System::LibraryLoader::GetModuleHandleW(std::ptr::null());
            let class = WNDCLASSW {
                lpfnWndProc: Some(fixture_proc),
                hInstance: instance,
                lpszClassName: name.as_ptr(),
                ..std::mem::zeroed()
            };
            assert_ne!(RegisterClassW(&class), 0);
            let root = CreateWindowExW(
                0,
                name.as_ptr(),
                wide("AXX · isolated dictation test").as_ptr(),
                WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                100,
                100,
                600,
                400,
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                instance,
                std::ptr::null(),
            );
            assert!(!root.is_null());
            let controls: Vec<_> = [0, 0, 0x20, 0x800]
                .iter()
                .enumerate()
                .map(|(i, extra)| {
                    CreateWindowExW(
                        0,
                        wide("EDIT").as_ptr(),
                        wide("").as_ptr(),
                        WS_CHILD | WS_VISIBLE | WS_TABSTOP | *extra,
                        20,
                        20 + i as i32 * 60,
                        500,
                        45,
                        root,
                        std::ptr::null_mut(),
                        std::ptr::null_mut(),
                        std::ptr::null(),
                    )
                })
                .collect();
            SetWindowLongPtrW(root, GWLP_USERDATA, controls[0] as isize);
            SetForegroundWindow(root);
            SetFocus(controls[0]);
            tx.send((
                GetCurrentThreadId(),
                root as isize,
                controls.iter().map(|h| *h as isize).collect::<Vec<_>>(),
            ))
            .unwrap();
            let mut message: MSG = std::mem::zeroed();
            while GetMessageW(&mut message, std::ptr::null_mut(), 0, 0) > 0 {
                if message.message == WM_APP {
                    SetWindowLongPtrW(root, GWLP_USERDATA, controls[message.wParam] as isize);
                    SetForegroundWindow(root);
                    SetFocus(controls[message.wParam]);
                } else {
                    TranslateMessage(&message);
                    DispatchMessageW(&message);
                }
            }
            DestroyWindow(root);
            if !previous.is_null() {
                SetForegroundWindow(previous);
            }
        });
        let (thread, root, controls) = rx.recv_timeout(Duration::from_secs(5)).unwrap();
        struct Cleanup(u32);
        impl Drop for Cleanup {
            fn drop(&mut self) {
                unsafe {
                    PostThreadMessageW(self.0, WM_QUIT, 0, 0);
                }
            }
        }
        let cleanup = Cleanup(thread);
        eprintln!("Waiting for foreground: AXX · isolated dictation test");
        for _ in 0..300 {
            if unsafe { GetForegroundWindow() } as isize == root {
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        assert_eq!(
            unsafe { GetForegroundWindow() } as isize,
            root,
            "Windows did not grant foreground to the isolated fixture"
        );
        unsafe {
            PostThreadMessageW(thread, WM_APP, 0, 0);
        }
        std::thread::sleep(Duration::from_millis(500));
        let started = native::send(Request::Start {}).unwrap();
        let session = started["session"].as_str().unwrap().to_string();
        let probe = || {
            native::send(Request::Probe {
                session: session.clone(),
            })
            .unwrap()
        };
        let mut focus = probe();
        for _ in 0..10 {
            if focus["editable"] == true {
                break;
            }
            unsafe {
                PostThreadMessageW(thread, WM_APP, 0, 0);
            }
            std::thread::sleep(Duration::from_millis(100));
            focus = probe();
        }
        assert_eq!(focus["editable"], true, "{focus}");
        assert_eq!(
            focus["hwnd"], root,
            "The native fixture must never target another window"
        );
        assert_eq!(focus["process_id"], std::process::id());
        let target = focus["target"].as_str().unwrap().to_string();
        let commit = |sequence, target: String| {
            native::send(Request::Commit {
                session: session.clone(),
                target,
                sequence,
                text: "AXX 123,45 mg ".into(),
            })
            .unwrap()
        };
        let result = commit(1, target.clone());
        assert_eq!(result["status"], "inserted", "{result}");
        assert_eq!(commit(1, target.clone())["duplicate"], true);
        let mut text = [0u16; 128];
        let count = unsafe { GetWindowTextW(controls[0] as _, text.as_mut_ptr(), 128) };
        assert_eq!(
            String::from_utf16_lossy(&text[..count as usize]),
            "AXX 123,45 mg "
        );
        unsafe {
            PostThreadMessageW(thread, WM_APP, 1, 0);
        }
        std::thread::sleep(Duration::from_millis(200));
        assert_eq!(commit(2, target)["status"], "pending");
        for index in [2, 3] {
            unsafe {
                PostThreadMessageW(thread, WM_APP, index, 0);
            }
            std::thread::sleep(Duration::from_millis(200));
            assert_eq!(probe()["editable"], false);
        }
        cancel();
        assert!(native::send(Request::Probe { session }).is_err());
        drop(cleanup);
        fixture.join().unwrap();
    }
}
