// Empirical Challenge Test Harness: Tentacle Clipping & Margin Verification
// Milestone 2 Challenger 2

const fs = require('fs');
const assert = require('assert');

console.log('=== Empirical Verification: Tentacle Clipping & Margin Invariants ===');

// --- 1. Static DOM & Code Invariants from 1.AXX/Axx.html ---
const html = fs.readFileSync('1.AXX/Axx.html', 'utf8');

// Assert margin = 72 in ResidentDesktop.layout()
const marginMatch = html.match(/const\s+g\s*=\s*this\.geometry,\s*size\s*=\s*this\.size,\s*half\s*=\s*size\s*\/\s*2,\s*margin\s*=\s*(\d+);/);
assert(marginMatch, 'ResidentDesktop.layout() must define margin');
const definedMargin = Number(marginMatch[1]);
assert.strictEqual(definedMargin, 72, `margin must be exactly 72px, found: ${definedMargin}`);
console.log('PASS: ResidentDesktop.layout() margin is verified as 72px');

// Assert resize handle styling and creation
assert(html.includes("handle.className = 'resident-resize-handle';"), 'Resize handle class missing');
assert(html.includes(".resident-resize-handle"), 'Resize handle CSS missing');
assert(html.includes("ensureResizeHandles()"), 'ensureResizeHandles method missing');
console.log('PASS: Interactive resize handles verified in frontend');

// Assert drag decoupling: transform used during pointermove, zero desktop_layout calls
assert(html.includes("pd.el.style.setProperty('transform', `translate3d(${dx}px, ${dy}px, 0)`, 'important');"), 'Pointer move must use local CSS transform');
assert(html.includes("isInteractiveOrContent"), 'Drag must check isInteractiveOrContent');
console.log('PASS: Panel drag gesture decoupling and input isolation verified');

// Assert layout reset function
assert(html.includes("resetLayout()"), 'resetLayout() method missing');
assert(html.includes("'axx.resident.panel-pos'"), 'localStorage panel-pos persistence key verified');
console.log('PASS: Layout persistence and resetLayout recovery mechanism verified');

// --- 2. Mathematical Simulation of Organic Tendril Geometry & Window Boundary Clipping ---

function flowArmRadius(t) {
    t = Math.max(0, Math.min(1, t));
    const body = 8.1 + 23 * Math.pow(1 - t, 2.6) + 4.2 * Math.pow(t, 5);
    const cap = Math.sqrt(Math.max(0, Math.min(1, (1 - t) / 0.055)));
    return body * cap;
}

function organicCurve(a, b, t, phase, quiet = false) {
    t = Math.max(0, Math.min(1, t));
    const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy);
    if (len < 0.001) return { x: a.x, y: a.y };
    const nx = -dy / len, ny = dx / len, s = Math.sin(Math.PI * t);
    const bend = (b.x >= a.x ? -1 : 1) * Math.min(52, len * 0.16) * s;
    const ripple = (quiet || phase === 0) ? 0 : Math.sin(t * 5.4 - phase * 0.9) * Math.min(5, len * 0.017) * s * s;
    return { x: a.x + dx * t + nx * (bend + ripple), y: a.y + dy * t + ny * (bend + ripple) };
}

function actionArmOffset(a, b, t, width) {
    if (b.y - a.y < 120 || Math.abs(b.x - a.x) > 150) return 0;
    const sign = a.x > width * 0.55 ? -1 : 1;
    return sign * Math.sin(Math.PI * Math.max(0, Math.min(1, t))) * Math.min(125, width * 0.31);
}

