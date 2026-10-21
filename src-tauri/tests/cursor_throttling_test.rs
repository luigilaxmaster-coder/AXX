// Empirical Challenge Test Harness: Cursor Throttling & Polling Invariants
// Milestone 1 Iteration 2 Challenger 2

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct RawPoint {
    x: i32,
    y: i32,
}

#[derive(Debug, Clone, PartialEq)]
struct CursorEventPayload {
    x: f64,
    y: f64,
    screen_x: i32,
    screen_y: i32,
    scale_factor: f64,
}

struct CursorThrottler {
    last_x: i32,
    last_y: i32,
    emitted: Vec<CursorEventPayload>,
}

impl CursorThrottler {
    fn new() -> Self {
        Self {
            last_x: i32::MIN,
            last_y: i32::MIN,
            emitted: Vec::new(),
        }
    }

    // Mirrors the exact gating logic in src-tauri/src/lib.rs:849-856
    fn tick(&mut self, point: RawPoint, screen_point: RawPoint, scale: f64) -> bool {
        let x = point.x as f64 / scale;
        let y = point.y as f64 / scale;
        if point.x != self.last_x || point.y != self.last_y {
            self.emitted.push(CursorEventPayload {
                x,
                y,
                screen_x: screen_point.x,
                screen_y: screen_point.y,
                scale_factor: scale,
            });
            self.last_x = point.x;
            self.last_y = point.y;
            true
        } else {
            false
        }
    }
}

#[test]
fn test_stationary_cursor_emits_zero_events_across_repeated_iterations() {
    let mut throttler = CursorThrottler::new();
    let initial_pos = RawPoint { x: 500, y: 300 };

    // Initial event when cursor is first sampled
    let first_emit = throttler.tick(initial_pos, initial_pos, 1.0);
    assert!(first_emit, "First sample should emit an initial position");
    assert_eq!(throttler.emitted.len(), 1);

    // Simulate cursor remaining stationary for 1,000 iterations (10 seconds at 100 Hz)
    let mut intermediate_emits = 0;
    for _ in 0..1000 {
        if throttler.tick(initial_pos, initial_pos, 1.0) {
            intermediate_emits += 1;
        }
    }

    assert_eq!(
        intermediate_emits, 0,
        "Stationary cursor must emit EXACTLY 0 events across repeated iterations"
    );
    assert_eq!(
        throttler.emitted.len(), 1,
        "Total emitted events after stationary loop must remain 1"
    );
}

#[test]
fn test_cursor_movement_emits_whenever_coordinates_change() {
    let mut throttler = CursorThrottler::new();
    let num_moves = 250;

    for i in 0..num_moves {
        let pt = RawPoint { x: i, y: i * 2 };
        let emitted = throttler.tick(pt, pt, 1.0);
        assert!(emitted, "Every moving coordinate change must trigger an event");
    }

    assert_eq!(
        throttler.emitted.len(),
        num_moves as usize,
        "Number of emitted events must match the number of distinct coordinate changes"
    );

    // Verify payload values
    for (i, payload) in throttler.emitted.iter().enumerate() {
        assert_eq!(payload.x, i as f64);
        assert_eq!(payload.y, (i * 2) as f64);
        assert_eq!(payload.screen_x, i as i32);
        assert_eq!(payload.screen_y, (i * 2) as i32);
    }
}

#[test]
fn test_interleaved_stationary_and_movement_patterns() {
    let mut throttler = CursorThrottler::new();
    let mut expected_emits = 0;

    let scenarios = [
        (RawPoint { x: 10, y: 20 }, 1),   // initial move -> 1
        (RawPoint { x: 10, y: 20 }, 50),  // 50 stationary ticks -> 0
        (RawPoint { x: 11, y: 20 }, 1),   // 1 pixel delta x -> 1
        (RawPoint { x: 11, y: 20 }, 100), // 100 stationary ticks -> 0
        (RawPoint { x: 11, y: 21 }, 1),   // 1 pixel delta y -> 1
        (RawPoint { x: 11, y: 21 }, 30),  // 30 stationary ticks -> 0
        (RawPoint { x: 100, y: 200 }, 1), // big jump -> 1
        (RawPoint { x: 100, y: 200 }, 75),// 75 stationary ticks -> 0
    ];

    for (pt, iterations) in scenarios {
        for iter in 0..iterations {
            let emitted = throttler.tick(pt, pt, 1.25);
            if iter == 0 {
                // If it's the first iteration of a new point, check if it changed
                if pt.x != throttler.last_x || pt.y != throttler.last_y {
                    // It will have already updated inside tick
                }
            }
            if emitted {
                expected_emits += 1;
            }
        }
    }

    // Exactly 4 distinct positions: (10,20), (11,20), (11,21), (100,200)
    assert_eq!(expected_emits, 4);
    assert_eq!(throttler.emitted.len(), 4);
}

#[test]
fn test_negative_coordinates_multi_monitor_support() {
    let mut throttler = CursorThrottler::new();

    // Multi-monitor coordinates to the left / top of primary
    let p1 = RawPoint { x: -1920, y: -100 };
    assert!(throttler.tick(p1, p1, 1.0));

    // Stationary on secondary monitor
    for _ in 0..50 {
        assert!(!throttler.tick(p1, p1, 1.0));
    }

    // Move within secondary monitor
    let p2 = RawPoint { x: -1919, y: -100 };
    assert!(throttler.tick(p2, p2, 1.0));

    // Cross into primary monitor (positive)
    let p3 = RawPoint { x: 50, y: 50 };
    assert!(throttler.tick(p3, p3, 1.0));

    assert_eq!(throttler.emitted.len(), 3);
}

#[test]
fn test_scale_factors_and_coordinate_scaling() {
    for scale in [1.0, 1.25, 1.5, 1.75, 2.0, 2.5] {
        let mut throttler = CursorThrottler::new();
        let pt = RawPoint { x: 300, y: 150 };
        throttler.tick(pt, pt, scale);

        let last = throttler.emitted.last().unwrap();
        assert!((last.x - (300.0 / scale)).abs() < 1e-6);
        assert!((last.y - (150.0 / scale)).abs() < 1e-6);
        assert_eq!(last.scale_factor, scale);
    }
}

#[test]
fn test_fuzz_property_transition_equivalence() {
    // Mathematical invariant: For any sequence P[0]..P[N],
    // emitted count == 1 + sum(P[i] != P[i-1]) for i in 1..N
    let mut throttler = CursorThrottler::new();

    // Generate pseudo-random sequence with stationary clusters
    let mut seed: u64 = 0xDEADBEEFCAFE;
    let mut prng = || {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        seed
    };

    let mut points = Vec::new();
    let mut current_pt = RawPoint { x: 100, y: 100 };

    for _ in 0..10_000 {
        let roll = prng() % 100;
        if roll < 70 {
            // 70% chance stationary
            points.push(current_pt);
        } else {
            // 30% chance move
            current_pt = RawPoint {
                x: ((prng() % 2000) as i32) - 500,
                y: ((prng() % 2000) as i32) - 500,
            };
            points.push(current_pt);
        }
    }

    let mut expected_transitions = 0;
    let mut prev = RawPoint { x: i32::MIN, y: i32::MIN };
    for pt in &points {
        if *pt != prev {
            expected_transitions += 1;
            prev = *pt;
        }
    }

    for pt in points {
        throttler.tick(pt, pt, 1.0);
    }

    assert_eq!(
        throttler.emitted.len(),
        expected_transitions,
        "Emitted count must strictly match the count of position transitions"
    );
}
