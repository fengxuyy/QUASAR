import express, { type NextFunction, type Request, type Response } from 'express';
import { WebSocketServer, WebSocket } from 'ws';
import { spawn, spawnSync, ChildProcess } from 'child_process';
import path from 'path';
import fs from 'fs';
import os from 'os';
import { createHash, randomBytes, timingSafeEqual } from 'crypto';
import { fileURLToPath } from 'url';
import type { IPty } from 'node-pty';
import multer from 'multer';
import {
  isAllowedResolvedPath,
  resolveSafeWorkspacePath,
  safePathError,
  safePathHttpStatus,
} from './pathSecurity.js';
import { loadPersistedSettings, savePersistedSettings } from './settingsPersistence.js';

type NodePtyModule = typeof import('node-pty');
let nodePtyModule: NodePtyModule | null = null;
let nodePtyLoadAttempted = false;

async function loadNodePty(): Promise<NodePtyModule | null> {
  if (!nodePtyLoadAttempted) {
    nodePtyLoadAttempted = true;
    try {
      nodePtyModule = await import('node-pty');
    } catch (err) {
      console.warn(
        '[Terminal] Optional module "node-pty" is unavailable; built-in terminal is disabled:',
        err instanceof Error ? err.message : String(err),
      );
      nodePtyModule = null;
    }
  }
  return nodePtyModule;
}

const upload = multer({ dest: path.join(os.tmpdir(), 'quasar-uploads') });

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const pythonCommand = process.env.QUASAR_PYTHON || 'python3';

const app = express();
app.use(express.json({ limit: '50mb' }));
const port = Number(process.env.PORT || process.env.QUASAR_WEB_PORT || 3001);
const configuredWebToken = process.env.QUASAR_WEB_TOKEN || process.env.WEB_UI_TOKEN || '';
const webAuthToken = configuredWebToken || randomBytes(32).toString('base64url');
const webTokenSource = configuredWebToken ? 'QUASAR_WEB_TOKEN' : 'generated';
const WEB_AUTH_COOKIE = 'quasar_web_token';

function getWorkspaceDir(): string {
  const raw = (process.env.WORKSPACE_DIR || process.env.HOME || '/workspace').trim();
  if (raw === '~') return os.homedir();
  if (raw.startsWith('~/') || raw.startsWith('~\\')) {
    return path.join(os.homedir(), raw.slice(2));
  }
  return path.resolve(raw);
}

function tokenMatches(candidate: unknown): boolean {
  if (typeof candidate !== 'string' || !candidate) {
    return false;
  }

  const expected = Buffer.from(webAuthToken);
  const provided = Buffer.from(candidate);
  return provided.length === expected.length && timingSafeEqual(provided, expected);
}

function extractBearerToken(headerValue: string | undefined): string {
  if (!headerValue) return '';
  const match = headerValue.match(/^Bearer\s+(.+)$/i);
  return match?.[1]?.trim() || '';
}

function extractCookieToken(cookieHeader: string | undefined): string {
  if (!cookieHeader) return '';
  const cookie = cookieHeader
    .split(';')
    .map(part => part.trim())
    .find(part => part.startsWith(`${WEB_AUTH_COOKIE}=`));
  if (!cookie) return '';
  try {
    return decodeURIComponent(cookie.slice(WEB_AUTH_COOKIE.length + 1));
  } catch {
    return '';
  }
}

function extractHttpAuthToken(req: Request): string {
  return (
    extractBearerToken(req.header('authorization')) ||
    req.header('x-quasar-web-token') ||
    extractCookieToken(req.header('cookie')) ||
    (typeof req.query.token === 'string' ? req.query.token : '') ||
    (typeof req.query.quasar_token === 'string' ? req.query.quasar_token : '')
  );
}

function extractWebSocketAuthToken(req: any): string {
  const requestUrl = new URL(req.url || '/', `http://${req.headers?.host || 'localhost'}`);
  return (
    extractBearerToken(req.headers?.authorization) ||
    req.headers?.['x-quasar-web-token'] ||
    extractCookieToken(req.headers?.cookie) ||
    requestUrl.searchParams.get('token') ||
    requestUrl.searchParams.get('quasar_token') ||
    ''
  );
}

function setWebAuthCookieFromQuery(req: Request, res: Response, next: NextFunction) {
  const queryToken = typeof req.query.token === 'string'
    ? req.query.token
    : (typeof req.query.quasar_token === 'string' ? req.query.quasar_token : '');

  if (tokenMatches(queryToken)) {
    res.cookie(WEB_AUTH_COOKIE, queryToken, {
      httpOnly: true,
      sameSite: 'strict',
      secure: req.secure || req.header('x-forwarded-proto') === 'https',
    });
  }

  next();
}

function requireWebAuth(req: Request, res: Response, next: NextFunction) {
  if (tokenMatches(extractHttpAuthToken(req))) {
    next();
    return;
  }

  res.setHeader('WWW-Authenticate', 'Bearer realm="QUASAR Web UI"');
  res.status(401).json({ error: 'Unauthorized' });
}

const bindHost = (process.env.QUASAR_BIND_HOST || '').trim();

// Create HTTP server (bind all interfaces by default so Docker port forwarding works; set QUASAR_BIND_HOST=127.0.0.1 to restrict)
const onListen = () => {
  console.log(`Bridge server running on ${bindHost ? `http://${bindHost}:${port}` : `port ${port}`}`);
  if (webTokenSource === 'generated') {
    console.warn('QUASAR_WEB_TOKEN is not set. Generated a one-time Web UI token for this server process.');
    console.warn(`Open the Web UI with: http://127.0.0.1:${port}/?token=${webAuthToken}`);
  } else {
    console.log('Web UI token protection enabled. Open the Web UI with ?token=<QUASAR_WEB_TOKEN>.');
  }
};
const server = bindHost ? app.listen(port, bindHost, onListen) : app.listen(port, onListen);

// Serve static files
const distPath = (process.env.QUASAR_WEB_STATIC_DIR || '').trim() || path.join(__dirname, '../dist');
if (process.env.NODE_ENV === 'production' || process.env.SERVE_STATIC === 'true') {
  console.log(`Serving static files from: ${distPath}`);
  app.use(setWebAuthCookieFromQuery);
  app.use(express.static(distPath));
}

app.use('/api', requireWebAuth);

// Create WebSocket server
const wss = new WebSocketServer({ server });

let pythonProcess: ChildProcess | null = null;
let messageBuffer: any[] = [];
let isAwaitingPlanConfirmation = false;
let isExecutionRunning = false;
let ragPreloaded = false;
let ragPreloadFailed = false;
let latestInitStatus: { status: string; message: string } = {
  status: 'initializing',
  message: 'Initializing system...',
};
let userSettings: Record<string, string> = {};
let latestUpdateEvent: any | null = null;
let latestThoughtStream: any | null = null;
let latestTaskProgress: any | null = null;
let latestContextUsage: any | null = null;

// PTY sessions per WebSocket client
const ptyProcesses = new Map<WebSocket, IPty>();

const WEB_TERMINAL_CLI_DISABLED_MESSAGE = 'The QUASAR CLI is disabled inside the Web UI terminal to avoid conflicts with the active web session. Use the Web UI controls, or open a separate terminal outside the Web UI.';
const WEB_TERMINAL_GUARD_BIN_DIR = path.join(process.env.TMPDIR || '/tmp', 'quasar-web-terminal-bin');

const QUASAR_ARCHIVE_DIR = 'quasar_archive';
const QUASAR_LOGS_DIR = 'quasar_logs';
const ARCHIVE_RUN_ID_PATTERN = /^quasar_run_\d{8}_\d{6}_[0-9a-f]{6}(?:_\d+)?$/;
const NEW_ARCHIVE_RUN_ID_PATTERN = /^quasar_run_(\d{8})_(\d{6})_([0-9a-f]{6})(?:_(\d+))?$/;
const FILE_TREE_IGNORED_DIRS = new Set([
  'node_modules',
  'dist',
  'dist-server',
  'build',
  'coverage',
  '__pycache__',
  '.pytest_cache',
  '.mypy_cache',
  '.ruff_cache',
  '.cache',
  'site-packages',
  'lost+found',
]);
const HISTORY_PREVIEW_BYTES = 24 * 1024;
const BRIDGE_MESSAGE_BUFFER_LIMIT = 2000;
const WS_BACKPRESSURE_LIMIT_BYTES = 2 * 1024 * 1024;
const TERMINAL_OUTPUT_FLUSH_MS = 16;
const TERMINAL_OUTPUT_FLUSH_BYTES = 16 * 1024;

type CheckpointCacheEntry = {
  key: string;
  value: any;
};

let checkpointInfoCache: CheckpointCacheEntry | null = null;
const archiveTraceCache = new Map<string, CheckpointCacheEntry>();
const structureProcessCache = new Map<string, any>();
const STRUCTURE_PROCESS_TIMEOUT_MS = 30000;
const STRUCTURE_PROCESS_CACHE_LIMIT = 20;

function getFileSignature(filePath: string): string | null {
  try {
    const stat = fs.statSync(filePath);
    // SQLite often mutates via -wal/-shm; include those so checkpoint metadata
    // is not served from a stale cache after operator work advances.
    let signature = `${stat.size}:${stat.mtimeMs}`;
    for (const suffix of ['-wal', '-shm']) {
      try {
        const side = fs.statSync(`${filePath}${suffix}`);
        signature += `|${suffix}:${side.size}:${side.mtimeMs}`;
      } catch {
        signature += `|${suffix}:missing`;
      }
    }
    return signature;
  } catch {
    return null;
  }
}

function waitForPythonProcessExit(timeoutMs = 2000): Promise<void> {
  if (!pythonProcess) return Promise.resolve();
  const proc = pythonProcess;
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      resolve();
    };
    proc.once('close', finish);
    proc.once('exit', finish);
    setTimeout(() => {
      if (pythonProcess === proc) {
        try {
          pythonProcess.kill('SIGKILL');
        } catch {
          // ignore
        }
        pythonProcess = null;
      }
      finish();
    }, timeoutMs);
  });
}

function readTextFileContent(filePath: string, maxSize = 0, offset = 0) {
  const stat = fs.statSync(filePath);
  if (stat.isDirectory()) {
    throw new Error('Cannot read directory content');
  }

  if (maxSize > 0) {
    const safeOffset = Math.max(0, Math.min(offset, stat.size));
    const bytesToRead = Math.max(0, Math.min(maxSize, stat.size - safeOffset));
    const fd = fs.openSync(filePath, 'r');
    try {
      const buffer = Buffer.alloc(bytesToRead);
      const bytesRead = fs.readSync(fd, buffer, 0, bytesToRead, safeOffset);
      return {
        content: buffer.subarray(0, bytesRead).toString('utf-8'),
        totalSize: stat.size,
        truncated: safeOffset + bytesRead < stat.size,
        offset: safeOffset,
        nextOffset: safeOffset + bytesRead,
      };
    } finally {
      fs.closeSync(fd);
    }
  }

  const content = fs.readFileSync(filePath, 'utf-8');
  return {
    content,
    totalSize: stat.size,
    truncated: false,
    offset: 0,
    nextOffset: stat.size,
  };
}

function readTextPreview(filePath: string, maxBytes = HISTORY_PREVIEW_BYTES): string {
  if (!fs.existsSync(filePath)) return '';
  const result = readTextFileContent(filePath, maxBytes);
  if (!result.truncated) return result.content;
  return `${result.content}\n\n... [truncated for responsive preview]`;
}

