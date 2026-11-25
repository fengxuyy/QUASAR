import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const CLI_UTILS_DIR = path.dirname(fileURLToPath(import.meta.url));
const CLI_PACKAGE_ROOT = path.resolve(CLI_UTILS_DIR, '../..');

export function resolvePythonCommand(): string {
    const configured = (process.env.QUASAR_PYTHON || '').trim();
    return configured || 'python3';
}

export function resolveBridgePath(): string | null {
    const fromEnv = (process.env.QUASAR_BRIDGE_PATH || '').trim();
    if (fromEnv && fs.existsSync(fromEnv)) {
        return fromEnv;
    }

    const runtimeRoot = (process.env.QUASAR_RUNTIME_ROOT || '').trim();
    const candidates = [
        runtimeRoot ? path.join(runtimeRoot, 'bridge.py') : '',
        path.resolve(process.cwd(), 'bridge.py'),
        path.resolve(process.cwd(), '../bridge.py'),
        path.resolve(CLI_PACKAGE_ROOT, '../bridge.py'),
        '/app/bridge.py',
    ].filter(Boolean);

    for (const candidate of candidates) {
        if (fs.existsSync(candidate)) {
            return candidate;
        }
    }

    return null;
}

export function resolveRuntimeRoot(): string {
    const bridgePath = resolveBridgePath();
    if (bridgePath) {
        return path.dirname(bridgePath);
    }

    const runtimeRoot = (process.env.QUASAR_RUNTIME_ROOT || '').trim();
    if (runtimeRoot && fs.existsSync(runtimeRoot)) {
        return runtimeRoot;
    }

    return process.cwd();
}
