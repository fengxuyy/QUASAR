import { isFinalPlanStatus, isInitialPlanStatus } from './planHelpers';
import { looksLikeToolValidationMessage } from './validationErrorMessage';

export type TaskStatus = 'running' | 'passed' | 'failed';

export interface BridgeMessage {
  type?: string;
  payload?: any;
  _taskNum?: number;      // Task number this message belongs to
  _taskStatus?: TaskStatus; // Status of the task (for task_progress entries)
  [key: string]: any;
}


const MAX_STREAM_OVERLAP_SCAN = 4096;

const getContentOverlapLength = (existing: string, incoming: string): number => {
  const maxOverlap = Math.min(existing.length, incoming.length, MAX_STREAM_OVERLAP_SCAN);
  for (let overlap = maxOverlap; overlap > 0; overlap--) {
    if (existing.slice(-overlap) === incoming.slice(0, overlap)) {
      return overlap;
    }
  }
  return 0;
};

const getCommonPrefixLength = (left: string, right: string): number => {
  const maxLength = Math.min(left.length, right.length);
  let idx = 0;

  while (idx < maxLength && left[idx] === right[idx]) {
    idx++;
  }

  return idx;
};

const getCommonSuffixLength = (left: string, right: string): number => {
  const maxLength = Math.min(left.length, right.length);
  let idx = 0;

  while (
    idx < maxLength &&
    left[left.length - 1 - idx] === right[right.length - 1 - idx]
  ) {
    idx++;
  }

  return idx;
};

const looksLikeRevisedCumulativeSnapshot = (existing: string, incoming: string): boolean => {
  const minLength = Math.min(existing.length, incoming.length);
  if (minLength < 48) {
    return false;
  }

  const commonPrefixLength = getCommonPrefixLength(existing, incoming);
  const commonSuffixLength = getCommonSuffixLength(
    existing.slice(commonPrefixLength),
    incoming.slice(commonPrefixLength)
  );
  const preservedRatio = (commonPrefixLength + commonSuffixLength) / minLength;

  // Some providers resend "full text so far" with a small rewrite in the middle.
  // Treat that as the latest snapshot instead of appending it as a new delta.
  const hasStrongSharedShape =
    (commonPrefixLength >= 24 && preservedRatio >= 0.7) ||
    preservedRatio >= 0.85;
  const incomingLooksLikeSnapshot =
    incoming.length >= existing.length || commonSuffixLength >= 16;

  return hasStrongSharedShape && incomingLooksLikeSnapshot;
};

function toolNameFromBridgeMessage(msg: BridgeMessage): string | undefined {
  const p = msg.payload;
  if (!p || typeof p !== 'object') return undefined;
  const raw =
    (p as { tool?: string }).tool ??
    (p as { name?: string }).name ??
    (p as { toolName?: string }).toolName;
  return typeof raw === 'string' && raw.trim() ? raw.trim() : undefined;
}

/** Merge one stream chunk into the running buffer. Handles delta chunks and
 *  cumulative chunks (where each event carries the full text so far), which
 *  some providers emit for incremental updates. */
export const mergeTextStreamChunks = (existing: string, incoming: string): string => {
  if (!existing) return incoming;
  if (!incoming) return existing;
  if (incoming === existing) return existing;

  // Cumulative snapshot: prefer the longer string when it extends what we have.
  if (incoming.startsWith(existing)) {
    return incoming;
  }
  if (looksLikeRevisedCumulativeSnapshot(existing, incoming)) {
    return incoming;
  }
  if (existing.startsWith(incoming)) {
    return existing;
  }

  const overlap = getContentOverlapLength(existing, incoming);
  return existing + incoming.slice(overlap);
};

/** Idle / analysis statuses that keep the text-stream open across chunks.
 *  Tool/action statuses (Reading…, Executing…) close the stream into "Analysed Task". */
export const isIdleAnalysisStatus = (status?: string | null): boolean => {
  if (!status) return false;
  const s = status.toLowerCase();
  return (
    s.includes('analysing') ||
    s.includes('analyzing') ||
    s === 'thinking' ||
    s.startsWith('thinking ') ||
    s.includes('evaluating task')
  );
};

