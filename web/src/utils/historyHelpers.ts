import {
  formatPlanTasksForDisplay,
  formatPlanTextForDisplay,
  getFinalPlanStatus,
  getInitialPlanStatus,
  getRevisedPlanStatus,
} from './planHelpers';
import { looksLikeToolValidationMessage } from './validationErrorMessage';

interface HistoryData {
  initial_plan_text?: string;
  full_plan_text?: string;
  /** Present when the final plan was revised from user feedback; penultimate plan in transcript */
  reviewed_plan_text?: string;
  /** Each snapshot from a user feedback revision round (order matches runtime step_complete events). */
  user_revised_plan_texts?: string[];
  /** User request text for each revision round (same length as user_revised_plan_texts when present). */
  user_revised_plan_feedbacks?: string[];
  final_plan_status?: string;
  final_plan_update_status?: string;
  plan?: string[];
  operator_items_by_task?: Record<string, any[]>;
  evaluator_items_by_task?: Record<string, any[]>;
  ordered_items_by_task?: Record<string, any[]>;
  step_results?: Record<string, string>;
  completed_steps?: string[];
  strategist_items?: any[];  // Tool calls made during planning phase
  is_replan?: boolean;
}

const REMOVED_FILE_TOOLS = new Set(['write_file', 'move_file', 'rename_file', 'delete_file']);

