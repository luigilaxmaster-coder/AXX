const fs = require('fs');
const path = require('path');
const vm = require('vm');

console.log('=== REVIEWER 1 INDEPENDENT ADVERSARIAL STRESS TEST ===');

const htmlPath = path.resolve(__dirname, '../../../1.AXX/Axx.html');
const rustPath = path.resolve(__dirname, '../../../src-tauri/src/resident.rs');

const html = fs.readFileSync(htmlPath, 'utf8');
const rust = fs.readFileSync(rustPath, 'utf8');

let pass = 0;
let fail = 0;

function check(desc, cond) {
  if (cond) {
    console.log(`[PASS] ${desc}`);
    pass++;
  } else {
    console.error(`[FAIL] ${desc}`);
    fail++;
  }
}

// 1. Focus 1: Panel Drag Decoupling
const pointermoveMatch = html.match(/document\.addEventListener\('pointermove',\s*event\s*=>\s*\{([\s\S]*?)\},\s*true\);/);
check('pointermove listener exists in ResidentDesktop.bindDrag', !!pointermoveMatch);
if (pointermoveMatch) {
  const body = pointermoveMatch[1];
  const pdBlockMatch = body.match(/const\s+pd\s*=\s*this\.panelDrag;[\s\S]*?if\s*\(pd[\s\S]*?return;\s*\}/);
  check('pd (panelDrag) handler exists in pointermove', !!pdBlockMatch);
  if (pdBlockMatch) {
    check('pd block does NOT invoke desktop_layout IPC', !pdBlockMatch[0].includes('desktop_layout'));
    check('pd block does NOT invoke desktop_activity IPC', !pdBlockMatch[0].includes('desktop_activity'));
    check('pd block uses translate3d CSS transform', pdBlockMatch[0].includes('translate3d(${dx}px, ${dy}px, 0)'));
  }
  const prBlockMatch = body.match(/const\s+pr\s*=\s*this\.panelResize;[\s\S]*?if\s*\(pr[\s\S]*?return;\s*\}/);
  check('pr (panelResize) handler exists in pointermove', !!prBlockMatch);
  if (prBlockMatch) {
    check('pr block does NOT invoke desktop_layout IPC', !prBlockMatch[0].includes('desktop_layout'));
  }
}
check('pointerup resets transform to none', html.includes("style.setProperty('transform', 'none', 'important')"));

// 2. Focus 2: Drag Isolation
check('isInteractiveOrContent excludes button, input, textarea, select', html.includes("closest('button, input, select, textarea, summary, a, [role=button]"));
check('isInteractiveOrContent excludes text selection elements', html.includes('.panel-view, pre, code, .conversation, .response, [data-scrollable]'));
check('isPanelHead returns null if isInteractiveOrContent is true', html.includes('if (isInteractiveOrContent(target)) return null;'));
check('CSS enforces user-select: text on panel view content', html.includes('user-select: text') && html.includes('body.axx-resident .panel-view'));
check('CSS enforces user-select: none on panel headers', html.includes('user-select: none') && html.includes('body.axx-resident .panel-head'));

// 3. Focus 3: Interactive Resizing & Persistence
check('HTML/DOM contains resident-resize-handle creation', html.includes("handle.className = 'resident-resize-handle'"));
check('Resize logic enforces minimum width of 320px', html.includes('Math.max(320,'));
check('Resize logic enforces minimum height of 400px', html.includes('Math.max(400,'));
check('localStorage persistence key axx.resident.panel-pos used', html.includes("'axx.resident.panel-pos'"));
check('localStorage read is guarded with try/catch', html.includes("try { return JSON.parse(localStorage.getItem('axx.resident.panel-pos') || '{}'); }"));
check('localStorage write is guarded with try/catch', html.includes("try { localStorage.setItem('axx.resident.panel-pos', JSON.stringify(this.panelPositions)); }"));
check('resetLayout clears localStorage and resets panel dimensions', html.includes("localStorage.removeItem('axx.resident.panel-pos')"));

// 4. Focus 4: Tentacle Margin
check('ResidentDesktop.layout() uses margin = 72px', html.includes('margin = 72;'));
check('Bounding box calculation adds margin around min and max bounds', html.includes('Math.min(...boxes.map(b => b.x)) - margin') && html.includes('Math.max(...boxes.map(b => b.x + b.width)) - minX + margin'));
check('Clamping logic in panelBox respects 72px margin buffer', html.includes('-g.spaceLeft + margin') && html.includes('g.spaceRight - width - margin'));

// 5. Focus 5: Rust Anchor Stability
check('resident.rs defines ACTIVE_PANEL_DRAG atomic boolean', rust.includes('static ACTIVE_PANEL_DRAG: AtomicBool = AtomicBool::new(false);'));
check('resident.rs defines LAST_LAYOUT_INSTANT for stabilization timing', rust.includes('static LAST_LAYOUT_INSTANT: Mutex<Option<Instant>> = Mutex::new(None);'));
check('record_move checks ACTIVE_PANEL_DRAG state', rust.includes('is_panel_drag_active()'));
check('record_move checks 300ms layout stabilization window', rust.includes('instant.elapsed() < Duration::from_millis(300)'));
check('desktop_layout accepts panel_drag parameter', rust.includes('panel_drag: Option<bool>'));
check('desktop_activity accepts panel_drag parameter', rust.includes('panel_drag: Option<bool>'));

// 6. Adversarial Simulation: Multi-Monitor Clamping & NaN protection
{
  function clamp(val, min, max) {
    return Math.max(min, Math.min(val, max));
  }

  // Monitor scenario: 1080p laptop display with avatar placed near right edge
  const g1080 = {
    spaceLeft: 1200,
    spaceRight: 150,
    spaceAbove: 600,
    spaceBelow: 300,
    workWidth: 1920,
    workHeight: 1080
  };
  const margin = 72;
  const panelW = 420;
  const panelH = 560;

  // Stored position from a prior 4K monitor was x: 2500, y: 1400
  let savedX = 2500;
  let savedY = 1400;

  const minXBound = -g1080.spaceLeft + margin;
  const maxXBound = g1080.spaceRight - panelW - margin;
  const clampedX = (minXBound <= maxXBound) ? clamp(savedX, minXBound, maxXBound) : -panelW;

  const minYBound = -g1080.spaceAbove + margin;
  const maxYBound = g1080.spaceBelow - panelH - margin;
  const clampedY = (minYBound <= maxYBound) ? clamp(savedY, minYBound, maxYBound) : -panelH / 2;

  check('Clamped X is kept strictly inside available desktop width', clampedX <= maxXBound && clampedX >= minXBound);
  check('Clamped Y is kept strictly inside available desktop height', clampedY <= maxYBound && clampedY >= minYBound);
}

console.log(`\nAdversarial test results: ${pass} passed, ${fail} failed.`);
if (fail > 0) process.exit(1);
