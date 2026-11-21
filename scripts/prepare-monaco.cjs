/** Bundle the pinned local editor; the WebView never loads code from a CDN. */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const source = path.join(root, 'node_modules/monaco-editor');
const version = require('../package.json').dependencies['monaco-editor'];
assert.equal(JSON.parse(fs.readFileSync(path.join(source, 'package.json'), 'utf8')).version, version);
const target = path.join(root, '1.AXX/scripts/vendor', 'monaco-' + version);
fs.mkdirSync(target, { recursive: true });
fs.cpSync(path.join(source, 'min/vs'), path.join(target, 'vs'), { recursive: true });
fs.copyFileSync(path.join(source, 'LICENSE'), path.join(target, 'LICENSE'));
assert(fs.statSync(path.join(target, 'vs/loader.js')).size > 0);
assert(fs.statSync(path.join(target, 'vs/editor/editor.main.js')).size > 0);
console.log('Prepared local Monaco ' + version);