// Helper function to process agent items (shared between operator and evaluator)
const processAgentItems = (items: any[], defaultAgentName: string, historyMessages: any[]) => {
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    // Use agent name from item if it exists (for interleaved lists), otherwise use default
    const agentName = item.agent ? (item.agent.charAt(0).toUpperCase() + item.agent.slice(1)) : defaultAgentName;
    
    if (item.type === 'model-text') {
      // Check if this is an API error message - display nicely as error type
      const content = item.content || '';
      if (
        content.startsWith('API Error:') ||
        content.includes("API Error executing step") ||
        looksLikeToolValidationMessage(content)
      ) {
        // Extract just the error message code and status for cleaner display
        let errorMessage = content;
        if (!looksLikeToolValidationMessage(content)) {
          const codeMatch = content.match(/(\d{3})\s+([A-Z_]+)/);
          if (codeMatch) {
            const statusMatch = content.match(/'message':\s*'([^']+)'/);
            const message = statusMatch ? statusMatch[1] : codeMatch[2].replace(/_/g, ' ');
            errorMessage = `${codeMatch[1]} ${codeMatch[2].replace(/_/g, ' ')}: ${message}`;
          }
        }
        let inferredTool: string | undefined;
        if (looksLikeToolValidationMessage(content)) {
          for (let k = i + 1; k < items.length; k++) {
            const it = items[k];
            if (it.type === 'tool' && it.name) {
              inferredTool = it.name;
              break;
            }
            if (
              it.type === 'model-text' ||
              it.type === 'code-snippet' ||
              it.type === 'code-result' ||
              it.type === 'image-analysis-result'
            ) {
              break;
            }
          }
        }
        historyMessages.push({
          type: 'error',
          payload: {
            message: errorMessage,
            agent: agentName.toLowerCase(),
            ...(looksLikeToolValidationMessage(content)
              ? { kind: 'tool_validation' as const, toolName: inferredTool }
              : { kind: 'api' as const }),
          },
        });
      } else {
        // Normal operator analysis: merge all consecutive model-text chunks (same agent)
        // into one "Analysed Task" so streamed output appears in a single collapsible block
        const baseAgent = (item.agent || '').toLowerCase();
        const chunks: string[] = [];
        let j = i;
        while (j < items.length) {
          const it = items[j];
          if (it.type !== 'model-text') break;
          if ((it.agent || '').toLowerCase() !== baseAgent) break;
          const c = (it.content || '').trim();
          if (
            c.startsWith('API Error:') ||
            c.includes("API Error executing step") ||
            looksLikeToolValidationMessage(c)
          ) {
            break;
          }
          if (c) chunks.push(c);
          j++;
        }
        if (chunks.length > 0) {
          const combinedAgent = item.agent
            ? (item.agent.charAt(0).toUpperCase() + item.agent.slice(1))
            : defaultAgentName;
          historyMessages.push({
            type: 'text_stream',
            payload: {
              agent: combinedAgent,
              content: chunks.join('\n\n'),
              is_complete: true
            }
          });
        }
        i = j - 1; // for-loop will increment to j
      }
    } else if (item.type === 'code-snippet') {
      continue;
    } else if (item.type === 'code-result') {
      // Paired with a following 'tool' row, or self-contained when `content.status` is set (checkpoint resume).
      const nextItem = items[i + 1];
      const embeddedStatus =
        typeof item.content?.status === 'string' && item.content.status.length > 0
          ? item.content.status
          : null;

      const pushExecuteStepComplete = (
        statusText: string,
        pairedAgent: string,
        skipFollowingTool: boolean
      ) => {
        const isDirectCodeExecution =
          statusText.includes('-c') ||
          (statusText.toLowerCase().startsWith('executed') &&
            statusText.includes('"') &&
            !statusText.includes('.py') &&
            !statusText.includes('.sh'));
        historyMessages.push({
          type: 'agent_event',
          payload: {
            agent: pairedAgent,
            event: 'step_complete',
            status: statusText,
            output: item.content.output,
            is_error: item.isError || isDirectCodeExecution,
          },
        });
        if (skipFollowingTool) {
          i++;
        }
      };

      if (embeddedStatus) {
        const pairedAgent =
          item.agent != null
            ? item.agent.charAt(0).toUpperCase() + item.agent.slice(1)
            : agentName;
        const shouldSkipTool =
          nextItem &&
          nextItem.type === 'tool' &&
          (nextItem.name === 'execute_python' ||
            nextItem.name === 'execute_code' ||
            (typeof nextItem.content === 'string' &&
              nextItem.content.toLowerCase().startsWith('executed')));
        pushExecuteStepComplete(embeddedStatus, pairedAgent, !!shouldSkipTool);
      } else if (
        nextItem &&
        nextItem.type === 'tool' &&
        nextItem.content.split(' ')[0].toLowerCase() === 'executed'
      ) {
        const nextAgentName = nextItem.agent
          ? nextItem.agent.charAt(0).toUpperCase() + nextItem.agent.slice(1)
          : agentName;
        const statusText = nextItem.content;
        const isDirectCodeExecution =
          statusText.includes('-c') ||
          (statusText.toLowerCase().startsWith('executed') &&
            statusText.includes('"') &&
            !statusText.includes('.py') &&
            !statusText.includes('.sh'));
        historyMessages.push({
          type: 'agent_event',
          payload: {
            agent: nextAgentName,
            event: 'step_complete',
            status: statusText,
            output: item.content.output,
            is_error: item.isError || isDirectCodeExecution,
          },
        });
        i++;
      } else {
        const fileName = item.content.filePath
          ? item.content.filePath.split('/').pop()
          : 'script';
        historyMessages.push({
          type: 'agent_event',
          payload: {
            agent: agentName,
            event: 'step_complete',
            status: `Executed ${fileName}`,
            output: item.content.output,
            is_error: item.isError,
          },
        });
      }
    } else if (item.type === 'image-analysis-result') {
      // This usually precedes a 'tool' item (Analyzed image)
      const nextItem = items[i+1];
      if (nextItem && nextItem.type === 'tool' && nextItem.content.toLowerCase().startsWith('analyzed')) {
        const nextAgentName = nextItem.agent ? (nextItem.agent.charAt(0).toUpperCase() + nextItem.agent.slice(1)) : agentName;
        historyMessages.push({ 
          type: 'agent_event', 
          payload: { 
            agent: nextAgentName, 
            event: 'step_complete', 
            status: nextItem.content,
            output: item.content.output,
            is_error: item.isError
          } 
        });
        i++; // Skip the next tool item
      } else {
        const fileName = item.content.filePath ? item.content.filePath.split('/').pop() : 'image';
        historyMessages.push({ 
          type: 'agent_event', 
          payload: { 
            agent: agentName, 
            event: 'step_complete', 
            status: `Analyzed ${fileName}`,
            output: item.content.output,
            is_error: item.isError
          } 
        });
      }
    } else if (item.type === 'tool') {
      const statusText = item.content || '';
      const toolName = (item.name || '').toLowerCase();
      if (
        REMOVED_FILE_TOOLS.has(toolName) ||
        /^(wrote|moved|renamed|deleted)\b/i.test(statusText)
      ) {
        continue;
      }
      // Skip evaluation-related tool items - they are handled separately
      if (statusText && (statusText.includes('Evaluation Passed') || statusText.includes('Evaluation Failed'))) {
        continue;
      }
      // Detect direct code execution (not allowed) - status contains -c flag
      const isDirectCodeExecution = statusText.includes('-c') || (statusText.toLowerCase().startsWith('executed') && statusText.includes('"') && !statusText.includes('.py') && !statusText.includes('.sh'));
      const payload: any = { 
        agent: agentName, 
        event: 'step_complete', 
        status: statusText,
        is_error: item.isError || isDirectCodeExecution
      };
      if (item.output != null && item.output !== '') {
        payload.output = item.output;
      }
      historyMessages.push({ type: 'agent_event', payload });
    } else if (item.type === 'evaluation-failed') {
      // Handle evaluation failed items with collapsible summary
      historyMessages.push({ 
        type: 'agent_event', 
        payload: { 
          agent: 'Evaluator', 
          event: 'complete', 
          status: item.content, // "Evaluation Failed - Retry n/n"
          output: item.summary,
          is_error: true
        } 
      });
    }
  }
};

