#!/usr/bin/env sh
set -eu
npm install
npm run check
npm pack
echo "Inspect ocular-audio-mcp-1.3.0.tgz before publishing."
