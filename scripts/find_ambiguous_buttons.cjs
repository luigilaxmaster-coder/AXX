const fs = require('fs');

const content = fs.readFileSync('1.AXX/Axx.html', 'utf8');

// Find all buttons in HTML template (around lines 1350 - 1700)
const htmlSegment = content.slice(content.indexOf('<body'), content.indexOf('<script'));
const buttonRegex = /<button([^>]*)>([\s\S]*?)<\/button>/gi;
let match;
const ambiguous = [];
while ((match = buttonRegex.exec(htmlSegment)) !== null) {
  const attrs = match[1];
  const inner = match[2].trim().replace(/\s+/g, ' ');
  // Check if text is just a symbol or icon, or very short punctuation
  const stripped = inner.replace(/<[^>]+>/g, '').trim();
  if (stripped.length <= 2 || !/[a-zA-ZáéíóúÁÉÍÓÚñÑ]/.test(stripped)) {
    ambiguous.push({ attrs: attrs.trim(), inner, text: stripped });
  }
}

console.log('Ambiguous buttons in template:', ambiguous.length);
ambiguous.forEach((b, i) => console.log(`${i+1}. [${b.text}] attrs: ${b.attrs.slice(0, 100)}`));

// Also check buttons created dynamically in JS
console.log('\n--- Dynamic buttons in minimalChat / OrganicDesk / Flow ---');
const dynamicButtonRegex = /document\.createElement\('button'\)[^;]*;[^;]*\.textContent\s*=\s*['"]([^'"]+)['"]/g;
while ((match = dynamicButtonRegex.exec(content)) !== null) {
  console.log('Dynamic button text:', match[1]);
}