// Compute full 3D tube vertex bounds inside the transparent OS window
function simulateTendrilAndLayout({
    size = 280,
    margin = 72,
    panelRelX = 200,
    panelRelY = -100,
    panelWidth = 420,
    panelHeight = 560,
    actionMode = false,
    quiet = false,
    phase = 1.0,
    musicPause = false,
    progress = 1.0
}) {
    const half = size / 2;
    const boxes = [
        { id: 'stage', x: -half, y: -half, width: size, height: size },
        { id: 'panel', x: panelRelX, y: panelRelY, width: panelWidth, height: panelHeight }
    ];

    const minX = Math.min(...boxes.map(b => b.x)) - margin;
    const minY = Math.min(...boxes.map(b => b.y)) - margin;
    const windowWidth = Math.ceil(Math.max(...boxes.map(b => b.x + b.width)) - minX + margin);
    const windowHeight = Math.ceil(Math.max(...boxes.map(b => b.y + b.height)) - minY + margin);

    const anchor = { x: -minX, y: -minY };

    // Body position in window coordinates
    const body = { x: anchor.x, y: anchor.y, size };

    // Panel box in window coordinates
    const panelBox = {
        x: anchor.x + panelRelX,
        y: anchor.y + panelRelY,
        width: panelWidth,
        height: panelHeight
    };

    // Calculate link target inside panel
    let end;
    if (windowWidth < 900) {
        end = { x: panelBox.x + panelBox.width * 0.5, y: panelBox.y + 18 };
    } else {
        end = {
            x: body.x > panelBox.x + panelBox.width / 2 ? panelBox.x + panelBox.width - 18 : panelBox.x + 18,
            y: Math.max(panelBox.y + 70, Math.min(panelBox.y + panelBox.height - 50, body.y + 15))
        };
    }

    const rootX = body.x + (musicPause ? (end.x >= body.x ? 1 : -1) * body.size * 0.098 : 0);
    const rootY = body.y;

    const link = {
        a: { x: rootX, y: rootY },
        b: end,
        progress
    };

    const p = Math.max(0, Math.min(1, link.progress));
    const point = (t) => {
        const q = organicCurve(link.a, link.b, t, phase, quiet);
        if (actionMode) {
            q.x += actionArmOffset(link.a, link.b, t, windowWidth);
        }
        return q;
    };

    const U = 24, V = 56;
    const totalDist = Math.hypot(link.b.x - link.a.x, link.b.y - link.a.y);
    const thinFactor = Math.max(0.42, Math.min(1.0, 240 / Math.max(240, totalDist * 0.75)));
    const thickness = 1.10;

    let minVertexX = Infinity, maxVertexX = -Infinity;
    let minVertexY = Infinity, maxVertexY = -Infinity;

    for (let j = 0; j <= V; j++) {
        const t = j / V;
        const center = point(t * p);
        const prev = point(Math.max(0, t - 0.003) * p);
        const next = point(Math.min(1, t + 0.003) * p);
        const dx = next.x - prev.x, dy = next.y - prev.y;
        const len = Math.hypot(dx, dy) || 1;
        const nx = -dy / len, ny = dx / len;
        const waveFactor = (quiet || phase === 0) ? 1 : (1 + 0.035 * Math.sin(t * 7 - phase * 1.4) * Math.sin(t * Math.PI));
        const rad = Math.max(2.5, flowArmRadius(t) * thinFactor) * thickness * (0.45 + 0.55 * Math.sqrt(p)) * waveFactor;

        for (let i = 0; i <= U; i++) {
            const theta = (i / U) * Math.PI * 2;
            const co = Math.cos(theta);
            const vx = center.x + nx * rad * co;
            const vy = center.y + ny * rad * co;

            if (vx < minVertexX) minVertexX = vx;
            if (vx > maxVertexX) maxVertexX = vx;
            if (vy < minVertexY) minVertexY = vy;
            if (vy > maxVertexY) maxVertexY = vy;
        }
    }

    const clearanceLeft = minVertexX - 0;
    const clearanceRight = windowWidth - maxVertexX;
    const clearanceTop = minVertexY - 0;
    const clearanceBottom = windowHeight - maxVertexY;
    const minClearance = Math.min(clearanceLeft, clearanceRight, clearanceTop, clearanceBottom);

    return {
        windowWidth,
        windowHeight,
        minVertexX,
        maxVertexX,
        minVertexY,
        maxVertexY,
        clearanceLeft,
        clearanceRight,
        clearanceTop,
        clearanceBottom,
        minClearance
    };
}