export const parseHistoryToMessages = (history: HistoryData): any[] => {
  const historyMessages: any[] = [];
  const isReplan = history.is_replan === true;
  
  // Process strategist tool calls (happen during planning phase, before plan is finalized)
  if (history.strategist_items && history.strategist_items.length > 0) {
    processAgentItems(history.strategist_items, 'Strategist', historyMessages);
  }
  
  // Add Strategist initial plan if it exists
  // Uses agent_event step_complete since processMessages deduplicates plan_stream to keep only one
  if (history.initial_plan_text) {
      historyMessages.push({
          type: 'agent_event',
          payload: {
              agent: 'strategist',
              event: 'step_complete',
              status: getInitialPlanStatus(isReplan),
              output: formatPlanTextForDisplay(history.initial_plan_text)
          }
      });
  }
  
  // Add Strategist reviewed/replan plan (the active one) using agent_event for consolidation
  if (history.full_plan_text || (history.plan && history.plan.length > 0)) {
      const reviewedPlanStatus = getFinalPlanStatus(isReplan);
      const revisedPlanStatus = getRevisedPlanStatus(isReplan);
      const isUserRevisedPlan =
        history.final_plan_status === revisedPlanStatus ||
        history.final_plan_update_status === 'Revising plan from user feedback';

      const userRevisionSnapshots = history.user_revised_plan_texts || [];
      const userRevisionFeedbacks = history.user_revised_plan_feedbacks || [];

      if (isUserRevisedPlan && history.reviewed_plan_text) {
        historyMessages.push({
          type: 'agent_event',
          payload: {
            agent: 'strategist',
            event: 'step_complete',
            status: reviewedPlanStatus,
            output: formatPlanTextForDisplay(history.reviewed_plan_text),
          }
        });
      }

      if (userRevisionSnapshots.length > 0) {
        userRevisionSnapshots.forEach((snapshot, idx) => {
          const isLastRevision = idx === userRevisionSnapshots.length - 1;
          const output =
            isLastRevision && history.plan && history.plan.length > 0
              ? formatPlanTasksForDisplay(history.plan)
              : formatPlanTextForDisplay(snapshot);
          const userFeedback = userRevisionFeedbacks[idx]?.trim();
          historyMessages.push({
            type: 'agent_event',
            payload: {
              agent: 'strategist',
              event: 'step_complete',
              status: revisedPlanStatus,
              output,
              ...(userFeedback ? { user_feedback: userFeedback } : {}),
            },
          });
        });
      } else {
        historyMessages.push({
          type: 'agent_event',
          payload: {
              agent: 'strategist',
              event: 'step_complete',
              status: history.final_plan_status || (isUserRevisedPlan ? revisedPlanStatus : reviewedPlanStatus),
              output: history.plan && history.plan.length > 0
                ? formatPlanTasksForDisplay(history.plan)
                : formatPlanTextForDisplay(history.full_plan_text)
          }
        });
      }
  }
  
  // Get all task IDs from both operator and evaluator
  const allTaskIds = new Set<string>();
  if (history.operator_items_by_task) {
    Object.keys(history.operator_items_by_task).forEach(id => allTaskIds.add(id));
  }
  if (history.evaluator_items_by_task) {
    Object.keys(history.evaluator_items_by_task).forEach(id => allTaskIds.add(id));
  }
  if (history.ordered_items_by_task) {
    Object.keys(history.ordered_items_by_task).forEach(id => allTaskIds.add(id));
  }
  if (history.step_results) {
    Object.keys(history.step_results).forEach(id => allTaskIds.add(id));
  }
  
  // Determine which tasks are completed (have step_results)
  const completedTaskCount = history.completed_steps?.length || 0;
  for (let taskIndex = 0; taskIndex < completedTaskCount; taskIndex++) {
    allTaskIds.add(String(taskIndex));
  }
  
  // Process tasks in order
  const totalTasks = history.plan?.length || allTaskIds.size;
  Array.from(allTaskIds).sort((a, b) => Number(a) - Number(b)).forEach(taskId => {
    const taskIndex = Number(taskId);
    const taskNumber = taskIndex + 1;
    
    // Only create task_progress with title for tasks that have actually been started by operator
    // A task has been started if it has operator_items (operator has worked on it)
    // or if it's completed (in completed_steps)
    const hasOperatorItems = history.operator_items_by_task?.[taskId] && history.operator_items_by_task[taskId].length > 0;
    const isCompleted = taskIndex < completedTaskCount;
    
    // Only show title if operator has actually started working on this task
    // This prevents showing task titles when interrupted during strategist work
    if (hasOperatorItems || isCompleted) {
      // Add task_progress separator at start of each task (matches runtime behavior)
      const taskTitle = history.plan?.[taskIndex]?.split('\n')[0]?.trim() || '';
      // Clean title (remove markdown prefixes)
      let cleanTitle = taskTitle;
      // Remove markdown headers
      while (cleanTitle.startsWith('#')) cleanTitle = cleanTitle.substring(1).trim();
      // Remove all ** pairs (markdown bold)
      cleanTitle = cleanTitle.replace(/\*\*/g, '');
      // Remove single * at start/end
      cleanTitle = cleanTitle.trim().replace(/^\*+|\*+$/g, '').trim();
      // Remove Task N: prefix
      cleanTitle = cleanTitle.replace(/^Task\s+\d+[:：]\s*/i, '').trim();
      
      historyMessages.push({
        type: 'task_progress',
        payload: {
          current: taskNumber,
          total: totalTasks,
          title: cleanTitle
        }
      });
    } else {
      // Task hasn't been started yet - don't create task_progress message
      // This prevents showing task titles for tasks that haven't been created yet
      // Skip processing this task entirely
      return;
    }
    
    // If we have ordered items, use them for a more accurate timeline
    const orderedItems = history.ordered_items_by_task?.[taskId];
    if (orderedItems && orderedItems.length > 0) {
      // Process interleaved items together to preserve grouping logic
      processAgentItems(orderedItems, 'Operator', historyMessages);
    } else {
      // Fallback: process operator items then evaluator items (existing behavior)
      const operatorItems = history.operator_items_by_task?.[taskId];
      if (operatorItems && operatorItems.length > 0) {
        processAgentItems(operatorItems, 'Operator', historyMessages);
      }
      
      const evaluatorItems = history.evaluator_items_by_task?.[taskId];
      if (evaluatorItems && evaluatorItems.length > 0) {
        processAgentItems(evaluatorItems, 'Evaluator', historyMessages);
      }
    }
    
    // For completed tasks, add the evaluation result from step_results
    if (taskIndex < completedTaskCount) {
      const summary = history.step_results?.[taskId];
      if (summary) {
        // Add evaluation passed with summary as output
        historyMessages.push({
          type: 'agent_event',
          payload: {
            agent: 'Evaluator',
            event: 'complete',
            status: 'Evaluation Passed',
            output: summary
          }
        });
      }
    }
  });
  
  // Add interrupted status at the end to indicate this is from checkpoint (not actively running)
  // This prevents "Analysing Request" and other update events from showing as active
  historyMessages.push({
    type: 'run_status',
    payload: { status: 'interrupted' }
  });
  
  return historyMessages;
};
