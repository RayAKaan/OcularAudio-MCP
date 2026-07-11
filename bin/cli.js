#!/usr/bin/env node

const { exec } = require('child_process');
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
if (args.length === 0 || args[0] === '-h' || args[0] === '--help') {
  console.log(`
OcularAudio MCP: Multi-Platform Video Transcript & Visual CLI

Usage:
  npx ocular-audio <video_url>

Options:
  -h, --help       Show this help message
  -v, --version    Show version number

Examples:
  npx ocular-audio "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  npx ocular-audio "https://vimeo.com/76979871"
`);
  process.exit(0);
}

if (args[0] === '-v' || args[0] === '--version') {
  const pkg = require('../package.json');
  console.log(pkg.version);
  process.exit(0);
}

const targetUrl = args[0];
const pythonScriptPath = path.join(__dirname, '..', 'ocular_audio_mcp.py');

// Detect Python command based on platform
const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';

console.log(`[INFO] OcularAudio MCP CLI v${require('../package.json').version}`);
console.log(`[INFO] Executing Python backend...`);

// Use spawn for better control over stdio and larger output handling
const { spawn } = require('child_process');

const pythonProcess = spawn(pythonCmd, [pythonScriptPath, targetUrl], {
  stdio: ['ignore', 'pipe', 'pipe'],
  timeout: 300000, // 5 minute timeout
  windowsHide: true,
});

let stdout = '';
let stderr = '';

pythonProcess.stdout.on('data', (data) => {
  stdout += data.toString();
});

pythonProcess.stderr.on('data', (data) => {
  stderr += data.toString();
});

pythonProcess.on('error', (error) => {
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

  // Print the transcript output
  console.log(stdout);

  // Build the prompt context for clipboard
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
