const fs = require('fs');
const path = require('path');

const axxPath = path.resolve(process.cwd(), '1.AXX/Axx.html');
const content = fs.readFileSync(axxPath, 'utf8');
const lines = content.split('\n');

lines.forEach((line, idx) => {
    if (line.includes('id="panel"') || line.includes("id='panel'")) {
        console.log(`Line ${idx + 1}: ${line.slice(0, 160)}`);
    }
});
