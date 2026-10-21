const fs = require('fs');
const path = require('path');
const vm = require('vm');

const axxPath = path.resolve(process.cwd(), '1.AXX/Axx.html');
const content = fs.readFileSync(axxPath, 'utf8');

// Extract script between <script>"use strict"; and </script>
const startIdx = content.indexOf('<script>"use strict";');
const endIdx = content.indexOf('</script><script src="scripts/native-voice.js">');

console.log('Script indices:', startIdx, endIdx);
if (startIdx !== -1 && endIdx !== -1) {
    const scriptCode = content.substring(startIdx + '<script>'.length, endIdx);
    console.log('Script length in characters:', scriptCode.length);
    try {
        new vm.Script(scriptCode, { filename: 'Axx.html.inline.js' });
        console.log('Syntax check: PASSED (no syntax errors)');
    } catch (err) {
        console.error('Syntax check: FAILED!', err);
    }
} else {
    console.log('Could not find exact script bounds!');
}
