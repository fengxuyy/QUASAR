import test from 'node:test';
import assert from 'node:assert/strict';

import { parseStatusWithFileLinks, resolveWorkspaceLinkTarget } from './fileLinkUtils';

test('parseStatusWithFileLinks shows only the basename for nested file reads', () => {
  const segments = parseStatusWithFileLinks('Read task_1/run.py');

  assert.deepEqual(segments, [
    { type: 'text', content: 'Read ' },
    { type: 'file', content: 'run.py', filePath: 'task_1/run.py' },
  ]);
});

test('parseStatusWithFileLinks shows only the basename for nested executed files', () => {
  const segments = parseStatusWithFileLinks('Executed task_1/run.py');

  assert.deepEqual(segments, [
    { type: 'text', content: 'Executed ' },
    { type: 'file', content: 'run.py', filePath: 'task_1/run.py' },
  ]);
});

test('parseStatusWithFileLinks links nested directory listings and shows only the end path', () => {
  const segments = parseStatusWithFileLinks('Listed task_1/output_dir');

  assert.deepEqual(segments, [
    { type: 'text', content: 'Listed ' },
    { type: 'file', content: 'output_dir', filePath: 'task_1/output_dir' },
  ]);
});

test('parseStatusWithFileLinks links directory listings that include a trailing slash', () => {
  const segments = parseStatusWithFileLinks('Listed ch4_gcmc_cifs/');

  assert.deepEqual(segments, [
    { type: 'text', content: 'Listed ' },
    { type: 'file', content: 'ch4_gcmc_cifs', filePath: 'ch4_gcmc_cifs' },
  ]);
});

test('parseStatusWithFileLinks hyperlinks each path for multi-directory list_directory', () => {
  const segments = parseStatusWithFileLinks('Listed task_3, task_4');

  assert.deepEqual(segments, [
    { type: 'text', content: 'Listed ' },
    { type: 'file', content: 'task_3', filePath: 'task_3' },
    { type: 'text', content: ', ' },
    { type: 'file', content: 'task_4', filePath: 'task_4' },
  ]);
});

test('parseStatusWithFileLinks hyperlinks nested paths in multi-directory listings', () => {
  const segments = parseStatusWithFileLinks('Listed runs/task_3, runs/task_4');

  assert.deepEqual(segments, [
    { type: 'text', content: 'Listed ' },
    { type: 'file', content: 'task_3', filePath: 'runs/task_3' },
    { type: 'text', content: ', ' },
    { type: 'file', content: 'task_4', filePath: 'runs/task_4' },
  ]);
});

test('parseStatusWithFileLinks does not split Listed dir (*.py) on commas inside glob', () => {
  const segments = parseStatusWithFileLinks('Listed out_dir (*.py, *.txt)');

  assert.deepEqual(segments, [
    { type: 'text', content: 'Listed ' },
    { type: 'file', content: 'out_dir', filePath: 'out_dir' },
    { type: 'text', content: ' (*.py, *.txt)' },
  ]);
});

test('parseStatusWithFileLinks preserves listing suffixes while linking nested paths', () => {
  const segments = parseStatusWithFileLinks('Listing task_1/output_dir (*.py)');

  assert.deepEqual(segments, [
    { type: 'text', content: 'Listing ' },
    { type: 'file', content: 'output_dir', filePath: 'task_1/output_dir' },
    { type: 'text', content: ' (*.py)' },
  ]);
});

test('parseStatusWithFileLinks preserves listing suffixes for paths with trailing slashes', () => {
  const segments = parseStatusWithFileLinks('Listing task_1/output_dir/ (*.py)');

  assert.deepEqual(segments, [
    { type: 'text', content: 'Listing ' },
    { type: 'file', content: 'output_dir', filePath: 'task_1/output_dir' },
    { type: 'text', content: ' (*.py)' },
  ]);
});

test('parseStatusWithFileLinks does not hyperlink bare quasar archive directories', () => {
  const segments = parseStatusWithFileLinks('Listed quasar_archive');

  assert.deepEqual(segments, [
    { type: 'text', content: 'Listed quasar_archive' },
  ]);
});

test('resolveWorkspaceLinkTarget extracts archive ids from quasar_archive-prefixed file paths', () => {
  const target = resolveWorkspaceLinkTarget('quasar_archive/quasar_run_20260519_103011_a1b2c3/final_results/summary.md');

  assert.deepEqual(target, {
    archiveId: 'quasar_run_20260519_103011_a1b2c3',
    filePath: 'final_results/summary.md',
  });
});

test('resolveWorkspaceLinkTarget treats archive roots as archive tab switches', () => {
  const target = resolveWorkspaceLinkTarget('quasar_archive/quasar_run_20260519_103011_a1b2c3');

  assert.deepEqual(target, {
    archiveId: 'quasar_run_20260519_103011_a1b2c3',
    filePath: '.',
  });
});
