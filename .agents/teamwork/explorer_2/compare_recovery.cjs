const fs = require('fs');
const path = require('path');

const rootPath = path.resolve(process.cwd(), '1.AXX/Axx.html');
const recoveryPath = path.resolve(process.cwd(), 'build/recovery-0.22.5-20261020/1.AXX/Axx.html');

const rootContent = fs.readFileSync(rootPath, 'utf8');
const recContent = fs.readFileSync(recoveryPath, 'utf8');

console.log('Root size:', rootContent.length, 'Recovery size:', recContent.length);

const rootLines = rootContent.split('\n');
const recLines = recContent.split('\n');
console.log('Root lines:', rootLines.length, 'Recovery lines:', recLines.length);

let diffCount = 0;
const maxDiffs = 10;
for (let i = 0; i < Math.max(rootLines.length, recLines.length); i++) {
    const l1 = rootLines[i] || '';
    const l2 = recLines[i] || '';
    if (l1 !== l2) {
        diffCount++;
        if (diffCount <= maxDiffs) {
            console.log(`Diff at line ${i + 1}:`);
            console.log(`  Root:     ${l1.slice(0, 100)}`);
            console.log(`  Recovery: ${l2.slice(0, 100)}`);
        }
    }
}
console.log('Total line differences:', diffCount);
