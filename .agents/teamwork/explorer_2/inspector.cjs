const fs = require('fs');
const path = require('path');

const axxPath = path.resolve(process.cwd(), '1.AXX/Axx.html');
const refPath = path.resolve(process.cwd(), 'reference/Axx_reference_v20.html');

console.log('Inspecting Axx.html at:', axxPath);
const axxContent = fs.readFileSync(axxPath, 'utf8');
const lines = axxContent.split('\n');
console.log('Total lines in Axx.html:', lines.length);

// Find classes
const classes = [];
lines.forEach((line, idx) => {
    const m = line.match(/^\s*class\s+([A-Za-z0-9_]+)/);
    if (m) {
        classes.push({ line: idx + 1, name: m[1] });
    }
});
console.log('Classes found (' + classes.length + '):');
classes.forEach(c => console.log(`  Line ${c.line}: ${c.name}`));

// Find top-level instances on Axx namespace
const instances = [];
lines.forEach((line, idx) => {
    const m = line.match(/Axx\.([A-Za-z0-9_]+)\s*=/);
    if (m) {
        instances.push({ line: idx + 1, expr: m[0].trim() });
    }
});
console.log('\nAxx properties assigned (' + instances.length + '):');
instances.slice(0, 100).forEach(i => console.log(`  Line ${i.line}: ${i.expr}`));
