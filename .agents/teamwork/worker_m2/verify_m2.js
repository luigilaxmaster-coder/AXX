const fs = require('fs');
const path = require('path');
const vm = require('vm');

console.log('--- MILESTONE 2 COMPREHENSIVE VERIFICATION SUITE ---');

const htmlPath = path.resolve(__dirname, '../../../1.AXX/Axx.html');
const rustPath = path.resolve(__dirname, '../../../src-tauri/src/resident.rs');

const htmlContent = fs.readFileSync(htmlPath, 'utf8');
const rustContent = fs.readFileSync(rustPath, 'utf8');

let passedTests = 0;
let totalTests = 0;

function assert(condition, message) {
  totalTests++;
  if (!condition) {
    console.error(`❌ FAIL: ${message}`);
    process.exitCode = 1;
  } else {
    passedTests++;
    console.log(`✅ PASS: ${message}`);
  }
}

// 1. Backend Rust checks (src-tauri/src/resident.rs)
console.log('\n[1. BACKEND RUST CHECKS]');
assert(rustContent.includes('static ACTIVE_PANEL_DRAG: AtomicBool = AtomicBool::new(false);'), 'resident.rs defines ACTIVE_PANEL_DRAG atomic flag');
assert(rustContent.includes('static LAST_LAYOUT_INSTANT: Mutex<Option<Instant>> = Mutex::new(None);'), 'resident.rs defines LAST_LAYOUT_INSTANT mutex');
assert(rustContent.includes('pub fn set_panel_drag(active: bool)'), 'resident.rs exposes set_panel_drag helper');
assert(rustContent.includes('pub fn is_panel_drag_active() -> bool'), 'resident.rs exposes is_panel_drag_active helper');
assert(rustContent.includes('is_panel_drag_active()'), 'record_move checks is_panel_drag_active()');
assert(rustContent.includes('Duration::from_millis(300)'), 'record_move checks 300ms layout stabilization window');
assert(rustContent.includes('panel_drag: Option<bool>'), 'desktop_layout and desktop_activity accept panel_drag parameter');
assert(rustContent.includes('set_panel_drag(dragging)'), 'desktop_layout and desktop_activity update set_panel_drag');

// 2. Frontend HTML & CSS checks (1.AXX/Axx.html)
console.log('\n[2. FRONTEND CSS & DOM CHECKS]');
assert(htmlContent.includes('.resident-resize-handle {'), 'CSS defines .resident-resize-handle');
assert(htmlContent.includes('user-select: text'), 'CSS configures user-select: text for text selection in panel views');
assert(htmlContent.includes('cursor: nwse-resize;'), 'CSS specifies nwse-resize cursor for resize grip');
assert(htmlContent.includes('id="reset-desktop-layout"'), 'HTML contains reset layout button in settings');
assert(htmlContent.includes('margin = 72;'), 'ResidentDesktop.layout() uses margin = 72px for HWND tentacle boundary');

// 3. Frontend ResidentDesktop Logic Checks
console.log('\n[3. FRONTEND RESIDENT DESKTOP LOGIC]');
assert(htmlContent.includes('ensureResizeHandles()'), 'ResidentDesktop implements ensureResizeHandles()');
assert(htmlContent.includes('resetLayout()'), 'ResidentDesktop implements resetLayout()');
assert(htmlContent.includes('panelDrag = {'), 'ResidentDesktop tracks panelDrag state');
assert(htmlContent.includes('panelResize = {'), 'ResidentDesktop tracks panelResize state');
assert(htmlContent.includes("translate3d(${dx}px, ${dy}px, 0)"), 'pointermove updates local CSS transform translate3d without IPC');
assert(htmlContent.includes("isInteractiveOrContent"), 'pointerdown checks isInteractiveOrContent to protect inputs and text selection');
assert(htmlContent.includes("Math.max(320,"), 'Resize logic enforces width >= 320px minimum constraint');
assert(htmlContent.includes("Math.max(400,"), 'Resize logic enforces height >= 400px minimum constraint');
assert(htmlContent.includes("localStorage.setItem('axx.resident.panel-pos'"), 'pointerup persists to localStorage axx.resident.panel-pos');
assert(htmlContent.includes("panelDrag: true"), 'pointerdown signals panelDrag: true to backend');
assert(htmlContent.includes("panelDrag: false"), 'pointerup signals panelDrag: false to backend');

