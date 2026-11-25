import React, { useEffect } from 'react';
import { useHistory } from '../../hooks/useHistory';
import { Loader2, FileText } from 'lucide-react';
import { HistoryItem } from './HistoryItem';
import { CurrentRunItem } from './CurrentRunItem';

export interface HistoryPanelProps {
  refreshKey?: number;
  onViewArchive?: (archiveId: string) => void;
  onViewTrace?: (archiveId: string) => void;
  onViewCurrentWorkspace?: () => void;
  isRunning?: boolean;
  hasCheckpoint?: boolean;
  currentPrompt?: string;
  isActive?: boolean;
}

export const HistoryPanel: React.FC<HistoryPanelProps> = ({
  refreshKey,
  onViewArchive,
  onViewTrace,
  onViewCurrentWorkspace,
  isRunning = false,
  hasCheckpoint = false,
  currentPrompt = '',
  isActive = true,
}) => {
  const { history, loading, refreshHistory } = useHistory(isActive);

  useEffect(() => {
    if (isActive && refreshKey !== undefined && refreshKey > 0) {
      refreshHistory();
    }
  }, [isActive, refreshKey, refreshHistory]);

  const showCurrentRun = isRunning || hasCheckpoint;

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden rounded-none border-0 border-slate-200/80 bg-white/75 p-3 shadow-sm backdrop-blur-2xl animate-fade-in sm:rounded-2xl sm:border sm:p-6 md:p-8">
      <div className="mb-3 shrink-0 border-b border-slate-200/60 pb-3 sm:mb-6 sm:pb-5">
        <h2 className="text-lg font-extrabold tracking-[-0.03em] text-slate-900 sm:text-2xl md:text-3xl">
          Execution <span className="quasar-gradient-text">History</span>
        </h2>
        <p className="mt-0.5 text-[11px] font-medium leading-snug text-slate-500 sm:mt-1 sm:text-xs">
          Past workflows, traces, and archives.
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain scrollbar-glass pb-[max(0.5rem,env(safe-area-inset-bottom))] pr-0.5 sm:pr-1">
        {showCurrentRun && (
          <CurrentRunItem
            title={currentPrompt}
            isRunning={isRunning}
            isActive={isActive}
            onViewDetails={onViewCurrentWorkspace}
          />
        )}

        {loading && history.length === 0 && !showCurrentRun ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 py-12 sm:gap-4 sm:py-16">
            <Loader2 size={36} className="animate-spin text-indigo-600 sm:h-[42px] sm:w-[42px]" />
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500 animate-pulse sm:text-xs">
              Loading archive…
            </p>
          </div>
        ) : history.length === 0 && !showCurrentRun ? (
          <div className="flex h-full flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300/80 bg-white/50 p-6 text-center sm:p-12">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-200/80 bg-white shadow-sm sm:mb-5 sm:h-16 sm:w-16">
              <FileText size={28} className="text-indigo-500/70 sm:h-8 sm:w-8" />
            </div>
            <h3 className="mb-1 text-base font-bold text-slate-800 sm:mb-1.5 sm:text-lg">
              No archived executions
            </h3>
            <p className="mx-auto max-w-sm text-sm leading-6 text-slate-500">
              Completed runs are indexed here automatically.
            </p>
          </div>
        ) : (
          <div className="animate-fade-in-up space-y-2.5 sm:space-y-3">
            {history.map(run => (
              <HistoryItem
                key={run.id}
                run={run}
                onViewDetails={onViewArchive}
                onViewTrace={onViewTrace}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
