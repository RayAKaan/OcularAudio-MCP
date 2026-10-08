#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const root = path.resolve(__dirname, '..');
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const server = JSON.parse(fs.readFileSync(path.join(root, 'server.json'), 'utf8'));
const expected = '1.3.0';
if (pkg.version !== expected || server.version !== expected || server.packages?.[0]?.version !== expected) throw new Error('All release versions must be 1.3.0');
if (pkg.name !== 'ocular-audio-mcp' || pkg.bin?.['ocular-audio'] !== './bin/cli.js') throw new Error('NPM package metadata is invalid');
if (!pkg.files.includes('ocular_audio_mcp.py')) throw new Error('Python server missing from package allowlist');
for (const required of ['README.md','LICENSE','requirements.txt']) if (!fs.existsSync(path.join(root, required))) throw new Error(required+' missing');
execFileSync(process.execPath, ['--check', path.join(root, 'bin', 'cli.js')], {stdio:'ignore'});
console.log('OcularAudio v1.3.0 release metadata: OK');
