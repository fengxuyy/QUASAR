import test from 'node:test';
import assert from 'node:assert/strict';

import { processMessages } from './messageHelpers';

test('processMessages merges cumulative partial chunks (full text so far per event)', () => {
  const processed = processMessages([
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Hello', is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Hello wo', is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Hello world', is_complete: true } },
  ]);

  const textStreams = processed.filter(msg => msg.type === 'text_stream');

  assert.equal(textStreams.length, 1);
  assert.equal(textStreams[0].payload?.content, 'Hello world');
});

test('processMessages keeps operator streaming text as one combined block across bursts', () => {
  const processed = processMessages([
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Hello', is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Hello', is_complete: true } },
    { type: 'text_stream', payload: { agent: 'operator', content: ' world', is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Hello world', is_complete: true } },
  ]);

  const textStreams = processed.filter(msg => msg.type === 'text_stream');

  assert.equal(textStreams.length, 1);
  assert.equal(textStreams[0].payload?.content, 'Hello world');
  assert.equal(textStreams[0].payload?.is_complete, true);
});

test('processMessages reopens a completed operator stream when more chunks arrive before an action boundary', () => {
  const processed = processMessages([
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'First fragment', is_complete: true } },
    { type: 'agent_event', payload: { agent: 'operator', event: 'update', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: ' and second fragment', is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'First fragment and second fragment', is_complete: true } },
  ]);

  const textStreams = processed.filter(msg => msg.type === 'text_stream');

  assert.equal(textStreams.length, 1);
  assert.equal(textStreams[0].payload?.content, 'First fragment and second fragment');
  assert.equal(textStreams[0].payload?.is_complete, true);
});

test('processMessages does not merge operator streams across a tool action boundary', () => {
  const processed = processMessages([
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'First analysis', is_complete: true } },
    { type: 'tool_call', payload: { tool: 'read_file' } },
    { type: 'agent_event', payload: { agent: 'operator', event: 'update', status: 'Reading input.in' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Second analysis', is_complete: true } },
  ]);

  const textStreams = processed.filter(msg => msg.type === 'text_stream');

  assert.equal(textStreams.length, 2);
  assert.equal(textStreams[0].payload?.content, 'First analysis');
  assert.equal(textStreams[1].payload?.content, 'Second analysis');
});

test('processMessages keeps continuous chunks as one Analysed Task across re-entrant Analysing starts', () => {
  // Backend may re-emit start/update "Analysing Task" between continuous LLM text
  // chunks; those must not split the UI into multiple Analysed Task headers.
  const processed = processMessages([
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Chunk one. ', is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Chunk one. Chunk two. ', is_complete: true } },
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Chunk three.', is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Chunk one. Chunk two. Chunk three.', is_complete: true } },
  ]);

  const textStreams = processed.filter(msg => msg.type === 'text_stream');

  assert.equal(textStreams.length, 1);
  assert.equal(textStreams[0].payload?.content, 'Chunk one. Chunk two. Chunk three.');
  assert.equal(textStreams[0].payload?.is_complete, true);
});

test('processMessages merges consecutive complete text_stream chunks with no agent events between them', () => {
  const processed = processMessages([
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Alpha', is_complete: true } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Beta', is_complete: true } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Gamma', is_complete: true } },
  ]);

  const textStreams = processed.filter(msg => msg.type === 'text_stream');

  assert.equal(textStreams.length, 1);
  assert.match(String(textStreams[0].payload?.content || ''), /Alpha/);
  assert.match(String(textStreams[0].payload?.content || ''), /Gamma/);
});

test('processMessages does not merge a fresh operator start into restored history text', () => {
  const processed = processMessages([
    { type: 'text_stream', _taskNum: 1, payload: { agent: 'operator', content: 'Restored analysis', is_complete: true } },
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Fresh analysis', is_complete: true } },
  ]);

  const textStreams = processed.filter(msg => msg.type === 'text_stream');

  assert.equal(textStreams.length, 2);
  assert.equal(textStreams[0].payload?.content, 'Restored analysis');
  assert.equal(textStreams[1].payload?.content, 'Fresh analysis');
});

test('processMessages does not duplicate the final streamed operator snapshot after tool selection', () => {
  const processed = processMessages([
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'First part ', is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'second part', is_complete: false } },
    { type: 'agent_event', payload: { agent: 'operator', event: 'update', status: 'Reading notes.txt' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'First part second part', is_complete: true } },
  ]);

  const textStreams = processed.filter(msg => msg.type === 'text_stream');

  assert.equal(textStreams.length, 1);
  assert.equal(textStreams[0].payload?.content, 'First part second part');
  assert.equal(textStreams[0].payload?.is_complete, true);
});

test('processMessages replaces nearly-cumulative snapshots instead of appending them', () => {
  const initial =
    "Now let me create the Quantum ESPRESSO inputs for the convergence tests. I'll create a Python script to generate the convergence test inputs:";
  const revised =
    "Now let me create the Quantum ESPRESSO input inputs for the convergence tests. I'll create a Python script to generate the convergence test inputs:";

  const processed = processMessages([
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: initial, is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: revised, is_complete: true } },
    { type: 'tool_call', payload: { tool: 'execute_python' } },
  ]);

  const textStreams = processed.filter(msg => msg.type === 'text_stream');

  assert.equal(textStreams.length, 1);
  assert.equal(textStreams[0].payload?.content, revised);
  assert.equal(textStreams[0].payload?.is_complete, true);
});

