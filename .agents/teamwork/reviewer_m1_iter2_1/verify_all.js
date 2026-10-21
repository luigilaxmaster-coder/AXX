const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

console.log('--- Starting Independent Review Verification ---');

// 1. Read files
const html = fs.readFileSync('1.AXX/Axx.html', 'utf8');
const rs = fs.readFileSync('src-tauri/src/lib.rs', 'utf8');

// 2. Focus 1: LiquidRenderer.hitMask() threshold
console.log('[Test 1] Checking LiquidRenderer.hitMask() threshold...');
const hitMaskMatch = html.match(/hitMask\(cols\s*=\s*64,\s*rows\s*=\s*64\)\s*\{[\s\S]*?return\s*\{[\s\S]*?\};\s*\}/g);
assert(hitMaskMatch && hitMaskMatch.length >= 2, 'Could not find hitMask definitions');
assert(hitMaskMatch[0].includes('> 16 ? 1 : 0'), 'LiquidRenderer.hitMask does not contain "> 16 ? 1 : 0"');
assert(!hitMaskMatch[0].includes('> 96'), 'LiquidRenderer.hitMask still contains "> 96"');
assert(!hitMaskMatch[0].includes('> 100'), 'LiquidRenderer.hitMask contains "> 100"');
console.log('  PASS: LiquidRenderer.hitMask() threshold is verified as > 16 (not > 96).');

// 3. Focus 2: interactiveRegions() excludes #stage / #avatar
console.log('[Test 2] Checking interactiveRegions() exclusion of #stage / #avatar...');
const irIdx = html.indexOf('interactiveRegions() {');
assert(irIdx !== -1, 'interactiveRegions() method not found');
const irSlice = html.slice(irIdx, irIdx + 500);
assert(!irSlice.includes('stage'), 'interactiveRegions() contains reference to stage');
assert(!irSlice.includes('avatar'), 'interactiveRegions() contains reference to avatar');
assert(irSlice.includes('document.querySelectorAll'), 'interactiveRegions() must query UI elements');
console.log('  PASS: interactiveRegions() excludes #stage / #avatar completely.');

// 4. Focus 3: Throttling window.emit("axx-cursor") in lib.rs
console.log('[Test 3] Checking cursor throttle in src-tauri/src/lib.rs...');
assert(rs.includes('let mut last_x = i32::MIN;'), 'Missing last_x initialization');
assert(rs.includes('let mut last_y = i32::MIN;'), 'Missing last_y initialization');
assert(rs.includes('if point.x != last_x || point.y != last_y {'), 'Missing throttling conditional on point.x / point.y');
assert(rs.includes('last_x = point.x;'), 'Missing last_x update');
assert(rs.includes('last_y = point.y;'), 'Missing last_y update');
console.log('  PASS: cursor emission is strictly throttled to point.x != last_x || point.y != last_y.');

// 5. Check JS syntax for all script blocks
console.log('[Test 4] Checking JavaScript syntax across all script blocks in Axx.html...');
const scriptRegex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
let match, count = 0;
while ((match = scriptRegex.exec(html)) !== null) {
    count++;
    new vm.Script(match[1]);
}
assert(count >= 5, 'Expected at least 5 script blocks in Axx.html');
console.log(`  PASS: All ${count} script blocks compiled cleanly without syntax errors.`);

console.log('--- ALL INDEPENDENT VERIFICATION TESTS PASSED ---');