/** Collapse adjacent same-agent text_stream rows into one Analysed Task block. */
export const mergeAdjacentTextStreams = (
  messages: BridgeMessage[],
  options: { onlyIfPreviousIncomplete?: boolean } = {},
): BridgeMessage[] => {
  const merged: BridgeMessage[] = [];
  for (const msg of messages) {
    const prev = merged[merged.length - 1];
    const canMerge =
      prev?.type === 'text_stream' &&
      msg.type === 'text_stream' &&
      (prev.payload?.agent || '').toLowerCase() === (msg.payload?.agent || '').toLowerCase() &&
      (prev._taskNum ?? null) === (msg._taskNum ?? null) &&
      (!options.onlyIfPreviousIncomplete || !prev.payload?.is_complete);

    if (canMerge) {
      const content = mergeTextStreamChunks(
        String(prev.payload?.content || ''),
        String(msg.payload?.content || ''),
      );
      let status = msg.payload?.status || prev.payload?.status;
      if (typeof status === 'string' && status.includes('Analysing')) {
        status = status.replace('Analysing', 'Analysed');
      }
      const isComplete = Boolean(prev.payload?.is_complete || msg.payload?.is_complete);
      merged[merged.length - 1] = {
        ...prev,
        payload: {
          ...(prev.payload || {}),
          ...(msg.payload || {}),
          content,
          status: isComplete && status ? status : (msg.payload?.status || prev.payload?.status),
          is_complete: isComplete,
        },
        _thoughts: msg._thoughts ?? prev._thoughts,
      };
    } else {
      merged.push(msg);
    }
  }
  return merged;
};