// Run 5,000 Stress Scenarios across parameter space
console.log('Running 5,000 multi-parameter stress tests for tentacle clipping...');

let totalTests = 0;
let minOverallClearance = Infinity;
let worstScenario = null;

const avatarSizes = [160, 240, 280, 400, 530, 640];
const panelWidths = [320, 420, 500, 700];
const panelHeights = [400, 560, 750, 900];
const panelRelativePlacements = [
    // Standard right / left / top / bottom / diagonal
    { x: 150, y: -150 },
    { x: 300, y: -280 },
    { x: -500, y: -200 },
    { x: -450, y: 100 },
    { x: 50, y: 200 },
    { x: 0, y: -450 },
    { x: 0, y: 350 },
    { x: -350, y: -350 },
    { x: 350, y: 350 }
];

for (const size of avatarSizes) {
    for (const pw of panelWidths) {
        for (const ph of panelHeights) {
            for (const pos of panelRelativePlacements) {
                for (const quiet of [false, true]) {
                    for (const actionMode of [false, true]) {
                        for (const musicPause of [false, true]) {
                            for (let phaseStep = 0; phaseStep < 4; phaseStep++) {
                                const phase = (phaseStep / 4) * Math.PI * 2;
                                totalTests++;
                                const result = simulateTendrilAndLayout({
                                    size,
                                    margin: 72,
                                    panelRelX: pos.x,
                                    panelRelY: pos.y,
                                    panelWidth: pw,
                                    panelHeight: ph,
                                    actionMode,
                                    quiet,
                                    phase,
                                    musicPause,
                                    progress: 1.0
                                });

                                if (result.minClearance < minOverallClearance) {
                                    minOverallClearance = result.minClearance;
                                    worstScenario = { size, pw, ph, pos, quiet, actionMode, phase, musicPause, result };
                                }

                                assert(result.clearanceLeft >= 0, `Left clipping: clearance=${result.clearanceLeft}`);
                                assert(result.clearanceRight >= 0, `Right clipping: clearance=${result.clearanceRight}`);
                                assert(result.clearanceTop >= 0, `Top clipping: clearance=${result.clearanceTop}`);
                                assert(result.clearanceBottom >= 0, `Bottom clipping: clearance=${result.clearanceBottom}`);
                            }
                        }
                    }
                }
            }
        }
    }
}

console.log(`PASS: Tested ${totalTests} extreme geometrical configurations with ZERO clipping.`);
console.log(`Global Minimum Clearance to OS Window Boundary: ${minOverallClearance.toFixed(3)}px`);
console.log('Worst-case scenario details:', {
    avatarSize: worstScenario.size,
    panelWidth: worstScenario.pw,
    panelHeight: worstScenario.ph,
    pos: worstScenario.pos,
    minClearance: worstScenario.result.minClearance.toFixed(3)
});

// Comparison against old margin = 12
console.log('\nTesting counterfactual: Old margin = 12px under the worst-case scenario...');
const oldMarginResult = simulateTendrilAndLayout({
    size: worstScenario.size,
    margin: 12,
    panelRelX: worstScenario.pos.x,
    panelRelY: worstScenario.pos.y,
    panelWidth: worstScenario.pw,
    panelHeight: worstScenario.ph,
    actionMode: worstScenario.actionMode,
    quiet: worstScenario.quiet,
    phase: worstScenario.phase,
    musicPause: worstScenario.musicPause,
    progress: 1.0
});
console.log(`With old margin = 12px, minimum clearance: ${oldMarginResult.minClearance.toFixed(3)}px`);
if (oldMarginResult.minClearance < 0) {
    console.log(`CONFIRMED BUG IN LEGACY CODE: Old margin=12 clipped tendril by ${Math.abs(oldMarginResult.minClearance).toFixed(3)}px!`);
} else {
    console.log(`Old margin clearance: ${oldMarginResult.minClearance.toFixed(3)}px`);
}

console.log('\nALL EMPIRICAL TENTACLE CLIPPING ASSERTIONS PASSED!');

module.exports = { simulateTendrilAndLayout, flowArmRadius, organicCurve };
