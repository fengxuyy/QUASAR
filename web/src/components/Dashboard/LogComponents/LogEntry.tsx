import React, { useEffect, useRef, useState } from 'react';
import { 
  AlertCircle, 
  RotateCcw, 
  Loader2, 
  CheckCircle2, 
  ListTodo, 
  ArrowRight, 
  Terminal, 
  FileCode,
  FileText,
  MessageSquare,
  ChevronDown,
  ChevronUp
} from 'lucide-react';
import { clsx } from 'clsx';
import { MarkdownRenderer } from '../../UI/MarkdownRenderer';
import type { BridgeMessage } from '../../../utils/messageHelpers';
import { agentColors } from './constants';
import { StepCompleteEntry } from './StepCompleteEntry';
import { TextStreamEntry } from './TextStreamEntry';
import { parseStatusWithFileLinks } from '../../../utils/fileLinkUtils';
import { useNavigation } from '../../../contexts/NavigationContext';
import { looksLikeToolValidationMessage } from '../../../utils/validationErrorMessage';
import { getToolValidationFailureTitle } from '../../../utils/toolValidationFailureTitle';

// Helper to filter out <PLAN> and </PLAN> tags from display content
const filterPlanTags = (text: string): string => {
  if (!text) return '';
  return text
    .replace(/<PLAN>/gi, '')
    .replace(/<\/PLAN>/gi, '')
    .trim();
};

