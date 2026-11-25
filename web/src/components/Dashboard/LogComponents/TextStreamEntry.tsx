import React, { useState } from 'react';
import { 
  Loader2, 
  MessageSquare,
  AlertCircle,
  ChevronDown,
  ChevronUp
} from 'lucide-react';
import { clsx } from 'clsx';
import { MarkdownRenderer } from '../../UI/MarkdownRenderer';
import { agentColors } from './constants';
import { looksLikeToolValidationMessage } from '../../../utils/validationErrorMessage';
import { getToolValidationFailureTitle } from '../../../utils/toolValidationFailureTitle';

interface TextStreamEntryProps {
  payload: {
    agent?: string;
    content?: string;
    is_complete?: boolean;
  };
}

/**
 * Component to display streaming LLM text output globally in the execution log.
 * While streaming: shows "Analysing Task" (or equivalent) with content inline.
 * When complete: shows "Analysed Task" with content in a collapsible section so
 * subsequent tool-call messages appear below it.
 */
export const TextStreamEntry: React.FC<TextStreamEntryProps> = ({ payload }) => {
  const { agent, content, is_complete } = payload || {};
  const agentName = agent?.toLowerCase() || 'unknown';
  const colorClass = agentColors[agentName] || agentColors.unknown;
  const [isExpanded, setIsExpanded] = useState(false);
  
  // Determine display text
  const rawContent = typeof content === 'string' ? content : '';
  const displayContent = is_complete ? rawContent.trim() : rawContent;
  const validationToolName =
    typeof (payload as { toolName?: string })?.toolName === 'string'
      ? (payload as { toolName?: string }).toolName
      : undefined;
  const isValidationError = is_complete && looksLikeToolValidationMessage(displayContent);

  // Status message mappings
  const thinkingStatuses: Record<string, string> = {
    'operator': 'Analysing Task',
    'strategist': 'Analysing Request',
    'evaluator': 'Evaluating Task Completion',
    'unknown': 'Thinking'
  };

  const completedStatuses: Record<string, string> = {
    'operator': 'Analysed Task',
    'strategist': 'Analysed Request',
    'evaluator': 'Evaluated Task Completion',
    'unknown': 'Thinking Complete'
  };
  
  // Format agent name for display as fallback
  const agentDisplayName = agentName.charAt(0).toUpperCase() + agentName.slice(1);

  // Determine header text
  const headerText = isValidationError
    ? getToolValidationFailureTitle(validationToolName)
    : is_complete
      ? (completedStatuses[agentName] || `${agentDisplayName} Response`)
      : (thinkingStatuses[agentName] || `${agentDisplayName} Thinking`);

  const hasContent = displayContent.length > 0;
  const showCollapsible = is_complete && hasContent;

  return (
    <div className="border-b border-white/10 bg-slate-50/30">
      <div 
        className={clsx(
          "flex items-center gap-3 py-2 px-4",
          showCollapsible && "cursor-pointer hover:bg-slate-100/50 transition-colors"
        )}
        onClick={() => showCollapsible && setIsExpanded(!isExpanded)}
      >
        <div className={`w-6 h-6 rounded-lg bg-gradient-to-br ${isValidationError ? 'from-red-500 to-red-600' : colorClass} flex items-center justify-center flex-shrink-0`}>
          {is_complete ? (
            isValidationError ? (
              <AlertCircle size={14} className="text-white" />
            ) : (
              <MessageSquare size={14} className="text-white" />
            )
          ) : (
            <Loader2 size={14} className="text-white animate-spin" />
          )}
        </div>
        <div className="flex-1 min-w-0 space-y-1">
          <span className={clsx(
            "font-bold text-sm",
            isValidationError ? "text-red-600" : is_complete ? "text-green-600" : "text-slate-700"
          )}>
            {headerText}
          </span>
          {/* While streaming: always show content inline. When complete: show content only when expanded */}
          {!is_complete && (
            <div className="text-sm text-slate-600 leading-relaxed">
              <MarkdownRenderer content={displayContent} />
            </div>
          )}
        </div>
        {showCollapsible && (
          <button className="text-slate-400 hover:text-slate-600 transition-colors flex-shrink-0">
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        )}
      </div>

      {/* Completed stream: collapsible body so tool calls sit below the header */}
      {showCollapsible && isExpanded && (
        <div className="px-4 pb-3">
          <div className={clsx(
            "ml-11 min-w-0 max-w-full overflow-x-hidden text-sm rounded-lg p-3 max-h-96 overflow-y-auto scrollbar-glass",
            isValidationError ? "text-red-800 bg-red-50/80 border border-red-100" : "text-slate-600 bg-slate-100/50"
          )}>
            <MarkdownRenderer content={displayContent} />
          </div>
        </div>
      )}
    </div>
  );
};
