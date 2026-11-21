/** Build from source so the pinned sanitizer override reaches the shipped editor. */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const { build } = require('esbuild');
const root = path.resolve(__dirname, '..'), config = require('../package.json');
const source = path.join(root, 'node_modules/monaco-editor');
const version = config.dependencies['monaco-editor'];
assert.equal(JSON.parse(fs.readFileSync(path.join(source, 'package.json'), 'utf8')).version, version);
assert.equal(require('dompurify').version, config.overrides.dompurify);
const target = path.join(root, '1.AXX/scripts/vendor', 'monaco-' + version + '-esm');
const entry = path.join(root, 'build/monaco-entry.mjs');
fs.mkdirSync(path.dirname(entry), { recursive: true });
fs.mkdirSync(target, { recursive: true });
fs.writeFileSync(entry, "export * from 'monaco-editor/editor/editor.api.js';\nimport 'monaco-editor/basic-languages/monaco.contribution.js';\n");
(async () => {
  const result = await build({absWorkingDir:root,entryPoints:{editor:entry,
    'editor.worker':path.join(source,'esm/vs/editor/editor.worker.js')},outdir:target,
    bundle:true,splitting:true,format:'esm',platform:'browser',minify:true,
    loader:{'.ttf':'file'},legalComments:'external',metafile:true});
  assert(Object.keys(result.metafile.inputs).some(input => input.includes('dompurify/')));
  fs.copyFileSync(path.join(source,'LICENSE'),path.join(target,'LICENSE'));
  fs.copyFileSync(path.join(root,'node_modules/dompurify/LICENSE'),path.join(target,'DOMPURIFY-LICENSE'));
  assert(fs.statSync(path.join(target,'editor.js')).size > 0);
  assert(fs.statSync(path.join(target,'editor.worker.js')).size > 0);
  console.log('Prepared Monaco ' + version + ' with DOMPurify ' + config.overrides.dompurify);
})().catch(error => { console.error(error); process.exitCode = 1; });
