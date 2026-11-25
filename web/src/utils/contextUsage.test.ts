import test from 'node:test';
import assert from 'node:assert/strict';

import {
  formatTokenCount,
  formatUsagePercent,
  getContextUsageProgress,
  getContextUsageTone,
} from './contextUsage';

const baseSnapshot = {
  agent: 'operator',
  model: 'gemini-2.5-pro',
  threshold_level: 'medium' as const,
  threshold_ratio: 0.4,
  threshold_percent: 40,
  max_context_tokens: 1_048_576,
  threshold_tokens: 419_430,
  input_tokens: 300_000,
  usage_percent: 71.5,
  max_context_percent: 28.6,
  remaining_tokens: 119_430,
  is_supported_model: true,
  is_over_limit: false,
};

test('formatTokenCount handles numbers and missing values', () => {
  assert.equal(formatTokenCount(419430), '419,430');
  assert.equal(formatTokenCount(null), '--');
});

test('formatUsagePercent preserves one decimal place only when needed', () => {
  assert.equal(formatUsagePercent(47.7), '47.7%');
  assert.equal(formatUsagePercent(100), '100%');
  assert.equal(formatUsagePercent(undefined), '--');
});

test('getContextUsageTone maps supported snapshots to UI states', () => {
  assert.equal(getContextUsageTone(baseSnapshot), 'safe');
  assert.equal(getContextUsageTone({ ...baseSnapshot, usage_percent: 82.5 }), 'warning');
  assert.equal(getContextUsageTone({ ...baseSnapshot, usage_percent: 111.3, is_over_limit: true }), 'danger');
  assert.equal(getContextUsageTone({ ...baseSnapshot, is_supported_model: false, usage_percent: null }), 'neutral');
});

test('getContextUsageProgress clamps values into the progress-bar range', () => {
  assert.equal(getContextUsageProgress(baseSnapshot), 71.5);
  assert.equal(getContextUsageProgress({ ...baseSnapshot, usage_percent: 143.2 }), 100);
  assert.equal(getContextUsageProgress({ ...baseSnapshot, is_supported_model: false, usage_percent: null }), 0);
});
