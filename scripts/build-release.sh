#!/usr/bin/env sh
set -eu
npm ci
npm run check
npm run verify:package
npm pack
echo "Inspect ocular-audio-mcp-1.3.1.tgz and its SHA-256 checksum before publishing."
