import React, { useDeferredValue, useMemo, useRef, useEffect } from 'react';
import { clsx } from 'clsx';
import { processMessages } from '../../utils/messageHelpers';
import type { BridgeMessage } from '../../utils/messageHelpers';
import { CompactAgentBand } from './LogComponents/CompactAgentBand';
import { LogEntry } from './LogComponents/LogEntry';
import { TaskSection } from './LogComponents/TaskSection';
import type { AgentType } from './LogComponents/constants';

interface ExecutionLogProps {
  messages: BridgeMessage[];
  filterAgent?: AgentType | null;
  activeAgent?: AgentType | null;
  selectedAgent?: AgentType | null;
  onAgentSelect?: (agent: AgentType | null) => void;
  /** Whether execution is currently running */
  isRunning?: boolean;
  /** Callback to revert to a specific task */
  onRevert?: (taskNumber: number) => Promise<void>;
  /** Archive/run ID if viewing an archived trace (used for file link navigation) */
  archiveId?: string | null;
  /** Reserve space for floating controls that overlap the bottom of the log. */
  reserveBottomSpace?: boolean;
  className?: string;
  /** Trailing control in the agent band (mobile), e.g. session terminate. */
  headerEnd?: React.ReactNode;
}

export const ExecutionLog: React.FC<ExecutionLogProps> = ({ 
  messages, 
  filterAgent,
  activeAgent,
  selectedAgent,
  onAgentSelect,
  isRunning = false,
  onRevert,
  archiveId,
  reserveBottomSpace = false,
  className,
  headerEnd,
}) => {
  // Use selectedAgent if passed, otherwise fall back to filterAgent for backwards compatibility
  const effectiveFilterAgent = selectedAgent ?? filterAgent;
  
  // Ref for the scrollable container
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const deferredMessages = useDeferredValue(messages);
  
  // Memoize message processing to prevent unnecessary recalculations
  const processedMessages = useMemo(() => {
    return processMessages(deferredMessages, effectiveFilterAgent);
  }, [deferredMessages, effectiveFilterAgent]);

  // Group messages by task for foldable sections
  const groupedMessages = useMemo(() => {
    const groups: (BridgeMessage | { type: 'task_group', taskProgress: BridgeMessage, messages: BridgeMessage[] })[] = [];
    let currentTaskGroup: { type: 'task_group', taskProgress: BridgeMessage, messages: BridgeMessage[] } | null = null;
    
    for (const msg of processedMessages) {
      // Start a new task group when we see task_progress
      if (msg.type === 'task_progress') {
        // If we have an open group, push it first
        if (currentTaskGroup) {
          groups.push(currentTaskGroup);
        }
        
        // Start new group
        currentTaskGroup = {
          type: 'task_group',
          taskProgress: msg,
          messages: []
        };
        continue;
      }
      
      // If message belongs to a task (has _taskNum), add to current group if it matches
      // match by task number if available, otherwise assume it belongs to current active group
      if (currentTaskGroup) {
        if (msg._taskNum && msg._taskNum !== currentTaskGroup.taskProgress.payload?.current) {
          // Message belongs to different task - close current group and push message as standalone
          // (This shouldn't happen often if processMessages is correct, but safe fallback)
          groups.push(currentTaskGroup);
          currentTaskGroup = null;
          groups.push(msg);
        } else {
          // Add to current task group
          currentTaskGroup.messages.push(msg);
        }
      } else {
        // No active task group, push as standalone message
        groups.push(msg);
      }
    }
    
    // Push final group
    if (currentTaskGroup) {
      groups.push(currentTaskGroup);
    }
    
    return groups;
  }, [processedMessages]);

  // Ref to track if we should auto-scroll (user is at bottom)
  const isAtBottomRef = useRef(true);

  const handleScroll = () => {
    if (scrollContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
      // If we are within 50px of the bottom, we consider it "at the bottom"
      const atBottom = scrollHeight - scrollTop - clientHeight < 50;
      isAtBottomRef.current = atBottom;
    }
  };

  // Auto-scroll to bottom when new messages arrive, but only if user is at bottom
  useEffect(() => {
    if (isAtBottomRef.current && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [processedMessages]);

  return (
    <div className={clsx(
      'glass-panel relative flex h-full w-full min-w-0 flex-col overflow-hidden rounded-2xl border-white/50',
      className,
    )}>
      <div className="pointer-events-none absolute inset-x-4 top-0 z-20 h-px bg-gradient-to-r from-transparent via-white/80 to-transparent" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-white/24 to-transparent" />
      {/* Compact Agent Progress Band */}
      <CompactAgentBand
        activeAgent={activeAgent}
        selectedAgent={selectedAgent}
        onAgentSelect={onAgentSelect}
        endSlot={headerEnd}
      />
      
      {/* Log Entries */}
      <div 
        ref={scrollContainerRef} 
        onScroll={handleScroll}
        className="relative flex-1 overflow-y-auto overflow-x-hidden scrollbar-glass"
      >
        {groupedMessages.length === 0 ? (
          <div className="flex h-full items-center justify-center p-8">
            <div className="rounded-2xl border border-white/60 bg-white/55 px-5 py-4 text-sm font-medium text-slate-500 shadow-sm">
              Waiting for agent activity
            </div>
          </div>
        ) : (
          <>
            {groupedMessages.map((item, idx) => {
              if ('type' in item && item.type === 'task_group') {
                return (
                  <TaskSection
                    key={`task-group-${item.taskProgress.payload?.current ?? idx}`}
                    taskProgress={item.taskProgress}
                    childMessages={item.messages}
                    taskStatus={item.taskProgress._taskStatus || 'running'}
                    isRunning={isRunning}
                    onRevert={onRevert}
                    archiveId={archiveId}
                  />
                );
              } else {
                return (
                  <LogEntry key={`${(item as BridgeMessage).type}-${idx}`} message={item as BridgeMessage} archiveId={archiveId} />
                );
              }
            })}
            {reserveBottomSpace && (
              <div className="h-24 shrink-0 max-lg:h-28" aria-hidden="true" />
            )}
          </>
        )}
      </div>
    </div>
  );
};
