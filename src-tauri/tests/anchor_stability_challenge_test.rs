// Empirical Challenge Test Harness: Rust ACTIVE_PANEL_DRAG & Anchor Stability
// Milestone 2 Challenger 2

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

// Exact model of the resident state and record_move logic from src-tauri/src/resident.rs
static ACTIVE_PANEL_DRAG: AtomicBool = AtomicBool::new(false);
static LAST_LAYOUT_INSTANT: Mutex<Option<Instant>> = Mutex::new(None);
static LAYOUT_CHANGING: AtomicBool = AtomicBool::new(false);

#[derive(Clone, Debug, PartialEq)]
pub struct Geometry {
    pub width: f64,
    pub height: f64,
    pub anchor_x: f64,
    pub anchor_y: f64,
    pub screen_x: f64,
    pub screen_y: f64,
    pub ready: bool,
}

pub struct ResidentState {
    pub geometry: Mutex<Geometry>,
    pub preferences_dirty: AtomicBool,
}

impl ResidentState {
    pub fn new(initial_screen_x: f64, initial_screen_y: f64, anchor_x: f64, anchor_y: f64) -> Self {
        Self {
            geometry: Mutex::new(Geometry {
                width: 400.0,
                height: 400.0,
                anchor_x,
                anchor_y,
                screen_x: initial_screen_x,
                screen_y: initial_screen_y,
                ready: true,
            }),
            preferences_dirty: AtomicBool::new(false),
        }
    }

    // Mirrors src-tauri/src/resident.rs:394-416 record_move()
    pub fn simulate_record_move(&self, p_x: i32, p_y: i32, scale: f64) -> bool {
        if LAYOUT_CHANGING.load(Ordering::Relaxed) || ACTIVE_PANEL_DRAG.load(Ordering::Relaxed) {
            return false; // suppressed
        }
        if let Ok(guard) = LAST_LAYOUT_INSTANT.lock() {
            if let Some(instant) = *guard {
                if instant.elapsed() < Duration::from_millis(300) {
                    return false; // suppressed
                }
            }
        }
        let mut g = self.geometry.lock().unwrap();
        g.screen_x = p_x as f64 + g.anchor_x * scale;
        g.screen_y = p_y as f64 + g.anchor_y * scale;
        self.preferences_dirty.store(true, Ordering::Relaxed);
        true // accepted and updated
    }

    pub fn trigger_layout_change(&self) {
        LAYOUT_CHANGING.store(true, Ordering::Relaxed);
        if let Ok(mut guard) = LAST_LAYOUT_INSTANT.lock() {
            *guard = Some(Instant::now());
        }
        // simulate layout work
        LAYOUT_CHANGING.store(false, Ordering::Relaxed);
        if let Ok(mut guard) = LAST_LAYOUT_INSTANT.lock() {
            *guard = Some(Instant::now());
        }
    }
}

#[test]
fn test_record_move_suppression_during_active_panel_drag() {
    let state = ResidentState::new(1000.0, 600.0, 150.0, 150.0);
    ACTIVE_PANEL_DRAG.store(true, Ordering::Relaxed);

    // Simulate 10,000 rapid WindowEvent::Moved events during panel drag
    for i in 0..10_000 {
        let jitter_x = 500 + (i % 200) - 100;
        let jitter_y = 300 + (i % 150) - 75;
        let updated = state.simulate_record_move(jitter_x, jitter_y, 1.0);
        assert!(!updated, "record_move must be suppressed during active panel drag");
    }

    let g = state.geometry.lock().unwrap();
    assert_eq!(g.screen_x, 1000.0, "Anchor screen_x must have ZERO drift during drag");
    assert_eq!(g.screen_y, 600.0, "Anchor screen_y must have ZERO drift during drag");
    assert!(!state.preferences_dirty.load(Ordering::Relaxed));
}

#[test]
fn test_record_move_suppression_during_300ms_layout_stabilization() {
    let state = ResidentState::new(1200.0, 700.0, 200.0, 200.0);
    ACTIVE_PANEL_DRAG.store(false, Ordering::Relaxed);

    // Layout completes (e.g. SetWindowPos called on pointerup)
    state.trigger_layout_change();

    // Spurious WindowEvent::Moved events arriving within 200ms of layout
    for i in 0..2_000 {
        let spurious_x = 400 + i;
        let spurious_y = 200 + i;
        let updated = state.simulate_record_move(spurious_x, spurious_y, 1.25);
        assert!(!updated, "record_move must be suppressed within 300ms cooldown window");
    }

    let g = state.geometry.lock().unwrap();
    assert_eq!(g.screen_x, 1200.0, "screen_x must be invariant during stabilization window");
    assert_eq!(g.screen_y, 700.0, "screen_y must be invariant during stabilization window");
}

#[test]
fn test_legitimate_avatar_move_accepted_after_stabilization() {
    let state = ResidentState::new(800.0, 500.0, 100.0, 100.0);
    ACTIVE_PANEL_DRAG.store(false, Ordering::Relaxed);

    // Set LAST_LAYOUT_INSTANT to 500ms in the past (cooldown expired)
    if let Ok(mut guard) = LAST_LAYOUT_INSTANT.lock() {
        *guard = Some(Instant::now() - Duration::from_millis(500));
    }

    // Legitimate avatar drag moves window HWND to (750, 450) with scale 1.5
    let updated = state.simulate_record_move(750, 450, 1.5);
    assert!(updated, "Legitimate avatar move must be accepted after stabilization");

    let g = state.geometry.lock().unwrap();
    // expected: p.x + anchor_x * scale = 750 + 100 * 1.5 = 900.0
    assert_eq!(g.screen_x, 900.0);
    // expected: p.y + anchor_y * scale = 450 + 100 * 1.5 = 600.0
    assert_eq!(g.screen_y, 600.0);
    assert!(state.preferences_dirty.load(Ordering::Relaxed));
}

#[test]
fn test_multithreaded_rapid_event_race_condition_resilience() {
    use std::sync::Arc;
    use std::thread;

    let state = Arc::new(ResidentState::new(1000.0, 1000.0, 150.0, 150.0));
    let mut handles = vec![];

    // Thread 1: Toggles panel drag state rapidly
    let s1 = Arc::clone(&state);
    handles.push(thread::spawn(move || {
        for _ in 0..1_000 {
            ACTIVE_PANEL_DRAG.store(true, Ordering::Relaxed);
            thread::sleep(Duration::from_micros(10));
            s1.trigger_layout_change();
            ACTIVE_PANEL_DRAG.store(false, Ordering::Relaxed);
            thread::sleep(Duration::from_micros(10));
        }
    }));

    // Threads 2..6: Flood simulate_record_move concurrently
    for t_idx in 0..4 {
        let s = Arc::clone(&state);
        handles.push(thread::spawn(move || {
            for i in 0..5_000 {
                let px = 800 + (t_idx * 10) + (i % 50);
                let py = 800 + (t_idx * 10) + (i % 50);
                let _ = s.simulate_record_move(px, py, 1.0);
            }
        }));
    }

    for h in handles {
        h.join().unwrap();
    }

    // Must not panic, deadlock, or enter NaN/corrupt state
    let g = state.geometry.lock().unwrap();
    assert!(g.screen_x.is_finite(), "screen_x must be finite");
    assert!(g.screen_y.is_finite(), "screen_y must be finite");
}
