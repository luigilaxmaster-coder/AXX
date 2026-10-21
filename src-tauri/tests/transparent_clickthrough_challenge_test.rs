// Empirical Challenge Test Harness: Transparent Desktop Click-Through & Hit-Testing Precision
// Milestone 1 Iteration 2 Challenger 1

#[derive(Clone, Copy, Debug, PartialEq)]
struct Rect {
    x: f64,
    y: f64,
    width: f64,
    height: f64,
}

impl Rect {
    fn contains(&self, x: f64, y: f64) -> bool {
        x >= self.x && y >= self.y && x < self.x + self.width && y < self.y + self.height
    }
}

struct PixelMask {
    bounds: Rect,
    cols: usize,
    rows: usize,
    bits: Vec<bool>,
}

impl PixelMask {
    // Exact copy of PixelMask::contains from src-tauri/src/lib.rs:55-81
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

// Mirrors the Tauri cursor hit test loop logic in src-tauri/src/lib.rs:857-876
fn evaluate_cursor_ignore(
    regions: &[Rect],
    mask: Option<&PixelMask>,
    x: f64,
    y: f64,
    lbutton_down: bool,
    current_ignore: bool,
) -> (bool, bool) {
    let regions_empty = regions.is_empty();
    let mask_present = mask.is_some();
    let inside = regions.iter().any(|r| r.contains(x, y))
        || mask.as_ref().is_some_and(|m| m.contains(x, y));

    let ignore = if inside {
        false
    } else if lbutton_down && !current_ignore {
        false
    } else {
        (!regions_empty || mask_present) && !inside
    };

    (inside, ignore)
}

// Generate realistic 64x64 liquid avatar mask: centered circular body (radius 130px in 530x530 stage)
fn create_test_avatar_stage_mask(stage_x: f64, stage_y: f64, stage_size: f64) -> PixelMask {
    let cols = 64;
    let rows = 64;
    let mut bits = vec![false; cols * rows];

    let center_x = stage_size / 2.0;
    let center_y = stage_size / 2.0;
    let radius = 130.0;

    for r in 0..rows {
        for c in 0..cols {
            let px = (c as f64 + 0.5) / cols as f64 * stage_size;
            let py = (r as f64 + 0.5) / rows as f64 * stage_size;
            let dist = ((px - center_x).powi(2) + (py - center_y).powi(2)).sqrt();
            if dist <= radius {
                bits[r * cols + c] = true;
            }
        }
    }

    PixelMask {
        bounds: Rect {
            x: stage_x,
            y: stage_y,
            width: stage_size,
            height: stage_size,
        },
        cols,
        rows,
        bits,
    }
}

#[test]
fn test_530x530_stage_four_corners_evaluate_to_click_through() {
    let stage_x = 100.0;
    let stage_y = 100.0;
    let stage_size = 530.0;
    let mask = create_test_avatar_stage_mask(stage_x, stage_y, stage_size);

    // Realistic UI regions (dock, panels) but EXCLUDING #stage and #avatar
    let regions = vec![
        Rect { x: 300.0, y: 650.0, width: 200.0, height: 48.0 }, // #dock-shell
        Rect { x: 650.0, y: 150.0, width: 420.0, height: 560.0 }, // secondary panel
    ];

    // Coordinates in the 4 corners of the 530x530 #stage area
    let corners = [
        ("Top-Left", stage_x + 10.0, stage_y + 10.0),
        ("Top-Right", stage_x + 520.0, stage_y + 10.0),
        ("Bottom-Left", stage_x + 10.0, stage_y + 520.0),
        ("Bottom-Right", stage_x + 520.0, stage_y + 520.0),
    ];

    for (name, x, y) in corners {
        // 1. PixelMask::contains must return false in transparent corners
        assert!(
            !mask.contains(x, y),
            "Corner {} at ({}, {}) must not be inside mask",
            name, x, y
        );

        // 2. Full hit-test loop must evaluate inside=false, ignore=true (desktop click-through enabled!)
        let (inside, ignore) = evaluate_cursor_ignore(&regions, Some(&mask), x, y, false, false);
        assert!(
            !inside,
            "Corner {} at ({}, {}) must evaluate inside=false",
            name, x, y
        );
        assert!(
            ignore,
            "Corner {} at ({}, {}) must evaluate ignore=true to allow click-through to desktop",
            name, x, y
        );
    }
}

#[test]
fn test_liquid_avatar_body_evaluates_to_axx_hit() {
    let stage_x = 100.0;
    let stage_y = 100.0;
    let stage_size = 530.0;
    let mask = create_test_avatar_stage_mask(stage_x, stage_y, stage_size);

    let regions = vec![
        Rect { x: 300.0, y: 650.0, width: 200.0, height: 48.0 },
    ];

    // Center of avatar body: (265, 265 relative to stage)
    let center_x = stage_x + 265.0;
    let center_y = stage_y + 265.0;

    assert!(
        mask.contains(center_x, center_y),
        "Center of avatar must be inside mask"
    );

    let (inside, ignore) = evaluate_cursor_ignore(&regions, Some(&mask), center_x, center_y, false, false);
    assert!(inside, "Center of avatar must evaluate inside=true");
    assert!(!ignore, "Center of avatar must evaluate ignore=false (caught by Axx)");

    // Sample points at radius 30, 60, 90, 110 px from center
    for r in [30.0, 60.0, 90.0, 110.0] {
        for angle in [0.0, std::f64::consts::FRAC_PI_2, std::f64::consts::PI, 3.0 * std::f64::consts::FRAC_PI_2] {
            let sx = center_x + r * angle.cos();
            let sy = center_y + r * angle.sin();

            assert!(
                mask.contains(sx, sy),
                "Liquid body point at radius {} angle {} must be inside mask",
                r, angle
            );

            let (inside, ignore) = evaluate_cursor_ignore(&regions, Some(&mask), sx, sy, false, false);
            assert!(inside, "Liquid body point must evaluate inside=true");
            assert!(!ignore, "Liquid body point must evaluate ignore=false (caught by Axx)");
        }
    }
}

#[test]
fn test_regression_dead_zone_eliminated_when_stage_rect_not_in_regions() {
    let stage_x = 0.0;
    let stage_y = 0.0;
    let stage_size = 530.0;
    let mask = create_test_avatar_stage_mask(stage_x, stage_y, stage_size);

    // Old bug: stage rect was pushed into interactive_regions
    let buggy_regions = vec![Rect {
        x: stage_x,
        y: stage_y,
        width: stage_size,
        height: stage_size,
    }];

    // Corner (10, 10): in buggy state, was blocked!
    let (buggy_inside, buggy_ignore) = evaluate_cursor_ignore(&buggy_regions, Some(&mask), 10.0, 10.0, false, false);
    assert!(buggy_inside, "BUG DEMONSTRATION: stage rect caused inside=true in transparent corner");
    assert!(!buggy_ignore, "BUG DEMONSTRATION: stage rect blocked desktop click-through in transparent corner");

    // Fixed state: stage rect is NOT in interactive_regions
    let fixed_regions: Vec<Rect> = vec![];
    let (fixed_inside, fixed_ignore) = evaluate_cursor_ignore(&fixed_regions, Some(&mask), 10.0, 10.0, false, false);
    assert!(!fixed_inside, "FIX VERIFIED: corner evaluates inside=false");
    assert!(fixed_ignore, "FIX VERIFIED: corner evaluates ignore=true (desktop click-through restored)");
}

#[test]
fn test_drag_continuity_across_transparent_boundaries() {
    let stage_x = 0.0;
    let stage_y = 0.0;
    let stage_size = 530.0;
    let mask = create_test_avatar_stage_mask(stage_x, stage_y, stage_size);
    let regions: Vec<Rect> = vec![];

    let center_x = 265.0;
    let center_y = 265.0;
    let corner_x = 10.0;
    let corner_y = 10.0;

    // 1. Initial click on avatar: inside=true, ignore=false
    let (inside_1, ignore_1) = evaluate_cursor_ignore(&regions, Some(&mask), center_x, center_y, true, true);
    assert!(inside_1);
    assert!(!ignore_1);

    // Current state becomes ignore=false
    let mut current_ignore = false;

    // 2. Drag moves outside avatar to corner (10, 10) while mouse button is held down (lbutton_down = true)
    let (inside_2, ignore_2) = evaluate_cursor_ignore(&regions, Some(&mask), corner_x, corner_y, true, current_ignore);
    assert!(!inside_2, "Outside mask");
    assert!(!ignore_2, "Drag must NOT be interrupted: ignore stays false while lbutton_down");
    current_ignore = ignore_2;

    // 3. User releases mouse button at corner (10, 10) (lbutton_down = false)
    let (inside_3, ignore_3) = evaluate_cursor_ignore(&regions, Some(&mask), corner_x, corner_y, false, current_ignore);
    assert!(!inside_3);
    assert!(ignore_3, "Releasing mouse button restores ignore=true (desktop click-through restored)");
}

#[test]
fn test_fuzz_coordinate_stability_and_no_panics() {
    let stage_size = 530.0;
    let mask = create_test_avatar_stage_mask(0.0, 0.0, stage_size);
    let regions: Vec<Rect> = vec![];

    // Extreme coordinates that could cause out-of-bounds or NaN panics
    let extreme_coords = [
        (-1000.0, -1000.0),
        (-0.00001, -0.00001),
        (0.0, 0.0),
        (530.0, 530.0),
        (530.0001, 530.0001),
        (10000.0, 10000.0),
        (f64::MAX, f64::MAX),
        (f64::MIN, f64::MIN),
    ];

    for (x, y) in extreme_coords {
        let _ = mask.contains(x, y);
        let _ = evaluate_cursor_ignore(&regions, Some(&mask), x, y, false, false);
    }

    // Fuzz 10,000 points strictly outside the stage
    let mut seed: u64 = 0xCAFEBABEF00D;
    let mut prng = || {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        seed
    };

    for _ in 0..10_000 {
        // Points outside 530x530 box
        let x = (prng() % 2000) as f64 - 1000.0;
        let y = (prng() % 2000) as f64 - 1000.0;
        if x < -5.0 || x > 535.0 || y < -5.0 || y > 535.0 {
            assert!(!mask.contains(x, y));
            let (inside, ignore) = evaluate_cursor_ignore(&regions, Some(&mask), x, y, false, false);
            assert!(!inside);
            assert!(ignore);
        }
    }
}
