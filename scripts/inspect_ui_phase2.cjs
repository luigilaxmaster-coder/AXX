const fs = require('fs');

const content = fs.readFileSync('1.AXX/Axx.html', 'utf8');
console.log('Total length:', content.length);

// Find panel templates or panels in DOM
const classMatches = content.match(/class=["'][^"']*(?:panel|card|modal|dialog|satellite|dock|sheet)[^"']*["']/gi) || [];
const uniqueClasses = [...new Set(classMatches)].slice(0, 30);
console.log('Unique UI classes:', uniqueClasses);

// Search for duplicated helper texts or instructions
const textBlocks = content.match(/<(?:p|small|span|div)[^>]*class=["'][^"']*(?:hint|desc|sub|help|instr|note)[^"']*["'][^>]*>([^<]+)<\//gi) || [];
console.log('Helper text count:', textBlocks.length);
console.log('Sample helper texts:', textBlocks.slice(0, 10));

// Find buttons with text or ambiguous icons
const buttons = content.match(/<button[^>]*>([\s\S]*?)<\/button>/gi) || [];
console.log('Total buttons:', buttons.length);
console.log('Sample buttons:', buttons.slice(0, 15).map(b => b.replace(/\s+/g, ' ').slice(0, 80)));
