const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('1.AXX/Axx.html', 'utf8');
const scriptRegex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
let match;
let scriptIndex = 0;
let errors = 0;

while ((match = scriptRegex.exec(html)) !== null) {
    const srcMatch = match[0].match(/src=["']([^"']+)["']/i);
    if (srcMatch) {
        console.log(`Script ${scriptIndex}: external src="${srcMatch[1]}" (skipped)`);
    } else {
        const code = match[1];
        if (code.trim().length === 0) continue;
        try {
            new vm.Script(code, { filename: `inline-script-${scriptIndex}.js` });
            console.log(`Script ${scriptIndex}: syntax VALID (${code.length} chars)`);
        } catch (err) {
            console.error(`Script ${scriptIndex}: SYNTAX ERROR:`, err);
            errors++;
        }
    }
    scriptIndex++;
}

if (errors === 0) {
    console.log('All inline scripts validated successfully with Node vm.Script!');
} else {
    process.exit(1);
}
