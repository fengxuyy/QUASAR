import React, { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, History, Calendar, ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { SlidingSegment } from '../UI/SlidingSegment';
import 'katex/dist/katex.min.css';

// Must match the constant in App.tsx
const AUTO_IMPROVE_MESSAGE =
  'Please analyze the previous run results and automatically improve the workflow. Review what was accomplished, identify any issues or areas for enhancement, and create an improved execution plan.';

interface CurrentRunItemProps {
  title: string;
  isRunning?: boolean;
  isActive?: boolean;
  onViewDetails?: () => void;
}

const CURRENT_RUN_PREVIEW_BYTES = 64 * 1024;

export const CurrentRunItem: React.FC<CurrentRunItemProps> = ({
  title,
  isRunning = true,
  isActive = true,
  onViewDetails,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [overview, setOverview] = useState<string | null>(null);
  const [usageReport, setUsageReport] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeView, setActiveView] = useState<'Overview' | 'Usage Report'>('Overview');
  const [startTime] = useState(() =>
    new Date().toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }),
  );

  const isAutoImprove = title === AUTO_IMPROVE_MESSAGE;
  const displayTitle = isAutoImprove ? 'Auto Improve' : title || 'Current Execution';

  const fetchOverview = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(
        `/api/files/content?path=quasar_logs/execution_overview.md&maxSize=${CURRENT_RUN_PREVIEW_BYTES}`,
      );
      if (response.ok) {
        const data = await response.json();
        setOverview(data.content);
      } else {
        setOverview(null);
      }
    } catch {
      setOverview(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchUsageReport = useCallback(async () => {
    try {
      const response = await fetch(
        `/api/files/content?path=quasar_logs/usage_report.md&maxSize=${CURRENT_RUN_PREVIEW_BYTES}`,
      );
      if (response.ok) {
        const data = await response.json();
        setUsageReport(data.content);
      } else {
        setUsageReport(null);
      }
    } catch {
      setUsageReport(null);
    }
  }, []);

  useEffect(() => {
    if (!isActive) return;
    fetchOverview();
    fetchUsageReport();
    if (isRunning) {
      const interval = setInterval(() => {
        fetchOverview();
        fetchUsageReport();
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [fetchOverview, fetchUsageReport, isActive, isRunning]);

  const hasUsageReport = usageReport !== null && usageReport.trim() !== '';

  const getContent = () => {
    if (activeView === 'Usage Report' && hasUsageReport) {
      return usageReport;
    }
    return overview;
  };

  return (
    <div
      className={`mb-2.5 overflow-hidden rounded-xl shadow-sm transition-all duration-300 hover:shadow-md sm:mb-4 sm:rounded-2xl ${
        isRunning ? 'animate-breathing-border' : 'border-2 border-amber-400/50'
      }`}
    >
      <button
        type="button"
        onClick={() => setIsExpanded(open => !open)}
        className={`flex w-full items-start gap-2 p-3 text-left transition-colors sm:items-center sm:gap-3 sm:p-5 ${
          isRunning
            ? 'bg-gradient-to-r from-blue-500/10 to-purple-500/10 hover:from-blue-500/20 hover:to-purple-500/20'
            : 'bg-gradient-to-r from-amber-500/10 to-orange-500/10 hover:from-amber-500/20 hover:to-orange-500/20'
        }`}
        aria-expanded={isExpanded}
      >
        <div className="min-w-0 flex-1">
          <h3 className="line-clamp-2 text-[0.9375rem] font-semibold leading-snug text-slate-800 sm:line-clamp-1 sm:text-lg">
            {displayTitle}
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500 sm:gap-4 sm:text-xs">
            <span className="inline-flex items-center gap-1">
              <History size={13} className={isRunning ? 'text-blue-500' : 'text-amber-500'} />
              <span className={`font-semibold ${isRunning ? 'text-blue-600' : 'text-amber-600'}`}>
                {isRunning ? 'Current' : 'Interrupted'}
              </span>
            </span>
            <span className="inline-flex items-center gap-1">
              <Calendar size={13} className="shrink-0 text-purple-500" />
              <span className="whitespace-nowrap">{startTime}</span>
            </span>
          </div>
        </div>
        <span className="mt-0.5 shrink-0 rounded-full bg-white/60 p-1.5 text-slate-400 sm:mt-0 sm:p-2">
          {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </span>
      </button>

      {onViewDetails && (
        <div className="flex flex-wrap items-center gap-2 border-t border-white/15 px-3 py-2.5 sm:px-5 sm:py-3">
          <button
            type="button"
            onClick={() => onViewDetails()}
            className="inline-flex min-h-9 items-center justify-center gap-1.5 rounded-lg border border-blue-200/70 bg-blue-50/80 px-3 py-1.5 text-[11px] font-semibold text-blue-600 transition-colors hover:bg-blue-100 sm:min-h-0 sm:rounded-xl sm:text-xs"
          >
            <ExternalLink size={13} className="shrink-0" />
            Workspace
          </button>
        </div>
      )}

      {isExpanded && (
        <div className="border-t border-white/20 bg-white/25 px-3 py-3 animate-fade-in sm:px-6 sm:py-5">
          {!isRunning && hasUsageReport && (
            <div className="mb-3 sm:mb-4">
              <SlidingSegment
                value={activeView}
                options={['Overview', 'Usage Report']}
                onChange={val => setActiveView(val as 'Overview' | 'Usage Report')}
                className="w-full max-w-none sm:max-w-xs"
              />
            </div>
          )}

          {loading && !overview ? (
            <div className="py-6 text-center text-sm text-slate-400 sm:py-8">
              <div className="animate-pulse">Loading execution overview…</div>
            </div>
          ) : getContent() ? (
            <div className="prose prose-slate max-w-none prose-sm dark:prose-invert prose-pre:text-[12px] prose-table:text-[12px] sm:prose-base sm:prose-pre:text-sm">
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex]}
                components={{
                  h1: ({ node: _n, ...props }) => (
                    <h1 className="mb-3 text-lg font-bold text-blue-800 sm:mb-4 sm:text-xl" {...props} />
                  ),
                  h2: ({ node: _n, ...props }) => (
                    <h2 className="mb-2 text-base font-bold text-blue-700 sm:mb-3 sm:text-lg" {...props} />
                  ),
                  h3: ({ node: _n, ...props }) => (
                    <h3 className="mb-2 text-sm font-bold text-blue-600 sm:text-base" {...props} />
                  ),
                  p: ({ node: _n, ...props }) => (
                    <p className="mb-3 font-sans leading-relaxed text-slate-700 sm:mb-4" {...props} />
                  ),
                  pre: ({ node: _n, ...props }) => (
                    <pre
                      className="mb-3 overflow-x-auto rounded-lg border border-slate-200 bg-slate-900/5 p-2.5 scrollbar-glass sm:mb-4 sm:rounded-xl sm:p-4"
                      {...props}
                    />
                  ),
                  code: ({ node: _n, ...props }) => (
                    <code
                      className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[12px] text-blue-600 sm:px-1.5 sm:text-sm"
                      {...props}
                    />
                  ),
                  table: ({ node: _n, ...props }) => (
                    <div className="-mx-1 my-3 overflow-x-auto overscroll-x-contain scrollbar-glass sm:mx-0 sm:my-4">
                      <table className="min-w-full border-collapse border border-slate-300" {...props} />
                    </div>
                  ),
                  th: ({ node: _n, ...props }) => (
                    <th
                      className="border border-slate-300 bg-slate-100 px-2 py-1.5 text-left text-[11px] font-semibold text-slate-700 sm:px-4 sm:py-2 sm:text-sm"
                      {...props}
                    />
                  ),
                  td: ({ node: _n, ...props }) => (
                    <td
                      className="border border-slate-300 px-2 py-1.5 text-[11px] text-slate-600 sm:px-4 sm:py-2 sm:text-sm"
                      {...props}
                    />
                  ),
                }}
              >
                {getContent()!}
              </ReactMarkdown>
            </div>
          ) : (
            <div className="py-6 text-center text-slate-400 sm:py-8">
              <p className="text-sm">Execution starting</p>
              <p className="mt-1 text-xs sm:text-sm">
                Overview will appear once the agent begins processing.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
