#!/usr/bin/env node

const path = require('path');
const fs = require('fs');
const os = require('os');

const CACHE_DIR = path.join(os.homedir(), '.cache', 'ocular_audio_mcp');
const VERSION = require('../package.json').version;

// ── Color helper (with graceful fallback) ──────────────────────────────────
let chalk;
try {
  chalk = require('chalk');
} catch {
  // Fallback: no colors
  chalk = new Proxy({}, {
    get: () => new Proxy({}, {
      get: () => (s) => s
    })
  });
}

// ── Clipboard helper ────────────────────────────────────────────────────────
async function getClipboardy() {
  try {
    const clipboardy = await import('clipboardy');
    return clipboardy.default;
  } catch {
    return null;
  }
}

// ── Cache helpers ───────────────────────────────────────────────────────────
function ensureCacheDir() {
  if (!fs.existsSync(CACHE_DIR)) {
    fs.mkdirSync(CACHE_DIR, { recursive: true });
  }
}

function listCachedFiles() {
  ensureCacheDir();
  return fs.readdirSync(CACHE_DIR).filter(f => f.endsWith('.json'));
}

function getCacheStats() {
  const files = listCachedFiles();
  let totalSize = 0;
  const videos = [];
  for (const file of files) {
    const filePath = path.join(CACHE_DIR, file);
    const stat = fs.statSync(filePath);
    totalSize += stat.size;
    try {
      const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
      videos.push({
        id: file.replace('.json', ''),
        title: data.metadata?.title || '(unknown)',
        uploader: data.metadata?.uploader || '(unknown)',
        size: stat.size,
        age: Date.now() - stat.mtimeMs,
      });
    } catch {
      videos.push({ id: file.replace('.json', ''), title: '(corrupted)', uploader: '', size: stat.size, age: 0 });
    }
  }
  return { count: files.length, totalSize, videos };
}

