import test from 'node:test';
import assert from 'node:assert/strict';

import { getToolValidationFailureTitle } from './toolValidationFailureTitle';

test('getToolValidationFailureTitle matches bridge_history tool names', () => {
  assert.equal(getToolValidationFailureTitle('query_rag'), 'Query RAG Failed');
  assert.equal(getToolValidationFailureTitle('grep_search'), 'Grep Files Failed');
});

test('getToolValidationFailureTitle title-cases unknown tools', () => {
  assert.equal(getToolValidationFailureTitle('custom_tool'), 'Custom Tool Failed');
});

test('getToolValidationFailureTitle fallback when tool unknown', () => {
  assert.equal(getToolValidationFailureTitle(undefined), 'Tool validation failed');
  assert.equal(getToolValidationFailureTitle(''), 'Tool validation failed');
});