function listArchiveRuns(workspaceDir: string): Array<{ id: string; path: string }> {
  const runs: Array<{ id: string; path: string }> = [];
  const archiveRoot = path.join(workspaceDir, QUASAR_ARCHIVE_DIR);
  if (!fs.existsSync(archiveRoot) || !fs.statSync(archiveRoot).isDirectory()) {
    return runs;
  }

  for (const item of fs.readdirSync(archiveRoot)) {
    const runPath = path.join(archiveRoot, item);
    if (ARCHIVE_RUN_ID_PATTERN.test(item) && fs.statSync(runPath).isDirectory()) {
      runs.push({ id: item, path: runPath });
    }
  }
  return runs;
}

function findArchiveRunPath(workspaceDir: string, runId: string): string | null {
  if (!ARCHIVE_RUN_ID_PATTERN.test(runId)) return null;

  const runPath = path.join(workspaceDir, QUASAR_ARCHIVE_DIR, runId);
  if (fs.existsSync(runPath) && fs.statSync(runPath).isDirectory()) {
    return runPath;
  }
  return null;
}

function findRunLogFile(runPath: string, filename: string): string | null {
  const candidate = path.join(runPath, QUASAR_LOGS_DIR, filename);
  return fs.existsSync(candidate) ? candidate : null;
}

function shouldSkipFileTreeItem(item: string, includeArchiveRoot = false): boolean {
  const lower = item.toLowerCase();
  if (item.startsWith('.')) return true;
  if (!includeArchiveRoot && [QUASAR_LOGS_DIR, QUASAR_ARCHIVE_DIR].includes(lower)) return true;
  if (includeArchiveRoot && lower === QUASAR_LOGS_DIR) return true;
  if (FILE_TREE_IGNORED_DIRS.has(lower)) return true;
  if (lower.includes('checkpoint')) return true;
  if (item.endsWith('.sqlite')) return true;
  if (item === 'checkpoint_settings.json') return true;
  if (item === 'pending_execution.json') return true;
  if (['conversation.md', 'input_messages.md', 'execution_overview.md', 'debug_cli.log'].includes(item)) return true;
  return false;
}

function treeRelativePath(baseDir: string, fullPath: string, pathPrefix: string, itemName: string): string {
  if (pathPrefix) {
    return path.posix.join(pathPrefix.replace(/\\/g, '/').replace(/\/+$/, ''), itemName);
  }
  return path.relative(baseDir, fullPath).split(path.sep).join('/');
}

function listFilesForTree(
  dir: string,
  baseDir: string,
  maxDepth: number,
  depth = 0,
  includeArchiveRoot = false,
  pathPrefix = '',
): any[] {
  if (!fs.existsSync(dir)) return [];
  const items = fs.readdirSync(dir);
  const result: any[] = [];

  let realBase: string;
  try {
    realBase = fs.realpathSync(baseDir);
  } catch {
    realBase = path.resolve(baseDir);
  }

  for (const item of items) {
    if (shouldSkipFileTreeItem(item, includeArchiveRoot)) continue;

    const fullPath = path.join(dir, item);
    const relativePath = treeRelativePath(baseDir, fullPath, pathPrefix, item);

    try {
      const lstat = fs.lstatSync(fullPath);
      let isDirectory = lstat.isDirectory();
      let size = lstat.size;
      let mtime = lstat.mtime;

      // Handle symlinks: only expand when the real target stays in-workspace or allowlisted roots.
      if (lstat.isSymbolicLink()) {
        try {
          const realTarget = fs.realpathSync(fullPath);
          if (!isAllowedResolvedPath(realBase, realTarget)) {
            isDirectory = false;
          } else {
            const stat = fs.statSync(fullPath);
            isDirectory = stat.isDirectory();
            size = stat.size;
            mtime = stat.mtime;
          }
        } catch (e) {
          // Broken symlink - treat as a file and don't spam console
          isDirectory = false;
        }
      }

      const shouldLoadChildren = isDirectory && depth < maxDepth;
      result.push({
        name: item,
        path: relativePath,
        isDirectory,
        size: isDirectory ? undefined : size,
        mtime,
        children: shouldLoadChildren
          ? listFilesForTree(fullPath, baseDir, maxDepth, depth + 1, includeArchiveRoot, relativePath)
          : undefined,
        childrenLoaded: isDirectory ? shouldLoadChildren : undefined,
      });
    } catch (e) {
      // Skip files that cannot be accessed or are otherwise problematic
    }
  }

  return result.sort((a, b) => {
    if (a.isDirectory && !b.isDirectory) return -1;
    if (!a.isDirectory && b.isDirectory) return 1;
    return a.name.localeCompare(b.name);
  });
}

function safeSendRaw(client: WebSocket, message: string): boolean {
  if (client.readyState !== WebSocket.OPEN) {
    return false;
  }
  if (client.bufferedAmount > WS_BACKPRESSURE_LIMIT_BYTES) {
    return false;
  }
  client.send(message);
  return true;
}

function safeSendJson(client: WebSocket, message: object): boolean {
  return safeSendRaw(client, JSON.stringify(message));
}

function broadcastRawToClients(message: string) {
  wss.clients.forEach((client) => {
    safeSendRaw(client, message);
  });
}

function resetLiveMessageState() {
  messageBuffer = [];
  latestUpdateEvent = null;
  latestThoughtStream = null;
  latestTaskProgress = null;
  latestContextUsage = null;
}

function mergeStreamContent(existing: string, incoming: string): string {
  if (!existing) return incoming;
  if (!incoming) return existing;
  if (incoming.startsWith(existing)) return incoming;
  if (existing.startsWith(incoming)) return existing;
  return `${existing}${incoming}`;
}

function canCompactBufferedMessage(previous: any, incoming: any): boolean {
  if (!previous || previous.type !== incoming.type) return false;

  if (incoming.type === 'text_stream' || incoming.type === 'thought_stream') {
    return previous.payload?.agent?.toLowerCase?.() === incoming.payload?.agent?.toLowerCase?.();
  }

  if (incoming.type === 'plan_stream') {
    return previous.payload?._isReplanning === incoming.payload?._isReplanning;
  }

  return false;
}

function compactBufferedMessage(previous: any, incoming: any): any {
  return {
    ...previous,
    ...incoming,
    payload: {
      ...(previous.payload || {}),
      ...(incoming.payload || {}),
      content: mergeStreamContent(
        String(previous.payload?.content || ''),
        String(incoming.payload?.content || ''),
      ),
    },
  };
}

function rememberBridgeMessage(parsed: any) {
  let remembered = parsed;
  const previous = messageBuffer[messageBuffer.length - 1];
  if (canCompactBufferedMessage(previous, parsed)) {
    remembered = compactBufferedMessage(previous, parsed);
    messageBuffer[messageBuffer.length - 1] = remembered;
  } else {
    messageBuffer.push(parsed);
    if (messageBuffer.length > BRIDGE_MESSAGE_BUFFER_LIMIT) {
      messageBuffer.splice(0, messageBuffer.length - BRIDGE_MESSAGE_BUFFER_LIMIT);
    }
  }

  if (remembered.type === 'agent_event' && remembered.payload?.event === 'update') {
    latestUpdateEvent = remembered;
  } else if (remembered.type === 'thought_stream') {
    latestThoughtStream = remembered;
  } else if (remembered.type === 'task_progress') {
    latestTaskProgress = remembered;
  } else if (remembered.type === 'context_usage') {
    latestContextUsage = remembered;
  }
}

function archiveRunSortKey(runId: string): string {
  const newMatch = runId.match(NEW_ARCHIVE_RUN_ID_PATTERN);
  if (newMatch) {
    const counter = (newMatch[4] || '0').padStart(6, '0');
    return `2-${newMatch[1]}${newMatch[2]}-${counter}-${newMatch[3]}`;
  }
  return `0-${runId}`;
}

function displayArchiveRunId(runId: string): string {
  const newMatch = runId.match(NEW_ARCHIVE_RUN_ID_PATTERN);
  if (newMatch) {
    const date = newMatch[1];
    const time = newMatch[2];
    return `Run ${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)} ${time.slice(0, 2)}:${time.slice(2, 4)}:${time.slice(4, 6)}`;
  }
  return runId;
}

function ensureWebTerminalGuardBin(): string | null {
  try {
    fs.mkdirSync(WEB_TERMINAL_GUARD_BIN_DIR, { recursive: true });
    const quasarGuardPath = path.join(WEB_TERMINAL_GUARD_BIN_DIR, 'quasar');
    const guardScript = `#!/usr/bin/env sh
echo "${WEB_TERMINAL_CLI_DISABLED_MESSAGE}" >&2
exit 1
`;
    fs.writeFileSync(quasarGuardPath, guardScript, { encoding: 'utf-8', mode: 0o755 });
    fs.chmodSync(quasarGuardPath, 0o755);
    return WEB_TERMINAL_GUARD_BIN_DIR;
  } catch (err) {
    console.error('[Terminal] Failed to prepare QUASAR CLI guard:', err);
    return null;
  }
}

// Find scripts
function resolveBridgePath(): string {
  const fromEnv = (process.env.QUASAR_BRIDGE_PATH || '').trim();
  if (fromEnv && fs.existsSync(fromEnv)) {
    return fromEnv;
  }

  const runtimeRoot = (process.env.QUASAR_RUNTIME_ROOT || '').trim();
  if (runtimeRoot) {
    const fromRoot = path.join(runtimeRoot, 'bridge.py');
    if (fs.existsSync(fromRoot)) {
      return fromRoot;
    }
  }

  return path.resolve(__dirname, '../../bridge.py');
}

const bridgePath = resolveBridgePath();
const projectRoot = path.dirname(bridgePath);
console.log(`Looking for bridge.py at: ${bridgePath}`);

/** Spawn a short Python helper; paths are passed via env (never string-interpolated). */
function spawnPythonHelper(script: string, extraEnv: Record<string, string> = {}) {
  return spawn(pythonCommand, ['-c', script], {
    cwd: path.dirname(bridgePath),
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      QUASAR_BRIDGE_PATH: bridgePath,
      ...extraEnv,
    },
  });
}

const PYTHON_HELPER_PREAMBLE = `
import os, sys, json
from traceback import format_exc
bridge_path = os.environ["QUASAR_BRIDGE_PATH"]
sys.path.insert(0, os.path.dirname(bridge_path))
`;

const DEFAULT_SETTINGS: Record<string, string> = {
  ACCURACY: 'standard',
  GRANULARITY: 'adaptive',
  CONTEXT_THRESHOLD: 'medium',
  AUTO_IMPROVE_CYCLES: '0',
  ENABLE_RAG: 'true',
  EXIT_ON_COMPLETION: 'false',
};

const SETTINGS_KEYS = [
  'MODEL', 'MODEL_API_KEY', 'OPENAI_API_BASE',
  'ACCURACY', 'GRANULARITY', 'CONTEXT_THRESHOLD', 'AUTO_IMPROVE_CYCLES',
  'NUM_CORES', 'PMG_MAPI_KEY', 'ENABLE_RAG', 'EXIT_ON_COMPLETION', 'AUTO_CONFIRM_PLAN',
  'STRATEGIST_MODEL', 'STRATEGIST_MODEL_API_KEY', 'STRATEGIST_API_BASE_URL',
  'OPERATOR_MODEL', 'OPERATOR_MODEL_API_KEY', 'OPERATOR_API_BASE_URL',
  'EVALUATOR_MODEL', 'EVALUATOR_MODEL_API_KEY', 'EVALUATOR_API_BASE_URL',
];
const SETTINGS_KEY_SET = new Set(SETTINGS_KEYS);
const PERSISTED_WEB_SETTINGS_FILE = '.quasar_web_settings.json';

