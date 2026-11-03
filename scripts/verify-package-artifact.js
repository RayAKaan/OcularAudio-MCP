#!/usr/bin/env node
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const root = path.resolve(__dirname, '..');
const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'ocular-audio-pack-'));

function run(command, args, options = {}) {
  return execFileSync(command, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], ...options }).trim();
}

try {
  const packed = JSON.parse(run('npm', ['pack', '--json', '--pack-destination', temporaryRoot], { cwd: root }));
  if (!Array.isArray(packed) || packed.length !== 1 || !packed[0].filename) {
    throw new Error('npm pack did not return exactly one package artifact');
  }

  const archive = path.join(temporaryRoot, packed[0].filename);
  if (!fs.existsSync(archive) || fs.statSync(archive).size === 0) {
    throw new Error('npm pack did not create a non-empty tarball');
  }

  const entries = run('tar', ['-tzf', archive]).split(/\r?\n/);
  const required = [
    'package/package.json',
    'package/bin/cli.js',
    'package/ocular_audio_mcp.py',
    'package/requirements.txt',
    'package/evidence_store.py',
    'package/protocol_contract.py',
    'package/docker/Dockerfile',
    'package/scripts/verify-release.js'
  ];
  const missing = required.filter((entry) => !entries.includes(entry));
  if (missing.length) throw new Error('Package tarball is missing: ' + missing.join(', '));

  fs.mkdirSync(path.join(temporaryRoot, 'unpacked'));
  run('tar', ['-xzf', archive, '-C', path.join(temporaryRoot, 'unpacked')]);
  const unpackedRoot = path.join(temporaryRoot, 'unpacked', 'package');
  const metadata = JSON.parse(fs.readFileSync(path.join(unpackedRoot, 'package.json'), 'utf8'));
  if (metadata.name !== 'ocular-audio-mcp' || metadata.version !== '1.3.0') {
    throw new Error('Packed package metadata does not match ocular-audio-mcp@1.3.0');
  }
  if (metadata.bin?.['ocular-audio'] !== './bin/cli.js') {
    throw new Error('Packed CLI executable mapping is invalid');
  }

  const cli = path.join(unpackedRoot, 'bin', 'cli.js');
  const version = run(process.execPath, [cli, '--version']);
  if (version !== metadata.version) throw new Error('Packed CLI version does not match package metadata');
  const help = run(process.execPath, [cli, '--help']);
  if (!help.includes('USAGE') || !help.includes('--transport')) {
    throw new Error('Packed CLI help output is incomplete');
  }

  console.log('Package artifact verified: ' + packed[0].filename + ' (' + packed[0].size + ' bytes).');
} finally {
  fs.rmSync(temporaryRoot, { recursive: true, force: true });
}
