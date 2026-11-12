//! Windows owns global PCM capture; a renderer heartbeat cannot keep it open indefinitely.
use serde_json::{Value, json};
use std::{
    sync::{
        Arc, Mutex, OnceLock,
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc,
    },
    time::{Duration, Instant},
};
use tauri::Emitter;
use windows::{
    Win32::{
        Devices::FunctionDiscovery::PKEY_Device_FriendlyName,
        Media::Audio::*,
        System::Com::{
            CLSCTX_ALL, COINIT_APARTMENTTHREADED, CoCreateInstance, CoInitializeEx, CoTaskMemFree,
            CoUninitialize, STGM_READ,
            StructuredStorage::{PropVariantClear, PropVariantToStringAlloc},
        },
    },
    core::PCWSTR,
};

static APP: OnceLock<tauri::AppHandle> = OnceLock::new();
static ACTIVE: AtomicBool = AtomicBool::new(false);
static HALT: AtomicU64 = AtomicU64::new(0);
static HEARTBEAT: OnceLock<Mutex<Instant>> = OnceLock::new();
pub type Destination = Arc<Mutex<Option<(String, u64)>>>;

pub fn init(app: tauri::AppHandle) {
    let _ = APP.set(app);
}
pub fn active() -> bool {
    ACTIVE.load(Ordering::SeqCst)
}
pub fn beat() {
    *HEARTBEAT
        .get_or_init(|| Mutex::new(Instant::now()))
        .lock()
        .unwrap() = Instant::now();
}
fn live(generation: u64, halt: u64, elapsed: Duration) -> bool {
    generation == super::dictation::CANCEL.load(Ordering::SeqCst)
        && halt == HALT.load(Ordering::SeqCst)
        && elapsed < Duration::from_secs(3)
}
pub fn stop() -> Result<Value, String> {
    HALT.fetch_add(1, Ordering::SeqCst);
    let deadline = Instant::now() + Duration::from_secs(2);
    while ACTIVE.load(Ordering::SeqCst) {
        if Instant::now() >= deadline {
            return Err("Native microphone release not confirmed".into());
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    Ok(json!({"microphone_open":false}))
}
fn emit(name: &str, value: Value) {
    if let Some(app) = APP.get() {
        let _ = app.emit(name, value);
    }
}
struct Apartment;
impl Apartment {
    fn new() -> windows::core::Result<Self> {
        unsafe {
            CoInitializeEx(None, COINIT_APARTMENTTHREADED).ok()?;
        }
        Ok(Self)
    }
}
impl Drop for Apartment {
    fn drop(&mut self) {
        unsafe {
            CoUninitialize();
        }
    }
}
struct Busy;
impl Drop for Busy {
    fn drop(&mut self) {
        ACTIVE.store(false, Ordering::SeqCst);
    }
}
struct Running(IAudioClient);
impl Drop for Running {
    fn drop(&mut self) {
        unsafe {
            let _ = self.0.Stop();
        }
    }
}
fn enumerator() -> windows::core::Result<IMMDeviceEnumerator> {
    unsafe { CoCreateInstance(&MMDeviceEnumerator, None, CLSCTX_ALL) }
}
unsafe fn string(value: windows::core::PWSTR) -> String {
    let text = unsafe { value.to_string() }.unwrap_or_default();
    unsafe {
        CoTaskMemFree(Some(value.0.cast()));
    }
    text
}
pub fn devices() -> Result<Value, String> {
    (|| -> windows::core::Result<Value> {
        let _com = Apartment::new()?;
        unsafe {
            let list = enumerator()?.EnumAudioEndpoints(eCapture, DEVICE_STATE_ACTIVE)?;
            let mut devices = Vec::new();
            for index in 0..list.GetCount()?.min(64) {
                let device = list.Item(index)?;
                let id = string(device.GetId()?);
                let mut label = "Micrófono".to_string();
                if let Ok(store) = device.OpenPropertyStore(STGM_READ) {
                    if let Ok(mut value) = store.GetValue(&PKEY_Device_FriendlyName) {
                        if let Ok(text) = PropVariantToStringAlloc(&value) {
                            label = string(text);
                        }
                        let _ = PropVariantClear(&mut value);
                    }
                }
                devices.push(json!({"id":id,"label":label}));
            }
            Ok(json!({"devices":devices}))
        }
    })()
    .map_err(|_| "Cannot enumerate native microphones".into())
}
pub fn start(
    session: String,
    device: String,
    destination: Destination,
    epoch: Arc<AtomicU64>,
    generation: u64,
) -> Result<Value, String> {
    if device.len() > 1024 || device.contains('\0') || APP.get().is_none() {
        return Err("Invalid native microphone request".into());
    }
    if ACTIVE
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_err()
    {
        return Err("Native microphone is busy".into());
    }
    let capture = uuid::Uuid::new_v4().to_string();
    let capture_id = capture.clone();
    let halt = HALT.load(Ordering::SeqCst);
    beat();
    let (tx, rx) = mpsc::sync_channel(1);
    let spawn = std::thread::Builder::new()
        .name("dictation-pcm".into())
        .spawn(move || {
            let _busy = Busy;
            let result = capture_loop(
                &session,
                &capture_id,
                &device,
                destination,
                epoch,
                generation,
                halt,
                &tx,
            );
            if result.is_err() {
                let _ = tx.try_send(Err("Native microphone initialization failed".to_string()));
            }
            emit(
                "axx-dictation-audio-stopped",
                json!({"session":session,"capture":capture_id,"error":result.is_err()}),
            );
        });
    if spawn.is_err() {
        ACTIVE.store(false, Ordering::SeqCst);
        return Err("Cannot start native microphone thread".into());
    }
    match rx.recv_timeout(Duration::from_secs(3)) {
        Ok(Ok(())) => Ok(json!({"capture":capture,"microphone_open":true,"sample_rate":16000})),
        _ => {
            let _ = stop();
            Err("Native microphone could not start".into())
        }
    }
}
fn capture_loop(
    session: &str,
    capture: &str,
    device: &str,
    destination: Destination,
    epoch: Arc<AtomicU64>,
    generation: u64,
    halt: u64,
    ready: &mpsc::SyncSender<Result<(), String>>,
) -> windows::core::Result<()> {
    let _com = Apartment::new()?;
    unsafe {
        let enumerator = enumerator()?;
        let device = if device.is_empty() {
            enumerator.GetDefaultAudioEndpoint(eCapture, eConsole)?
        } else {
            let id: Vec<u16> = device.encode_utf16().chain(Some(0)).collect();
            enumerator.GetDevice(PCWSTR(id.as_ptr()))?
        };
        // A selected endpoint must still be an input, even if the device ID was tampered with.
        let endpoint: IMMEndpoint = windows::core::Interface::cast(&device)?;
        if endpoint.GetDataFlow()? != eCapture {
            return Err(windows::core::Error::from_hresult(
                windows::Win32::Foundation::E_INVALIDARG,
            ));
        }
        let client: IAudioClient = device.Activate(CLSCTX_ALL, None)?;
        let format = WAVEFORMATEX {
            wFormatTag: 1,
            nChannels: 1,
            nSamplesPerSec: 16000,
            nAvgBytesPerSec: 32000,
            nBlockAlign: 2,
            wBitsPerSample: 16,
            cbSize: 0,
        };
        client.Initialize(
            AUDCLNT_SHAREMODE_SHARED,
            AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,
            1_000_000,
            0,
            &format,
            None,
        )?;
        let input: IAudioCaptureClient = client.GetService()?;
        if !live(generation, halt, Duration::ZERO) {
            return Ok(());
        }
        client.Start()?;
        let _running = Running(client);
        if ready.send(Ok(())).is_err() {
            return Ok(());
        }
        let mut samples: Vec<i16> = Vec::with_capacity(2048);
        let mut target: Option<String> = None;
        let mut first_packet = true;
        loop {
            let age = HEARTBEAT.get().unwrap().lock().unwrap().elapsed();
            if !live(generation, halt, age) || !super::dictation::desktop_available() {
                break;
            }
            let current = destination
                .lock()
                .unwrap()
                .clone()
                .filter(|(_, e)| *e == epoch.load(Ordering::SeqCst))
                .map(|(id, _)| id);
            if destination.lock().unwrap().is_none() {
                break;
            }
            if current != target {
                samples.clear();
                target = current;
            }
            for _ in 0..32 {
                if input.GetNextPacketSize()? == 0 {
                    break;
                }
                let (mut data, mut frames, mut flags) = (std::ptr::null_mut(), 0, 0);
                input.GetBuffer(&mut data, &mut frames, &mut flags, None, None)?;
                let bounded = frames <= 16000
                    && (first_packet
                        || flags & AUDCLNT_BUFFERFLAGS_DATA_DISCONTINUITY.0 as u32 == 0)
                    && (frames == 0
                        || !data.is_null()
                        || flags & AUDCLNT_BUFFERFLAGS_SILENT.0 as u32 != 0);
                if bounded && target.is_some() {
                    for index in 0..frames as usize {
                        let value = if flags & AUDCLNT_BUFFERFLAGS_SILENT.0 as u32 != 0 {
                            0
                        } else {
                            std::ptr::read_unaligned(data.add(index * 2).cast::<i16>())
                        };
                        samples.push(value);
                        if samples.len() == 2048 {
                            if live(
                                generation,
                                halt,
                                HEARTBEAT.get().unwrap().lock().unwrap().elapsed(),
                            ) && destination.lock().unwrap().as_ref().is_some_and(|(id, e)| {
                                Some(id) == target.as_ref() && *e == epoch.load(Ordering::SeqCst)
                            }) {
                                emit(
                                    "axx-dictation-pcm",
                                    json!({"session":session,"capture":capture,"target":target,"samples":samples}),
                                );
                            }
                            samples.clear();
                        }
                    }
                }
                input.ReleaseBuffer(frames)?;
                first_packet = false;
                if !bounded {
                    return Err(windows::core::Error::from_hresult(
                        windows::Win32::Foundation::E_INVALIDARG,
                    ));
                }
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn renderer_liveness_is_bounded() {
        let generation = super::super::dictation::CANCEL.load(Ordering::SeqCst);
        let halt = HALT.load(Ordering::SeqCst);
        assert!(live(generation, halt, Duration::from_secs(2)));
        assert!(!live(generation, halt, Duration::from_secs(3)));
        assert!(!live(generation.wrapping_add(1), halt, Duration::ZERO));
        assert!(!live(generation, halt.wrapping_add(1), Duration::ZERO));
    }
}