const CHECKPOINT_SETTINGS_FILE = 'checkpoint_settings.json';
const CHECKPOINT_DB_FILE = 'checkpoints.sqlite';
const PENDING_EXECUTION_FILE = 'pending_execution.json';
const CHECKPOINT_ARTIFACT_FILES = [
  CHECKPOINT_DB_FILE,
  `${CHECKPOINT_DB_FILE}-shm`,
  `${CHECKPOINT_DB_FILE}-wal`,
  CHECKPOINT_SETTINGS_FILE,
  PENDING_EXECUTION_FILE,
];

function checkpointArtifactPath(workspaceDir: string, fileName: string): string {
  return path.join(workspaceDir, QUASAR_LOGS_DIR, fileName);
}

function legacyCheckpointArtifactPath(workspaceDir: string, fileName: string): string {
  return path.join(workspaceDir, fileName);
}

function existingCheckpointArtifactPath(workspaceDir: string, fileName: string): string {
  const primaryPath = checkpointArtifactPath(workspaceDir, fileName);
  if (fs.existsSync(primaryPath)) {
    return primaryPath;
  }
  const legacyPath = legacyCheckpointArtifactPath(workspaceDir, fileName);
  return fs.existsSync(legacyPath) ? legacyPath : primaryPath;
}

function checkpointDbPath(workspaceDir: string): string {
  return existingCheckpointArtifactPath(workspaceDir, CHECKPOINT_DB_FILE);
}

function checkpointSettingsPath(workspaceDir: string): string {
  return checkpointArtifactPath(workspaceDir, CHECKPOINT_SETTINGS_FILE);
}

// API keys that should NOT be saved to checkpoint_settings.json
const API_KEY_KEYS = [
  'MODEL_API_KEY', 'OPENAI_API_BASE', 'PMG_MAPI_KEY',
  'STRATEGIST_MODEL_API_KEY', 'STRATEGIST_API_BASE_URL',
  'OPERATOR_MODEL_API_KEY', 'OPERATOR_API_BASE_URL',
  'EVALUATOR_MODEL_API_KEY', 'EVALUATOR_API_BASE_URL',
];
const SENSITIVE_SETTING_MASK = '********';

function sanitizeIncomingSettings(settings: unknown): Record<string, string> {
  if (!settings || typeof settings !== 'object' || Array.isArray(settings)) {
    return {};
  }

  const sanitized: Record<string, string> = {};
  Object.entries(settings as Record<string, unknown>).forEach(([key, value]) => {
    if (typeof value !== 'string') {
      return;
    }
    if (API_KEY_KEYS.includes(key) && value === SENSITIVE_SETTING_MASK) {
      return;
    }
    sanitized[key] = value;
  });
  return sanitized;
}

function publicSettings(settings: Record<string, string>): Record<string, string> {
  const safeSettings: Record<string, string> = { ...settings };
  API_KEY_KEYS.forEach(key => {
    if (safeSettings[key]) {
      safeSettings[key] = SENSITIVE_SETTING_MASK;
    }
  });
  return safeSettings;
}

// Helper function to mask API keys in settings for logging
function maskApiKeys(settings: Record<string, string>): Record<string, string> {
  const masked: Record<string, string> = { ...settings };
  API_KEY_KEYS.forEach(key => {
    if (masked[key]) {
      masked[key] = SENSITIVE_SETTING_MASK;
    }
  });
  return masked;
}

// Helper function to mask a single value if it's an API key
function maskApiKeyValue(key: string, value: string): string {
  return API_KEY_KEYS.includes(key) ? SENSITIVE_SETTING_MASK : value;
}

function persistedWebSettingsPath(): string {
  const workspaceDir = getWorkspaceDir();
  return path.join(workspaceDir, PERSISTED_WEB_SETTINGS_FILE);
}

function loadWebSettings(): Record<string, string> {
  const settingsPath = persistedWebSettingsPath();
  const settings = loadPersistedSettings(settingsPath, SETTINGS_KEY_SET);
  if (settings) {
    console.log('Loaded persisted web settings from:', settingsPath);
  }
  return settings || {};
}

function persistWebSettings(settings: Record<string, string>): void {
  const settingsPath = persistedWebSettingsPath();
  try {
    savePersistedSettings(settingsPath, settings, SETTINGS_KEY_SET);
    console.log('Persisted web settings to:', settingsPath);
  } catch (e) {
    console.error('Failed to persist web settings:', e);
  }
}

// Save settings to checkpoint file (called when starting a run)
// Excludes API keys for security and MODEL (tracked in _usage_stats.hardware_signature)
// Merges with existing content to preserve _usage_stats from Python
function saveCheckpointSettings(settings: Record<string, string>) {
  const workspaceDir = getWorkspaceDir();
  const settingsPath = checkpointSettingsPath(workspaceDir);
  try {
    fs.mkdirSync(path.dirname(settingsPath), { recursive: true });
    // Load existing content to preserve _usage_stats and other internal data
    let existingContent: Record<string, any> = {};
    const readableSettingsPath = existingCheckpointArtifactPath(workspaceDir, CHECKPOINT_SETTINGS_FILE);
    if (fs.existsSync(readableSettingsPath)) {
      try {
        existingContent = JSON.parse(fs.readFileSync(readableSettingsPath, 'utf-8'));
      } catch (e) {
        // File exists but is invalid JSON, start fresh
      }
    }

    // Filter out API keys, MODEL, and EXECUTION_TIMEOUT before saving
    // MODEL is tracked in _usage_stats
    const safeSettings: Record<string, string> = {};
    Object.entries(settings).forEach(([key, value]) => {
      if (!API_KEY_KEYS.includes(key) && key !== 'MODEL' && key !== 'EXECUTION_TIMEOUT' && value && typeof value === 'string' && value.trim()) {
        safeSettings[key] = value;
      }
    });

    // Merge with existing content (preserves _usage_stats and other internal data)
    const mergedContent = { ...existingContent, ...safeSettings };

    // Explicitly delete retired settings if they exist in old data
    delete mergedContent.EXECUTION_TIMEOUT;
    delete mergedContent.CHECK_INTERVAL;

    fs.writeFileSync(settingsPath, JSON.stringify(mergedContent, null, 2));
    const legacySettingsPath = legacyCheckpointArtifactPath(workspaceDir, CHECKPOINT_SETTINGS_FILE);
    if (legacySettingsPath !== settingsPath && fs.existsSync(legacySettingsPath)) {
      fs.unlinkSync(legacySettingsPath);
    }
    console.log('Saved checkpoint settings to:', settingsPath);
  } catch (e) {
    console.error('Failed to save checkpoint settings:', e);
  }
}


// Load settings from checkpoint file (returns null if not found)
// Merges checkpoint settings with API keys from environment variables
// Extracts MODEL from _usage_stats.model_name if not set at top level
function loadCheckpointSettings(): Record<string, string> | null {
  const workspaceDir = getWorkspaceDir();
  const checkpointPath = checkpointDbPath(workspaceDir);
  const settingsPath = existingCheckpointArtifactPath(workspaceDir, CHECKPOINT_SETTINGS_FILE);

  // Only load if both checkpoint AND settings file exist
  if (!fs.existsSync(checkpointPath) || !fs.existsSync(settingsPath)) {
    return null;
  }

  try {
    const content = fs.readFileSync(settingsPath, 'utf-8');
    const settings = JSON.parse(content);

    // Extract MODEL from _usage_stats.model_name if not set at top level
    // This removes redundancy - model_name is already tracked in usage stats
    if (!settings.MODEL && settings._usage_stats?.model_name) {
      settings.MODEL = settings._usage_stats.model_name;
      console.log('Extracted MODEL from _usage_stats:', settings.MODEL);
    }

    // Merge API keys from environment variables (they're not saved in checkpoint)
    API_KEY_KEYS.forEach(key => {
      const envValue = process.env[key];
      if (envValue && envValue.trim()) {
        settings[key] = envValue;
      }
    });

    console.log('Loaded checkpoint settings from:', settingsPath);
    return settings;
  } catch (e) {
    console.error('Failed to load checkpoint settings:', e);
    return null;
  }
}



// Clear checkpoint settings file (called on fresh start)
function clearCheckpointSettings() {
  const workspaceDir = getWorkspaceDir();
  const settingsPath = checkpointSettingsPath(workspaceDir);
  try {
    if (fs.existsSync(settingsPath)) {
      fs.unlinkSync(settingsPath);
      console.log('Cleared checkpoint settings file');
    }
    const legacySettingsPath = legacyCheckpointArtifactPath(workspaceDir, CHECKPOINT_SETTINGS_FILE);
    if (fs.existsSync(legacySettingsPath)) {
      fs.unlinkSync(legacySettingsPath);
    }
  } catch (e) {
    console.error('Failed to clear checkpoint settings:', e);
  }
}

function clearCheckpointArtifacts(workspaceDir: string): string[] {
  const deleted: string[] = [];
  for (const fileName of CHECKPOINT_ARTIFACT_FILES) {
    for (const filePath of [checkpointArtifactPath(workspaceDir, fileName), legacyCheckpointArtifactPath(workspaceDir, fileName)]) {
      try {
        if (fs.existsSync(filePath)) {
          fs.unlinkSync(filePath);
          deleted.push(path.relative(workspaceDir, filePath));
        }
      } catch (e) {
        console.error(`Failed to delete ${fileName}:`, e);
      }
    }
  }
  return deleted;
}

function isStrategistStageCheckpoint(workspaceDir: string): boolean {
  const checkpointPath = checkpointDbPath(workspaceDir);
  if (!fs.existsSync(checkpointPath)) {
    return false;
  }

  const result = spawnSync(pythonCommand, ['-c', `
import os
import sys

sys.path.insert(0, ${JSON.stringify(projectRoot)})
os.environ["WORKSPACE_DIR"] = ${JSON.stringify(workspaceDir)}

from src.checkpoint import checkpoint_is_strategist_stage

print("true" if checkpoint_is_strategist_stage() else "false")
`], {
    cwd: projectRoot,
    env: { ...process.env, WORKSPACE_DIR: workspaceDir },
    encoding: 'utf-8',
  });

  if (result.error || result.status !== 0) {
    console.error('Failed to inspect checkpoint stage:', result.error || result.stderr);
    return false;
  }

  return result.stdout.trim().split(/\s+/).pop() === 'true';
}

// Initialize settings from environment variables, defaults, or checkpoint
function initializeSettings() {
  console.log('Initializing settings from environment variables...');
  const persistedSettings = loadWebSettings();

  // First, check if checkpoint settings exist (takes priority when resuming)
  const checkpointSettings = loadCheckpointSettings();
  if (checkpointSettings) {
    console.log('Using checkpoint settings with persisted web credentials');
    userSettings = { ...DEFAULT_SETTINGS, ...persistedSettings, ...checkpointSettings };
    console.log('Final preloaded settings keys:', Object.keys(userSettings));
    return;
  }

  // Otherwise, load persisted browser settings, then let explicit env vars win.
  const settings: Record<string, string> = { ...DEFAULT_SETTINGS, ...persistedSettings };

  SETTINGS_KEYS.forEach(key => {
    const val = process.env[key];
    if (val && val.trim()) {
      console.log(`  Found env var: ${key}=${maskApiKeyValue(key, val)}`);
      settings[key] = val;
    }
  });

  userSettings = settings;
  console.log('Final preloaded settings keys:', Object.keys(userSettings));
}

// Initialize settings
initializeSettings();

