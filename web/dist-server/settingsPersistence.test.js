import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { loadPersistedSettings, savePersistedSettings } from './settingsPersistence.js';
test('persisted model settings survive a server restart without unrelated keys', () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'quasar-settings-'));
    const settingsPath = path.join(tempDir, '.quasar_web_settings.json');
    const allowedKeys = new Set(['MODEL', 'MODEL_API_KEY', 'OPENAI_API_BASE']);
    try {
        savePersistedSettings(settingsPath, {
            MODEL: 'custom-model',
            MODEL_API_KEY: 'secret-key',
            OPENAI_API_BASE: 'http://model-server/v1',
            UNRELATED_KEY: 'should-not-persist',
        }, allowedKeys);
        assert.deepEqual(loadPersistedSettings(settingsPath, allowedKeys), {
            MODEL: 'custom-model',
            MODEL_API_KEY: 'secret-key',
            OPENAI_API_BASE: 'http://model-server/v1',
        });
        assert.equal(fs.statSync(settingsPath).mode & 0o777, 0o600);
    }
    finally {
        fs.rmSync(tempDir, { recursive: true, force: true });
    }
});
test('malformed persisted settings are ignored', () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'quasar-settings-'));
    const settingsPath = path.join(tempDir, '.quasar_web_settings.json');
    try {
        fs.writeFileSync(settingsPath, '{not-json');
        assert.equal(loadPersistedSettings(settingsPath, new Set(['MODEL'])), null);
    }
    finally {
        fs.rmSync(tempDir, { recursive: true, force: true });
    }
});
