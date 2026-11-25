import test from 'node:test';
import assert from 'node:assert/strict';

import { looksLikeToolValidationMessage } from './validationErrorMessage';

test('looksLikeToolValidationMessage matches format_validation_error output', () => {
  assert.ok(
    looksLikeToolValidationMessage(
      "Validation error (2 issues): Field 'query': Field required; Field 'library': Field required"
    )
  );
});

test('looksLikeToolValidationMessage rejects normal analysis text', () => {
  assert.equal(looksLikeToolValidationMessage('I will query the RAG index next.'), false);
});