// Pre-download RAG resources (index + embedding model) and docs on server startup
// This does NOT load the vectorstore - that happens when Python bridge starts
function preloadResources() {
  const workspaceDir = getWorkspaceDir();
  console.log(`Starting resource pre-download in ${workspaceDir} (index + embeddings model + docs)...`);

  const preloadProcess = spawnPythonHelper(`
import os
import sys
from pathlib import Path
bridge_path = os.environ["QUASAR_BRIDGE_PATH"]
sys.path.insert(0, os.path.dirname(bridge_path))

def status(code, message):
    print(f'INIT_STATUS:{code}:{message}', flush=True)

enable_rag = os.environ.get('ENABLE_RAG', 'true').lower() not in ['false', '0', 'no', 'off']

# Get and ensure workspace directory exists (never fall back to Docker-only /workspace on local installs)
raw_ws = (os.environ.get('WORKSPACE_DIR') or os.environ.get('HOME') or '/workspace').strip()
workspace_dir = Path(raw_ws).expanduser()
workspace_dir.mkdir(parents=True, exist_ok=True)

# Link pre-cached resources (docs, .rag_index, .hf_cache) from image cache if present
try:
    from src.rag.resource_cache import link_cached_resources
    linked = link_cached_resources(workspace_dir)
    if linked:
        print(f'Linked cached resources into workspace: {", ".join(linked)}', flush=True)
except Exception as e:
    print(f'Warning: failed to link cached resources: {e}', flush=True)

# Step 1: Download documentation (always, regardless of RAG setting)
status('downloading_docs', 'Checking documentation cache...')
try:
    from src.rag.docs_downloader import download_docs, is_docs_available
    if is_docs_available(workspace_dir):
        status('docs_ready', 'Documentation ready')
    else:
        status('downloading_docs', 'Downloading documentation...')
        docs_ok = download_docs(
            workspace_dir,
            status_tracker=lambda msg: status('downloading_docs', msg),
        )
        if docs_ok:
            status('docs_ready', 'Documentation ready')
        else:
            status('docs_error', 'Documentation download incomplete')
except Exception as e:
    status('docs_error', f'Failed to download docs: {e}')

if enable_rag:
    try:
        from src.rag.index_downloader import download_index, is_index_valid
        from src.rag.embeddings import initialize_embeddings

        # Step 2: Download/verify index exists
        status('downloading_index', 'Checking knowledge base index...')
        if not is_index_valid(workspace_dir):
            status('downloading_index', 'Downloading knowledge base index...')
            if not download_index(
                workspace_dir,
                status_tracker=lambda msg: status('downloading_index', msg),
            ):
                raise RuntimeError('Failed to download knowledge base index')
        status('index_ready', 'Index ready')

        # Step 3: Download embedding model (cached by transformers/sentence-transformers)
        status('downloading_embeddings', 'Loading embedding model...')
        embeddings = initialize_embeddings(
            workspace_dir=workspace_dir,
            status_tracker=lambda msg: status('downloading_embeddings', msg),
        )
        if embeddings is None:
            raise RuntimeError('Failed to load embedding model')
        status('ready', 'System ready')
    except Exception as e:
        status('error', f'Failed to initialize: {e}')
else:
    status('ready', 'System ready (RAG disabled)')
`, {
    WORKSPACE_DIR: workspaceDir,
    HF_HUB_DISABLE_IMPLICIT_TOKEN: '1',
    HF_HUB_DISABLE_PROGRESS_BARS: '1',
    TOKENIZERS_PARALLELISM: 'false',
    TRANSFORMERS_VERBOSITY: 'error',
  });

  preloadProcess.stdout?.on('data', (data) => {
    const output = data.toString();
    // Split by newlines to handle multiple status updates in one chunk
    const lines = output.split('\n').map((l: string) => l.trim()).filter((l: string) => l);

    for (const line of lines) {
      console.log(`[Preload] ${line}`);

      // Only broadcast INIT_STATUS messages to clients
      if (line.startsWith('INIT_STATUS:')) {
        const parts = line.replace('INIT_STATUS:', '').split(':');
        const status = parts[0];
        const message = parts.slice(1).join(':') || status;
        if (!ragPreloaded || status === 'ready' || status === 'error') {
          latestInitStatus = { status, message };
          broadcastToClients({ type: 'init_status', payload: latestInitStatus });
        } else {
          console.log(`[Preload] (post-ready) ${status}: ${message}`);
        }

        if (status === 'ready' || status === 'error') {
          ragPreloaded = true;
          ragPreloadFailed = status === 'error';
          // Also send rag_status for backward compatibility
          broadcastToClients({ type: 'rag_status', payload: { status: ragPreloadFailed ? 'error' : 'ready' } });
        }
      }
    }
  });

  preloadProcess.stderr?.on('data', (data) => {
    console.log(`[Preload] ${data.toString().trim()}`);
  });

  preloadProcess.on('close', (code) => {
    console.log(`Resource preload finished with code ${code}`);
    if (!ragPreloaded) {
      ragPreloaded = true;
      if (code === 0 && !ragPreloadFailed) {
        latestInitStatus = { status: 'ready', message: 'System ready' };
        broadcastToClients({ type: 'init_status', payload: latestInitStatus });
        broadcastToClients({ type: 'rag_status', payload: { status: 'ready' } });
      } else {
        ragPreloadFailed = true;
        latestInitStatus = {
          status: 'error',
          message: `Resource initialization failed (exit code ${code ?? 'unknown'})`,
        };
        broadcastToClients({ type: 'init_status', payload: latestInitStatus });
        broadcastToClients({ type: 'rag_status', payload: { status: 'error' } });
      }
    }
  });
}

function broadcastToClients(message: object) {
  const msgStr = JSON.stringify(message);
  wss.clients.forEach((client) => {
    safeSendRaw(client, msgStr);
  });
}

function startPythonBridge(settings: Record<string, string> = {}) {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }

  resetLiveMessageState();
  isAwaitingPlanConfirmation = false;

  // Merge user settings with process.env
  const envVars: Record<string, string> = { ...process.env as Record<string, string> };
  const sanitizedSettings = sanitizeIncomingSettings(settings);

  // Apply user settings from web UI
  Object.entries(sanitizedSettings).forEach(([key, value]) => {
    if (value && typeof value === 'string' && value.trim()) {
      envVars[key] = value;
    }
  });

  envVars['PYTHONUNBUFFERED'] = '1';

  // Save settings for checkpoint restoration
  saveCheckpointSettings(sanitizedSettings);

  console.log('Starting Python bridge with settings:', Object.keys(sanitizedSettings).filter(k => sanitizedSettings[k]));

  pythonProcess = spawn(pythonCommand, [bridgePath], {
    cwd: path.dirname(bridgePath),
    stdio: ['pipe', 'pipe', 'inherit'],
    env: envVars
  });

  console.log('Python bridge started with PID:', pythonProcess.pid);

  let stdoutLineBuffer = '';

  const handleBridgeStdoutLine = (line: string) => {
    const msg = line.trim();
    if (!msg) return;

    try {
      const parsed = JSON.parse(msg);
      rememberBridgeMessage(parsed);

      if (parsed.type === 'system_status') {
        if (parsed.payload?.status === 'running') {
          isExecutionRunning = true;
        } else if (parsed.payload?.status === 'completed') {
          isExecutionRunning = false;
        }
      } else if (parsed.type === 'plan_awaiting_confirm') {
        // Auto-confirm plan if AUTO_CONFIRM_PLAN is enabled
        if (userSettings.AUTO_CONFIRM_PLAN?.toLowerCase() === 'true') {
          pythonProcess?.stdin?.write(JSON.stringify({ command: 'plan_confirm', action: 'confirm', feedback: '' }) + '\n');
        } else {
          isAwaitingPlanConfirmation = true;
        }
      } else if (parsed.type === 'plan_declined' || parsed.type === 'done' || parsed.type === 'error') {
        isAwaitingPlanConfirmation = false;
        isExecutionRunning = false;
      }

      // Check for run completion and exit if EXIT_ON_COMPLETION is enabled
      // Exit on: 'completed' (successful), 'error' (API/backend error), 'gave_up' (agent gave up)
      // Do NOT exit on: 'interrupted' (user pressed stop button)
      const exitStatuses = ['completed', 'error', 'gave_up'];
      if (parsed.type === 'done' &&
          exitStatuses.includes(parsed.payload?.status) &&
          userSettings.EXIT_ON_COMPLETION === 'true') {
        console.log(`Run finished with status '${parsed.payload?.status}' - EXIT_ON_COMPLETION enabled, exiting server...`);
        // Allow time for final messages to be sent to clients
        setTimeout(() => {
          console.log('Exiting server after run completion.');
          process.exit(0);
        }, 1000);
      }
    } catch (e) {
      // Non-JSON output is still forwarded; the web client ignores it.
    }

    broadcastRawToClients(msg);
  };

  if (pythonProcess.stdout) {
    pythonProcess.stdout.on('data', (data) => {
      stdoutLineBuffer += data.toString();
      let newlineIndex = stdoutLineBuffer.indexOf('\n');
      while (newlineIndex !== -1) {
        const line = stdoutLineBuffer.slice(0, newlineIndex);
        stdoutLineBuffer = stdoutLineBuffer.slice(newlineIndex + 1);
        handleBridgeStdoutLine(line);
        newlineIndex = stdoutLineBuffer.indexOf('\n');
      }
    });
  }

  pythonProcess.on('close', (code) => {
    if (stdoutLineBuffer.trim()) {
      handleBridgeStdoutLine(stdoutLineBuffer);
      stdoutLineBuffer = '';
    }
    console.log(`Python bridge exited with code ${code}`);
    isAwaitingPlanConfirmation = false;
    isExecutionRunning = false;
    pythonProcess = null;
  });
}

