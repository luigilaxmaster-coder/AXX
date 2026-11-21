/** Resolve renderer fixtures exactly as nested script URLs, without leaving the asset root. */
const path = require('node:path');

function scriptPath(url) {
  const pathname = decodeURIComponent(url.split('?')[0]);
  if (!pathname.startsWith('/scripts/')) throw new Error('Expected a renderer script URL');
  const file = path.resolve(__dirname, pathname.slice('/scripts/'.length));
  const relative = path.relative(__dirname, file);
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('Asset outside script root');
  return file;
}

module.exports = { scriptPath };

if (require.main === module) {
  const assert = require('node:assert/strict'), fs = require('node:fs');
  const html = fs.readFileSync(path.join(__dirname, '../Axx.html'), 'utf8');
  const urls = [...html.matchAll(/(?:src|href)="(scripts\/[^"?#]+)(?:[?#][^"]*)?"/g)].map(match => '/' + match[1]);
  assert(urls.some(url => url.includes('/magic-pen/scene-history.js')));
  for (const url of urls) assert(fs.statSync(scriptPath(url + '?v=test')).isFile(), url);
  for (const url of ['/scripts/../Axx.html', '/scripts/%2e%2e/Axx.html', '/scripts/..\\Axx.html', '/other.js']) {
    assert.throws(() => scriptPath(url));
  }
  console.log(`Renderer static assets: ${urls.length} nested and legacy URLs passed`);
}
