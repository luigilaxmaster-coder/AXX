//! Local Windows media transport and output metering. No microphone or audio capture.
use serde_json::{Value, json};
use std::sync::{Arc, Mutex, OnceLock, mpsc};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

struct Request {
    id: String,
    command: String,
    value: Option<f64>,
    expires: Instant,
    reply: mpsc::Sender<Result<bool, String>>,
}
struct Service {
    state: Arc<Mutex<Value>>,
    commands: mpsc::SyncSender<Request>,
}
static SERVICE: OnceLock<Service> = OnceLock::new();
fn now() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}
fn service() -> &'static Service {
    SERVICE.get_or_init(|| {
        let state = Arc::new(Mutex::new(
            json!({"available":false,"audioAvailable":false,"peak":0,"sessions":[],"updatedAt":0}),
        ));
        let (commands, rx) = mpsc::sync_channel(4);
        let shared = state.clone();
        std::thread::spawn(move || {
            #[cfg(windows)]
            if let Err(e) = native::run(shared.clone(), rx) {
                shared.lock().unwrap()["error"] = json!(e.to_string());
            }
            #[cfg(not(windows))]
            {
                let _ = rx;
                shared.lock().unwrap()["error"] = json!("Disponible en Windows");
            }
        });
        Service { state, commands }
    })
}
#[tauri::command]
pub fn system_media_status() -> Value {
    service().state.lock().unwrap().clone()
}

pub fn control(id: String, command: String, value: Option<f64>) -> Result<bool, String> {
    if id.is_empty() || !["play", "pause", "next", "previous", "seek"].contains(&command.as_str()) {
        return Err("Control multimedia no válido".into());
    }
    if command == "seek" && !value.is_some_and(|v| v.is_finite() && (0.0..=604800.0).contains(&v)) {
        return Err("Posición no válida".into());
    }
    let (reply, rx) = mpsc::channel();
    service()
        .commands
        .try_send(Request {
            id,
            command,
            value,
            expires: Instant::now() + Duration::from_secs(3),
            reply,
        })
        .map_err(|_| "El reproductor está ocupado")?;
    rx.recv_timeout(Duration::from_secs(5))
        .map_err(|_| "El reproductor no respondió")?
}
#[tauri::command]
pub async fn system_media_control(
    id: String,
    command: String,
    value: Option<f64>,
) -> Result<bool, String> {
    tauri::async_runtime::spawn_blocking(move || control(id, command, value))
        .await
        .map_err(|e| e.to_string())?
}