// Handle WebSocket connections
wss.on('connection', (ws, req) => {
  if (!tokenMatches(extractWebSocketAuthToken(req))) {
    console.warn(`Rejected unauthorized WebSocket connection from ${req.socket.remoteAddress || 'unknown'}`);
    ws.close(1008, 'Unauthorized');
    return;
  }

  console.log('Client connected');

  // Send current initialization status
  ws.send(JSON.stringify({
    type: 'init_status',
    payload: latestInitStatus,
  }));
  // Also send rag_status for backward compatibility
  ws.send(JSON.stringify({
    type: 'rag_status',
    payload: { status: ragPreloadFailed ? 'error' : (ragPreloaded ? 'ready' : 'initializing') }
  }));

  // Send current execution status
  ws.send(JSON.stringify({
    type: 'execution_status',
    payload: { running: isExecutionRunning }
  }));

  // Check if checkpoint exists - if so, DON'T send messageBuffer
  // The frontend will load history from checkpoint instead
  // Only truly new messages after this point will be sent via live WebSocket
  const checkpointPath = checkpointDbPath(getWorkspaceDir());
  const hasCheckpoint = fs.existsSync(checkpointPath);

  if (isExecutionRunning && messageBuffer.length > 0 && !hasCheckpoint) {
    // No checkpoint exists, so send buffered messages
    // This handles the case where a new run just started but hasn't checkpointed yet
    console.log(`Syncing ${messageBuffer.length} buffered messages to new client (no checkpoint)`);
    messageBuffer.forEach(msg => {
      safeSendJson(ws, msg);
    });
  } else if (isExecutionRunning && messageBuffer.length > 0) {
    console.log(`Skipping messageBuffer sync (${messageBuffer.length} msgs) - checkpoint exists, frontend will load history`);

    // But send the latest live status so the UI shows the current running state.
    // Skip when awaiting plan confirmation: the last update is often "Self-reviewing plan" even though
    // planning finished — step_complete is not an 'update', so the buffer's latest update is stale.
    if (latestUpdateEvent && !isAwaitingPlanConfirmation) {
      console.log(`Sending latest update event: ${latestUpdateEvent.payload?.status}`);
      safeSendJson(ws, latestUpdateEvent);
    }

    // Also send the latest thought stream (if any) so the UI can render it under the update status
    if (latestThoughtStream && !isAwaitingPlanConfirmation) {
      safeSendJson(ws, latestThoughtStream);
    }

    // Also send the latest task_progress so task header is visible
    if (latestTaskProgress) {
      console.log(`Sending latest task_progress: Task ${latestTaskProgress.payload?.current}`);
      safeSendJson(ws, latestTaskProgress);
    }

    if (latestContextUsage) {
      safeSendJson(ws, latestContextUsage);
    }
  }

  if (isAwaitingPlanConfirmation && hasCheckpoint) {
    safeSendJson(ws, { type: 'plan_awaiting_confirm', payload: {} });
  }

  // Don't start Python bridge on connect - wait for first prompt

  // Handle case where we're already running but user refreshed
  if (pythonProcess && messageBuffer.length > 0) {
     // Check if we have the prompt to set currentPrompt on frontend
     const lastPromptMsg = [...messageBuffer].reverse().find(m => m.type === 'log' && m.payload?.text?.startsWith('> '));
     if (lastPromptMsg) {
         // Optionally send a specific message to help frontend recover currentPrompt
     }
  }

  ws.on('message', (message) => {
    try {
      const data = JSON.parse(message.toString());

      // Handle terminal start - spawn PTY for this client
      if (data.command === 'terminal_start') {
        void (async () => {
          // Clean up existing PTY if any
          const existingPty = ptyProcesses.get(ws);
          if (existingPty) {
            existingPty.kill();
            ptyProcesses.delete(ws);
          }

          const pty = await loadNodePty();
          if (!pty) {
            safeSendJson(ws, {
              type: 'terminal_error',
              payload: {
                error: 'Built-in web terminal is unavailable because the optional native module "node-pty" is not installed on this machine.',
              },
            });
            return;
          }

          // Spawn new PTY
          const shell = process.env.SHELL || '/bin/bash';
          const workspaceDir = getWorkspaceDir();

          try {
            // Include userSettings in the PTY environment so terminal has access to configured variables.
            // Preserve the host user's real HOME so shell init scripts (.zshenv, .bashrc, ~/.cargo/env)
            // resolve properly in local/pip installs; fall back to workspaceDir only when HOME is unset.
            const ptyEnv: { [key: string]: string } = {
              ...process.env as { [key: string]: string },
              TERM: 'xterm-256color',
              HOME: (process.env.HOME || '').trim() || workspaceDir,
              WORKSPACE_DIR: workspaceDir,
            };

            // Apply user settings to PTY environment
            Object.entries(userSettings).forEach(([key, value]) => {
              if (value && typeof value === 'string' && value.trim()) {
                ptyEnv[key] = value;
              }
            });

            ptyEnv.QUASAR_WEB_TERMINAL = 'true';
            ptyEnv.QUASAR_WEB_TERMINAL_MESSAGE = WEB_TERMINAL_CLI_DISABLED_MESSAGE;

            const guardBinDir = ensureWebTerminalGuardBin();
            if (guardBinDir) {
              ptyEnv.PATH = `${guardBinDir}${path.delimiter}${ptyEnv.PATH || ''}`;
            }

            const initialCols = Number.isFinite(data.cols) ? Math.min(240, Math.max(20, Math.floor(data.cols))) : 80;
            const initialRows = Number.isFinite(data.rows) ? Math.min(120, Math.max(8, Math.floor(data.rows))) : 24;

            const ptyProcess = pty.spawn(shell, [], {
              name: 'xterm-256color',
              cols: initialCols,
              rows: initialRows,
              cwd: workspaceDir,
              env: ptyEnv
            });

            if (ws.readyState !== WebSocket.OPEN) {
              ptyProcess.kill();
              return;
            }

            ptyProcesses.set(ws, ptyProcess);
            console.log(`[Terminal] PTY spawned for client, PID: ${ptyProcess.pid}`);

            let terminalOutputBuffer = '';
            let terminalFlushTimer: ReturnType<typeof setTimeout> | null = null;

            const flushTerminalOutput = () => {
              if (terminalFlushTimer) {
                clearTimeout(terminalFlushTimer);
                terminalFlushTimer = null;
              }
              if (!terminalOutputBuffer) return;
              const chunk = terminalOutputBuffer;
              terminalOutputBuffer = '';
              safeSendJson(ws, { type: 'terminal_output', payload: { data: chunk } });
            };

            const scheduleTerminalFlush = () => {
              if (terminalOutputBuffer.length >= TERMINAL_OUTPUT_FLUSH_BYTES) {
                flushTerminalOutput();
                return;
              }
              if (!terminalFlushTimer) {
                terminalFlushTimer = setTimeout(flushTerminalOutput, TERMINAL_OUTPUT_FLUSH_MS);
              }
            };

            // Pipe PTY output to WebSocket in small batches so large terminal bursts
            // do not trigger one React/xterm write per PTY chunk.
            ptyProcess.onData((chunk: string) => {
              if (ws.readyState === WebSocket.OPEN) {
                terminalOutputBuffer += chunk;
                scheduleTerminalFlush();
              }
            });

            ptyProcess.onExit(({ exitCode }) => {
              flushTerminalOutput();
              console.log(`[Terminal] PTY exited with code ${exitCode}`);
              ptyProcesses.delete(ws);
            });
          } catch (err) {
            console.error('[Terminal] Failed to spawn PTY:', err);
            safeSendJson(ws, { type: 'terminal_error', payload: { error: String(err) } });
          }
        })();
        return;
      }

      // Handle terminal data - write to PTY stdin
      if (data.command === 'terminal_data') {
        const ptyProcess = ptyProcesses.get(ws);
        if (ptyProcess && data.data) {
          ptyProcess.write(data.data);
        }
        return;
      }

      // Handle terminal resize
      if (data.command === 'terminal_resize') {
        const ptyProcess = ptyProcesses.get(ws);
        if (ptyProcess && data.cols && data.rows) {
          ptyProcess.resize(data.cols, data.rows);
        }
        return;
      }

      // Handle settings update
      if (data.command === 'update_settings') {
        const sanitizedSettings = sanitizeIncomingSettings(data.settings);
        userSettings = { ...userSettings, ...sanitizedSettings };
        persistWebSettings(userSettings);
        console.log('Settings updated:', Object.keys(sanitizedSettings));
        ws.send(JSON.stringify({ type: 'settings_updated', payload: { success: true } }));

        if (pythonProcess?.stdin && Object.keys(sanitizedSettings).length > 0) {
          pythonProcess.stdin.write(JSON.stringify({ command: 'update_env', updates: sanitizedSettings }) + '\n');
        }

        // Broadcast to all clients that settings have changed - terminals should restart to pick up new env vars
        broadcastToClients({ type: 'terminal_settings_updated', payload: { settingKeys: Object.keys(sanitizedSettings) } });
        return;
      }

      // Handle prompt - now we start Python if not running
      if (data.command === 'prompt') {
        isAwaitingPlanConfirmation = false;
        isExecutionRunning = true;
        resetLiveMessageState();
        if (!pythonProcess) {
          startPythonBridge(userSettings);

          // Wait a moment for Python to initialize before sending prompt
          setTimeout(() => {
            if (pythonProcess?.stdin) {
              pythonProcess.stdin.write(message.toString() + '\n');
            }
          }, 500);
        } else {
          if (pythonProcess.stdin) {
            pythonProcess.stdin.write(message.toString() + '\n');
          }
        }
        return;
      }

      if (data.command === 'plan_confirm') {
        isAwaitingPlanConfirmation = false;
      }

      // Forward other messages to Python
      if (pythonProcess?.stdin) {
        pythonProcess.stdin.write(message.toString() + '\n');
      }
    } catch (e) {
      console.error("Failed to process message", e);
    }
  });

  ws.on('close', () => {
    console.log('Client disconnected');
    // Clean up PTY for this client
    const ptyProcess = ptyProcesses.get(ws);
    if (ptyProcess) {
      console.log(`[Terminal] Cleaning up PTY for disconnected client`);
      ptyProcess.kill();
      ptyProcesses.delete(ws);
    }
  });
});

// API endpoints
app.post('/api/settings', (req, res) => {
  const sanitizedSettings = sanitizeIncomingSettings(req.body);
  userSettings = { ...userSettings, ...sanitizedSettings };
  persistWebSettings(userSettings);
  console.log('Settings updated via API:', Object.keys(sanitizedSettings));
  res.json({ success: true });
});

app.get('/api/settings', (req, res) => {
  console.log(`Serving settings to ${req.ip}. Keys:`, Object.keys(userSettings));
  res.json(publicSettings(userSettings));
});

app.post('/api/restart', (req, res) => {
  isExecutionRunning = false;
  startPythonBridge(userSettings);
  broadcastToClients({ type: 'bridge_restarted', payload: {} });
  res.json({ status: 'restarted' });
});

// Cancel current execution. Do not auto-restart the bridge; resume starts it.
app.post('/api/cancel', async (req, res) => {
  console.log('Cancelling execution...');
  isAwaitingPlanConfirmation = false;
  isExecutionRunning = false;
  // Force a fresh checkpoint metadata read after interrupt.
  checkpointInfoCache = null;

  // Send SIGINT to Python bridge (triggers signal handler that saves stats)
  if (pythonProcess) {
    console.log('Sending SIGINT to Python bridge...');
    try {
      pythonProcess.kill('SIGINT');
    } catch {
      // ignore
    }
    // Wait for graceful exit (or force-kill on timeout) before reading checkpoint.
    await waitForPythonProcessExit(1500);
  }

  // Check for checkpoint (SQLite database file) and drop hollow unstarted checkpoints
  const workspaceDir = getWorkspaceDir();
  const checkpointPath = checkpointDbPath(workspaceDir);
  let hasCheckpoint = fs.existsSync(checkpointPath);
  if (hasCheckpoint) {
    const cleanupResult = spawnSync(pythonCommand, ['-c', `
${PYTHON_HELPER_PREAMBLE}
from src.checkpoint import cleanup_empty_checkpoint_if_needed
print("true" if cleanup_empty_checkpoint_if_needed() else "false")
`], {
      cwd: projectRoot,
      env: { ...process.env, QUASAR_BRIDGE_PATH: bridgePath, WORKSPACE_DIR: workspaceDir },
      encoding: 'utf-8',
    });
    if (!cleanupResult.error && cleanupResult.status === 0) {
      hasCheckpoint = cleanupResult.stdout.trim().split(/\s+/).pop() === 'true';
    } else {
      hasCheckpoint = fs.existsSync(checkpointPath);
    }
  }

  if (!hasCheckpoint) {
    resetLiveMessageState();
  }

  console.log(`Checkpoint path: ${checkpointPath}, exists: ${hasCheckpoint}`);

  broadcastToClients({ type: 'bridge_restarted', payload: {} });
  // Immediate lightweight status so the UI leaves the running state quickly.
  broadcastToClients({ type: 'checkpoint_status', payload: { exists: hasCheckpoint } });

  res.json({ status: 'cancelled', hasCheckpoint });
});

