const fs = require('fs');
const txt = fs.readFileSync('1.AXX/Axx.html', 'utf8');
const lines = txt.split('\n');
lines.forEach((l, i) => {
    if (l.includes('.axx-resident') || l.includes('resident-invoked')) {
        console.log(`Line ${i + 1}: ${l.slice(0, 110)}`);
    }
});