#[cfg(windows)]
mod native {
    use super::*;
    use windows::{
        Media::Control::*,
        Win32::{
            Media::Audio::{Endpoints::*, *},
            System::{Com::*, WinRT::*},
        },
        core::*,
    };
    type Session = GlobalSystemMediaTransportControlsSession;
    type Manager = GlobalSystemMediaTransportControlsSessionManager;
    // Bound all WinRT requests. A stalled media app must not hang Axx or accumulate workers.
    macro_rules! wait {
        ($expr:expr) => {{
            let op = $expr?;
            let deadline = Instant::now() + Duration::from_millis(600);
            while op.Status()?.0 == 0 {
                if Instant::now() >= deadline {
                    let _ = op.Cancel();
                    return Err(Error::new(
                        windows::core::HRESULT(0x800705B4u32 as i32),
                        "El reproductor no respondió",
                    ));
                }
                std::thread::sleep(Duration::from_millis(10));
            }
            op.GetResults()
        }};
    }
    fn manager() -> Result<Manager> {
        wait!(Manager::RequestAsync())
    }
    fn properties(s: &Session) -> Result<GlobalSystemMediaTransportControlsSessionMediaProperties> {
        wait!(s.TryGetMediaPropertiesAsync())
    }
    fn transport(s: &Session, r: &Request) -> Result<bool> {
        let c = s.GetPlaybackInfo()?.Controls()?;
        match r.command.as_str() {
            "play" if c.IsPlayEnabled()? => wait!(s.TryPlayAsync()),
            "pause" if c.IsPauseEnabled()? => wait!(s.TryPauseAsync()),
            "next" if c.IsNextEnabled()? => wait!(s.TrySkipNextAsync()),
            "previous" if c.IsPreviousEnabled()? => wait!(s.TrySkipPreviousAsync()),
            "seek" if c.IsPlaybackPositionEnabled()? => {
                let t = s.GetTimelineProperties()?;
                let ticks =
                    (r.value.unwrap_or(0.0) * 10_000_000.0) as i64 + t.StartTime()?.Duration;
                wait!(s.TryChangePlaybackPositionAsync(ticks.clamp(
                    t.MinSeekTime()?.Duration,
                    t.MaxSeekTime()?.Duration.max(t.MinSeekTime()?.Duration)
                )))
            }
            _ => Ok(false),
        }
    }
    fn meters() -> Result<Vec<IAudioMeterInformation>> {
        unsafe {
            let enumerator: IMMDeviceEnumerator =
                CoCreateInstance(&MMDeviceEnumerator, None, CLSCTX_ALL)?;
            let devices = enumerator.EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE)?;
            let mut out = Vec::new();
            for i in 0..devices.GetCount()? {
                if let Ok(m) = devices
                    .Item(i)
                    .and_then(|d| d.Activate::<IAudioMeterInformation>(CLSCTX_ALL, None))
                {
                    out.push(m);
                }
            }
            Ok(out)
        }
    }
    pub fn run(shared: Arc<Mutex<Value>>, rx: mpsc::Receiver<Request>) -> Result<()> {
        unsafe {
            RoInitialize(RO_INIT_MULTITHREADED)?;
        }
        let mut mgr = manager().ok();
        let mut known: Vec<(String, Session)> = vec![];
        let mut serial = 0u64;
        let mut outputs = vec![];
        let mut last = Instant::now() - Duration::from_secs(10);
        let mut last_devices = last;
        loop {
            if let Ok(r) = rx.try_recv() {
                if Instant::now() > r.expires {
                    let _ = r
                        .reply
                        .send(Err("La orden caducó; vuelve a intentarlo".into()));
                    continue;
                }
                // Re-enumerate before acting: stale IDs never switch to another media application.
                let target = known.iter().find(|(id, _)| *id == r.id).map(|(_, s)| s);
                let live = mgr.as_ref().and_then(|m| m.GetSessions().ok());
                let result = if let Some(s) = target.filter(|s| {
                    live.as_ref()
                        .is_some_and(|xs| xs.into_iter().any(|x| x == **s))
                }) {
                    transport(s, &r).map_err(|e| e.to_string()).and_then(|ok| {
                        if ok {
                            Ok(true)
                        } else {
                            Err("La aplicación no acepta ese control ahora".into())
                        }
                    })
                } else {
                    Err("La sesión terminó. Elige un reproductor disponible".into())
                };
                let _ = r.reply.send(result);
                last = Instant::now() - Duration::from_secs(10);
            }
            if last_devices.elapsed() >= Duration::from_secs(3) {
                match meters() {
                    Ok(meters) => {
                        outputs = meters;
                        shared.lock().unwrap()["audioError"] = json!("");
                    }
                    Err(e) => {
                        outputs.clear();
                        shared.lock().unwrap()["audioError"] = json!(e.to_string());
                    }
                }
                last_devices = Instant::now();
            }
            let mut peak = 0.0f32;
            for output in &outputs {
                if let Ok(p) = unsafe { output.GetPeakValue() } {
                    peak = peak.max(p);
                }
            }
            {
                let mut state = shared.lock().unwrap();
                state["peak"] = json!(peak.clamp(0.0, 1.0));
                state["audioAvailable"] = json!(!outputs.is_empty());
                state["updatedAt"] = json!(now());
            }
            if last.elapsed() >= Duration::from_millis(750) {
                if mgr.is_none() {
                    mgr = manager().ok();
                }
                let mut rows = vec![];
                let mut next = vec![];
                let mut current_id = String::new();
                let cycle = Instant::now();
                if let Some(m) = &mgr {
                    if let Ok(sessions) = m.GetSessions() {
                        let current = m.GetCurrentSession().ok();
                        for s in sessions.into_iter().take(32) {
                            let id = known
                                .iter()
                                .find(|(_, old)| *old == s)
                                .map(|(id, _)| id.clone())
                                .unwrap_or_else(|| {
                                    serial += 1;
                                    format!("media-{serial}")
                                });
                            if current.as_ref() == Some(&s) {
                                current_id = id.clone();
                            }
                            // A closing or unresponsive app cannot terminate the monitor.
                            let row = (|| -> Result<Value> {
                                let info = s.GetPlaybackInfo()?;
                                let c = info.Controls()?;
                                let p = if cycle.elapsed() < Duration::from_millis(300) {
                                    properties(&s).ok()
                                } else {
                                    None
                                };
                                let t = s.GetTimelineProperties().ok();
                                let start = t
                                    .as_ref()
                                    .and_then(|t| t.StartTime().ok())
                                    .map_or(0, |t| t.Duration);
                                let seconds = |n: i64| ((n - start) as f64 / 10_000_000.0).max(0.0);
                                Ok(
                                    json!({"id":id,"app":s.SourceAppUserModelId()?.to_string(),"title":p.as_ref().and_then(|p|p.Title().ok()).map(|p|p.to_string()).unwrap_or_default(),"subtitle":p.as_ref().and_then(|p|p.Artist().ok()).map(|p|p.to_string()).unwrap_or_default(),"playing":info.PlaybackStatus()?==GlobalSystemMediaTransportControlsSessionPlaybackStatus::Playing,"canPlay":c.IsPlayEnabled()?,"canPause":c.IsPauseEnabled()?,"canNext":c.IsNextEnabled()?,"canPrevious":c.IsPreviousEnabled()?,"canSeek":c.IsPlaybackPositionEnabled()?,"time":t.as_ref().and_then(|t|t.Position().ok()).map_or(0.0,|t|seconds(t.Duration)),"duration":t.as_ref().and_then(|t|t.EndTime().ok()).map_or(0.0,|t|seconds(t.Duration))}),
                                )
                            })();
                            if let Ok(row) = row {
                                rows.push(row);
                            }
                            next.push((id, s));
                        }
                    } else {
                        mgr = None;
                    }
                }
                known = next;
                let mut state = shared.lock().unwrap();
                state["sessions"] = json!(rows);
                state["currentId"] = json!(current_id);
                state["available"] = json!(mgr.is_some());
                state["sessionsUpdatedAt"] = json!(now());
                last = Instant::now();
            }
            std::thread::sleep(Duration::from_millis(50));
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_arbitrary_commands_and_bad_positions() {
        assert!(control("x".into(), "shell".into(), None).is_err());
        for value in [f64::NAN, -1.0, f64::INFINITY, 604801.0] {
            assert!(control("x".into(), "seek".into(), Some(value)).is_err());
        }
    }
}