// Check if checkpoint exists and return detailed info
app.get('/api/checkpoint', async (req, res) => {
  const workspaceDir = getWorkspaceDir();
  const checkpointPath = checkpointDbPath(workspaceDir);

  if (!fs.existsSync(checkpointPath)) {
    // Check if archive runs exist
    const runs = listArchiveRuns(workspaceDir);
    const hasArchive = runs.length > 0;
    const archiveCount = runs.length;
    return res.json({ exists: false, hasArchive, archiveCount });
  }

  console.log(`Checkpoint found at ${checkpointPath}, extracting info...`);
  const checkpointCacheKey = getFileSignature(checkpointPath);
  if (checkpointCacheKey && checkpointInfoCache?.key === checkpointCacheKey) {
    const result = { ...checkpointInfoCache.value };
    const savedSettings = loadCheckpointSettings();
    if (savedSettings) {
      result.savedSettings = publicSettings(savedSettings);
    }
    result.isRunning = isExecutionRunning;
    return res.json(result);
  }

  // Run Python snippet to extract history and previous input
  const extractProcess = spawnPythonHelper(`
${PYTHON_HELPER_PREAMBLE}
from pathlib import Path

try:
    from src.checkpoint import (
        checkpoint_file_exists,
        checkpoint_has_progress,
        create_checkpoint_infrastructure,
        delete_checkpoint,
        get_thread_config,
        release_checkpoint_resources,
    )
    from src.graph import build_graph
    from src.llm_config import initialize_llm
    from bridge_history import extract_checkpoint_history
    from bridge import _read_previous_input_from_conversation
    from src.usage_tracker import generate_interrupted_report_if_needed
    from src.resume_steering import checkpoint_allows_resume_steering

    if not checkpoint_file_exists():
        print(json.dumps({"exists": False}))
        sys.exit(0)

    is_exec_running = os.environ.get("QUASAR_EXECUTION_RUNNING", "false") == "true"

    # Initialize minimal components to read state
    # We need a dummy LLM just to build the graph structure
    class FakeLLM:
        def invoke(self, *args, **kwargs): return None
        def bind_tools(self, *args, **kwargs): return self

    llm = FakeLLM()
    graph_builder = build_graph(llm)
    graph = create_checkpoint_infrastructure(graph_builder)
    config = get_thread_config()
    state = graph.get_state(config)
    state_values = state.values if state else {}

    # If no execution is running and the checkpoint has zero real progress
    # (e.g. failed immediately on invalid API key/model or cancelled before planning),
    # clean it up so the UI returns to the input home page.
    if not is_exec_running and not checkpoint_has_progress(state_values):
        release_checkpoint_resources()
        delete_checkpoint()
        print(json.dumps({"exists": False}))
        sys.exit(0)

    # Generate usage report for interrupted run BEFORE loading checkpoint
    # This ensures interrupted runs get their reports even if killed with SIGKILL
    try:
        generate_interrupted_report_if_needed()
    except Exception:
        pass

    state_history = list(graph.get_state_history(config))
    checkpoint_next = list(getattr(state, "next", ()) or []) if state else []
    can_resume_steering = checkpoint_allows_resume_steering(
        checkpoint_next,
        state_values,
    )

    history = None
    if state_values:
        history = extract_checkpoint_history(
            state_values,
            state_values.get('messages', []),
            state_history=state_history,
        )

    previous_input = _read_previous_input_from_conversation()

    print(json.dumps({
        "exists": True,
        "previous_input": previous_input,
        "history": history,
        "checkpoint_next": checkpoint_next,
        "can_resume_steering": can_resume_steering
    }))
except Exception as e:
    print(json.dumps({
        "exists": True,
        "error": str(e),
        "traceback": format_exc()
    }))
`, { WORKSPACE_DIR: workspaceDir, QUASAR_EXECUTION_RUNNING: isExecutionRunning ? 'true' : 'false' });

  let output = '';
  let stderr = '';
  extractProcess.stdout?.on('data', (data) => {
    output += data.toString();
  });
  extractProcess.stderr?.on('data', (data) => {
    stderr += data.toString();
  });

  extractProcess.on('close', (code) => {
    try {
      const extracted = JSON.parse(output.trim());
      if (!extracted.exists) {
        checkpointInfoCache = null;
        const runs = listArchiveRuns(workspaceDir);
        return res.json({
          exists: false,
          hasArchive: runs.length > 0,
          archiveCount: runs.length,
          isRunning: isExecutionRunning,
        });
      }
      // Recompute signature after extract in case WAL was checkpointed/merged.
      const freshCacheKey = getFileSignature(checkpointPath) || checkpointCacheKey;
      if (freshCacheKey && !extracted.error) {
        checkpointInfoCache = { key: freshCacheKey, value: extracted };
      }
      const result = { ...extracted };
      // Include saved settings in the response
      const savedSettings = loadCheckpointSettings();
      if (savedSettings) {
        result.savedSettings = publicSettings(savedSettings);
      }
      // Include isRunning to indicate if a live session is active
      // This helps frontend avoid loading stale history when system is running
      result.isRunning = isExecutionRunning;
      // Ensure the steering flag is always a boolean for the web client.
      if (result.exists === true && typeof result.can_resume_steering !== 'boolean') {
        result.can_resume_steering = false;
      }
      res.json(result);
    } catch (e) {
      console.error('Failed to parse checkpoint info:', output, stderr, 'code=', code);
      res.status(500).json({
        exists: true,
        error: 'Failed',
        isRunning: isExecutionRunning,
        can_resume_steering: false,
      });
    }
  });
});

// Revert to a specific task - time travel back to a checkpoint
app.post('/api/revert', async (req, res) => {
  const { targetTask } = req.body;

  if (!targetTask || typeof targetTask !== 'number' || targetTask < 1) {
    return res.status(400).json({ success: false, error: 'Invalid targetTask parameter' });
  }

  // Don't allow revert while running
  if (isExecutionRunning) {
    return res.status(400).json({ success: false, error: 'Cannot revert while execution is running' });
  }

  const workspaceDir = getWorkspaceDir();
  const checkpointPath = checkpointDbPath(workspaceDir);

  if (!fs.existsSync(checkpointPath)) {
    return res.status(400).json({ success: false, error: 'No checkpoint exists to revert' });
  }

  console.log(`Reverting to task ${targetTask}...`);

  // Run Python revert utility
  const revertProcess = spawnPythonHelper(`
${PYTHON_HELPER_PREAMBLE}
try:
    from src.revert import revert_to_task
    target = int(os.environ["QUASAR_REVERT_TARGET_TASK"])
    result = revert_to_task(target)
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({
        "success": False,
        "error": str(e),
        "traceback": format_exc()
    }))
`, { QUASAR_REVERT_TARGET_TASK: String(targetTask) });

  let output = '';
  let errorOutput = '';

  revertProcess.stdout?.on('data', (data) => {
    output += data.toString();
  });

  revertProcess.stderr?.on('data', (data) => {
    errorOutput += data.toString();
  });

  revertProcess.on('close', (code) => {
    try {
      const result = JSON.parse(output.trim());
      console.log(`Revert result:`, result);

      if (result.success) {
        // Clear message buffer since we're reverting
        messageBuffer = [];
        // Broadcast that workspace has changed
        broadcastToClients({ type: 'workspace_reverted', payload: { targetTask, deletedFiles: result.deleted_files } });
      }

      res.json(result);
    } catch (e) {
      console.error('Failed to parse revert result:', output, errorOutput);
      res.status(500).json({ success: false, error: 'Failed to parse revert result', output, errorOutput });
    }
  });
});

// Start fresh. Strategist-only checkpoints clear checkpoint files without touching workspace files.
app.post('/api/fresh', (req, res) => {
  const workspaceDir = getWorkspaceDir();
  console.log(`Starting fresh - cleaning workspace: ${workspaceDir}`);
  isExecutionRunning = false;
  resetLiveMessageState();
  checkpointInfoCache = null;

  const { includeArchive } = req.body;
  const preserveWorkspaceForStrategist = !includeArchive && isStrategistStageCheckpoint(workspaceDir);

  // Clear checkpoint settings file only - keep current userSettings
  // (which may have been modified by user via UI)
  clearCheckpointSettings();

  try {
    if (preserveWorkspaceForStrategist) {
      const deleted = clearCheckpointArtifacts(workspaceDir);
      console.log(`Strategist-stage reset complete. Deleted checkpoint artifacts: ${deleted.join(', ')}`);
      res.json({
        success: true,
        deleted,
        skipped: ['workspace'],
        workspaceReset: false,
      });
      return;
    }

    const items = fs.readdirSync(workspaceDir);
    const deleted: string[] = [];
    const skipped: string[] = [];

    for (const item of items) {
      // Skip dotfiles/folders (like .rag_index)
      if (item.startsWith('.')) {
        skipped.push(item);
        continue;
      }

      // Skip docs folder always
      if (item === 'docs') {
        skipped.push(item);
        continue;
      }

      // Skip QUASAR archive folder unless includeArchive is true
      if (item === QUASAR_ARCHIVE_DIR && !includeArchive) {
        skipped.push(item);
        continue;
      }

      const itemPath = path.join(workspaceDir, item);
      try {
        const stat = fs.statSync(itemPath);
        if (stat.isDirectory()) {
          fs.rmSync(itemPath, { recursive: true, force: true });
        } else {
          fs.unlinkSync(itemPath);
        }
        deleted.push(item);
      } catch (e) {
        console.error(`Failed to delete ${item}:`, e);
      }
    }

    // Ensure QUASAR logs directory exists after cleanup
    const logsDir = path.join(workspaceDir, QUASAR_LOGS_DIR);
    if (!fs.existsSync(logsDir)) {
      fs.mkdirSync(logsDir, { recursive: true });
    }

    console.log(`Fresh start complete. Deleted: ${deleted.join(', ')}. Skipped: ${skipped.join(', ')}`);

    broadcastToClients({ type: 'workspace_cleaned', payload: { deleted, skipped } });
    res.json({ success: true, deleted, skipped });
  } catch (e) {
    console.error('Failed to clean workspace:', e);
    res.status(500).json({ success: false, error: (e as Error).message });
  }
});

// List workspace files with filtering
app.get('/api/files', (req, res) => {
  const workspaceDir = getWorkspaceDir();
  const requestedPath = typeof req.query.path === 'string' ? req.query.path : '';
  const depthParam = Number.parseInt(req.query.depth as string, 10);
  const maxDepth = Number.isFinite(depthParam) && depthParam >= 0 ? Math.min(depthParam, 5) : Number.MAX_SAFE_INTEGER;
  try {
    const safe = resolveSafeWorkspacePath(workspaceDir, requestedPath || '.', 'existing');
    if (!safe.ok) {
      return res.status(safePathHttpStatus(safe)).json({ error: safePathError(safe) });
    }
    const targetDir = safe.absolute;
    if (!fs.existsSync(targetDir) || !fs.statSync(targetDir).isDirectory()) {
      return res.status(404).json({ error: 'Directory not found' });
    }

    const pathPrefix = !requestedPath || requestedPath === '.'
      ? ''
      : requestedPath.replace(/\\/g, '/').replace(/\/+$/, '');
    const files = listFilesForTree(targetDir, workspaceDir, maxDepth, 0, false, pathPrefix);
    res.json(files);
  } catch (e) {
    console.error('Failed to list files:', e);
    res.status(500).json({ error: (e as Error).message });
  }
});

