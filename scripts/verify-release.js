#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const root = path.resolve(__dirname, '..');
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const server = JSON.parse(fs.readFileSync(path.join(root, 'server.json'), 'utf8'));
const expectedSourceVersion = '1.3.0';
const registryVersion = server.packages?.[0]?.version;
const validVersion = (value) => /^\d+\.\d+\.\d+$/.test(value || '');
const versionParts = (value) => value.split('.').map(Number);
const isNewer = (candidate, reference) => {
  const a = versionParts(candidate);
  const b = versionParts(reference);
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) return a[i] > b[i];
  }
  return false;
};
if (pkg.version !== expectedSourceVersion || server.version !== expectedSourceVersion) {
  throw new Error('Local source/package version must remain 1.3.0');
}
if (!validVersion(registryVersion)) {
  throw new Error('MCP registry package version must be an explicit semantic version');
}
if (isNewer(registryVersion, pkg.version)) {
  throw new Error('MCP registry cannot reference a package newer than this source checkout');
}
if (pkg.name !== 'ocular-audio-mcp' || pkg.bin?.['ocular-audio'] !== './bin/cli.js') throw new Error('NPM package metadata is invalid');
if (!pkg.files.includes('ocular_audio_mcp.py')) throw new Error('Python server missing from package allowlist');
for (const required of ['README.md','LICENSE','requirements.txt']) if (!fs.existsSync(path.join(root, required))) throw new Error(required+' missing');
execFileSync(process.execPath, ['--check', path.join(root, 'bin', 'cli.js')], {stdio:'ignore'});
console.log('OcularAudio source v' + pkg.version + ': metadata OK; MCP registry manifest targets v' + registryVersion + '.');
