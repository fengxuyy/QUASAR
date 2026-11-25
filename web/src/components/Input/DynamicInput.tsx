import React, { useState, useRef, useEffect } from 'react';
import { Send, Square, Loader2, RotateCcw, Play, Trash2, X } from 'lucide-react';
import { clsx } from 'clsx';
import { useIsCoarsePointer } from '../../hooks/useMediaQuery';
import type { ContextUsage } from '../../hooks/useQuasarBridge';
import { formatUsagePercent, getContextUsageTone } from '../../utils/contextUsage';

interface DynamicInputProps {
  onSend: (message: string) => void;
  onCancel: () => void;
  onPlanConfirm?: () => void;
  onPlanDecline?: () => void;
  onPlanAdjust?: () => void;
  hasStarted: boolean;
  isRunning: boolean;
  isAwaitingPlanConfirmation?: boolean;
  currentPrompt?: string;
  isStarting?: boolean;
  isInitializing?: boolean;
  hasCheckpoint?: boolean;
  allowResumeSteering?: boolean;
  /** Interrupt in flight — keep resume shell (avoid empty composer flash). */
  isInterrupting?: boolean;
  hasArchive?: boolean;
  archiveCount?: number;
  onResume?: () => void;
  onResumeWithMessage?: () => void;
  onStartFresh?: () => void;
  onClearArchive?: () => void;
  onEmptySubmit?: () => void;
  value: string;
  onChange: (value: string) => void;
  justLoadedCheckpoint?: boolean;
  runJustFinished?: boolean;
  // Trace viewing mode props
  isViewingTrace?: boolean;
  traceInput?: string;
  traceArchiveId?: string | null;
  onExitTrace?: () => void;
  /** Shown as a compact “Ctx xx%” chip in the running bar on mobile. */
  contextUsage?: ContextUsage | null;
}

const formatArchiveLabel = (archiveId?: string | null): string => {
  if (!archiveId) return '';
  const newMatch = archiveId.match(/^quasar_run_(\d{8})_(\d{6})_[0-9a-f]{6}(?:_\d+)?$/);
  if (newMatch) {
    const date = newMatch[1];
    const time = newMatch[2];
    return `Run ${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)} ${time.slice(0, 2)}:${time.slice(2, 4)}:${time.slice(4, 6)}`;
  }
  return archiveId;
};