// List files from a specific archive run
app.get('/api/archive/files', (req, res) => {
  const runId = req.query.runId as string;
  const requestedPath = typeof req.query.path === 'string' ? req.query.path : '';
  const depthParam = Number.parseInt(req.query.depth as string, 10);
  const maxDepth = Number.isFinite(depthParam) && depthParam >= 0 ? Math.min(depthParam, 5) : Number.MAX_SAFE_INTEGER;
  if (!runId) {
    return res.status(400).json({ error: 'runId is required' });
  }

  const workspaceDir = getWorkspaceDir();

  // Security: ensure runId is a known QUASAR archive id
  const archiveDir = findArchiveRunPath(workspaceDir, runId);
  if (!archiveDir) {
    return res.status(400).json({ error: 'Invalid runId format' });
  }

  try {
    const safe = requestedPath
      ? resolveSafeWorkspacePath(archiveDir, requestedPath, 'existing')
      : { ok: true as const, absolute: path.resolve(archiveDir), realBase: path.resolve(archiveDir), realPath: path.resolve(archiveDir) };
    if (!safe.ok) {
      return res.status(safePathHttpStatus(safe)).json({ error: safePathError(safe) });
    }
    const targetDir = safe.realPath || safe.absolute;
    if (!fs.existsSync(targetDir) || !fs.statSync(targetDir).isDirectory()) {
      return res.status(404).json({ error: 'Directory not found' });
    }

    const files = listFilesForTree(targetDir, archiveDir, maxDepth, 0, true);
    res.json(files);
  } catch (e) {
    console.error('Failed to list archive files:', e);
    res.status(500).json({ error: (e as Error).message });
  }
});

// Get file content from a specific archive run
app.get('/api/archive/files/content', (req, res) => {
  const runId = req.query.runId as string;
  const filePath = req.query.path as string;

  if (!runId) return res.status(400).json({ error: 'runId is required' });
  if (!filePath) return res.status(400).json({ error: 'Path is required' });

  const workspaceDir = getWorkspaceDir();
  const archiveDir = findArchiveRunPath(workspaceDir, runId);
  if (!archiveDir) {
    return res.status(400).json({ error: 'Invalid runId format' });
  }
  const safe = resolveSafeWorkspacePath(archiveDir, filePath, 'existing');
  if (!safe.ok) {
    return res.status(safePathHttpStatus(safe)).json({ error: safePathError(safe) });
  }
  const fullPath = safe.realPath || safe.absolute;

  const maxSize = parseInt(req.query.maxSize as string) || 0;

  try {
    const stat = fs.statSync(fullPath);
    if (stat.isDirectory()) {
      return res.status(400).json({ error: 'Cannot read directory content' });
    }

    const offset = parseInt(req.query.offset as string) || 0;
    res.json(readTextFileContent(fullPath, maxSize, offset));
  } catch (e) {
    console.error(`Failed to read archive file ${fullPath}:`, e);
    res.status(500).json({ error: (e as Error).message });
  }
});

// Get raw file from archive (for images, etc.)
app.get('/api/archive/files/raw', (req, res) => {
  const runId = req.query.runId as string;
  const filePath = req.query.path as string;

  if (!runId) return res.status(400).json({ error: 'runId is required' });
  if (!filePath) return res.status(400).json({ error: 'Path is required' });

  const workspaceDir = getWorkspaceDir();
  const archiveDir = findArchiveRunPath(workspaceDir, runId);
  if (!archiveDir) {
    return res.status(400).json({ error: 'Invalid runId format' });
  }
  const safe = resolveSafeWorkspacePath(archiveDir, filePath, 'existing');
  if (!safe.ok) {
    return res.status(safePathHttpStatus(safe)).json({ error: safePathError(safe) });
  }
  const fullPath = safe.realPath || safe.absolute;

  try {
    if (!fs.existsSync(fullPath)) {
      return res.status(404).json({ error: 'File not found' });
    }
    res.sendFile(fullPath);
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});

// Upload files
app.post('/api/upload', (req, res, next) => {
  upload.array('files')(req, res, (err) => {
    if (err) {
      console.error('Multer upload error:', err);
      return res.status(500).json({ error: err.message });
    }
    next();
  });
}, (req, res) => {
  const workspaceDir = getWorkspaceDir();
  const files = req.files as Express.Multer.File[];

  console.log(`[Upload] Request received at /api/upload`);
  console.log(`[Upload] Workspace Dir: ${workspaceDir}`);

  if (!files || files.length === 0) {
    console.warn('[Upload] No files found in request');
    return res.status(400).json({ error: 'No files uploaded' });
  }

  // Parse relative paths if provided
  let relativePaths: string[] = [];
  try {
    relativePaths = JSON.parse(req.body.relativePaths || '[]');
  } catch (e) {
    console.warn('[Upload] Failed to parse relativePaths:', e);
  }

  console.log(`[Upload] Processing ${files.length} files`);

  const results: any[] = [];
  const errors: any[] = [];

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    try {
      // Use the provided relative path if available, else fallback to originalname
      const relativePath = String(relativePaths[i] || file.originalname || '').replace(/^\/+/, '');
      const safe = resolveSafeWorkspacePath(workspaceDir, relativePath, 'new');
      if (!safe.ok) {
        throw new Error(`Invalid path: ${relativePath}`);
      }
      const targetPath = safe.absolute;

      console.log(`[Upload] Processing file: ${relativePath} -> ${targetPath}`);

      // Create parent directory if it doesn't exist
      const parentDir = path.dirname(targetPath);
      if (!fs.existsSync(parentDir)) {
        console.log(`[Upload] Creating directory: ${parentDir}`);
        fs.mkdirSync(parentDir, { recursive: true });
      }

      // Move file from temp to target
      // Note: fs.renameSync can fail across devices (e.g. /tmp to /home), so we use copy+unlink if needed
      try {
        fs.renameSync(file.path, targetPath);
      } catch (renameErr: any) {
         if (renameErr.code === 'EXDEV') {
            fs.copyFileSync(file.path, targetPath);
            fs.unlinkSync(file.path);
         } else {
            throw renameErr;
         }
      }

      console.log(`[Upload] Successfully saved: ${relativePath}`);
      results.push(relativePath);
    } catch (e) {
      console.error(`[Upload] Error saving file ${file.originalname}:`, e);
      errors.push({ file: file.originalname, error: (e as Error).message });
      // Try to clean up temp file
      try {
        if (fs.existsSync(file.path)) fs.unlinkSync(file.path);
      } catch {
        // Ignore cleanup failures after reporting the original upload error.
      }
    }
  }

  res.json({
    success: true,
    uploaded: results,
    errors: errors.length > 0 ? errors : undefined
  });
});

// Rename file or folder
app.post('/api/files/rename', (req, res) => {
  const workspaceDir = getWorkspaceDir();
  const { oldPath, newPath } = req.body;

  if (!oldPath || !newPath) {
    return res.status(400).json({ error: 'oldPath and newPath are required' });
  }

  const safeOld = resolveSafeWorkspacePath(workspaceDir, String(oldPath), 'existing');
  const safeNew = resolveSafeWorkspacePath(workspaceDir, String(newPath), 'new');
  if (!safeOld.ok) {
    return res.status(safePathHttpStatus(safeOld)).json({ error: safePathError(safeOld) });
  }
  if (!safeNew.ok) {
    return res.status(safePathHttpStatus(safeNew)).json({ error: safePathError(safeNew) });
  }
  const fullOldPath = safeOld.realPath || safeOld.absolute;
  const fullNewPath = safeNew.absolute;

  try {
    // Fallback for cross-device rename if needed (though rare for rename in same workspace)
    try {
      fs.renameSync(fullOldPath, fullNewPath);
    } catch (err: any) {
      if (err.code === 'EXDEV') {
        // For directories, we'd need recursive copy, but usually rename within same mount is fine
        // If it's a file:
        if (fs.statSync(fullOldPath).isFile()) {
          fs.copyFileSync(fullOldPath, fullNewPath);
          fs.unlinkSync(fullOldPath);
        } else {
          throw new Error('Cannot rename directory across devices');
        }
      } else {
        throw err;
      }
    }

    console.log(`[Rename] ${oldPath} -> ${newPath}`);
    res.json({ success: true });
  } catch (e) {
    console.error(`[Rename] Error:`, e);
    res.status(500).json({ error: (e as Error).message });
  }
});

// Delete file or folder
app.post('/api/files/delete', (req, res) => {
  const workspaceDir = getWorkspaceDir();
  const { path: itemPath } = req.body;

  if (!itemPath) {
    return res.status(400).json({ error: 'Path is required' });
  }

  // Lexical only so users can remove dangling/outside-pointing symlinks without following them.
  const safe = resolveSafeWorkspacePath(workspaceDir, String(itemPath), 'lexical');
  if (!safe.ok) {
    return res.status(safePathHttpStatus(safe)).json({ error: safePathError(safe) });
  }
  const fullPath = safe.absolute;

  try {
    fs.lstatSync(fullPath);
  } catch {
    return res.status(404).json({ error: 'File not found' });
  }

  try {
    fs.rmSync(fullPath, { recursive: true, force: true });
    console.log(`[Delete] ${itemPath}`);
    res.json({ success: true });
  } catch (e) {
    console.error(`[Delete] Error:`, e);
    res.status(500).json({ error: (e as Error).message });
  }
});

// Write/save file content
app.post('/api/files/write', (req, res) => {
  const workspaceDir = getWorkspaceDir();
  const { path: filePath, content } = req.body;

  if (!filePath) {
    return res.status(400).json({ error: 'Path is required' });
  }

  if (content === undefined) {
    return res.status(400).json({ error: 'Content is required' });
  }

  const safe = resolveSafeWorkspacePath(workspaceDir, String(filePath), 'new');
  if (!safe.ok) {
    return res.status(safePathHttpStatus(safe)).json({ error: safePathError(safe) });
  }
  const fullPath = safe.absolute;

  try {
    // Create parent directory if it doesn't exist
    const parentDir = path.dirname(fullPath);
    if (!fs.existsSync(parentDir)) {
      fs.mkdirSync(parentDir, { recursive: true });
    }

    fs.writeFileSync(fullPath, content, 'utf-8');
    console.log(`[Write] ${filePath}`);
    res.json({ success: true });
  } catch (e) {
    console.error(`[Write] Error:`, e);
    res.status(500).json({ error: (e as Error).message });
  }
});