// Separate component for plan_stream to manage its own collapsed state
const PlanStreamEntry: React.FC<{ payload: any }> = ({ payload }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const { content, is_complete, parsed_plan, _isReviewPhase, _isReplanning } = payload || {};
  
  // Determine the phase: review, replanning, or initial plan
  const isReplanning = _isReplanning === true;
  const isReview = !isReplanning && (_isReviewPhase !== undefined ? !!_isReviewPhase : (is_complete && parsed_plan && parsed_plan.length > 0));
  
  // Set messages based on phase
  let creatingMessage: string;
  let completedMessage: string;
  if (isReplanning) {
    creatingMessage = 'Creating Plan';
    completedMessage = 'Completed Plan';
  } else if (isReview) {
    creatingMessage = 'Reviewing Initial Plan';
    completedMessage = 'Reviewed Plan';
  } else {
    creatingMessage = 'Creating Initial Plan';
    completedMessage = 'Completed Initial Plan';
  }
  
  const hasContent = is_complete && parsed_plan && parsed_plan.length > 0;
  
  // Filter out <PLAN> tags from streaming content for display
  const displayContent = filterPlanTags(content);
  
  return (
    <div className="border-b border-white/10 bg-slate-50/30">
      <div 
        className={clsx(
          "flex items-center gap-3 py-2 px-4",
          hasContent && "cursor-pointer hover:bg-slate-100/50 transition-colors"
        )}
        onClick={() => hasContent && setIsExpanded(!isExpanded)}
      >
        <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-purple-500 to-indigo-500 flex items-center justify-center flex-shrink-0">
          {is_complete ? (
            <CheckCircle2 size={14} className="text-white" />
          ) : (
            <Loader2 size={14} className="text-white animate-spin" />
          )}
        </div>
        <div className="flex-1 flex items-center gap-2 min-w-0">
          <span className={clsx("text-sm font-bold", is_complete ? "text-green-600" : "text-slate-600")}>
            {is_complete ? completedMessage : creatingMessage}
          </span>
        </div>
        {hasContent && (
          <button className="text-slate-400 hover:text-slate-600 transition-colors">
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        )}
      </div>
      
      {/* Show parsed plan when expanded, or streaming content during creation */}
      {hasContent && isExpanded ? (
        <div className="px-4 pb-3">
          <div className="ml-11 space-y-2 bg-purple-50/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <ListTodo size={14} className="text-purple-500" />
              <span className="text-sm font-medium text-purple-700">Tasks:</span>
            </div>
            {parsed_plan.map((task: string, idx: number) => (
              <div key={idx} className="flex items-start gap-2">
                <ArrowRight size={14} className="text-purple-400 mt-1 flex-shrink-0" />
                <div className="text-sm text-slate-700 flex-1">
                  <MarkdownRenderer content={task} />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : displayContent && !is_complete ? (
        <div className="px-4 pb-3">
          <div className="ml-11 text-sm text-slate-600">
            <MarkdownRenderer content={displayContent} />
          </div>
        </div>
      ) : null}
    </div>
  );
};

// Component to render update event status with clickable file links
// Optimized to also handle consolidated streaming content
const UpdateEventEntry: React.FC<{
  status: string;
  colorClass: string;
  is_error?: boolean;
  thoughts?: string;
  content?: string;
  output?: string;
  payload_is_complete?: boolean;
  archiveId?: string | null;
}> = ({ status, colorClass, is_error, thoughts, content, output, payload_is_complete, archiveId }) => {
  const hasOutputAtMount = !!(output && output.trim().length > 0);
  const [isExpanded, setIsExpanded] = useState(!hasOutputAtMount); // Collapsed when showing details (code block, grep pattern, etc.); expanded for streaming text only
  const thoughtContainerRef = useRef<HTMLDivElement | null>(null);
  const { navigateToFile } = useNavigation();
  const segments = parseStatusWithFileLinks(status);
  
  const hasContent = typeof content === 'string' && content.length > 0;
  const hasOutput = typeof output === 'string' && output.trim().length > 0;
  const hasExpandableContent = hasContent || hasOutput;
  // If we have content and it's complete, we show a message icon instead of a spinner
  const showCompleteIcon = payload_is_complete && hasContent;

  const thoughtContent = !hasContent && !hasOutput && typeof thoughts === 'string' ? thoughts : "";

  useEffect(() => {
    if (thoughtContainerRef.current) {
      thoughtContainerRef.current.scrollTop = thoughtContainerRef.current.scrollHeight;
    }
  }, [thoughtContent]);

  return (
    <div className="border-b border-white/10 bg-slate-50/30">
      <div 
        className={clsx(
          "flex items-center gap-3 py-2 px-4",
          hasExpandableContent && "cursor-pointer hover:bg-slate-100/50 transition-colors"
        )}
        onClick={() => hasExpandableContent && setIsExpanded(!isExpanded)}
      >
        <div className={`w-6 h-6 rounded-lg bg-gradient-to-br ${is_error ? 'from-red-500 to-red-600' : colorClass} flex items-center justify-center flex-shrink-0`}>
          {showCompleteIcon ? (
            <MessageSquare size={14} className="text-white" />
          ) : (
            <Loader2 size={14} className="text-white animate-spin" />
          )}
        </div>
        <div className="flex-1 min-w-0 flex items-center gap-2">
          <p className={clsx(
            "text-sm font-bold",
            is_error ? "text-red-500" : (showCompleteIcon ? "text-green-600" : "text-slate-600")
          )}>
            {segments.map((segment, idx) => {
              if (segment.type === 'file' && segment.filePath) {
                return (
                  <button
                    key={idx}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigateToFile(segment.filePath!, archiveId);
                    }}
                    className={clsx(
                      "italic transition-colors cursor-pointer px-0.5 font-bold underline underline-offset-2 decoration-sky-400/80",
                      "text-sky-700 hover:text-sky-800"
                    )}
                    title={`View ${segment.filePath} in Workspace`}
                  >
                    {segment.content}
                  </button>
                );
              }
              return <span key={idx}>{segment.content}</span>;
            })}
          </p>
        </div>
        {hasExpandableContent && (
          <button className="text-slate-400 hover:text-slate-600 transition-colors">
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        )}
      </div>

      {/* Show scrollable thought content if no main content yet */}
      {thoughtContent && (
        <div className="px-4 pb-3">
          <div
            ref={thoughtContainerRef}
            className="ml-11 min-w-0 max-w-full overflow-x-hidden text-xs text-slate-500 bg-slate-100/40 rounded-lg p-3 max-h-40 overflow-y-auto scrollbar-glass"
          >
            <MarkdownRenderer content={thoughtContent} />
          </div>
        </div>
      )}

      {/* Show output (code details) in collapsible section - for executing state */}
      {hasOutput && isExpanded && (
        <div className="px-4 pb-3">
          <div className={clsx(
            "ml-11 min-w-0 max-w-full overflow-x-hidden space-y-2 rounded-lg p-3 border max-h-96 overflow-y-auto scrollbar-glass",
            is_error ? "bg-red-50/50 border-red-100" : "bg-slate-100/50 border-slate-200"
          )}>
            <div className="flex items-center gap-2 mb-1">
              <FileText size={14} className={is_error ? "text-red-500" : "text-slate-500"} />
              <span className={clsx(
                "text-xs font-bold uppercase tracking-wider",
                is_error ? "text-red-700" : "text-slate-600"
              )}>
                {is_error ? 'Details' : 'Result Content'}
              </span>
            </div>
            <div className={clsx(
              "prose prose-sm prose-slate max-w-none",
              is_error && "prose-red"
            )}>
              <MarkdownRenderer content={output} />
            </div>
          </div>
        </div>
      )}

      {/* Show streaming content or expanded completed content */}
      {hasContent && (!payload_is_complete || isExpanded) && (
        <div className="px-4 pb-3">
          <div className="ml-11 min-w-0 max-w-full overflow-x-hidden text-sm text-slate-600 bg-slate-100/50 rounded-lg p-3 max-h-96 overflow-y-auto scrollbar-glass">
            {payload_is_complete ? (
              <MarkdownRenderer content={content} />
            ) : (
              <MarkdownRenderer content={content} />
            )}
          </div>
        </div>
      )}
    </div>
  );
};


export const LogEntry = React.memo<{ message: BridgeMessage; archiveId?: string | null }>(({ message, archiveId }) => {
  const { type, payload } = message;

  // System status - not shown in log (sidebar indicates running/completed state)
  if (type === 'system_status') {
    return null;
  }

  // Task progress - handled by parent ExecutionLog in TaskSection
  if (type === 'task_progress') {
    return null;
  }


  // Run status - show interrupted/resumed/starting messages
  if (type === 'run_status') {
    const status = payload?.status;
    if (status === 'interrupted') {
      return (
        <div className="flex items-center gap-3 py-2 px-4 border-b border-white/10 bg-red-50/50">
          <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-red-500 to-red-600 flex items-center justify-center">
            <AlertCircle size={14} className="text-white" />
          </div>
          <span className="text-sm font-bold text-red-700">Run Interrupted</span>
        </div>
      );
    }
    if (status === 'resumed') {
      return (
        <div className="flex items-center gap-3 py-2 px-4 border-b border-white/10 bg-amber-50/50">
          <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center">
            <RotateCcw size={14} className="text-white" />
          </div>
          <span className="text-sm font-bold text-amber-700">Resuming from checkpoint</span>
        </div>
      );
    }
    // 'starting' status - don't show, it's handled by the floating banner
    return null;
  }

  // Error message - display prominently
  if (type === 'error') {
    const errorMessage = payload?.message || 'An unknown error occurred';
    const traceback = payload?.traceback;
    const toolName =
      typeof payload?.toolName === 'string' && payload.toolName.trim()
        ? payload.toolName.trim()
        : undefined;
    const isToolValidation =
      payload?.kind === 'tool_validation' || looksLikeToolValidationMessage(errorMessage);

    if (isToolValidation && !traceback) {
      const agentLabel = typeof payload?.agent === 'string' ? payload.agent : 'operator';
      return (
        <StepCompleteEntry
          status={getToolValidationFailureTitle(toolName)}
          output={errorMessage}
          hasOutput={errorMessage.trim().length > 0}
          isError={true}
          colorClass={agentColors[agentLabel.toLowerCase()] || agentColors.unknown}
          agentName={agentLabel.toLowerCase()}
          archiveId={archiveId}
          outputSectionLabel="Details"
        />
      );
    }

    const headerTitle =
      payload?.kind === 'api' ||
      errorMessage.startsWith('API Error:') ||
      errorMessage.includes('API Error executing')
        ? 'API Error'
        : 'Error';

    return (
      <div className="py-2 px-4 border-b border-white/10 bg-red-50/50">
        <div className="flex items-start gap-3">
          <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-red-500 to-red-600 flex items-center justify-center flex-shrink-0">
            <AlertCircle size={14} className="text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <span className="text-sm font-bold text-red-700">{headerTitle}</span>
            <p className="text-sm text-red-600 mt-1 whitespace-pre-wrap break-words">{errorMessage}</p>
            {traceback && (
              <details className="mt-2">
                <summary className="text-xs text-red-500 cursor-pointer hover:text-red-600">
                  Show traceback
                </summary>
                <pre className="mt-2 text-xs text-red-400 bg-red-100/50 p-2 rounded overflow-x-auto scrollbar-glass whitespace-pre-wrap">
                  {traceback}
                </pre>
              </details>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Agent event
  if (type === 'agent_event') {
    const { agent, event, status, is_error } = payload || {};
    const agentName = agent?.toLowerCase() || 'unknown';
    const colorClass = agentColors[agentName] || agentColors.unknown;

    // Start event - show as an update event if it has a status
    if (event === 'start' && status) {
      return (
        <UpdateEventEntry 
          status={status}
          colorClass={colorClass}
          is_error={is_error}
          thoughts={(message as any)._thoughts}
          content={payload?.content}
          output={payload?.output}
          payload_is_complete={payload?.is_complete}
          archiveId={archiveId}
        />
      );
    }

    // Skip start events if they have no status (internal lifecycle marks)
    if (event === 'start') {
      return null;
    }

    // Validation / fatal step errors (e.g. operator ValidationError)
    if (event === 'error' && payload?.status) {
      const errMsg = String(payload.status);
      const tName =
        typeof payload?.toolName === 'string' && payload.toolName.trim()
          ? payload.toolName.trim()
          : undefined;
      return (
        <StepCompleteEntry
          status={getToolValidationFailureTitle(tName)}
          output={errMsg}
          hasOutput={errMsg.trim().length > 0}
          isError={true}
          colorClass={colorClass}
          agentName={agentName}
          archiveId={archiveId}
          outputSectionLabel="Details"
        />
      );
    }

    // Step complete - show as a completed action with a checkmark and collapsible output
    if (event === 'step_complete' && status) {
      const output = payload?.output;
      const userFeedback =
        typeof payload?.user_feedback === 'string' ? payload.user_feedback.trim() : '';
      const hasOutput =
        (output && output.length > 0) || (userFeedback && userFeedback.length > 0);
      
      return (
        <StepCompleteEntry 
          status={status} 
          output={output} 
          hasOutput={hasOutput}
          isError={is_error}
          colorClass={colorClass}
          agentName={agentName}
          archiveId={archiveId}
          userFeedback={userFeedback || undefined}
        />
      );
    }
    
    if (event === 'update' && status) {
      return (
        <UpdateEventEntry 
          status={status}
          colorClass={colorClass}
          is_error={is_error}
          thoughts={(message as any)._thoughts}
          content={payload?.content}
          output={payload?.output}
          payload_is_complete={payload?.is_complete}
          archiveId={archiveId}
        />
      );
    }
    
    if (event === 'complete') {
      const output = payload?.output;
      const hasOutput = output && output.length > 0;

      return (
        <StepCompleteEntry 
          status={status || 'Completed'} 
          output={output} 
          hasOutput={hasOutput}
          isError={is_error === true}
          colorClass={is_error ? 'from-red-500 to-red-600' : colorClass}
          agentName={agentName}
          archiveId={archiveId}
        />
      );
    }
    return null;
  }

  // Plan stream - use dedicated component for collapsible state
  if (type === 'plan_stream') {
    return <PlanStreamEntry payload={payload} />;
  }

  // Text stream - display streaming LLM text output
  if (type === 'text_stream') {
    return <TextStreamEntry payload={payload} />;
  }


  // Checkpoint status
  if (type === 'checkpoint_status') {
    const { is_resuming, task_num, total_tasks } = payload || {};
    if (is_resuming) {
      return (
        <div className="flex items-center gap-3 py-2 px-4 border-b border-white/10 bg-amber-50/50">
          <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center">
            <RotateCcw size={14} className="text-white" />
          </div>
          <span className="text-amber-700">
            Resuming from checkpoint: Task {task_num} of {total_tasks}
          </span>
        </div>
      );
    }
    return null;
  }

  // Tool call (from agent_event with tool info)
  if (type === 'tool_call' || (type === 'agent_event' && payload?.tool)) {
    const toolName = payload?.tool || payload?.name || 'Tool';
    const result = payload?.result;
    const isError = payload?.is_error;
    
    return (
      <div className="py-2 px-4 border-b border-white/10 bg-slate-50/30">
        <div className="flex items-center gap-2 mb-1">
          <Terminal size={14} className="text-slate-400" />
          <span className="text-sm font-mono text-slate-600">{toolName}</span>
          {isError && <AlertCircle size={14} className="text-red-500" />}
        </div>
        {result && (
          <div className="ml-6 mt-2 max-h-48 overflow-y-auto scrollbar-glass rounded-lg">
            <MarkdownRenderer 
              content={(() => {
                const resultStr = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
                return resultStr.trim().startsWith('{') || resultStr.trim().startsWith('[') 
                  ? `\`\`\`json\n${resultStr}\n\`\`\`` 
                  : resultStr;
              })()} 
            />
          </div>
        )}
      </div>
    );
  }

  // Code result
  if (type === 'code_result') {
    const { output, file_path, is_error } = payload || {};
    return (
      <div className="py-2 px-4 border-b border-white/10 bg-slate-50/30">
        <div className="flex items-center gap-2 mb-1">
          <FileCode size={14} className={is_error ? "text-red-500" : "text-green-500"} />
          <span className="text-sm font-medium text-slate-600">
            {is_error ? 'Execution Error' : 'Code Output'}
          </span>
          {file_path && <span className="text-xs text-slate-400">({file_path})</span>}
        </div>
        {output && (
          <div className="ml-6 mt-2 max-h-64 overflow-y-auto scrollbar-glass rounded-lg">
            <MarkdownRenderer 
              content={output.trim().startsWith('{') || output.trim().startsWith('[') 
                ? `\`\`\`json\n${output}\n\`\`\`` 
                : output
              } 
            />
          </div>
        )}
      </div>
    );
  }

  // RAG status
  if (type === 'rag_status') {
    return null; // Handled separately in the UI
  }

  // Generic log
  if (type === 'log') {
    return (
      <div className="py-2 px-4 border-b border-white/10 bg-slate-50/30">
        <p className="text-sm text-slate-600">{payload?.text || JSON.stringify(payload)}</p>
      </div>
    );
  }

  // Internal/system messages that shouldn't be displayed as standalone entries
  if (type === 'settings_updated' || type === 'bridge_restarted' || type === 'workspace_cleaned' ||
      type === 'ready' || type === 'init' || type === 'status' || type === 'execution_status' || type === 'checkpoint_status_check' ||
      type === 'file_content' || type === 'tool_call' || type === 'code_result' || type === 'final_summary') {
    return null;
  }

  // Default: show raw JSON for unknown types
  return (
    <div className="py-2 px-4 border-b border-white/10">
      <pre className="text-xs font-mono text-slate-400 whitespace-pre-wrap">
        {JSON.stringify(message, null, 2)}
      </pre>
    </div>
  );
});

LogEntry.displayName = 'LogEntry';
