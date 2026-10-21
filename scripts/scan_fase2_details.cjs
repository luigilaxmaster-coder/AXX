const fs = require('fs');

const content = fs.readFileSync('1.AXX/Axx.html', 'utf8');

// Find all occurrences of panel-description
const lines = content.split('\n');
console.log('--- PANEL DESCRIPTIONS ---');
lines.forEach((line, idx) => {
  if (line.includes('panel-description') || line.includes('scope-note') || line.includes('bottom-hint')) {
    console.log(`L${idx+1}: ${line.trim().slice(0, 140)}`);
  }
});

// Check details / advanced options in panels
console.log('\n--- ADVANCED SECTIONS / CONTROLS ---');
lines.forEach((line, idx) => {
  if (line.includes('advanced') || line.includes('opciones-avanzadas') || line.includes('config-avanzada')) {
    if (line.includes('<button') || line.includes('<details') || line.includes('<section') || line.includes('<div')) {
      console.log(`L${idx+1}: ${line.trim().slice(0, 140)}`);
    }
  }
});
