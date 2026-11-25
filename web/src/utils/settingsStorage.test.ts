import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getStoredSettings,
  hasConfiguredApiKey,
  mergeSettingsPreservingMaskedValues,
  sanitizeSettings,
  setStoredSettings,
  SENSITIVE_SETTING_MASK,
} from './settingsStorage';

const memory = new Map<string, string>();
(globalThis as unknown as { localStorage: Storage }).localStorage = {
  getItem: (k: string) => memory.get(k) ?? null,
  setItem: (k: string, v: string) => {
    memory.set(k, v);
  },
  removeItem: (k: string) => {
    memory.delete(k);
  },
  clear: () => {
    memory.clear();
  },
  key: () => null,
  length: 0,
};

test('masked server settings do not overwrite a real browser API key', () => {
  const merged = mergeSettingsPreservingMaskedValues(
    {
      MODEL: 'custom-model',
      MODEL_API_KEY: 'real-secret',
      OPENAI_API_BASE: 'http://localhost:1234/v1',
    },
    {
      MODEL: 'custom-model',
      MODEL_API_KEY: SENSITIVE_SETTING_MASK,
      OPENAI_API_BASE: SENSITIVE_SETTING_MASK,
    }
  );

  assert.equal(merged.MODEL_API_KEY, 'real-secret');
  assert.equal(merged.OPENAI_API_BASE, 'http://localhost:1234/v1');
});

test('masked server setting is retained as a configured sentinel without a local key', () => {
  const merged = mergeSettingsPreservingMaskedValues(
    { MODEL: 'custom-model' },
    { MODEL_API_KEY: SENSITIVE_SETTING_MASK }
  );

  assert.equal(merged.MODEL_API_KEY, SENSITIVE_SETTING_MASK);
  assert.equal(hasConfiguredApiKey(merged, { allowServerMask: true }), true);
  assert.equal(hasConfiguredApiKey(merged), false);
});

test('retired scientific-engine overrides are removed from browser settings', () => {
  assert.deepEqual(
    sanitizeSettings({
      MODEL: 'gemini-2.5-pro',
      QUASAR_QE_PATH: '/custom/qe',
      QUASAR_LAMMPS_PATH: '/custom/lammps',
    }),
    { MODEL: 'gemini-2.5-pro' }
  );
});

test('mask sentinels are never persisted into localStorage', () => {
  memory.clear();
  setStoredSettings({
    MODEL: 'gemini-2.5-pro',
    MODEL_API_KEY: SENSITIVE_SETTING_MASK,
  });
  assert.deepEqual(getStoredSettings(), { MODEL: 'gemini-2.5-pro' });
});
