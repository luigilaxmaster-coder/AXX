const fs = require('fs');
const path = require('path');

const axxPath = path.resolve(process.cwd(), '1.AXX/Axx.html');
const content = fs.readFileSync(axxPath, 'utf8');

// 1. Inspect DOM structure: all elements with id or class related to panels, views, buttons
const idMatches = [...content.matchAll(/id="([^"]+)"/g)].map(m => m[1]);
console.log('Total unique IDs in Axx.html:', new Set(idMatches).size);

const views = idMatches.filter(id => id.startsWith('view-') || id.includes('panel') || id.includes('flow-'));
console.log('\nViews & Flow IDs:', views);

// 2. Search for all panel-view or data-view occurrences
const panelViews = [...content.matchAll(/id="(view-[^"]+)"/g)].map(m => m[1]);
console.log('\nPanel views found:', panelViews);

// 3. Search for event listeners attached in JS
console.log('\n--- Event Listeners Search ---');
const addEventListenerMatches = [];
const lines = content.split('\n');
lines.forEach((line, idx) => {
    if (line.includes('addEventListener(') || line.includes('.onclick =') || line.includes('.onmousedown =') || line.includes('.onpointerdown =')) {
        addEventListenerMatches.push({ line: idx + 1, code: line.trim() });
    }
});
console.log('Total event listener attachments:', addEventListenerMatches.length);

// 4. Specifically look for avatar click / touch handling
console.log('\n--- Avatar / Stage / Canvas Event Handlers ---');
addEventListenerMatches.filter(m => 
    m.code.includes('avatar') || m.code.includes('stage') || m.code.includes('canvas')
).forEach(m => console.log(`  Line ${m.line}: ${m.code.slice(0, 140)}`));

// 5. Look for radial / dock / flow-fan buttons and handlers
console.log('\n--- Radial / Dock / Tool Buttons ---');
addEventListenerMatches.filter(m => 
    m.code.includes('flow-') || m.code.includes('dock') || m.code.includes('orbit') || m.code.includes('quick') || m.code.includes('tool')
).forEach(m => console.log(`  Line ${m.line}: ${m.code.slice(0, 140)}`));
