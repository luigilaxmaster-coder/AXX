const fs = require("fs");
const html = fs.readFileSync("1.AXX/Axx.html", "utf8");
const regex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
let match;
let count = 0;
while ((match = regex.exec(html)) !== null) {
    count++;
    const code = match[1];
    try {
        new Function(code);
        console.log(`Script #${count} syntax is VALID! Length: ${code.length}`);
    } catch (e) {
        console.error(`Script #${count} ERROR: ${e.message}`);
        process.exit(1);
    }
}
console.log(`All ${count} scripts verified!`);
