import test from 'node:test';
import assert from 'node:assert/strict';

import {
  beginTrackedRun,
  canApplyRunCompletion,
  createRunLifecycleState,
  suppressRunCompletion,
} from './runLifecycle';

test('intentional stop suppresses late completion events', () => {
  const lifecycle = createRunLifecycleState();
  const runningRevision = beginTrackedRun(lifecycle);

  suppressRunCompletion(lifecycle);

  assert.equal(canApplyRunCompletion(lifecycle, runningRevision), false);
  assert.equal(canApplyRunCompletion(lifecycle, lifecycle.revision), false);
});

test('fresh reset invalidates an outstanding completion check', () => {
  const lifecycle = createRunLifecycleState();
  const completionCheckRevision = beginTrackedRun(lifecycle);

  suppressRunCompletion(lifecycle);

  assert.equal(canApplyRunCompletion(lifecycle, completionCheckRevision), false);
});

test('starting a new run re-enables completion handling with a new revision', () => {
  const lifecycle = createRunLifecycleState();
  const oldRevision = beginTrackedRun(lifecycle);
  suppressRunCompletion(lifecycle);
  const newRevision = beginTrackedRun(lifecycle);

  assert.equal(canApplyRunCompletion(lifecycle, oldRevision), false);
  assert.equal(canApplyRunCompletion(lifecycle, newRevision), true);
});