export const processMessages = (messages: BridgeMessage[], filterAgent?: string | null): BridgeMessage[] => {
  const internalTypes = [
    'settings_updated', 'bridge_restarted', 'workspace_cleaned', 'rag_status',
    'ready', 'init', 'status', 'execution_status', 'checkpoint_status_check',
    'file_content', 'system_status', 'terminal_settings_updated',
    'plan_awaiting_confirm', 'plan_declined', 'env_updated', 'context_usage',
    'final_summary', 'done'
  ];

  // First pass: Build task status map based on evaluator complete events
  // Task status: 'running' (default), 'passed' (Evaluation Passed), 'failed' (Evaluation Failed)
  const taskStatusMap: Record<number, TaskStatus> = {};
  let currentTaskNum = 0;
  
  for (const msg of messages) {
    if (msg.type === 'task_progress') {
      currentTaskNum = msg.payload?.current || currentTaskNum;
      if (currentTaskNum && !taskStatusMap[currentTaskNum]) {
        taskStatusMap[currentTaskNum] = 'running';
      }
    } else if (msg.type === 'agent_event') {
      const agentName = msg.payload?.agent?.toLowerCase();
      const eventType = msg.payload?.event;
      const status = msg.payload?.status || '';
      
      if (agentName === 'evaluator' && eventType === 'complete') {
        if (status.toLowerCase().includes('passed')) {
          taskStatusMap[currentTaskNum] = 'passed';
        } else if (status.toLowerCase().includes('failed')) {
          taskStatusMap[currentTaskNum] = 'failed';
        }
      }
    }
  }

  const result: BridgeMessage[] = [];
  let latestPlanStream: BridgeMessage | null = null;
  let planStreamInsertIndex = -1;

  const stepCompleteEvents: Record<string, BridgeMessage[]> = {};
  const latestUpdateEvents: Record<string, BridgeMessage> = {};
  const latestThoughtStreams: Record<string, BridgeMessage> = {};
  const agentStreamContext: Record<string, { accumulated: string, lastMsgWasComplete: boolean }> = {};
  const streamClosedByActionBoundary: Record<string, boolean> = {};
  let initialPlanCreated = false;
  let runInterrupted = false;
  let pendingTaskProgress: BridgeMessage | null = null;

  const maybeReopenTrailingTextStream = (agentName: string): string => {
    if (streamClosedByActionBoundary[agentName]) {
      return "";
    }

    const last = result[result.length - 1];
    if (!last || last.type !== 'text_stream') {
      return "";
    }

    const lastAgent = last.payload?.agent?.toLowerCase() || 'unknown';
    if (lastAgent !== agentName) {
      return "";
    }

    const lastTaskNum = last._taskNum ?? currentTaskNum;
    if (lastTaskNum !== currentTaskNum) {
      return "";
    }

    result.pop();
    return String(last.payload?.content || "");
  };

  const buildCompletedTextStream = (agentName: string): BridgeMessage | null => {
    const ctx = agentStreamContext[agentName];
    const pending = latestUpdateEvents[agentName];
    const accumulated = ctx?.accumulated?.trim() || '';

    if (!ctx || !pending || pending.type !== 'text_stream' || !accumulated) {
      return null;
    }

    if (looksLikeToolValidationMessage(accumulated)) {
      return {
        type: 'error',
        _taskNum: currentTaskNum,
        payload: {
          message: accumulated,
          agent: agentName,
          kind: 'tool_validation',
        },
      };
    }

    let finalStatus = pending.payload?.status || 'Thinking Complete';
    if (finalStatus.includes('Analysing')) {
      finalStatus = finalStatus.replace('Analysing', 'Analysed');
    }

    return {
      ...pending,
      type: 'text_stream',
      _taskNum: currentTaskNum,
      payload: {
        ...(pending.payload || { agent: agentName }),
        event: 'update',
        status: finalStatus,
        content: ctx.accumulated,
        is_complete: true,
      },
      _thoughts: latestThoughtStreams[agentName]?.payload?.content,
    };
  };

  const flushCompletedTextStream = (agentName: string): boolean => {
    const ctx = agentStreamContext[agentName];
    const pending = latestUpdateEvents[agentName];

    if (!ctx?.lastMsgWasComplete || !pending || pending.type !== 'text_stream') {
      return false;
    }

    const finalized = buildCompletedTextStream(agentName);

    delete latestUpdateEvents[agentName];
    delete latestThoughtStreams[agentName];
    delete agentStreamContext[agentName];

    if (!finalized) {
      return false;
    }

    result.push(finalized);
    return true;
  };



  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    const type = msg.type;

    if (!type || internalTypes.includes(type)) {
      continue;
    }

    // Deduplicate task_progress - keep only one per task number, prefer ones with title
    // Skip task_progress when filtering by strategist (it's only relevant for operator)
    if (type === 'task_progress') {
      if (filterAgent === 'strategist') {
        continue; // Don't show task separators in strategist view
      }

      const payload = msg.payload || {};
      const taskNum = payload.current;
      const hasTitle = !!payload.title;
      
      // Update currentTaskNum so subsequent messages are assigned to correct task
      currentTaskNum = taskNum || currentTaskNum;
      
      // Annotate with task status from our pre-built map
      const annotatedMsg: BridgeMessage = {
        ...msg,
        _taskNum: taskNum,
        _taskStatus: taskStatusMap[taskNum] || 'running'
      };

      if (filterAgent === 'evaluator') {
        // For evaluator filter, delay showing the task title until an evaluator event occurs for this task
        // We update/replace pending if a better one (with title) comes for same task, or if new task starts
        if (!pendingTaskProgress || pendingTaskProgress.payload?.current !== taskNum || (hasTitle && !pendingTaskProgress.payload?.title)) {
          pendingTaskProgress = annotatedMsg;
        }
        continue;
      }

      const existingIdx = result.findIndex(
        m => m.type === 'task_progress' && m.payload?.current === taskNum
      );
      if (existingIdx !== -1) {
        // If new one has title and existing doesn't, replace it
        if (hasTitle && !result[existingIdx].payload?.title) {
          result[existingIdx] = annotatedMsg;
        }
        continue; // Skip duplicate
      }
      result.push(annotatedMsg);
      continue;
    }


    if (type === 'run_status') {
      const status = msg.payload?.status;
      if (status === 'interrupted') {
        runInterrupted = true;
        Object.keys(latestUpdateEvents).forEach(agentName => {
          flushCompletedTextStream(agentName);
        });
        Object.keys(latestUpdateEvents).forEach(key => delete latestUpdateEvents[key]);
        Object.keys(latestThoughtStreams).forEach(key => delete latestThoughtStreams[key]);
        Object.keys(agentStreamContext).forEach(key => delete agentStreamContext[key]);
        if (latestPlanStream) {
          latestPlanStream = {
            ...latestPlanStream,
            payload: { ...latestPlanStream.payload, is_complete: true }
          } as BridgeMessage;
        }
      } else if (status === 'resumed' || status === 'starting') {
        runInterrupted = false;
        // Clear stream state so "Analysing Task" after resume starts with empty content
        Object.keys(agentStreamContext).forEach(key => delete agentStreamContext[key]);
        Object.keys(latestUpdateEvents).forEach(key => delete latestUpdateEvents[key]);
        Object.keys(latestThoughtStreams).forEach(key => delete latestThoughtStreams[key]);
      }
      continue;
    }

    if (type === 'plan_stream') {
      if (filterAgent && filterAgent !== 'strategist') {
        continue;
      }
      if (planStreamInsertIndex === -1) {
        planStreamInsertIndex = result.length;
        result.push(msg); // Placeholder
      }
      latestPlanStream = { 
        ...msg, 
        payload: { 
          ...msg.payload, 
          _isReviewPhase: initialPlanCreated && !msg.payload?._isReplanning,
          _isReplanning: msg.payload?._isReplanning !== undefined ? msg.payload._isReplanning : undefined
        } 
      } as BridgeMessage;
      continue;
    }

    // Text stream - merge with latest agent event or add as standalone if no event
    if (type === 'text_stream') {
      const agent = msg.payload?.agent?.toLowerCase() || 'unknown';
      if (filterAgent && agent !== filterAgent) {
        continue;
      }
      
      const payload = msg.payload || {};
      const reopenedContent = agentStreamContext[agent]?.accumulated
        ? ""
        : maybeReopenTrailingTextStream(agent);
      const ctx = agentStreamContext[agent] || {
        accumulated: reopenedContent,
        lastMsgWasComplete: true
      };

      // From execution history: standalone complete stream (no live stream for this agent).
      // Push in place so "Analysed Task" appears before subsequent tool messages.
      // Do not seed agentStreamContext here: after a refresh/checkpoint restore, the
      // next live update event must show its own running status instead of reusing
      // the last completed analysis content from history.
      if (payload.is_complete && !latestUpdateEvents[agent] && !reopenedContent) {
        result.push(msg);
        delete agentStreamContext[agent];
        streamClosedByActionBoundary[agent] = false;
        continue;
      }
      
      // If a new stream burst is starting, append separator to accumulated
      // User requested to remove this separator to make the stream continuous
      // if (ctx.lastMsgWasComplete && !payload.is_complete && payload.content.trim()) {
      //   if (ctx.accumulated) {
      //     ctx.accumulated += "\n\n---\n\n"; // Visible separator for new thinking rounds
      //   }
      // }

      const incomingContent = payload.content || "";
      const currentTotal = mergeTextStreamChunks(ctx.accumulated, incomingContent);
      ctx.accumulated = currentTotal;
      if (payload.is_complete) {
        ctx.lastMsgWasComplete = true;
      } else {
        ctx.lastMsgWasComplete = false;
      }
      agentStreamContext[agent] = ctx;
      streamClosedByActionBoundary[agent] = false;

      // Update the active status event
      if (latestUpdateEvents[agent]) {
        // Transition "Analysing" to "Analysed" if complete
        let newStatus = latestUpdateEvents[agent].payload.status;
        if (payload.is_complete && newStatus.includes('Analysing')) {
          newStatus = newStatus.replace('Analysing', 'Analysed');
        }

        latestUpdateEvents[agent] = {
          ...latestUpdateEvents[agent],
          type: 'text_stream',
          payload: {
            ...latestUpdateEvents[agent].payload,
            status: newStatus,
            content: currentTotal,
            // Force incomplete to keep spinner going until tool call
            is_complete: false 
          },
          _thoughts: latestThoughtStreams[agent]?.payload?.content
        };
      } else {
        // Fallback: create an event if none exists
        // Always "Analysing Task" (spinning) regardless of payload completion, until tool call closes it
        const status = agent === 'operator' ? 'Analysing Task' : 'Thinking';
        latestUpdateEvents[agent] = {
          type: 'text_stream',
          payload: {
            agent,
            event: 'update', // Keep strictly for compat if needed, though type=text_stream overrides
            status,
            content: currentTotal,
            is_complete: false
          },
          _thoughts: latestThoughtStreams[agent]?.payload?.content
        };
      }
      continue;
    }

    if (type === 'thought_stream') {
      const agent = msg.payload?.agent?.toLowerCase() || 'unknown';
      if (filterAgent && agent !== filterAgent) {
        continue;
      }
      
      // If thinking is complete, clear the thoughts so they don't persist
      // when the agent transitions to tool calling
      if (msg.payload?.is_complete) {
        delete latestThoughtStreams[agent];
        // Clear thoughts from the ongoing event
        if (latestUpdateEvents[agent]) {
          latestUpdateEvents[agent] = {
            ...latestUpdateEvents[agent],
            _thoughts: undefined
          };
        }
      } else {
        latestThoughtStreams[agent] = msg;
        // Update ongoing event with current thoughts
        if (latestUpdateEvents[agent]) {
          latestUpdateEvents[agent] = {
            ...latestUpdateEvents[agent],
            _thoughts: msg.payload?.content
          };
        }
      }
      continue;
    }

    if (type === 'error' && msg.payload?.kind === 'api') {
      runInterrupted = true;
      Object.keys(latestUpdateEvents).forEach(key => delete latestUpdateEvents[key]);
      Object.keys(latestThoughtStreams).forEach(key => delete latestThoughtStreams[key]);
      Object.keys(agentStreamContext).forEach(key => delete agentStreamContext[key]);
      result.push({ ...msg, _taskNum: currentTaskNum });
      continue;
    }

    if (type === 'agent_event') {
      const agentName = msg.payload?.agent?.toLowerCase() || 'unknown';
      const eventType = msg.payload?.event;

      if (filterAgent && agentName !== filterAgent) {
        continue;
      }

      // Reaching here means agent matches filterAgent (or no filter)
      if (pendingTaskProgress) {
        result.push(pendingTaskProgress);
        pendingTaskProgress = null;
      }

      if (agentName === 'strategist' && eventType !== 'step_complete' && eventType !== 'update' && eventType !== 'complete') {
        continue;
      }

      if (agentName === 'strategist' && eventType === 'step_complete' && isInitialPlanStatus(msg.payload?.status)) {
        initialPlanCreated = true;
        // Drop pending "Creating plan…" / streaming updates so the tail flush does not re-show a spinner
        delete latestUpdateEvents[agentName];
        if (planStreamInsertIndex !== -1) {
          // Check if strategist tool-call entries were pushed after the plan_stream placeholder.
          // If so, the placeholder is in the wrong position (before tool calls) — remove it
          // and push the plan at the end so tool calls appear first chronologically.
          if (planStreamInsertIndex < result.length - 1) {
            result.splice(planStreamInsertIndex, 1);
            result.push(msg);
          } else {
            result[planStreamInsertIndex] = msg;
          }
          planStreamInsertIndex = -1;
          latestPlanStream = null;
          continue;
        } else {
          result.push(msg);
          continue;
        }
      }

      // Finalized strategist plans should replace the active plan_stream placeholder.
      if (agentName === 'strategist' && eventType === 'step_complete' && isFinalPlanStatus(msg.payload?.status)) {
        // Clear e.g. "Self-reviewing plan" — it is an update, so it can outrank step_complete in the tail flush
        delete latestUpdateEvents[agentName];
        if (planStreamInsertIndex !== -1) {
          // Same chronological fix as initial plan: push after tool calls if any
          if (planStreamInsertIndex < result.length - 1) {
            result.splice(planStreamInsertIndex, 1);
            result.push(msg);
          } else {
            result[planStreamInsertIndex] = msg;
          }
          planStreamInsertIndex = -1;
          latestPlanStream = null;
          continue;
        } else {
          result.push(msg);
          continue;
        }
      }

      if (agentName === 'strategist' && eventType === 'update' && initialPlanCreated) {
        latestUpdateEvents[agentName] = msg;
        continue;
      }

      if (eventType === 'step_complete') {
        flushCompletedTextStream(agentName);
        result.push(msg);
        streamClosedByActionBoundary[agentName] = true;
        continue;
      }

      if (eventType === 'start' || eventType === 'update') {
        const statusText = String(msg.payload?.status || '');
        const continuingAnalysis = isIdleAnalysisStatus(statusText);

        // Only finalize "Analysed Task" when moving to a real action (tool status),
        // not when the backend re-emits Analysing Task between continuous stream chunks.
        if (!continuingAnalysis) {
          flushCompletedTextStream(agentName);
        }

        // Clear update events from OTHER agents when a new agent starts
        if (eventType === 'start') {
          Object.keys(latestUpdateEvents).forEach(key => {
            if (key !== agentName) {
              flushCompletedTextStream(key);
              delete latestUpdateEvents[key];
            }
          });
          Object.keys(latestThoughtStreams).forEach(key => {
            if (key !== agentName) {
              delete latestThoughtStreams[key];
            }
          });

          if (continuingAnalysis && !streamClosedByActionBoundary[agentName]) {
            // Re-entrant "Analysing Task" without a tool boundary: keep one stream.
            streamClosedByActionBoundary[agentName] = false;
            const reopened = maybeReopenTrailingTextStream(agentName);
            if (reopened) {
              const existing = agentStreamContext[agentName];
              agentStreamContext[agentName] = {
                accumulated: mergeTextStreamChunks(existing?.accumulated || '', reopened),
                lastMsgWasComplete: false,
              };
            }
          } else {
            // Fresh analysis after a tool/action boundary (or non-analysis start).
            delete agentStreamContext[agentName];
            streamClosedByActionBoundary[agentName] = !continuingAnalysis;
          }
        }
        
        // Preserve current accumulated content in the new status message
        const ctx = agentStreamContext[agentName];
        latestUpdateEvents[agentName] = {
          ...msg,
          // Force text_stream type if we have accumulated text content to keep the global stream UI
          type: ctx?.accumulated ? 'text_stream' : msg.type,
          _taskNum: currentTaskNum, // Ensure it stays in correct task group
          payload: {
            ...msg.payload,
            content: ctx?.accumulated,
            // Force incomplete if it's a text stream, waiting for tool call
            is_complete: ctx?.accumulated ? false : ctx?.lastMsgWasComplete
          },
          _thoughts: latestThoughtStreams[agentName]?.payload?.content
        };
        continue;
      }

      if (eventType === 'complete') {
        if (!flushCompletedTextStream(agentName)) {
          delete latestUpdateEvents[agentName];
          delete latestThoughtStreams[agentName];
          delete agentStreamContext[agentName];
        }
        streamClosedByActionBoundary[agentName] = true;

        if (msg.payload?.status === 'Replanning Complete') {
          continue;
        }
        if (msg.payload?.status) {
          result.push({ ...msg, _taskNum: currentTaskNum });
        }
        continue;
      }
    }

    if (type === 'tool_call' || type === 'code_result') {
      // If we have a pending text stream (analyzing), close it now that we have a tool call (action)
      const agent = 'operator'; // Tool calls are primarily operator actions
      if (latestUpdateEvents[agent] && latestUpdateEvents[agent].type === 'text_stream') {
        const pending = latestUpdateEvents[agent];
        const streamed = String(
          pending.payload?.content ?? agentStreamContext[agent]?.accumulated ?? ''
        ).trim();
        if (looksLikeToolValidationMessage(streamed)) {
          const toolName =
            type === 'tool_call' ? toolNameFromBridgeMessage(msg) : undefined;
          result.push({
            type: 'error',
            _taskNum: currentTaskNum,
            payload: {
              message: streamed,
              agent,
              kind: 'tool_validation',
              toolName,
            },
          });
        } else {
          result.push({
            ...pending,
            payload: {
              ...pending.payload,
              status: 'Analysed Task',
              is_complete: true,
            },
          });
        }
        delete latestUpdateEvents[agent];
        delete agentStreamContext[agent];
      }
      streamClosedByActionBoundary[agent] = true;

      if (filterAgent && filterAgent !== 'operator') {
        continue;
      }
      continue;
    }

    result.push(msg);
  }

  if (latestPlanStream && planStreamInsertIndex !== -1) {
    if (planStreamInsertIndex < result.length) {
      result.splice(planStreamInsertIndex, 1);
      result.push(latestPlanStream);
    } else {
      result[planStreamInsertIndex] = latestPlanStream;
    }
  }

  const allAgents = new Set([
    ...Object.keys(stepCompleteEvents),
    ...Object.keys(latestUpdateEvents)
  ]);

  for (const agentName of allAgents) {
    if (flushCompletedTextStream(agentName)) {
      continue;
    }
    if (latestUpdateEvents[agentName] && !runInterrupted) {
      if (agentName === 'strategist' && latestPlanStream) {
        continue;
      }
      const thoughtContent = latestThoughtStreams[agentName]?.payload?.content;
      let tail = latestUpdateEvents[agentName];
      if (
        tail.type === 'text_stream' &&
        looksLikeToolValidationMessage(String(tail.payload?.content || '').trim())
      ) {
        tail = {
          type: 'error',
          _taskNum: currentTaskNum,
          payload: {
            message: String(tail.payload?.content || '').trim(),
            agent: agentName,
            kind: 'tool_validation',
          },
        };
      }
      result.push(
        thoughtContent ? { ...tail, _thoughts: thoughtContent } : tail
      );
    }
  }

  if (runInterrupted) {
    result.push({ type: 'run_status', payload: { status: 'interrupted' } });
  }

  // Collapse only open/incomplete adjacent streams (live chunk spam). Fully
  // completed rows separated by tools are left alone — tool boundaries do not
  // always leave a marker between text_stream rows in `result`.
  return mergeAdjacentTextStreams(result, { onlyIfPreviousIncomplete: true });
};