// List history from archive
app.get('/api/history', (req, res) => {
  const workspaceDir = getWorkspaceDir();
  const archiveRuns = listArchiveRuns(workspaceDir);

  if (archiveRuns.length === 0) {
    return res.json([]);
  }

  try {
    const runs = archiveRuns
      .map(({ id: runDir, path: runPath }) => {
        // Extract prompt from quasar_logs/conversation.md
        let prompt = "Self Improvement";
        const convPath = findRunLogFile(runPath, 'conversation.md');
        if (convPath && fs.existsSync(convPath)) {
          const content = readTextPreview(convPath);
          const match = content.match(/## \[User\]: Request\n\n([\s\S]*?)(?=\n\n|$)/);
          if (match && match[1] && match[1].trim()) {
            prompt = match[1].trim();
          }
        }

        // Extract summary from final_results/summary.md, run dir, or task subdirectories
        let summary = "No summary available.";
        let summaryPath = path.join(runPath, 'final_results', 'summary.md');
        if (!fs.existsSync(summaryPath)) {
          summaryPath = path.join(runPath, 'summary.md');
        }
        // If not found at top level, search inside task_N subdirectories
        if (!fs.existsSync(summaryPath)) {
          try {
            const entries = fs.readdirSync(runPath).filter(e =>
              e.startsWith('task_') && fs.statSync(path.join(runPath, e)).isDirectory()
            ).sort((a, b) => {
              // Sort by task number descending to get the latest task first
              const numA = parseInt(a.replace('task_', '')) || 0;
              const numB = parseInt(b.replace('task_', '')) || 0;
              return numB - numA;
            });
            for (const taskDir of entries) {
              const candidate = path.join(runPath, taskDir, 'final_results', 'summary.md');
              if (fs.existsSync(candidate)) {
                summaryPath = candidate;
                break;
              }
              const candidate2 = path.join(runPath, taskDir, 'summary.md');
              if (fs.existsSync(candidate2)) {
                summaryPath = candidate2;
                break;
              }
            }
          } catch (e) { /* ignore */ }
        }
        if (fs.existsSync(summaryPath)) {
          summary = readTextPreview(summaryPath);
        }

        // Extract usage report from quasar_logs/usage_report.md
        let usageReport = null;
        const usageReportPath = findRunLogFile(runPath, 'usage_report.md');
        if (usageReportPath && fs.existsSync(usageReportPath)) {
          usageReport = readTextPreview(usageReportPath);
        }

        // Extract execution overview from quasar_logs/execution_overview.md
        let executionOverview = null;
        const executionOverviewPath = findRunLogFile(runPath, 'execution_overview.md');
        if (executionOverviewPath && fs.existsSync(executionOverviewPath)) {
          executionOverview = readTextPreview(executionOverviewPath);
        }

        const stat = fs.statSync(runPath);
        // Extract execution time from quasar_logs/input_messages.md
        let timestamp: Date = stat.mtime;
        const inputLogsPath = findRunLogFile(runPath, 'input_messages.md');
        if (inputLogsPath && fs.existsSync(inputLogsPath)) {
          const content = readTextPreview(inputLogsPath);
          const timeMatch = content.match(/\*Logged at: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\*/);
          if (timeMatch && timeMatch[1]) {
            timestamp = new Date(timeMatch[1]);
          }
        }

        return {
          id: runDir,
          displayId: displayArchiveRunId(runDir),
          title: prompt,
          summary: summary,
          usageReport: usageReport,
          executionOverview: executionOverview,
          timestamp: timestamp.toISOString()
        };
      })
      .sort((a, b) => {
        const timeDiff = new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
        if (timeDiff !== 0) return timeDiff;
        return archiveRunSortKey(b.id).localeCompare(archiveRunSortKey(a.id));
      });


    res.json(runs);
  } catch (e) {
    console.error('Failed to list history:', e);
    res.status(500).json({ error: (e as Error).message });
  }
});

// Get execution trace from an archived run
app.get('/api/archive/:id/trace', async (req, res) => {
  const archiveId = req.params.id;
  const workspaceDir = getWorkspaceDir();
  const archivePath = findArchiveRunPath(workspaceDir, archiveId);

  if (!archivePath) {
    return res.status(404).json({ error: 'Archive not found' });
  }

  const checkpointPath = existingCheckpointArtifactPath(archivePath, CHECKPOINT_DB_FILE);

  if (!fs.existsSync(checkpointPath)) {
    return res.status(404).json({ error: 'No checkpoint found in archive' });
  }

  // Extract prompt from quasar_logs/conversation.md
  let previousInput = "Self Improvement";
  const convPath = findRunLogFile(archivePath, 'conversation.md');
  if (convPath && fs.existsSync(convPath)) {
    const content = readTextPreview(convPath);
    const match = content.match(/## \[User\]: Request\n\n([\s\S]*?)(?=\n\n|$)/);
    if (match && match[1] && match[1].trim()) {
      previousInput = match[1].trim();
    }
  }

  console.log(`Loading trace from archive: ${archiveId}`);
  const traceCacheKey = getFileSignature(checkpointPath);
  const cachedTrace = traceCacheKey ? archiveTraceCache.get(archiveId) : null;
  if (traceCacheKey && cachedTrace?.key === traceCacheKey) {
    return res.json({
      ...cachedTrace.value,
      previousInput,
      archiveId,
    });
  }

  // Run Python snippet to extract history from archive checkpoint
  const extractProcess = spawnPythonHelper(`
${PYTHON_HELPER_PREAMBLE}
from pathlib import Path

try:
    from src.checkpoint import get_thread_config
    from src.graph import build_graph
    from bridge_history import extract_checkpoint_history
    from langgraph.checkpoint.sqlite import SqliteSaver

    # Use archive-specific checkpoint path
    archive_checkpoint_path = os.environ["QUASAR_ARCHIVE_CHECKPOINT_PATH"]

    # Initialize minimal components to read state
    class FakeLLM:
        def invoke(self, *args, **kwargs): return None
        def bind_tools(self, *args, **kwargs): return self

    llm = FakeLLM()
    graph_builder = build_graph(llm)

    # Create checkpoint infrastructure pointing to archive
    # SqliteSaver.from_conn_string returns a context manager
    with SqliteSaver.from_conn_string(archive_checkpoint_path) as memory:
        graph = graph_builder.compile(checkpointer=memory)
        config = get_thread_config()
        state = graph.get_state(config)
        state_history = list(graph.get_state_history(config))

        history = None
        if state and state.values:
            history = extract_checkpoint_history(
                state.values,
                state.values.get('messages', []),
                state_history=state_history,
            )

        print(json.dumps({
            "exists": True,
            "history": history
        }))
except Exception as e:
    print(json.dumps({
        "exists": False,
        "error": str(e),
        "traceback": format_exc()
    }))
`, { QUASAR_ARCHIVE_CHECKPOINT_PATH: checkpointPath });

  let output = '';
  extractProcess.stdout?.on('data', (data) => {
    output += data.toString();
  });

  let stderr = '';
  extractProcess.stderr?.on('data', (data) => {
    stderr += data.toString();
  });

  extractProcess.on('close', (code) => {
    try {
      const extracted = JSON.parse(output.trim());
      if (traceCacheKey && !extracted.error) {
        archiveTraceCache.set(archiveId, { key: traceCacheKey, value: extracted });
      }
      const result = { ...extracted };
      result.previousInput = previousInput;
      result.archiveId = archiveId;
      res.json(result);
    } catch (e) {
      console.error('Failed to parse archive trace:', output, stderr);
      res.status(500).json({ error: 'Failed to extract trace', details: stderr });
    }
  });
});

// Get raw file (for images, etc.)
app.get('/api/files/raw', (req, res) => {
  const filePath = req.query.path as string;
  if (!filePath) return res.status(400).json({ error: 'Path is required' });

  const workspaceDir = getWorkspaceDir();
  const safe = resolveSafeWorkspacePath(workspaceDir, filePath, 'existing');
  if (!safe.ok) {
    return res.status(safePathHttpStatus(safe)).json({ error: safePathError(safe) });
  }
  const fullPath = safe.realPath || safe.absolute;

  try {
    res.sendFile(fullPath);
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});

// Get file content (supports partial loading via maxSize query param)
app.get('/api/files/content', (req, res) => {
  const filePath = req.query.path as string;
  const maxSize = parseInt(req.query.maxSize as string) || 0;
  if (!filePath) return res.status(400).json({ error: 'Path is required' });

  const workspaceDir = getWorkspaceDir();
  const safe = resolveSafeWorkspacePath(workspaceDir, filePath, 'existing');
  if (!safe.ok) {
    return res.status(safePathHttpStatus(safe)).json({ error: safePathError(safe) });
  }
  const fullPath = safe.realPath || safe.absolute;

  try {
    const stat = fs.statSync(fullPath);
    if (stat.isDirectory()) {
      return res.status(400).json({ error: 'Cannot read directory content' });
    }

    const offset = parseInt(req.query.offset as string) || 0;
    res.json(readTextFileContent(fullPath, maxSize, offset));
  } catch (e) {
    console.error(`Failed to read file ${fullPath}:`, e);
    res.json({ error: (e as Error).message });
  }
});

// Process CIF structure with pymatgen (cell transformations, CrystalNN bonding)
app.post('/api/structure/process', (req, res) => {
  const { cifContent, cellType, bonding, draw_image_atoms, bonded_sites_outside_unit_cell, unit_cell_repeats, mof_mode } = req.body;

  if (!cifContent) {
    return res.status(400).json({ error: 'cifContent is required' });
  }

  // In production, __dirname is dist-server/, but script is in server/scripts/
  // Resolve to the source server directory or explicit QUASAR_WEB_SCRIPTS_DIR override
  const serverDir = __dirname.replace('/dist-server', '/server').replace('\\dist-server', '\\server');
  const scriptsDir = (process.env.QUASAR_WEB_SCRIPTS_DIR || '').trim() || path.join(serverDir, 'scripts');
  const scriptPath = path.join(scriptsDir, 'structure_processor.py');

  // Check if script exists
  if (!fs.existsSync(scriptPath)) {
    console.error(`Structure processor script not found at ${scriptPath}`);
    return res.status(500).json({ error: 'Structure processor not available' });
  }

  const inputData = JSON.stringify({
    cif_content: cifContent,
    cell_type: cellType || 'input',
    bonding: bonding || 'jmol',
    draw_image_atoms: draw_image_atoms !== false, // Default to true
    bonded_sites_outside_unit_cell: bonded_sites_outside_unit_cell === true, // Default to false
    unit_cell_repeats: Array.isArray(unit_cell_repeats) ? unit_cell_repeats : [1, 1, 1],
    mof_mode: mof_mode === true
  });
  const processorSignature = getFileSignature(scriptPath) || 'unknown';
  const cacheKey = createHash('sha256')
    .update(inputData)
    .update(processorSignature)
    .digest('hex');
  const cached = structureProcessCache.get(cacheKey);
  if (cached) {
    return res.json(cached);
  }

  const pythonProcess = spawn(pythonCommand, [scriptPath], {
    cwd: path.dirname(scriptPath),
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' }
  });

  let stdout = '';
  let stderr = '';
  let responded = false;
  const timeout = setTimeout(() => {
    responded = true;
    pythonProcess.kill('SIGKILL');
    res.status(504).json({ error: 'Structure processing timed out' });
  }, STRUCTURE_PROCESS_TIMEOUT_MS);

  pythonProcess.stdout?.on('data', (data) => {
    stdout += data.toString();
  });

  pythonProcess.stderr?.on('data', (data) => {
    stderr += data.toString();
  });

  // Send input to Python script
  pythonProcess.stdin?.write(inputData);
  pythonProcess.stdin?.end();

  pythonProcess.on('close', (code) => {
    clearTimeout(timeout);
    if (responded) return;
    responded = true;
    if (code !== 0) {
      console.error(`Structure processor exited with code ${code}: ${stderr}`);
      return res.status(500).json({ error: `Processing failed: ${stderr || 'Unknown error'}` });
    }

    try {
      const result = JSON.parse(stdout.trim());
      if (result.error) {
        return res.status(400).json({ error: result.error });
      }
      structureProcessCache.set(cacheKey, result);
      if (structureProcessCache.size > STRUCTURE_PROCESS_CACHE_LIMIT) {
        const oldestKey = structureProcessCache.keys().next().value;
        if (oldestKey) structureProcessCache.delete(oldestKey);
      }
      res.json(result);
    } catch (e) {
      console.error('Failed to parse structure processor output:', stdout);
      res.status(500).json({ error: 'Failed to parse processor output' });
    }
  });

  pythonProcess.on('error', (err) => {
    clearTimeout(timeout);
    if (responded) return;
    responded = true;
    console.error('Failed to spawn structure processor:', err);
    res.status(500).json({ error: 'Failed to start structure processor' });
  });
});

// SPA fallback - must be last
if (process.env.NODE_ENV === 'production' || process.env.SERVE_STATIC === 'true') {
  app.use((req, res) => {
    res.sendFile(path.join(distPath, 'index.html'));
  });
}

// Start resource preloading
preloadResources();
