#!/usr/bin/env node

const path = require('path');
const fs = require('fs');

async function getClipboardy() {
  try {
    const clipboardy = await import('clipboardy');
    return clipboardy.default;
  } catch (e) {
    return null;
  }
}

const args = process.argv.slice(2);

// Parse arguments
let detailLevel = 'auto';
let targetUrl = null;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '-h' || args[i] === '--help') {
    console.log(`
OcularAudio MCP: Multi-Platform Video Transcript & Visual CLI

Usage:
  npx ocular-audio [options] <video_url>

Options:
  -h, --help              Show this help message
  -v, --version           Show version number
  --detail <level>        Set detail level: overview, balanced, deep, auto (default: auto)
                            overview  - Transcript only, no screenshots (fastest)
                            balanced  - Screenshots at key visual moments
                            deep      - Screenshots at every important moment
                            auto      - Adapts to video length and content (default)

Examples:
  npx ocular-audio "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  npx ocular-audio --detail overview "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  npx ocular-audio --detail deep "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
`);
    process.exit(0);
  }
  if (args[i] === '-v' || args[i] === '--version') {
    const pkg = require('../package.json');
    console.log(pkg.version);
    process.exit(0);
  }
  if (args[i] === '--detail' && i + 1 < args.length) {
    const valid = ['overview', 'balanced', 'deep', 'auto'];
    const val = args[i + 1].toLowerCase();
    if (valid.includes(val)) {
      detailLevel = val;
    } else {
      console.error(`[ERROR] Invalid detail level: ${args[i + 1]}`);
      console.error(`  Valid options: ${valid.join(', ')}`);
      process.exit(1);
    }
    i++; // skip the value
    continue;
  }
  if (!args[i].startsWith('-')) {
    targetUrl = args[i];
  }
}

if (!targetUrl) {
  console.error('[ERROR] No video URL provided.');
  console.error('Usage: npx ocular-audio [options] <video_url>');
  console.error('Run with --help for more information.');
  process.exit(1);
}

if (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://')) {
  console.error('[ERROR] Invalid URL. Must start with http:// or https://');
  process.exit(1);
}

const pythonScriptPath = path.join(__dirname, '..', 'ocular_audio_mcp.py');
const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';

console.log(`[INFO] OcularAudio MCP CLI v${require('../package.json').version}`);
console.log(`[INFO] Detail level: ${detailLevel}`);
console.log(`[INFO] Executing Python backend...`);

const { spawn } = require('child_process');

const pythonProcess = spawn(pythonCmd, [pythonScriptPath, targetUrl, detailLevel], {
  stdio: ['ignore', 'pipe', 'pipe'],
  windowsHide: true,
});

// Timeout after 5 minutes (spawn does not support timeout option)
const SPAWN_TIMEOUT_MS = 5 * 60 * 1000;
const timeoutId = setTimeout(() => {
  console.error(`[ERROR] Process timed out after ${SPAWN_TIMEOUT_MS / 1000}s. Killing...`);
  pythonProcess.kill('SIGTERM');
}, SPAWN_TIMEOUT_MS);

let stdout = '';
let stderr = '';

pythonProcess.stdout.on('data', (data) => {
  stdout += data.toString();
});

pythonProcess.stderr.on('data', (data) => {
  stderr += data.toString();
});

pythonProcess.on('error', (error) => {
  clearTimeout(timeoutId);
  if (error.code === 'ENOENT') {
    console.error(`[ERROR] Python not found. Please install Python 3.9+ and ensure it's in your PATH.`);
    console.error(`  - Windows: Download from https://python.org`);
    console.error(`  - macOS: brew install python3`);
    console.error(`  - Linux: sudo apt install python3`);
  } else {
    console.error(`[ERROR] Failed to start Python: ${error.message}`);
  }
  process.exit(1);
});

pythonProcess.on('close', async (code) => {
  clearTimeout(timeoutId);
  if (code !== 0) {
    console.error(`[ERROR] Python script exited with code ${code}`);
    if (stderr) {
      console.error(`[STDERR]: ${stderr}`);
    }
    process.exit(1);
  }

  if (stderr && !stdout) {
    console.error(`[WARNINGS]: ${stderr}`);
  }

  console.log(stdout);

  const formattedPrompt = `Please analyze this video thoroughly using the verified video data, uploader chapters, and complete transcript provided below.

--- VIDEO CONTEXT ---
${stdout}`;

  const clipboardy = await getClipboardy();
  if (clipboardy) {
    try {
      clipboardy.writeSync(formattedPrompt);
      console.log("============================================================");
      console.log("[SUCCESS: Context Copied to Clipboard]");
      console.log("[INSTRUCTION: Paste the clipboard contents inside Claude Web/ChatGPT]");
      console.log("============================================================\n");
    } catch (e) {
      fallbackSave(formattedPrompt);
    }
  } else {
    fallbackSave(formattedPrompt);
  }
});

function fallbackSave(content) {
  const outputFile = path.join(process.cwd(), 'video_context.txt');
  try {
    fs.writeFileSync(outputFile, content, 'utf-8');
    console.log("============================================================");
    console.log("[SUCCESS: Transcribed Successfully]");
    console.log(`[INFO: Saved context block to: ${outputFile}]`);
    console.log("[INSTRUCTION: Upload or copy the contents of the text file directly into your Web AI model]");
    console.log("============================================================\n");
  } catch (writeError) {
    console.error("[ERROR] Failed to write fallback text file:", writeError.message);
  }
}