function clearAllCache() {
  ensureCacheDir();
  const files = listCachedFiles();
  for (const file of files) {
    fs.unlinkSync(path.join(CACHE_DIR, file));
  }
  return files.length;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatAge(ms) {
  const days = Math.floor(ms / 86400000);
  if (days > 0) return `${days}d ago`;
  const hours = Math.floor(ms / 3600000);
  if (hours > 0) return `${hours}h ago`;
  const mins = Math.floor(ms / 60000);
  return `${mins}m ago`;
}

// ── Help text ───────────────────────────────────────────────────────────────
function showHelp() {
  console.log(`
OcularAudio MCP v${VERSION} — Video Transcript & Visual Context CLI

USAGE
  npx ocular-audio [options] <video_url>

OPTIONS
  -h, --help              Show this help message
  -v, --version           Show version number

  Output Control:
  --stdout                Print transcript to stdout only (no clipboard, no file)
  --no-clipboard          Skip clipboard copy (still saves file if --output not set)
  --output <file>         Write context to a specific file path
  --json                  Output raw JSON (metadata + transcript) for programmatic use

  Detail Level:
  --detail <level>        Legacy screenshot mode (default: auto)
                            overview  — Transcript only, no screenshots
                            balanced  — Screenshots at key visual moments
                            deep      — Screenshots at important moments
                            auto      — Adapts to video length and content

  --analysis-depth <level> Universal ingestion depth
                            glance      — Minimal, fastest
                            understand  — Recommended default
                            deep        — High-fidelity analysis
                            omniscient  — Maximum practical preservation

  OCR:
  --visual-index          Build the persistent visual evidence index
  --visual-search <q>    Search indexed visual OCR evidence
  --frame-at <seconds>    Capture a higher-resolution frame at a timestamp
  --frame-burst <s> <r> <n>
                          Capture a bounded frame burst around a timestamp
  --hybrid-search <q>   Search transcript + visual evidence
  --semantic-weight <w> Hybrid semantic weight (0..1)
  --multimodal-search <q>
                          Search unified transcript + visual + OCR moments
  --multimodal           Analyze unified multimodal evidence
  --ocr                   Extract text from screenshots using Tesseract OCR
                            Requires: brew install tesseract (macOS) / choco install tesseract (Windows) / apt install tesseract-ocr (Linux)
                            Also requires: pip install pytesseract

  Cache Control:
  --force                 Bypass cache and re-process the video
  --list-cached           List all cached videos with titles
  --cache-info            Show cache statistics (count, size, oldest/newest)
  --clear-cache           Delete all cached transcripts and screenshots

  Verbosity:
  --verbose               Show detailed progress information
  --quiet                 Suppress summary and status messages

  System:
  --check                 Check system dependencies (Python, FFmpeg, Whisper, Tesseract)

EXAMPLES
  npx ocular-audio "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  npx ocular-audio --stdout "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  npx ocular-audio --detail overview --output transcript.txt "URL"
  npx ocular-audio --json "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  npx ocular-audio --ocr "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  npx ocular-audio --force "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  npx ocular-audio --check
  npx ocular-audio --list-cached
  npx ocular-audio --cache-info
  npx ocular-audio --clear-cache
`);
}

// ── Parse arguments ─────────────────────────────────────────────────────────
const args = process.argv.slice(2);

let detailLevel = 'auto';
let analysisDepth = 'understand';
let targetUrl = null;
let stdoutMode = false;
let noClipboard = false;
let outputFile = null;
let jsonMode = false;
let listCached = false;
let cacheInfo = false;
let clearCache = false;
let enableOcr = false;
let checkMode = false;
let forceMode = false;
let verboseMode = false;
let quietMode = false;
let visualIndexMode = false;
let visualSearchQuery = null;
let frameAt = null;
let frameBurst = null;
let hybridSearchQuery = null;
let semanticWeight = null;
let multimodalSearchQuery = null;
let multimodalMode = false;

for (let i = 0; i < args.length; i++) {
  const arg = args[i];

  if (arg === '-h' || arg === '--help') {
    showHelp();
    process.exit(0);
  }
  if (arg === '-v' || arg === '--version') {
    console.log(VERSION);
    process.exit(0);
  }
  if (arg === '--stdout') {
    stdoutMode = true;
    continue;
  }
  if (arg === '--no-clipboard') {
    noClipboard = true;
    continue;
  }
  if (arg === '--json') {
    jsonMode = true;
    continue;
  }
  if (arg === '--ocr') {
    enableOcr = true;
    continue;
  }
  if (arg === '--visual-index') {
    visualIndexMode = true;
    continue;
  }
  if (arg === '--visual-search' && i + 1 < args.length) {
    visualSearchQuery = args[++i];
    continue;
  }
  if (arg === '--frame-at' && i + 1 < args.length) {
    frameAt = args[++i];
    continue;
  }
  if (arg === '--frame-burst' && i + 3 < args.length) {
    frameBurst = [args[++i], args[++i], args[++i]];
    continue;
  }
  if (arg === '--hybrid-search' && i + 1 < args.length) {
    hybridSearchQuery = args[++i];
    continue;
  }
  if (arg === '--semantic-weight' && i + 1 < args.length) {
    semanticWeight = args[++i];
    continue;
  }
  if (arg === '--multimodal-search' && i + 1 < args.length) {
    multimodalSearchQuery = args[++i];
    continue;
  }
  if (arg === '--multimodal') {
    multimodalMode = true;
    continue;
  }
  if (arg === '--check') {
    checkMode = true;
    continue;
  }
  if (arg === '--force') {
    forceMode = true;
    continue;
  }
  if (arg === '--verbose') {
    verboseMode = true;
    continue;
  }
  if (arg === '--quiet') {
    quietMode = true;
    continue;
  }
  if (arg === '--list-cached') {
    listCached = true;
    continue;
  }
  if (arg === '--cache-info') {
    cacheInfo = true;
    continue;
  }
  if (arg === '--clear-cache') {
    clearCache = true;
    continue;
  }
  if (arg === '--detail' && i + 1 < args.length) {
    const valid = ['overview', 'balanced', 'deep', 'auto'];
    const val = args[i + 1].toLowerCase();
    if (valid.includes(val)) {
      detailLevel = val;
    } else {
      console.error(`[ERROR] Invalid detail level: ${args[i + 1]}`);
      console.error(`  Valid options: ${valid.join(', ')}`);
      process.exit(1);
    }
    i++;
    continue;
  }
  if (arg === '--analysis-depth' && i + 1 < args.length) {
    const valid = ['glance', 'understand', 'deep', 'omniscient', 'minimal', 'standard', 'normal', 'maximum', 'extreme'];
    const val = args[i + 1].toLowerCase();
    if (valid.includes(val)) {
      analysisDepth = val;
    } else {
      console.error(`[ERROR] Invalid analysis depth: ${args[i + 1]}`);
      console.error(`  Valid options: glance, understand, deep, omniscient`);
      process.exit(1);
    }
    i++;
    continue;
  }
  if (arg === '--output' && i + 1 < args.length) {
    outputFile = args[i + 1];
    i++;
    continue;
  }
  if (!arg.startsWith('-')) {
    targetUrl = arg;
  }
}

// ── Handle cache commands (no URL required) ─────────────────────────────────
if (listCached) {
  const files = listCachedFiles();
  if (files.length === 0) {
    console.log(chalk.gray('[INFO] No cached videos found.'));
    console.log(chalk.gray(`[INFO] Cache directory: ${CACHE_DIR}`));
    process.exit(0);
  }
  console.log(chalk.cyan(`\nCached Videos (${files.length} total):\n`));
  const stats = getCacheStats();
  for (const v of stats.videos) {
    console.log(chalk.white(`  ${v.id}  ${chalk.bold(v.title)}`));
    console.log(chalk.gray(`           by ${v.uploader} | ${formatBytes(v.size)} | ${formatAge(v.age)}`));
  }
  console.log(chalk.gray(`\nCache: ${CACHE_DIR}\n`));
  process.exit(0);
}

if (cacheInfo) {
  const stats = getCacheStats();
  if (stats.count === 0) {
    console.log(chalk.gray('[INFO] Cache is empty.'));
    console.log(chalk.gray(`[INFO] Cache directory: ${CACHE_DIR}`));
    process.exit(0);
  }
  const oldest = stats.videos.reduce((a, b) => (a.age > b.age ? a : b));
  const newest = stats.videos.reduce((a, b) => (a.age < b.age ? a : b));
  console.log(chalk.cyan(`\nCache Statistics:`));
  console.log(chalk.white(`  Location:   ${CACHE_DIR}`));
  console.log(chalk.white(`  Videos:     ${stats.count}`));
  console.log(chalk.white(`  Total size: ${formatBytes(stats.totalSize)}`));
  console.log(chalk.gray(`  Oldest:     ${oldest.id} (${oldest.title}) — ${formatAge(oldest.age)}`));
  console.log(chalk.gray(`  Newest:     ${newest.id} (${newest.title}) — ${formatAge(newest.age)}\n`));
  process.exit(0);
}

if (clearCache) {
  const count = clearAllCache();
  console.log(chalk.green(`[SUCCESS] Cleared ${count} cached video(s) from ${CACHE_DIR}`));
  process.exit(0);
}

// ── Handle --check mode ─────────────────────────────────────────────────────
if (checkMode) {
  console.log(chalk.cyan('[INFO] Checking system capabilities...\n'));
  const { spawn } = require('child_process');
  const pythonScriptPath = path.join(__dirname, '..', 'ocular_audio_mcp.py');
  const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';

  const checkProcess = spawn(pythonCmd, [pythonScriptPath, '--check'], {
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  let checkStdout = '';
  let checkStderr = '';

  checkProcess.stdout.on('data', (data) => {
    checkStdout += data.toString();
  });

  checkProcess.stderr.on('data', (data) => {
    checkStderr += data.toString();
  });

  checkProcess.on('close', (code) => {
    if (code === 0 && checkStdout) {
      console.log(checkStdout);
    } else {
      console.error('[ERROR] Failed to check capabilities.');
      if (checkStderr) console.error(checkStderr);
    }
    process.exit(code);
  });

  checkProcess.on('error', (error) => {
    if (error.code === 'ENOENT') {
      console.error('[ERROR] Python not found. Please install Python 3.9+ and add it to your PATH.');
    } else {
      console.error(`[ERROR] Failed to start Python: ${error.message}`);
    }
    process.exit(1);
  });

  // Don't exit here, let the process handle it
  return;
}

// ── Validate URL ────────────────────────────────────────────────────────────
if (!targetUrl) {
  console.error(chalk.red('[ERROR] No video URL provided.'));
  console.error(chalk.gray('Usage: npx ocular-audio [options] <video_url>'));
  console.error(chalk.gray('Run with --help for more information.'));
  process.exit(1);
}

const localSource = fs.existsSync(targetUrl) && fs.statSync(targetUrl).isFile();
if (!localSource && !/^https?:\/\/|^rtmp(?:s|e|t|ts)?:\/\//i.test(targetUrl)) {
  console.error(chalk.red('[ERROR] Invalid media source.'));
  console.error(chalk.gray('Provide an http(s)/rtmp URL or an existing local media file.'));
  process.exit(1);
}

// ── Build Python arguments ──────────────────────────────────────────────────
const pythonScriptPath = path.join(__dirname, '..', 'ocular_audio_mcp.py');
const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';

const pyArgs = [pythonScriptPath, targetUrl, detailLevel, '--analysis-depth', analysisDepth];
if (stdoutMode) pyArgs.push('--stdout');
if (noClipboard) pyArgs.push('--no-clipboard');
if (jsonMode) pyArgs.push('--json');
if (enableOcr) pyArgs.push('--ocr');
if (visualIndexMode) pyArgs.push('--visual-index');
if (visualSearchQuery !== null) pyArgs.push('--visual-search', visualSearchQuery);
if (frameAt !== null) pyArgs.push('--frame-at', frameAt);
if (frameBurst) pyArgs.push('--frame-burst', ...frameBurst);
if (hybridSearchQuery !== null) pyArgs.push('--hybrid-search', hybridSearchQuery);
if (semanticWeight !== null) pyArgs.push('--semantic-weight', semanticWeight);
if (multimodalSearchQuery !== null) pyArgs.push('--multimodal-search', multimodalSearchQuery);
if (multimodalMode) pyArgs.push('--multimodal');
if (forceMode) pyArgs.push('--force');
if (verboseMode) pyArgs.push('--verbose');
if (quietMode) pyArgs.push('--quiet');
if (outputFile) {
  pyArgs.push('--output');
  pyArgs.push(outputFile);
}

// ── Print header ────────────────────────────────────────────────────────────
if (!stdoutMode && !jsonMode && !quietMode) {
  console.log(chalk.cyan(`[INFO] OcularAudio MCP v${VERSION}`));
  console.log(chalk.gray(`[INFO] Detail level: ${detailLevel}`));
  console.log(chalk.gray(`[INFO] Analysis depth: ${analysisDepth}`));
  if (forceMode) console.log(chalk.yellow(`[INFO] Cache bypass: enabled`));
  if (outputFile) console.log(chalk.gray(`[INFO] Output file: ${outputFile}`));
  console.log(chalk.gray(`[INFO] Processing...\n`));
}

// ── Spawn Python process ────────────────────────────────────────────────────
const { spawn } = require('child_process');

const pythonProcess = spawn(pythonCmd, pyArgs, {
  stdio: ['ignore', 'pipe', 'pipe'],
  windowsHide: true,
});

// 5-minute timeout
const SPAWN_TIMEOUT_MS = 5 * 60 * 1000;
const timeoutId = setTimeout(() => {
  console.error(`[ERROR] Process timed out after ${SPAWN_TIMEOUT_MS / 1000}s. Killing...`);
  pythonProcess.kill('SIGTERM');
  process.exit(1);
}, SPAWN_TIMEOUT_MS);

let stdout = '';
let stderr = '';

pythonProcess.stdout.on('data', (data) => {
  stdout += data.toString();
});

// Stream stderr as real-time progress indicators
pythonProcess.stderr.on('data', (data) => {
  const line = data.toString().trim();
  if (line && !stdoutMode) {
    // Show Python [INFO] messages as progress (only in non-quiet modes)
    if (verboseMode) {
      // In verbose mode, show all progress messages
      process.stderr.write(`  ${line}\n`);
    } else if (line.includes('PROGRESS:')) {
      // Always show PROGRESS messages (stripped of the PROGRESS: prefix)
      const cleanLine = line.replace(/\[.*?\]\s*PROGRESS:\s*/, '  ');
      process.stderr.write(`  ${cleanLine}\n`);
    }
  }
  stderr += data.toString();
});

pythonProcess.on('error', (error) => {
  clearTimeout(timeoutId);
  if (error.code === 'ENOENT') {
    console.error(chalk.red('\n[ERROR] Python not found. Please install Python 3.9+ and add it to your PATH.\n'));
    console.error(chalk.gray('  Windows:  Download from https://python.org'));
    console.error(chalk.gray('  macOS:    brew install python3'));
    console.error(chalk.gray('  Linux:    sudo apt install python3 python3-pip\n'));
    console.error(chalk.gray('  Then install dependencies:'));
    console.error(chalk.gray(`    pip install -r ${path.join(__dirname, '..', 'requirements.txt')}\n`));
  } else {
    console.error(chalk.red(`[ERROR] Failed to start Python: ${error.message}`));
  }
  process.exit(1);
});

pythonProcess.on('close', async (code) => {
  clearTimeout(timeoutId);

  if (code !== 0) {
    console.error(chalk.red(`\n[ERROR] Python process exited with code ${code}`));
    if (stderr) {
      // Parse stderr for actionable error messages
      if (stderr.includes('No local ASR engines found')) {
        console.error(chalk.yellow('\n  Missing Whisper engine. Install one:'));
        console.error(chalk.gray('    pip install faster-whisper'));
        console.error(chalk.gray('    — OR —'));
        console.error(chalk.gray('    pip install openai-whisper torch\n'));
      } else if (stderr.includes('Audio track download failed')) {
        console.error(chalk.yellow('\n  Failed to download audio. Possible fixes:'));
        console.error(chalk.gray('    1. Check your internet connection'));
        console.error(chalk.gray('    2. For age-restricted videos, add cookies.txt (see README)'));
        console.error(chalk.gray('    3. Ensure FFmpeg is installed: ffmpeg -version\n'));
      } else if (stderr.includes('Failed to extract a playable video stream')) {
        console.error(chalk.yellow('\n  Cannot extract video stream. Possible causes:'));
        console.error(chalk.gray('    1. Video may be private or geo-blocked'));
        console.error(chalk.gray('    2. Try adding cookies.txt (see README)'));
        console.error(chalk.gray('    3. Verify the video is still available\n'));
      } else if (stderr.includes('invalid video URL or ID')) {
        console.error(chalk.yellow('\n  Could not parse video ID from URL.'));
        console.error(chalk.gray('  Expected format: https://www.youtube.com/watch?v=XXXXXXXXXXX'));
        console.error(chalk.gray('  Got: ' + targetUrl + '\n'));
      } else {
        // Generic fallback — show raw stderr
        console.error(chalk.red(`\n[STDERR]: ${stderr.slice(-500)}`));
      }
    }
    process.exit(1);
  }

  // Success — output the transcript
  if (stdout) {
    console.log(stdout);
  }

  // Skip status messages in stdout-only or json modes
  if (stdoutMode || jsonMode) {
    return;
  }

  // Handle clipboard / file output on the Node side as well
  // (Python side also handles this, but the CLI wrapper adds a secondary safety net)
  if (outputFile && !stdout.includes('[SUCCESS:')) {
    // Python may not have written the file (old version), write it here
    const formattedPrompt = `Please analyze this video thoroughly using the verified video data, uploader chapters, and complete transcript provided below.\n\n--- VIDEO CONTEXT ---\n${stdout}`;
    try {
      fs.writeFileSync(outputFile, formattedPrompt, 'utf-8');
      console.log(chalk.green(`\n[SUCCESS: Saved to ${path.resolve(outputFile)}]`));
    } catch (e) {
      console.error(chalk.red(`[ERROR] Failed to write output file: ${e.message}`));
    }
  }
});