export const DynamicInput: React.FC<DynamicInputProps> = ({ 
  onSend, 
  onCancel,
  onPlanConfirm,
  onPlanDecline,
  onPlanAdjust,
  hasStarted, 
  isRunning,
  isAwaitingPlanConfirmation,
  currentPrompt,
  isStarting,
  isInitializing,
  hasCheckpoint,
  allowResumeSteering = false,
  isInterrupting = false,
  hasArchive,
  archiveCount,
  onResume,
  onResumeWithMessage,
  onStartFresh,
  onClearArchive,
  onEmptySubmit,
  value,
  onChange,
  justLoadedCheckpoint,
  runJustFinished,
  isViewingTrace,
  traceInput,
  traceArchiveId,
  onExitTrace,
  contextUsage = null,
}: DynamicInputProps) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  /** Glass shell — used to reserve vertical space so welcome templates never sit under the input. */
  const shellRef = useRef<HTMLDivElement>(null);
  const [isHovered, setIsHovered] = useState(false);
  const [isHoveredPersistent, setIsHoveredPersistent] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const retreatTimerRef = useRef<NodeJS.Timeout | null>(null);
  const checkpointExpandTimerRef = useRef<NodeJS.Timeout | null>(null);
  const traceExpandTimerRef = useRef<NodeJS.Timeout | null>(null);
  const [hasTriggeredCheckpointExpand, setHasTriggeredCheckpointExpand] = useState(false);
  const [hasTriggeredTraceExpand, setHasTriggeredTraceExpand] = useState(false);
  const [isOverflowing, setIsOverflowing] = useState(false);
  const isCoarsePointer = useIsCoarsePointer();

  // Handle automatic expansion when checkpoint is just loaded
  // This shows the input frame fully for 4 seconds before auto-folding
  useEffect(() => {
    if (justLoadedCheckpoint && !hasTriggeredCheckpointExpand) {
      setHasTriggeredCheckpointExpand(true);
      setIsHoveredPersistent(true);
      
      // Start 4-second timer to auto-fold
      checkpointExpandTimerRef.current = setTimeout(() => {
        // Only fold if user is not currently hovering
        if (!isHovered) {
          setIsHoveredPersistent(false);
        }
        checkpointExpandTimerRef.current = null;
      }, 4000);
    }
    
    return () => {
      if (checkpointExpandTimerRef.current) {
        clearTimeout(checkpointExpandTimerRef.current);
      }
    };
  }, [justLoadedCheckpoint, hasTriggeredCheckpointExpand, isHovered]);

  // Expand fully as soon as interrupt begins so steering UI does not fade in collapsed.
  useEffect(() => {
    if (isInterrupting) {
      setIsHoveredPersistent(true);
      setHasTriggeredCheckpointExpand(true);
    }
  }, [isInterrupting]);

  // Handle automatic expansion when viewing trace
  // This shows the input frame fully for 5 seconds before auto-folding
  useEffect(() => {
    if (isViewingTrace && !hasTriggeredTraceExpand) {
      setHasTriggeredTraceExpand(true);
      setIsHoveredPersistent(true);
      
      // Start 5-second timer to auto-fold
      traceExpandTimerRef.current = setTimeout(() => {
        // Only fold if user is not currently hovering
        if (!isHovered) {
          setIsHoveredPersistent(false);
        }
        traceExpandTimerRef.current = null;
      }, 5000);
    }
    
    // Reset when exiting trace view
    if (!isViewingTrace && hasTriggeredTraceExpand) {
      setHasTriggeredTraceExpand(false);
    }
    
    return () => {
      if (traceExpandTimerRef.current) {
        clearTimeout(traceExpandTimerRef.current);
      }
    };
  }, [isViewingTrace, hasTriggeredTraceExpand, isHovered]);

  // Handle hover persistence with delay
  useEffect(() => {
    if (isHovered) {
      if (retreatTimerRef.current) {
        clearTimeout(retreatTimerRef.current);
        retreatTimerRef.current = null;
      }
      setIsHoveredPersistent(true);
    } else if (isHoveredPersistent) {
      // Start 4s timer to retreat
      retreatTimerRef.current = setTimeout(() => {
        setIsHoveredPersistent(false);
        retreatTimerRef.current = null;
      }, 4000);
    }
    
    return () => {
      if (retreatTimerRef.current) {
        clearTimeout(retreatTimerRef.current);
      }
    };
  }, [isHovered, isHoveredPersistent]);


  // Check if we're in the "archive found, no checkpoint" state
  const isArchiveState = hasArchive && !hasCheckpoint && !isInterrupting;
  // When run just finished, center the input instead of bottom-anchoring
  const isBottomAnchored = hasStarted && !isArchiveState && !runJustFinished;
  // Trace viewing mode should also be bottom-anchored
  // Keep bottom chrome during interrupt so the bar does not jump to center mid-stop.
  const isCurrentlyBottom = isRunning || isBottomAnchored || isViewingTrace || isInterrupting;
  // Resume shell: checkpoint ready, or interrupt still settling metadata
  const inResumeShell = !isRunning && (hasCheckpoint || isInterrupting);
  // Touch devices have no hover — keep the bar fully expanded and tappable
  const isExpanded =
    !isCurrentlyBottom ||
    isHoveredPersistent ||
    isFocused ||
    isCoarsePointer ||
    !!isAwaitingPlanConfirmation ||
    isInterrupting ||
    inResumeShell;

  useEffect(() => {
    // Auto-resize textarea and check for overflow
    if (textareaRef.current) {
      // Plan-feedback field stays compact on phones; main composer is taller
      const isMobileViewport =
        typeof window !== 'undefined' && window.matchMedia('(max-width: 639.98px)').matches;
      const fixedHeight = isAwaitingPlanConfirmation
        ? (isMobileViewport ? 34 : 44)
        : isCurrentlyBottom
          ? 44
          : 50;
      // Welcome (centered) state: keep growth modest so templates stay visible.
      // Bottom/run state can grow taller — nothing sits under the bar there.
      const maxHeight = isAwaitingPlanConfirmation
        ? 96
        : isCurrentlyBottom
          ? 192
          : isMobileViewport
            ? 112
            : 140;

      // For empty textarea, use a fixed height to avoid extra space from placeholder
      if (!value.trim()) {
        // Set both height and minHeight to ensure consistent sizing
        textareaRef.current.style.height = fixedHeight + 'px';
        textareaRef.current.style.minHeight = fixedHeight + 'px';
        setIsOverflowing(false);
      } else {
        // Temporarily set height to 0 to get accurate scrollHeight for content
        // (using 'auto' can cause visual flicker)
        textareaRef.current.style.height = '0';
        const scrollHeight = textareaRef.current.scrollHeight;

        // Only expand if content actually needs more than the fixed height
        // This prevents height jumping when you start typing single-line content
        const targetHeight = scrollHeight > fixedHeight ? Math.min(scrollHeight, maxHeight) : fixedHeight;

        // Check if content overflows the max height
        const overflowing = scrollHeight > maxHeight;
        setIsOverflowing(overflowing);

        // Set height based on content, maintaining fixed height for single line
        textareaRef.current.style.height = targetHeight + 'px';
        textareaRef.current.style.minHeight = fixedHeight + 'px';      }
    }
  }, [value, isCurrentlyBottom, isArchiveState, isInitializing, runJustFinished, isAwaitingPlanConfirmation]);

  // Keep DashboardWelcome template band clear of the growing composer.
  // Title/templates use --quasar-welcome-input-lane as a reserved vertical slot.
  useEffect(() => {
    if (isCurrentlyBottom) return;
    const shell = shellRef.current;
    if (!shell || typeof ResizeObserver === 'undefined') return;

    const publishLane = () => {
      const height = shell.getBoundingClientRect().height;
      // Small buffer so shadows / focus rings do not kiss the template cards.
      const lanePx = Math.max(116, Math.ceil(height + 20));
      document.documentElement.style.setProperty(
        '--quasar-welcome-input-lane',
        `${lanePx}px`,
      );
    };

    publishLane();
    const observer = new ResizeObserver(() => {
      publishLane();
    });
    observer.observe(shell);
    return () => {
      observer.disconnect();
      document.documentElement.style.removeProperty('--quasar-welcome-input-lane');
    };
  }, [isCurrentlyBottom, value, isOverflowing, isAwaitingPlanConfirmation]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !isRunning && !isInitializing) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    if (isRunning || isInitializing) return;

    if (hasCheckpoint) {
      if (allowResumeSteering && value.trim()) {
        onResumeWithMessage?.();
      } else {
        onResume?.();
      }
      return;
    }
    
    // If hasArchive and no text, trigger empty submit confirmation
    if (hasArchive && !hasCheckpoint && !value.trim()) {
      onEmptySubmit?.();
      return;
    }
    
    if (value.trim()) {
      onSend(value);
    }
  };

  const handlePlanFeedbackKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const normalizedValue = value.trim().toLowerCase();
      if (!normalizedValue) return;
      if (normalizedValue === 'yes') {
        onPlanConfirm?.();
        return;
      }
      if (normalizedValue === 'no') {
        onPlanDecline?.();
        return;
      }
      if (value.trim()) {
        onPlanAdjust?.();
      }
    }
  };

  // Determine placeholder text
  const getPlaceholder = () => {
    if (isInitializing) return "Initializing";
    if (runJustFinished) {
      return "Run Completed. Enter a request to refine, or leave blank to auto-improve.";
    }
    if (hasArchive && !hasCheckpoint) {
      return `Previous run${archiveCount && archiveCount > 1 ? 's' : ''} detected. Enter a request to refine, or leave blank to auto-improve.`;
    }
    if (isInterrupting) {
      return "Stopping… you can add resume instructions";
    }
    if (hasCheckpoint) {
      return allowResumeSteering
        ? "Add instructions for the resumed run"
        : "Resume from checkpoint";
    }
    if (hasStarted) return "Send a message";
    return "Describe your computation";
  };

  const AUTO_IMPROVE_MESSAGE = "Please analyze the previous run results and automatically improve the workflow. Review what was accomplished, identify any issues or areas for enhancement, and create an improved execution plan.";


  return (
    <div className="flex w-full flex-col items-center">
      <div
        className={clsx(
          'absolute left-1/2 z-20 -translate-x-1/2 transition-[top,transform,opacity,width,max-width] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]',
          // Bottom-anchored while running / mid-run
          isCurrentlyBottom
            ? 'top-full w-[calc(100%-1.5rem)] max-w-[min(100%,48rem)] pb-[max(0.75rem,env(safe-area-inset-bottom))] md:pb-6'
            : 'top-[var(--quasar-welcome-input-top,50%)] w-[var(--quasar-welcome-input-width)]',
          // Width caps by state (empty dashboard uses CSS var width above)
          // Prefer resume width during interrupt so Stop → steering does not pop max-width.
          isCurrentlyBottom &&
            (isAwaitingPlanConfirmation
              ? 'max-w-4xl'
              : isRunning && !isInterrupting
                ? 'max-w-lg'
                : 'max-w-xl'),
          // Hover-collapse only on fine-pointer desktops
          isCurrentlyBottom && !isExpanded && 'translate-y-[calc(-8px)] opacity-40',
          isCurrentlyBottom && isExpanded && 'translate-y-[-100%] opacity-100',
          // Empty dashboard: vertically centered on the welcome lane
          !isCurrentlyBottom && '-translate-y-1/2 opacity-100',
        )}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <div
          ref={shellRef}
          className={clsx(
            'glass-input relative flex min-h-[3.25rem] items-center rounded-2xl border transition-[background-color,border-color,box-shadow,padding,min-height] duration-300 ease-out',
            isRunning && !isInterrupting ? 'p-0.5' : 'p-1',
            isCurrentlyBottom ? 'shadow-lg' : 'shadow-2xl',
            isInterrupting && 'ring-1 ring-amber-200/80',
          )}
        >
          {isViewingTrace ? (
            // Trace Viewing Mode
            <>
              <div className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 font-medium text-slate-600 sm:px-4">
                <span className="flex-shrink-0 rounded-full border border-purple-200 bg-purple-100 px-2 py-0.5 text-xs font-bold text-purple-700 shadow-sm">
                  {formatArchiveLabel(traceArchiveId)}
                </span>
                <span className="truncate text-sm text-slate-700">
                  {traceInput || 'No input recorded'}
                </span>
              </div>

              <button
                onClick={onExitTrace}
                className="m-1 flex flex-shrink-0 items-center gap-1 rounded-xl bg-slate-500 p-2 text-white shadow-md transition-all duration-300 hover:bg-slate-600"
                title="Exit trace viewing"
              >
                <X size={16} />
                <span className="pr-1 text-sm font-medium">Exit</span>
              </button>
            </>
          ) : isRunning && !isInterrupting ? (
            // Running State Content
            <>
              {isAwaitingPlanConfirmation ? (
                <div className="flex min-w-0 flex-1 flex-col items-stretch gap-1.5 px-2 py-1.5 sm:gap-3 sm:px-3 sm:py-2 sm:flex-row">
                  <div className="flex min-w-0 flex-1 flex-col gap-1.5 sm:gap-2">
                    <div className="flex min-w-0 items-center gap-2 font-medium text-slate-600">
                      <span className="flex-shrink-0 rounded-full border border-amber-200 bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-700 shadow-sm sm:text-xs">
                        Plan Ready
                      </span>
                      {currentPrompt === AUTO_IMPROVE_MESSAGE ? (
                        <span className="flex-shrink-0 rounded-full border border-purple-200 bg-purple-100 px-2 py-0.5 text-[10px] font-bold text-purple-700 shadow-sm sm:text-xs">
                          Auto Improve
                        </span>
                      ) : (
                        <span className="truncate text-xs text-slate-700 sm:text-sm">
                          {currentPrompt || 'Review the proposed plan'}
                        </span>
                      )}
                    </div>
                    <label className="sr-only" htmlFor="plan-feedback-input">
                      Optional plan feedback
                    </label>
                    <div className="relative">
                      <textarea
                        id="plan-feedback-input"
                        ref={textareaRef}
                        value={value}
                        onChange={(e) => onChange(e.target.value)}
                        onKeyDown={handlePlanFeedbackKeyDown}
                        onFocus={() => setIsFocused(true)}
                        onBlur={() => setIsFocused(false)}
                        placeholder="Type feedback or changes…"
                        className={clsx(
                          // Compact, clearly interactive field on mobile
                          'w-full max-h-24 resize-none rounded-lg border border-slate-300/90 bg-white px-2.5 py-1.5 text-[13px] leading-snug text-slate-700 shadow-sm outline-none transition-colors',
                          'placeholder:text-slate-400',
                          'focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200/70',
                          'min-h-[34px] sm:min-h-[44px] sm:max-h-32 sm:rounded-xl sm:border-white/60 sm:bg-white/55 sm:px-3 sm:py-2 sm:text-sm sm:shadow-inner sm:shadow-white/40',
                          isOverflowing ? 'overflow-y-auto scrollbar-glass' : 'overflow-y-hidden',
                        )}
                        rows={1}
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-1 sm:flex sm:items-end sm:gap-2">
                    <button
                      onClick={onPlanDecline}
                      className="flex h-8 flex-shrink-0 items-center justify-center gap-0.5 rounded-lg bg-slate-200 px-1.5 py-1 text-slate-700 shadow-sm transition-all duration-300 hover:bg-slate-300 sm:h-auto sm:gap-1 sm:rounded-xl sm:p-2"
                      title="Cancel this plan and return to editing"
                    >
                      <X size={14} className="sm:h-4 sm:w-4" />
                      <span className="text-[11px] font-medium leading-none sm:pr-1 sm:text-sm">Cancel</span>
                    </button>
                    <button
                      onClick={onPlanAdjust}
                      disabled={!value.trim()}
                      className={clsx(
                        'flex h-8 flex-shrink-0 items-center justify-center gap-0.5 rounded-lg px-1.5 py-1 transition-all duration-300 sm:h-auto sm:gap-1 sm:rounded-xl sm:p-2',
                        value.trim()
                          ? 'bg-amber-500 text-white shadow-md hover:bg-amber-600'
                          : 'cursor-not-allowed bg-amber-200 text-amber-50',
                      )}
                      title="Ask the strategist to revise the plan"
                    >
                      <RotateCcw size={14} className="sm:h-4 sm:w-4" />
                      <span className="text-[11px] font-medium leading-none sm:pr-1 sm:text-sm">
                        <span className="sm:hidden">Update</span>
                        <span className="hidden sm:inline">Update Plan</span>
                      </span>
                    </button>
                    <button
                      onClick={onPlanConfirm}
                      className="flex h-8 flex-shrink-0 items-center justify-center gap-0.5 rounded-lg bg-[#4a5fe4] px-1.5 py-1 text-white shadow-md shadow-indigo-300/40 transition-all duration-300 hover:bg-[#3a4ed0] sm:h-auto sm:gap-1 sm:rounded-xl sm:p-2"
                      title="Approve this plan and continue execution"
                    >
                      <Play size={14} className="sm:h-4 sm:w-4" fill="currentColor" />
                      <span className="text-[11px] font-medium leading-none sm:pr-1 sm:text-sm">Confirm</span>
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  {/* Show current prompt */}
                  <div className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 font-medium text-slate-600 sm:px-4">
                    {currentPrompt === AUTO_IMPROVE_MESSAGE ? (
                      // Show just "Auto Improve" text for auto-improve runs
                      <span className="rounded-full border border-purple-200 bg-purple-100 px-2 py-0.5 text-xs font-bold text-purple-700 shadow-sm">
                        Auto Improve
                      </span>
                    ) : (
                      // Show the actual prompt for regular runs
                      <span className="truncate text-sm text-slate-700">
                        {currentPrompt || (isStarting ? 'Starting' : 'Resuming')}
                      </span>
                    )}
                  </div>

                  {/* Compact context chip — mobile only (full TokenTrackerPanel is desktop) */}
                  {(() => {
                    const tone = getContextUsageTone(contextUsage);
                    const pct = formatUsagePercent(contextUsage?.usage_percent);
                    const toneClass =
                      tone === 'danger'
                        ? 'border-rose-200 bg-rose-50 text-rose-700'
                        : tone === 'warning'
                          ? 'border-amber-200 bg-amber-50 text-amber-700'
                          : tone === 'safe'
                            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                            : 'border-slate-200 bg-slate-50 text-slate-600';
                    return (
                      <span
                        className={clsx(
                          'mr-0.5 hidden shrink-0 rounded-full border px-2 py-0.5 font-mono text-[10px] font-bold tabular-nums tracking-tight max-lg:inline-flex',
                          toneClass,
                        )}
                        title={
                          contextUsage?.usage_percent != null
                            ? `Context usage ${pct}`
                            : 'Context usage'
                        }
                      >
                        Ctx {pct}
                      </span>
                    );
                  })()}
                  
                  {/* Loading spinner while starting, then Stop button */}
                  {isStarting ? (
                    <div className="m-1 flex items-center justify-center p-2">
                      <Loader2 size={20} className="animate-spin text-[#4a5fe4]" />
                    </div>
                  ) : (
                    <button 
                      onClick={onCancel}
                      className="m-1 flex-shrink-0 rounded-xl bg-red-500 p-2 text-white shadow-md transition-all duration-300 hover:bg-red-600"
                      title="Stop execution"
                    >
                      <Square size={16} fill="currentColor" />
                    </button>
                  )}
                </>
              )}
            </>
          ) : (
            // Idle State Content (Initial or Bottom-anchored)
            <>
              {/* Show Auto Improve badge for idle auto-improve prompts. Keep checkpoint resumes editable. */}
              {!hasCheckpoint && value === AUTO_IMPROVE_MESSAGE ? (
                <div className="flex-1 px-4 py-2 flex items-center gap-2">
                  <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs font-bold rounded-full border border-purple-200 shadow-sm">
                    Auto Improve
                  </span>
                </div>
              ) : (
                <textarea
                  ref={textareaRef}
                  value={value}
                  onChange={(e) => onChange(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onFocus={() => setIsFocused(true)}
                  onBlur={() => setIsFocused(false)}
                  placeholder={getPlaceholder()}
                  className={clsx(
                    // text-base (16px) on small screens avoids iOS focus zoom
                    // Welcome: tighter cap so growth does not cover templates;
                    // bottom bar can grow taller (max-h-48).
                    'flex-1 resize-none border-none bg-transparent px-3 font-medium leading-tight text-slate-700 outline-none placeholder:text-slate-400 sm:px-4',
                    isCurrentlyBottom ? 'max-h-48' : 'max-h-28 sm:max-h-36',
                    isOverflowing ? 'overflow-y-auto scrollbar-glass' : 'overflow-y-hidden',
                    isCurrentlyBottom ? 'py-2.5 text-base sm:text-sm' : 'py-3 text-base sm:text-[15px]',
                  )}
                  style={{
                    minHeight: isCurrentlyBottom ? '44px' : '50px',
                    lineHeight: '1.4',
                  }}
                  rows={1}
                  disabled={isRunning || isInitializing}
                  readOnly={hasCheckpoint && !allowResumeSteering}
                />
              )}
              
              {inResumeShell ? (
                // Checkpoint / interrupt settle — Resume/Start Fresh (or spinner while stopping)
                <div className="flex items-center gap-1 px-1">
                   <button 
                    onClick={onStartFresh}
                    disabled={isInitializing || isInterrupting}
                    className={clsx(
                      "p-2 rounded-xl transition-all duration-300",
                      isInitializing || isInterrupting
                        ? "text-slate-300 cursor-not-allowed"
                        : "text-slate-400 hover:text-slate-600 hover:bg-slate-100/60"
                    )}
                    title="Start Fresh"
                  >
                    <RotateCcw size={18} />
                  </button>
                  {isInterrupting ? (
                    <div
                      className="m-1 flex items-center justify-center rounded-xl bg-[#4a5fe4]/10 p-2"
                      title="Stopping run…"
                    >
                      <Loader2 size={18} className="animate-spin text-[#4a5fe4]" />
                    </div>
                  ) : (
                    <button 
                      onClick={allowResumeSteering && value.trim() ? onResumeWithMessage : onResume}
                      disabled={isInitializing}
                      className={clsx(
                        "p-2 rounded-xl transition-all duration-300",
                        isInitializing ? "text-slate-300 cursor-not-allowed" : "text-[#4a5fe4] hover:bg-[#4a5fe4] hover:text-white hover:shadow-md"
                      )}
                      title={allowResumeSteering && value.trim() ? "Resume with message" : "Resume"}
                    >
                      {allowResumeSteering && value.trim() ? <Send size={18} /> : <Play size={18} fill="currentColor" />}
                    </button>
                  )}
                </div>
              ) : isArchiveState ? (
                // Archive exists but no checkpoint - show Reset/Submit buttons
                <div className="flex items-center gap-1 px-1">
                  <button 
                    onClick={onClearArchive}
                    disabled={isInitializing}
                    className={clsx(
                      "p-2 rounded-xl transition-all duration-300",
                      isInitializing ? "text-slate-300 cursor-not-allowed" : "text-slate-400 hover:text-red-500 hover:bg-red-50"
                    )}
                    title="Reset Workspace - Prepare for new run"
                  >
                    <Trash2 size={18} />
                  </button>
                  <button 
                    onClick={handleSubmit}
                    disabled={isInitializing || isStarting}
                    className={clsx(
                      "p-2 rounded-xl transition-all duration-300 m-1 flex-shrink-0",
                      isStarting
                        ? "bg-[#4a5fe4] text-white shadow-md shadow-indigo-300/40"
                        : "bg-[#4a5fe4] text-white shadow-md shadow-indigo-300/40 hover:bg-[#3a4ed0]"
                    )}
                    title={value.trim() ? "Submit new request" : "Auto-improve previous results"}
                  >
                    {isStarting ? (
                      <Loader2 size={18} className="animate-spin" />
                    ) : (
                      <Send size={18} />
                    )}
                  </button>
                </div>
              ) : (
                // Default state - just Submit button
                <button 
                  onClick={handleSubmit}
                  disabled={isRunning || isInitializing || isStarting || !value.trim()}
                  className={clsx(
                      "p-2 rounded-xl transition-all duration-300 m-1 flex-shrink-0",
                      isStarting
                        ? "bg-[#4a5fe4] text-white shadow-md shadow-indigo-300/40"
                        : value.trim() && !isRunning && !isInitializing
                          ? "bg-[#4a5fe4] text-white shadow-md shadow-indigo-300/40 hover:bg-[#3a4ed0]" 
                          : "bg-slate-200 text-slate-400"
                  )}
                >
                  {isStarting ? (
                    <Loader2 size={18} className="animate-spin" />
                  ) : (
                    <Send size={18} />
                  )}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
