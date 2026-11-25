import React, { useEffect, useState } from 'react';
import type { HistoryRun } from '../../hooks/useHistory';
import { ChevronDown, ChevronRight, History, Calendar, ExternalLink, PlayCircle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { SlidingSegment } from '../UI/SlidingSegment';
import 'katex/dist/katex.min.css';
import { withAuthUrl } from '../../utils/apiAuth';

interface HistoryItemProps {
  run: HistoryRun;
  onViewDetails?: (archiveId: string) => void;
  onViewTrace?: (archiveId: string) => void;
}

function formatRunDate(timestamp: number | string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return String(timestamp);
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export const HistoryItem: React.FC<HistoryItemProps> = ({ run, onViewDetails, onViewTrace }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const formattedDate = formatRunDate(run.timestamp);
  const hasUsageReport = run.usageReport !== null && run.usageReport.trim() !== '';
  const hasOverview = run.executionOverview !== null && run.executionOverview.trim() !== '';

  const [activeView, setActiveView] = useState<'Overview' | 'Summary' | 'Usage Report'>(
    hasOverview ? 'Overview' : 'Summary',
  );

  useEffect(() => {
    if (!isExpanded) {
      setActiveView(hasOverview ? 'Overview' : 'Summary');
    }
  }, [isExpanded, hasOverview]);

  const segmentOptions = [
    ...(hasOverview ? (['Overview'] as const) : []),
    'Summary' as const,
    ...(hasUsageReport ? (['Usage Report'] as const) : []),
  ];

  return (
    <div className="overflow-hidden rounded-xl border border-white/20 bg-white/40 shadow-sm transition-all duration-300 hover:shadow-md sm:rounded-2xl">
      {/* Expandable header — no nested interactive controls */}
      <button
        type="button"
        onClick={() => setIsExpanded(open => !open)}
        className="flex w-full items-start gap-2 p-3 text-left transition-colors hover:bg-white/25 sm:items-center sm:gap-3 sm:p-5"
        aria-expanded={isExpanded}
      >
        <div className="min-w-0 flex-1">
          <h3 className="line-clamp-2 text-[0.9375rem] font-semibold leading-snug text-slate-800 sm:line-clamp-1 sm:text-lg sm:leading-normal">
            {run.title}
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500 sm:mt-1 sm:gap-4 sm:text-xs">
            <span className="inline-flex min-w-0 max-w-full items-center gap-1">
              <History size={13} className="shrink-0 text-blue-500" />
              <span className="truncate font-mono text-[10px] sm:text-xs">{run.displayId}</span>
            </span>
            <span className="inline-flex items-center gap-1">
              <Calendar size={13} className="shrink-0 text-purple-500" />
              <span className="whitespace-nowrap">{formattedDate}</span>
            </span>
          </div>
        </div>
        <span className="mt-0.5 shrink-0 rounded-full bg-white/60 p-1.5 text-slate-400 sm:mt-0 sm:p-2">
          {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </span>
      </button>

      {/* Actions outside the expand control — tappable, wrap cleanly on mobile */}
      {(onViewDetails || onViewTrace) && (
        <div className="flex flex-wrap items-center gap-2 border-t border-white/15 px-3 py-2.5 sm:gap-2.5 sm:px-5 sm:py-3">
          {onViewDetails && (
            <button
              type="button"
              onClick={() => onViewDetails(run.id)}
              className="inline-flex min-h-9 items-center justify-center gap-1.5 rounded-lg border border-blue-200/70 bg-blue-50/80 px-3 py-1.5 text-[11px] font-semibold text-blue-600 transition-colors hover:bg-blue-100 sm:min-h-0 sm:rounded-xl sm:text-xs"
            >
              <ExternalLink size={13} className="shrink-0" />
              Workspace
            </button>
          )}
          {onViewTrace && (
            <button
              type="button"
              onClick={() => onViewTrace(run.id)}
              className="inline-flex min-h-9 items-center justify-center gap-1.5 rounded-lg border border-purple-200/70 bg-purple-50/80 px-3 py-1.5 text-[11px] font-semibold text-purple-600 transition-colors hover:bg-purple-100 sm:min-h-0 sm:rounded-xl sm:text-xs"
            >
              <PlayCircle size={13} className="shrink-0" />
              Trace
            </button>
          )}
        </div>
      )}

      {isExpanded && (
        <div className="border-t border-white/20 bg-white/25 px-3 py-3 animate-fade-in sm:px-6 sm:py-5">
          {(hasOverview || hasUsageReport) && (
            <div className="mb-3 sm:mb-4">
              <SlidingSegment
                value={activeView}
                options={segmentOptions as string[]}
                onChange={val => setActiveView(val as 'Overview' | 'Summary' | 'Usage Report')}
                className="w-full max-w-none sm:max-w-md"
              />
            </div>
          )}
          <div className="prose prose-slate max-w-none prose-sm dark:prose-invert prose-headings:scroll-mt-4 prose-pre:text-[12px] prose-table:text-[12px] sm:prose-base sm:prose-pre:text-sm">
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
                    <table className="min-w-full border-collapse border border-slate-300 text-left" {...props} />
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
                img: ({ node: _n, src, ...props }) => {
                  if (src && !src.startsWith('http') && !src.startsWith('data:')) {
                    const imagePath = `final_results/${src}`;
                    const apiUrl = withAuthUrl(
                      `/api/archive/files/raw?runId=${encodeURIComponent(run.id)}&path=${encodeURIComponent(imagePath)}`,
                    );
                    return (
                      <img
                        src={apiUrl}
                        className="my-4 h-auto max-w-full rounded-lg border border-white/50 shadow-md sm:my-6 sm:rounded-xl sm:shadow-lg"
                        {...props}
                      />
                    );
                  }
                  return (
                    <img
                      src={src}
                      className="my-4 h-auto max-w-full rounded-lg border border-white/50 shadow-md sm:my-6 sm:rounded-xl sm:shadow-lg"
                      {...props}
                    />
                  );
                },
              }}
            >
              {activeView === 'Overview' && hasOverview
                ? run.executionOverview!
                : activeView === 'Usage Report' && hasUsageReport
                  ? run.usageReport!
                  : run.summary}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
};
