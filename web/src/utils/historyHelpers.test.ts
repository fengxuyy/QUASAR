import test from 'node:test';
import assert from 'node:assert/strict';

import { parseHistoryToMessages } from './historyHelpers';

test('parseHistoryToMessages renders completed tasks even when only summaries are available', () => {
  const messages = parseHistoryToMessages({
    plan: [
      'Task 1: Prepare data',
      'Task 2: Run analysis',
      'Task 3: Write summary',
    ],
    completed_steps: ['Prepare data', 'Run analysis', 'Write summary'],
    step_results: {
      '0': 'Prepared data successfully.',
      '1': 'Ran the analysis successfully.',
      '2': 'Saved the final summary successfully.',
    },
  } as any);

  const taskNumbers = messages
    .filter(message => message.type === 'task_progress')
    .map(message => message.payload?.current);

  const evaluationSummaries = messages
    .filter(
      message =>
        message.type === 'agent_event' &&
        message.payload?.agent === 'Evaluator' &&
        message.payload?.status === 'Evaluation Passed'
    )
    .map(message => message.payload?.output);

  assert.deepEqual(taskNumbers, [1, 2, 3]);
  assert.deepEqual(evaluationSummaries, [
    'Prepared data successfully.',
    'Ran the analysis successfully.',
    'Saved the final summary successfully.',
  ]);
});

test('parseHistoryToMessages uses code-result status for execute_python (matches runtime label)', () => {
  const messages = parseHistoryToMessages({
    plan: ['Task 1: Run script'],
    completed_steps: ['Run script'],
    step_results: { '0': 'Task done.' },
    ordered_items_by_task: {
      '0': [
        {
          type: 'code-result',
          agent: 'operator',
          content: {
            output: '**Execution Result:**\n\nok\n',
            filePath: 'analysis/run.py',
            status: 'Executed run.py',
          },
          isError: false,
        },
        {
          type: 'tool',
          agent: 'operator',
          name: 'execute_python',
          content: 'Executed task_1/run.py',
          tool_id: 'exec-1',
        },
      ],
    },
  } as any);

  const step = messages.find(
    m =>
      m.type === 'agent_event' &&
      m.payload?.event === 'step_complete' &&
      typeof m.payload?.status === 'string' &&
      m.payload.status === 'Executed run.py'
  );
  assert.ok(step, 'expected step_complete with runtime-style execute_python status');
  assert.equal(
    (step as any).payload.output,
    '**Execution Result:**\n\nok\n'
  );
});

test('parseHistoryToMessages ignores removed file-tool history rows', () => {
  const messages = parseHistoryToMessages({
    plan: ['Task 1: Update files'],
    completed_steps: ['Update files'],
    step_results: { '0': 'Task done.' },
    ordered_items_by_task: {
      '0': [
        {
          type: 'code-snippet',
          content: { name: 'out.py', content: 'print(1)' },
        },
        {
          type: 'tool',
          agent: 'operator',
          name: 'write_file',
          content: 'Wrote out.py',
        },
        {
          type: 'tool',
          agent: 'operator',
          name: 'move_file',
          content: 'Moved out.py to archive/out.py',
        },
        {
          type: 'tool',
          agent: 'operator',
          name: 'rename_file',
          content: 'Renamed old.py to new.py',
        },
        {
          type: 'tool',
          agent: 'operator',
          name: 'delete_file',
          content: 'Deleted stale.py',
        },
        {
          type: 'tool',
          agent: 'operator',
          name: 'execute_python',
          content: 'Executed run.py',
        },
      ],
    },
  } as any);

  const statuses = messages
    .filter(message => message.type === 'agent_event')
    .map(message => message.payload?.status);

  assert.equal(statuses.includes('Wrote out.py'), false);
  assert.equal(statuses.includes('Moved out.py to archive/out.py'), false);
  assert.equal(statuses.includes('Renamed old.py to new.py'), false);
  assert.equal(statuses.includes('Deleted stale.py'), false);
  assert.equal(
    messages.some(message => message.type === 'log' && message.payload?.text === 'File: out.py'),
    false
  );
  assert.equal(statuses.includes('Executed run.py'), true);
});

test('parseHistoryToMessages maps validation model-text to error, not text_stream', () => {
  const validation =
    "Validation error (2 issues): Field 'query': Field required; Field 'library': Field required";
  const messages = parseHistoryToMessages({
    plan: ['Task 1: X'],
    completed_steps: ['x'],
    step_results: { '0': 'Summary' },
    ordered_items_by_task: {
      '0': [{ type: 'model-text', content: validation, agent: 'operator' }],
    },
  } as any);

  const err = messages.find(m => m.type === 'error');
  assert.ok(err, 'expected error message');
  assert.equal((err as any).payload.message, validation);
  assert.equal((err as any).payload.kind, 'tool_validation');
  assert.equal((err as any).payload.toolName, undefined);
  assert.equal(
    messages.some(m => m.type === 'text_stream'),
    false,
    'validation should not become Analysed Task stream'
  );
});

test('parseHistoryToMessages preserves query_rag output on step_complete entries', () => {
  const ragOutput = '## Match 1\n\nUse the embedding dimension from the model metadata.';
  const messages = parseHistoryToMessages({
    plan: ['Task 1: Query docs'],
    completed_steps: ['Query docs'],
    step_results: { '0': 'Done.' },
    ordered_items_by_task: {
      '0': [
        {
          type: 'tool',
          agent: 'operator',
          name: 'query_rag',
          content: 'Queried RAG embedding dimension in docs',
          output: ragOutput,
        },
      ],
    },
  } as any);

  const step = messages.find(
    m =>
      m.type === 'agent_event' &&
      m.payload?.event === 'step_complete' &&
      m.payload?.status === 'Queried RAG embedding dimension in docs'
  );

  assert.ok(step, 'expected query_rag step_complete entry');
  assert.equal((step as any).payload.output, ragOutput);
});

test('parseHistoryToMessages infers toolName for validation from the next tool row', () => {
  const validation = "Validation error (1 issue): Field 'pattern': Field required";
  const messages = parseHistoryToMessages({
    plan: ['Task 1: T'],
    completed_steps: ['x'],
    step_results: { '0': 'Summary' },
    ordered_items_by_task: {
      '0': [
        { type: 'model-text', content: validation, agent: 'operator' },
        { type: 'tool', name: 'grep_search', content: 'Grepped *.py', agent: 'operator' },
      ],
    },
  } as any);

  const err = messages.find(m => m.type === 'error');
  assert.equal((err as any)?.payload?.toolName, 'grep_search');
});