test('processMessages pins completed operator text before the next operator status update', () => {
  const processed = processMessages([
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Need to inspect files first.', is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Need to inspect files first.', is_complete: true } },
    { type: 'agent_event', payload: { agent: 'operator', event: 'update', status: 'Reading input.in' } },
  ]);

  const textStreams = processed.filter(msg => msg.type === 'text_stream');
  const update = processed.find(
    msg => msg.type === 'agent_event' && msg.payload?.event === 'update'
  );

  assert.equal(textStreams.length, 1);
  assert.equal(textStreams[0].payload?.content, 'Need to inspect files first.');
  assert.equal(textStreams[0].payload?.is_complete, true);
  assert.ok(update);
});

test('processMessages keeps completed operator text when another agent starts', () => {
  const processed = processMessages([
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'I have enough context now.', is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'I have enough context now.', is_complete: true } },
    { type: 'agent_event', payload: { agent: 'evaluator', event: 'start', status: 'Evaluating Task Completion' } },
  ]);

  const textStreams = processed.filter(msg => msg.type === 'text_stream');

  assert.equal(textStreams.length, 1);
  assert.equal(textStreams[0].payload?.content, 'I have enough context now.');
  assert.equal(textStreams[0].payload?.is_complete, true);
  assert.ok(
    processed.some(
      msg =>
        msg.type === 'agent_event' &&
        msg.payload?.agent === 'evaluator' &&
        msg.payload?.event === 'start'
    )
  );
});

test('processMessages keeps the final completed operator text snapshot clean on agent completion', () => {
  const processed = processMessages([
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Need one last check', is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: 'Need one last check', is_complete: true } },
    { type: 'agent_event', payload: { agent: 'operator', event: 'complete', status: '' } },
  ]);

  const textStreams = processed.filter(msg => msg.type === 'text_stream');

  assert.equal(textStreams.length, 1);
  assert.equal(textStreams[0].payload?.content, 'Need one last check');
  assert.equal(textStreams[0].payload?.is_complete, true);
});

test('processMessages emits error instead of Analysed Task when stream is tool validation', () => {
  const validation =
    "Validation error (2 issues): Field 'query': Field required; Field 'library': Field required";
  const processed = processMessages([
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: validation, is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: validation, is_complete: true } },
    { type: 'tool_call', payload: { tool: 'query_rag' } },
  ]);

  const errors = processed.filter(m => m.type === 'error');
  assert.equal(errors.length, 1);
  assert.equal(errors[0].payload?.message, validation);
  assert.equal(errors[0].payload?.kind, 'tool_validation');
  assert.equal(errors[0].payload?.toolName, 'query_rag');
  assert.equal(processed.some(m => m.type === 'text_stream'), false);
});

test('processMessages maps validation stream on operator complete to error', () => {
  const validation = "Validation error (1 issue): Field 'x': Field required";
  const processed = processMessages([
    { type: 'agent_event', payload: { agent: 'operator', event: 'start', status: 'Analysing Task' } },
    { type: 'text_stream', payload: { agent: 'operator', content: validation, is_complete: false } },
    { type: 'text_stream', payload: { agent: 'operator', content: validation, is_complete: true } },
    { type: 'agent_event', payload: { agent: 'operator', event: 'complete', status: '' } },
  ]);

  const errors = processed.filter(m => m.type === 'error');
  assert.equal(errors.length, 1);
  assert.equal(errors[0].payload?.message, validation);
  assert.equal(errors[0].payload?.kind, 'tool_validation');
});

test('processMessages hides live final_summary event from execution log', () => {
  const processed = processMessages([
    {
      type: 'final_summary',
      payload: {
        content: '# Final Summary\n\nAll tasks completed.',
      },
    },
    { type: 'done', payload: { status: 'completed' } },
  ]);

  assert.deepEqual(processed, []);
});

test('processMessages hides transient bridge status events from execution log', () => {
  const processed = processMessages([
    {
      type: 'status',
      payload: {
        text: 'Initializing model client...',
        loading: false,
      },
    },
    {
      type: 'status',
      payload: {
        text: 'Initializing agent model clients...',
        loading: false,
      },
    },
  ]);

  assert.deepEqual(processed, []);
});

test('processMessages shows API failure and removes the active agent spinner', () => {
  const processed = processMessages([
    {
      type: 'agent_event',
      payload: {
        agent: 'strategist',
        event: 'start',
        status: 'Analysing Request',
      },
    },
    {
      type: 'error',
      payload: {
        message: "Error code: 404 - {'error': {'message': 'Not Found', 'code': 404}}",
        agent: 'strategist',
        kind: 'api',
      },
    },
    {
      type: 'done',
      payload: { status: 'interrupted' },
    },
  ]);

  assert.equal(
    processed.some(
      message =>
        message.type === 'agent_event' &&
        message.payload?.status === 'Analysing Request'
    ),
    false
  );
  assert.equal(
    processed.some(
      message =>
        message.type === 'error' &&
        message.payload?.kind === 'api'
    ),
    true
  );
  assert.equal(
    processed.some(
      message =>
        message.type === 'run_status' &&
        message.payload?.status === 'interrupted'
    ),
    true
  );
});

test('processMessages preserves collapsible error details on an API retry update', () => {
  const errorDetails =
    "Error code: 404 - {'error': {'message': 'Not Found', 'code': 404}}";
  const processed = processMessages([
    {
      type: 'agent_event',
      payload: {
        agent: 'strategist',
        event: 'update',
        status: 'API Error - Retrying (1/3)...',
        is_error: true,
        output: errorDetails,
      },
    },
  ]);

  const retryMessage = processed.find(
    message =>
      message.type === 'agent_event' &&
      message.payload?.status === 'API Error - Retrying (1/3)...'
  );

  assert.equal(retryMessage?.payload?.is_error, true);
  assert.equal(retryMessage?.payload?.output, errorDetails);
});