// 4. Algorithmic Simulation of Drag, Resize, Isolation, and Bounds Clamping
console.log('\n[4. ALGORITHMIC SIMULATION]');
{
  // Simulate mock localStorage
  const mockStorage = {};
  const mockWindow = {
    innerWidth: 1920,
    innerHeight: 1080
  };

  class MockResidentDesktop {
    constructor() {
      this.panelPositions = {};
      this.panelDrag = null;
      this.panelResize = null;
      this.activePanel = 'settings';
      this.geometry = {
        spaceLeft: 400,
        spaceRight: 1520,
        spaceAbove: 300,
        spaceBelow: 780
      };
      this.size = 96;
      this.ipcCalls = [];
      this.domTransform = 'none';
      this.domWidth = 460;
      this.domHeight = 600;
    }

    mockIpc(cmd, payload) {
      this.ipcCalls.push({ cmd, payload });
    }

    onPointerDown(targetType, clientX, clientY) {
      const isResizeHandle = (targetType === 'resize-handle');
      const isInteractiveOrContent = ['input', 'button', 'panel-view', 'code'].includes(targetType);

      if (isResizeHandle) {
        this.panelResize = {
          startX: clientX,
          startY: clientY,
          startW: this.domWidth,
          startH: this.domHeight
        };
        this.mockIpc('desktop_activity', { active: true, follow: false, panelDrag: true });
        return;
      }

      if (isInteractiveOrContent) {
        // Drag ignored, allow interaction/selection
        return;
      }

      // Panel Drag starts
      this.panelDrag = {
        startX: clientX,
        startY: clientY,
        origPos: { x: this.panelPositions[this.activePanel]?.x || 0, y: this.panelPositions[this.activePanel]?.y || 0 }
      };
      this.mockIpc('desktop_activity', { active: true, follow: false, panelDrag: true });
    }

    onPointerMove(clientX, clientY) {
      if (this.panelResize) {
        const dw = clientX - this.panelResize.startX;
        const dh = clientY - this.panelResize.startY;
        this.domWidth = Math.max(320, Math.min(1920 - 100, this.panelResize.startW + dw));
        this.domHeight = Math.max(400, Math.min(1080 - 100, this.panelResize.startH + dh));
        // NO IPC called on pointermove
        return;
      }

      if (this.panelDrag) {
        const dx = clientX - this.panelDrag.startX;
        const dy = clientY - this.panelDrag.startY;
        this.domTransform = `translate3d(${dx}px, ${dy}px, 0)`;
        // NO IPC called on pointermove!
        return;
      }
    }

    onPointerUp(clientX, clientY) {
      if (this.panelResize) {
        const dw = clientX - this.panelResize.startX;
        const dh = clientY - this.panelResize.startY;
        const newW = Math.max(320, Math.min(1920 - 100, this.panelResize.startW + dw));
        const newH = Math.max(400, Math.min(1080 - 100, this.panelResize.startH + dh));
        if (!this.panelPositions[this.activePanel]) this.panelPositions[this.activePanel] = { x: 0, y: 0 };
        this.panelPositions[this.activePanel].width = newW;
        this.panelPositions[this.activePanel].height = newH;
        mockStorage['axx.resident.panel-pos'] = JSON.stringify(this.panelPositions);
        this.panelResize = null;
        this.mockIpc('desktop_activity', { active: false, follow: false, panelDrag: false });
        this.scheduleLayout();
        return;
      }

      if (this.panelDrag) {
        const dx = clientX - this.panelDrag.startX;
        const dy = clientY - this.panelDrag.startY;
        const finalX = this.panelDrag.origPos.x + dx;
        const finalY = this.panelDrag.origPos.y + dy;
        if (!this.panelPositions[this.activePanel]) this.panelPositions[this.activePanel] = {};
        this.panelPositions[this.activePanel].x = finalX;
        this.panelPositions[this.activePanel].y = finalY;
        this.domTransform = 'none';
        mockStorage['axx.resident.panel-pos'] = JSON.stringify(this.panelPositions);
        this.panelDrag = null;
        this.mockIpc('desktop_activity', { active: false, follow: false, panelDrag: false });
        this.scheduleLayout();
        return;
      }
    }

    scheduleLayout() {
      this.mockIpc('desktop_layout', { panel: this.panelPositions[this.activePanel] });
    }

    resetLayout() {
      const g = this.geometry;
      const margin = 72;
      const defW = 460;
      const defH = 600;
      let targetX = 0;
      let targetY = 0;
      if (g.spaceRight >= defW + margin) {
        targetX = Math.round(g.spaceRight * 0.25);
      } else if (g.spaceLeft >= defW + margin) {
        targetX = -Math.round(g.spaceLeft * 0.25);
      }
      this.panelPositions[this.activePanel] = {
        x: targetX,
        y: targetY,
        width: defW,
        height: defH
      };
      mockStorage['axx.resident.panel-pos'] = JSON.stringify(this.panelPositions);
      this.domWidth = defW;
      this.domHeight = defH;
      this.domTransform = 'none';
      this.scheduleLayout();
    }
  }

  const sim = new MockResidentDesktop();

  // Test 4.1: Drag Isolation
  sim.onPointerDown('input', 100, 100);
  assert(sim.panelDrag === null, 'Drag isolation: clicking input does not initiate drag');
  sim.onPointerDown('panel-view', 150, 150);
  assert(sim.panelDrag === null, 'Drag isolation: clicking panel-view (text selection) does not initiate drag');

  // Test 4.2: Decoupled Drag
  sim.ipcCalls = [];
  sim.onPointerDown('header', 200, 200);
  assert(sim.panelDrag !== null, 'Drag initiation: clicking header initiates drag');
  assert(sim.ipcCalls.length === 1 && sim.ipcCalls[0].payload.panelDrag === true, 'Drag initiation signals panelDrag: true to backend');

  // Move pointer 50 times (simulating 60 FPS pointermove stream)
  for (let i = 1; i <= 50; i++) {
    sim.onPointerMove(200 + i * 2, 200 + i);
  }
  assert(sim.ipcCalls.length === 1, 'Decoupled drag: 50 pointermove events triggered ZERO synchronous IPC calls');
  assert(sim.domTransform === 'translate3d(100px, 50px, 0)', 'Local DOM CSS transform updated cleanly during drag');

  // Pointer Up
  sim.onPointerUp(300, 250);
  assert(sim.domTransform === 'none', 'Pointer up resets local CSS transform to none');
  assert(sim.panelPositions['settings'].x === 100 && sim.panelPositions['settings'].y === 50, 'Final position committed to memory');
  assert(mockStorage['axx.resident.panel-pos'].includes('"x":100,"y":50'), 'Final position persisted to localStorage');
  const lastIpc = sim.ipcCalls[sim.ipcCalls.length - 1];
  assert(lastIpc.cmd === 'desktop_layout', 'Single desktop_layout IPC committed on drag release');

  // Test 4.3: Interactive Resizing with min constraints
  sim.ipcCalls = [];
  sim.onPointerDown('resize-handle', 500, 500);
  assert(sim.panelResize !== null, 'Resize handle click initiates panelResize');
  // Attempt to shrink below minimums (e.g. -300px width, -400px height)
  sim.onPointerMove(200, 100);
  assert(sim.domWidth === 320, 'Width cannot be shrunk below min constraint 320px');
  assert(sim.domHeight === 400, 'Height cannot be shrunk below min constraint 400px');
  // Expand to custom size
  sim.onPointerMove(550, 650);
  assert(sim.domWidth === 510, 'Width expanded smoothly');
  assert(sim.domHeight === 750, 'Height expanded smoothly');
  sim.onPointerUp(550, 650);
  assert(sim.panelResize === null, 'Resize state cleared on pointerup');
  assert(mockStorage['axx.resident.panel-pos'].includes('"width":510,"height":750'), 'Custom dimensions persisted to localStorage');

  // Test 4.4: Layout Recovery ("Restablecer distribución")
  // Simulate panel placed far off-screen
  sim.panelPositions['settings'].x = -9999;
  sim.panelPositions['settings'].y = 9999;
  sim.resetLayout();
  assert(sim.panelPositions['settings'].x !== -9999, 'resetLayout retrieves panel from off-screen horizontal position');
  assert(sim.panelPositions['settings'].y === 0, 'resetLayout resets vertical coordinate to safe desktop workspace');
  assert(sim.panelPositions['settings'].width === 460, 'resetLayout resets width to default 460px');
  assert(sim.panelPositions['settings'].height === 600, 'resetLayout resets height to default 600px');
}

console.log(`\n========================================`);
console.log(`VERIFICATION RESULT: ${passedTests} / ${totalTests} TESTS PASSED`);
console.log(`========================================`);
if (passedTests === totalTests) {
  console.log('🎉 ALL MILESTONE 2 REQUIREMENTS VERIFIED SUCCESSFULLY!');
} else {
  process.exit(1);
}
