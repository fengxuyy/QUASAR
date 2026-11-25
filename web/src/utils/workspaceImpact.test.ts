import test from 'node:test';
import assert from 'node:assert/strict';

import { extractWorkspaceImpacts } from './workspaceImpact';
import type { BridgeMessage } from './messageHelpers';

const byPath = (items: ReturnType<typeof extractWorkspaceImpacts>) =>
  Object.fromEntries(items.map((item) => [item.path, item]));

test('extractWorkspaceImpacts reads nested file paths from statuses', () => {
  const messages: BridgeMessage[] = [
    { type: 'task_progress', payload: { current: 2, total: 4, title: 'Run analysis' } },
    { type: 'agent_event', payload: { agent: 'operator', event: 'step_complete', status: 'Read task_1/run.py' } },
  ];

  const impacts = extractWorkspaceImpacts(messages);

  assert.equal(impacts.length, 1);
  assert.equal(impacts[0].path, 'task_1/run.py');
  assert.equal(impacts[0].displayName, 'run.py');
  assert.equal(impacts[0].kind, 'read');
  assert.equal(impacts[0].lastTask, 2);
});

test('extractWorkspaceImpacts groups repeated references to the same path', () => {
  const impacts = extractWorkspaceImpacts([
    { type: 'agent_event', payload: { agent: 'operator', event: 'step_complete', status: 'Read results.csv' } },
    { type: 'agent_event', payload: { agent: 'operator', event: 'step_complete', status: 'Read ./results.csv' } },
  ]);

  assert.equal(impacts.length, 1);
  assert.equal(impacts[0].path, 'results.csv');
  assert.equal(impacts[0].count, 2);
});

test('extractWorkspaceImpacts classifies edited, executed, listed, and analyzed impacts', () => {
  const impactsByPath = byPath(extractWorkspaceImpacts([
    { type: 'agent_event', payload: { agent: 'operator', event: 'step_complete', status: 'Edited src/example.py' } },
    { type: 'agent_event', payload: { agent: 'operator', event: 'step_complete', status: 'Executed task_1/run.py' } },
    { type: 'agent_event', payload: { agent: 'operator', event: 'step_complete', status: 'Listed task_1/output_dir' } },
    { type: 'agent_event', payload: { agent: 'evaluator', event: 'step_complete', status: 'Analyzed images/result.png' } },
  ]));

  assert.equal(impactsByPath['src/example.py'].kind, 'edit');
  assert.equal(impactsByPath['task_1/run.py'].kind, 'execute');
  assert.equal(impactsByPath['task_1/output_dir'].kind, 'read');
  assert.equal(impactsByPath['images/result.png'].kind, 'execute');
});

test('extractWorkspaceImpacts marks errored file events', () => {
  const impacts = extractWorkspaceImpacts([
    { type: 'agent_event', payload: { agent: 'operator', event: 'step_complete', status: 'Read missing.py', is_error: true } },
  ]);

  assert.equal(impacts.length, 1);
  assert.equal(impacts[0].path, 'missing.py');
  assert.equal(impacts[0].kind, 'error');
  assert.equal(impacts[0].isError, true);
});

test('extractWorkspaceImpacts ignores messages without file or directory references', () => {
  const impacts = extractWorkspaceImpacts([
    { type: 'agent_event', payload: { agent: 'operator', event: 'update', status: 'Analysing Task' } },
    { type: 'agent_event', payload: { agent: 'operator', event: 'step_complete', status: 'Searched catalyst synthesis (4 results)' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Thinking', is_complete: false } },
  ]);

  assert.deepEqual(impacts, []);
});
