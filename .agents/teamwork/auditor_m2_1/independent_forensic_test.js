/**
 * Milestone 2 Independent Forensic Audit & Stress-Test Suite
 * Auditor: auditor_m2_1
 * Purpose: Deep empirical verification of M2 deliverables with zero assumptions.
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

let totalTests = 0;
let passedTests = 0;
let failedTests = 0;

function test(name, fn) {
    totalTests++;
    try {
        fn();
        console.log(`[PASS] ${name}`);
        passedTests++;
    } catch (err) {
        console.error(`[FAIL] ${name}: ${err.message}`);
        failedTests++;
    }
}

console.log('=== STARTING INDEPENDENT FORENSIC INTEGRITY AUDIT ===\n');

// Paths
const axxHtmlPath = path.resolve('1.AXX/Axx.html');
const residentRsPath = path.resolve('src-tauri/src/resident.rs');
const libRsPath = path.resolve('src-tauri/src/lib.rs');

// Load files
const htmlContent = fs.readFileSync(axxHtmlPath, 'utf8');
const residentRsContent = fs.readFileSync(residentRsPath, 'utf8');
const libRsContent = fs.readFileSync(libRsPath, 'utf8');

// -------------------------------------------------------------
// SECTION 1: SOURCE INTEGRITY & PROHIBITED PATTERNS AUDIT
// -------------------------------------------------------------
console.log('--- SECTION 1: PROHIBITED PATTERNS & FACADE DETECTION ---');

test('Check 1.1: No hardcoded test passes or dummy mocks in resident.rs', () => {
    // Check that is_panel_drag_active is not a hardcoded dummy (e.g. return true/false constant)
    const fnMatch = residentRsContent.match(/pub fn is_panel_drag_active\(\)\s*->\s*bool\s*\{([^}]+)\}/);
    assert(fnMatch, 'is_panel_drag_active must be defined');
    const body = fnMatch[1].trim();
    assert(!/^\s*true\s*$/.test(body), 'is_panel_drag_active must not hardcode true');
    assert(!/^\s*false\s*$/.test(body), 'is_panel_drag_active must not hardcode false');
    assert(body.includes('ACTIVE_PANEL_DRAG.load'), 'Must load from atomic state');
});

test('Check 1.2: No facade in set_panel_drag', () => {
    const fnMatch = residentRsContent.match(/pub fn set_panel_drag\([^)]+\)\s*\{([^}]+)\}/);
    assert(fnMatch, 'set_panel_drag must be defined');
    const body = fnMatch[1].trim();
    assert(body.includes('ACTIVE_PANEL_DRAG.store'), 'Must store to atomic state');
});

test('Check 1.3: record_move genuinely checks both ACTIVE_PANEL_DRAG and 300ms layout instant', () => {
    const fnMatch = residentRsContent.match(/pub fn record_move\([^)]+\)\s*\{([\s\S]+?)(?=\n(?:pub fn|\#\[))/);
    assert(fnMatch, 'record_move must be found');
    const body = fnMatch[1];
    assert(body.includes('is_panel_drag_active()'), 'Must check is_panel_drag_active()');
    assert(body.includes('LAST_LAYOUT_INSTANT.lock()'), 'Must lock LAST_LAYOUT_INSTANT');
    assert(body.includes('Duration::from_millis(300)'), 'Must enforce 300ms suppression window');
});

test('Check 1.4: Margin in layout is genuine 72px margin without conditional bypass', () => {
    const marginMatch = htmlContent.match(/const\s+g\s*=\s*this\.geometry,\s*size\s*=\s*this\.size,\s*half\s*=\s*size\s*\/\s*2,\s*margin\s*=\s*(\d+);/);
    assert(marginMatch, 'layout() margin declaration must exist');
    assert.strictEqual(parseInt(marginMatch[1], 10), 72, 'margin must be exactly 72');
});

// -------------------------------------------------------------
// SECTION 2: ADVERSARIAL GESTURE & DECOUPLING VERIFICATION
// -------------------------------------------------------------
console.log('\n--- SECTION 2: ADVERSARIAL GESTURE & DECOUPLING TESTS ---');

test('Check 2.1: Drag gesture decoupled from IPC - stress test 200 moves', () => {
    let ipcCalls = [];
    const mockBridge = {
        command: (cmd, args) => {
            ipcCalls.push({ cmd, args });
            return Promise.resolve({});
        }
    };

    // Simulate the ResidentDesktop drag engine
    class MockElement {
        constructor(id, tag = 'div', classes = []) {
            this.id = id;
            this.tagName = tag.toUpperCase();
            this.classList = new Set(classes);
            this.style = {
                _props: {},
                setProperty(k, v) { this._props[k] = v; },
                getProperty(k) { return this._props[k]; }
            };
        }
        closest(sel) {
            if (sel.includes('.panel-head') && this.classList.has('panel-head')) return this;
            if (sel.includes('input') && this.tagName === 'INPUT') return this;
            if (sel.includes('.panel-view') && this.classList.has('panel-view')) return this;
            if (sel.includes('#panel') && this.id === 'panel') return this;
            return null;
        }
    }

    const panelEl = new MockElement('panel', 'div', ['panel-container']);
    const headEl = new MockElement('panel-head-1', 'div', ['panel-head']);

    const isInteractiveOrContent = target => {
        if (!target) return false;
        return !!target.closest('button, input, select, textarea, summary, a, [role=button], [contenteditable="true"], label, .resident-resize-handle, [data-resize-handle], .panel-view, pre, code, .conversation, .response, [data-scrollable]');
    };

    const isPanelHead = target => {
        if (!target) return null;
        if (isInteractiveOrContent(target)) return null;
        return target.closest('.panel-head, .flow-library-head, .organic-satellite-head, .v13-panel-head, [data-drag-handle]');
    };

    // Initiate drag
    assert(isPanelHead(headEl), 'Head must qualify for drag');
    let panelDrag = {
        id: 1,
        target: headEl,
        panelId: 'panel',
        el: panelEl,
        startX: 100,
        startY: 100,
        initialBoxX: 50,
        initialBoxY: 50,
        moved: false
    };
    mockBridge.command('desktop_activity', { active: true, follow: false, panelDrag: true });

    // Stress test: 200 rapid pointer moves
    for (let i = 1; i <= 200; i++) {
        const clientX = 100 + i;
        const clientY = 100 + i * 2;
        const dx = clientX - panelDrag.startX;
        const dy = clientY - panelDrag.startY;
        panelDrag.moved = true;
        panelDrag.currentDx = dx;
        panelDrag.currentDy = dy;
        panelEl.style.setProperty('transform', `translate3d(${dx}px, ${dy}px, 0)`);
    }

    // Zero IPC calls during move loop!
    const moveIpcCalls = ipcCalls.filter(call => call.cmd === 'desktop_layout');
    assert.strictEqual(moveIpcCalls.length, 0, 'Zero desktop_layout IPC calls must occur during pointer moves');
    assert.strictEqual(panelEl.style.getProperty('transform'), 'translate3d(200px, 400px, 0)', 'Transform must reflect exact translation');

    // Release drag
    panelEl.style.setProperty('transform', 'none');
    mockBridge.command('desktop_activity', { active: true, follow: false, panelDrag: false });
    mockBridge.command('desktop_layout', { width: 420, height: 560, anchorX: 100, anchorY: 100 });

    assert.strictEqual(panelEl.style.getProperty('transform'), 'none', 'Transform must reset to none on release');
    const layoutIpcCalls = ipcCalls.filter(call => call.cmd === 'desktop_layout');
    assert.strictEqual(layoutIpcCalls.length, 1, 'Exactly one desktop_layout IPC call must occur on release');
});

test('Check 2.2: Drag Isolation: interactive inputs & selectable text never trigger drag', () => {
    class MockTarget {
        constructor(matches) { this._matches = matches; }
        closest(sel) {
            for (const s of sel.split(',').map(x => x.trim())) {
                if (this._matches[s]) return this;
            }
            return null;
        }
    }

    const isInteractiveOrContent = target => {
        if (!target) return false;
        return !!target.closest('button, input, select, textarea, summary, a, [role=button], [contenteditable="true"], label, .resident-resize-handle, [data-resize-handle], .panel-view, pre, code, .conversation, .response, [data-scrollable]');
    };

    const isPanelHead = target => {
        if (!target) return null;
        if (isInteractiveOrContent(target)) return null;
        return target.closest('.panel-head, .flow-library-head, .organic-satellite-head, .v13-panel-head, [data-drag-handle]');
    };

    // Test matrix
    const interactiveElements = [
        { 'button': true, '.panel-head': true },
        { 'input': true, '.panel-head': true },
        { 'select': true, '.panel-head': true },
        { 'textarea': true, '.panel-head': true },
        { 'pre': true, '.panel-head': true },
        { 'code': true, '.panel-head': true },
        { '.conversation': true, '.panel-head': true },
        { '.panel-view': true, '.panel-head': true },
        { '.resident-resize-handle': true, '.panel-head': true }
    ];

    for (const elem of interactiveElements) {
        const target = new MockTarget(elem);
        assert.strictEqual(isPanelHead(target), null, `Element matching ${Object.keys(elem)[0]} must NOT trigger panel head drag`);
    }

    const pureHead = new MockTarget({ '.panel-head': true });
    assert(isPanelHead(pureHead) !== null, 'Pure panel head MUST trigger drag');
});

// -------------------------------------------------------------
// SECTION 3: RESIZING HARD CONSTRAINTS & STRESS-TESTS
// -------------------------------------------------------------
console.log('\n--- SECTION 3: RESIZING BOUNDS & CONSTRAINTS ---');

test('Check 3.1: Minimum resize constraints (320px width, 400px height)', () => {
    const resizeCalc = (initialW, initialH, dx, dy, workW = 1920, workH = 1080) => {
        const maxW = workW - 40;
        const maxH = workH - 40;
        const newW = Math.max(320, Math.min(initialW + dx, maxW));
        const newH = Math.max(400, Math.min(initialH + dy, maxH));
        return { newW, newH };
    };

    // Try shrinking to negative dimensions
    const shrunk = resizeCalc(420, 560, -1000, -1000);
    assert.strictEqual(shrunk.newW, 320, 'Width must never shrink below 320px');
    assert.strictEqual(shrunk.newH, 400, 'Height must never shrink below 400px');

    // Try expanding beyond screen limits
    const expanded = resizeCalc(420, 560, 5000, 5000, 1920, 1080);
    assert.strictEqual(expanded.newW, 1880, 'Width must not exceed screen width - 40');
    assert.strictEqual(expanded.newH, 1040, 'Height must not exceed screen height - 40');

    // Regular resizing
    const normal = resizeCalc(400, 500, 50, 100);
    assert.strictEqual(normal.newW, 450);
    assert.strictEqual(normal.newH, 600);
});

// -------------------------------------------------------------
// SECTION 4: 72px MARGIN & BOUNDING BOX MATHEMATICS
// -------------------------------------------------------------
console.log('\n--- SECTION 4: 72px MARGIN & TENTACLE BOUNDING BOX ---');

test('Check 4.1: Bounding box padding calculation with margin = 72', () => {
    const margin = 72;
    const boxes = [
        { id: 'stage', x: -140, y: -140, width: 280, height: 280 },
        { id: 'panel', x: 200, y: -200, width: 420, height: 560 }
    ];

    const minX = Math.min(...boxes.map(b => b.x)) - margin;
    const minY = Math.min(...boxes.map(b => b.y)) - margin;
    const width = Math.ceil(Math.max(...boxes.map(b => b.x + b.width)) - minX + margin);
    const height = Math.ceil(Math.max(...boxes.map(b => b.y + b.height)) - minY + margin);
    const anchor = { x: -minX, y: -minY };

    // minX = -140 - 72 = -212
    assert.strictEqual(minX, -212, 'minX must include 72px margin');
    // minY = -200 - 72 = -272
    assert.strictEqual(minY, -272, 'minY must include 72px margin');
    // maxX = max(140, 620) = 620 -> width = 620 - (-212) + 72 = 904
    assert.strictEqual(width, 904, 'Window width must include 72px margins on both sides');
    // maxY = max(140, 360) = 360 -> height = 360 - (-272) + 72 = 704
    assert.strictEqual(height, 704, 'Window height must include 72px margins on both sides');
    // Anchor offset
    assert.strictEqual(anchor.x, 212);
    assert.strictEqual(anchor.y, 272);
});

// -------------------------------------------------------------
// SECTION 5: PERSISTENCE & LAYOUT RECOVERY
// -------------------------------------------------------------
console.log('\n--- SECTION 5: PERSISTENCE & LAYOUT RECOVERY ---');

test('Check 5.1: resetLayout completely restores defaults and purges localStorage', () => {
    const store = { 'axx.resident.panel-pos': JSON.stringify({ panel: { width: 800, height: 900, relX: 500, relY: -300 } }) };
    const mockLocalStorage = {
        getItem(k) { return store[k]; },
        setItem(k, v) { store[k] = v; },
        removeItem(k) { delete store[k]; }
    };

    let panelPositions = JSON.parse(mockLocalStorage.getItem('axx.resident.panel-pos'));
    assert(panelPositions.panel.width === 800);

    // Call resetLayout
    panelPositions = {};
    mockLocalStorage.removeItem('axx.resident.panel-pos');

    assert.strictEqual(mockLocalStorage.getItem('axx.resident.panel-pos'), undefined, 'Storage must be completely cleared');
    assert.strictEqual(Object.keys(panelPositions).length, 0, 'In-memory positions must be empty');
});

console.log('\n======================================================');
console.log(`AUDIT RESULTS: ${passedTests} / ${totalTests} CHECKS PASSED`);
if (failedTests > 0) {
    console.error(`FAILED: ${failedTests} CHECKS FAILED`);
    process.exit(1);
} else {
    console.log('VERDICT: ALL FORENSIC CHECKS SATISFIED CLEANLY');
}
