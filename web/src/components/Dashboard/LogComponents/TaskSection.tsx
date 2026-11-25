import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, XCircle, RotateCcw } from 'lucide-react';
import { clsx } from 'clsx';
import type { BridgeMessage, TaskStatus } from '../../../utils/messageHelpers';
import { LogEntry } from './LogEntry';

interface TaskSectionProps {
  taskProgress: BridgeMessage;
  childMessages: BridgeMessage[];
  taskStatus: TaskStatus;
  /** Whether execution is currently running */
  isRunning?: boolean;
  /** Callback to revert to this task */
  onRevert?: (taskNumber: number) => Promise<void>;
  /** Archive/run ID if viewing an archived trace (used for file link navigation) */
  archiveId?: string | null;
}

/**
 * TaskSection component that wraps task messages in a foldable section.
 * - Auto-folds when task status becomes 'passed'
 * - Stays unfolded while 'running' or 'failed'
 * - User can manually toggle fold state
 * - Shows revert button when execution is stopped
 */
export const TaskSection: React.FC<TaskSectionProps> = ({
  taskProgress,
  childMessages,
  taskStatus,
  isRunning = false,
  onRevert,
  archiveId
}) => {
  const { current, title } = taskProgress.payload || {}; // removed total
  
  // Completed tasks start folded so long checkpoint/trace restores do not mount
  // every child log row before the auto-fold effect gets a chance to run.
  const [isFolded, setIsFolded] = useState(taskStatus === 'passed');
  const [isReverting, setIsReverting] = useState(false);
  
  // Auto-fold when task passes
  useEffect(() => {
    if (taskStatus === 'passed') {
      setIsFolded(true);
    }
  }, [taskStatus]);
  
  // Clean title: remove markdown bold markers, Task N: prefix, and trim
  let cleanTitle = title;
  if (cleanTitle) {
    cleanTitle = cleanTitle.replace(/\*\*/g, '');
    cleanTitle = cleanTitle.trim().replace(/^\*+|\*+$/g, '').trim();
    cleanTitle = cleanTitle.replace(/^Task\s*\d+\s*[:-]\s*/i, '').trim();
  }
  
  // Handle revert click
  const handleRevert = async (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent fold toggle
    if (onRevert && current) {
      setIsReverting(true);
      try {
        await onRevert(current);
      } finally {
        setIsReverting(false);
      }
    }
  };
  
  // Show revert button when:
  // 1. Execution is stopped (not running)
  // 2. We have a revert callback
  // 3. Task number is valid (> 0)
  const showRevertButton = !isRunning && onRevert && current > 0;
  
  // Determine icon based on status - only show for failed tasks
  const StatusIcon = () => {
    if (taskStatus === 'failed') {
      return <XCircle size={16} className="text-red-500" />;
    } else {
      return null; // No icon for passed or running state
    }
  };
  
  // Status-based styling
  const headerBgClass = taskStatus === 'passed' 
    ? 'bg-gradient-to-r from-green-50/80 via-emerald-50/60 to-green-50/80 border-green-200/50'
    : taskStatus === 'failed'
    ? 'bg-gradient-to-r from-red-50/80 via-rose-50/60 to-red-50/80 border-red-200/50'
    : 'bg-gradient-to-r from-indigo-50/80 via-purple-50/60 to-indigo-50/80 border-indigo-200/50';
  
  const badgeBgClass = taskStatus === 'passed'
    ? 'text-green-600 bg-green-100'
    : taskStatus === 'failed'
    ? 'text-red-600 bg-red-100'
    : 'text-indigo-600 bg-indigo-100';

  return (
    <div className="task-section">
      {/* Task Header - Clickable to toggle fold */}
      <div 
        className={clsx(
          "py-3 px-4 border-y cursor-pointer transition-colors hover:brightness-95",
          headerBgClass
        )}
        onClick={() => setIsFolded(!isFolded)}
      >
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          {/* Fold/Unfold chevron */}
          <button
            type="button"
            className="shrink-0 text-slate-500 transition-colors hover:text-slate-700"
            aria-label={isFolded ? 'Expand task' : 'Collapse task'}
          >
            {isFolded ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
          </button>
          
          {/* Status icon */}
          <StatusIcon />
          
          {/* Task badge */}
          <span className={clsx('shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold', badgeBgClass)}>
            Task {current}
          </span>
          
          {/* Task title — ellipsis when too long so the log width never expands */}
          {cleanTitle && (
            <span
              className="min-w-0 flex-1 truncate text-sm font-bold text-slate-700"
              title={cleanTitle}
            >
              {cleanTitle}
            </span>
          )}
          
          {/* Revert button - appears when execution is stopped */}
          {showRevertButton && (
            <button
              type="button"
              onClick={handleRevert}
              disabled={isReverting}
              className={clsx(
                'flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-all',
                'border-amber-200 bg-amber-100 text-amber-700 hover:border-amber-300 hover:bg-amber-200 hover:text-amber-800',
                isReverting && 'cursor-not-allowed opacity-50',
              )}
              title={`Revert to the start of Task ${current}`}
            >
              <RotateCcw size={12} className={isReverting ? 'animate-spin' : ''} />
              {isReverting ? 'Reverting' : 'Revert'}
            </button>
          )}
        </div>
      </div>
      
      {/* Child messages - hidden when folded */}
      {!isFolded && (
        <div className="task-content">
          {childMessages.map((msg, idx) => (
            <LogEntry key={`task-${current}-msg-${idx}`} message={msg} archiveId={archiveId} />
          ))}
        </div>
      )}
    </div>
  );
};
