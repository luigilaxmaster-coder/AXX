const fs = require('fs');
const path = require('path');
const vm = require('vm');

const scripts = [
    '1.AXX/scripts/native-voice.js',
    '1.AXX/scripts/command-library.js',
    '1.AXX/scripts/axx-connect.js'
];

for (const s of scripts) {
    const fullPath = path.resolve(process.cwd(), s);
    if (!fs.existsSync(fullPath)) {
        console.error(`Missing script: ${s}`);
        continue;
    }
    const code = fs.readFileSync(fullPath, 'utf8');
    try {
        new vm.Script(code, { filename: path.basename(s) });
        console.log(`Syntax check ${s}: PASSED (${code.length} chars)`);
    } catch (e) {
        console.error(`Syntax check ${s}: FAILED!`, e);
    }
}
