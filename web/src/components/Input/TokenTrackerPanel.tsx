import React from 'react';
import { Activity, Gauge, Layers3, ShieldAlert } from 'lucide-react';
import { clsx } from 'clsx';
import type { ContextUsage } from '../../hooks/useQuasarBridge';
import {
  formatTokenCount,
  formatUsagePercent,
  getContextUsageTone,
} from '../../utils/contextUsage';

interface TokenTrackerPanelProps {
  contextUsage: ContextUsage | null;
  className?: string;
}

const TONE_STYLES = {
  neutral: {
    chip: 'bg-slate-100 text-slate-600 border-slate-200',
    bar: 'from-slate-400 to-slate-500',
    glow: 'shadow-slate-200/70',
    icon: 'bg-slate-100 text-slate-600',
  },
  safe: {
    chip: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    bar: 'from-emerald-400 to-teal-500',
    glow: 'shadow-emerald-200/70',
    icon: 'bg-emerald-100 text-emerald-700',
  },
  warning: {
    chip: 'bg-amber-100 text-amber-700 border-amber-200',
    bar: 'from-amber-400 to-orange-500',
    glow: 'shadow-amber-200/80',
    icon: 'bg-amber-100 text-amber-700',
  },
  danger: {
    chip: 'bg-rose-100 text-rose-700 border-rose-200',
    bar: 'from-rose-400 to-red-500',
    glow: 'shadow-rose-200/80',
    icon: 'bg-rose-100 text-rose-700',
  },
} as const;

export const TokenTrackerPanel: React.FC<TokenTrackerPanelProps> = ({
  contextUsage,
  className,
}) => {
  const tone = getContextUsageTone(contextUsage);
  const styles = TONE_STYLES[tone];
  const fullContextProgress = Math.max(
    0,
    Math.min(contextUsage?.max_context_percent ?? 0, 100)
  );
  const thresholdMarkers = [
    { level: 'low', percent: 20 },
    { level: 'medium', percent: 40 },
    { level: 'hard', percent: 60 },
  ] as const;

  return (
    <div className={clsx('w-full min-w-0', className)}>
      <div className={clsx(
        'glass-panel relative overflow-hidden rounded-2xl border border-white/50 bg-white/60 p-4 backdrop-blur-xl',
        styles.glow
      )}>
        <div className="pointer-events-none absolute inset-x-4 top-0 h-px bg-gradient-to-r from-transparent via-white/90 to-transparent" />
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div className={clsx('mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl shadow-sm', styles.icon)}>
              <Gauge className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                Context Tokens
              </div>
              <div className="mt-1 text-2xl font-semibold leading-none text-slate-800">
                {formatUsagePercent(contextUsage?.usage_percent)}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-5">
          <div className="relative h-3 overflow-hidden rounded-full border border-white/70 bg-slate-200/70 shadow-inner">
            <div
              className={clsx('h-full rounded-full bg-gradient-to-r shadow-sm transition-all duration-500', styles.bar)}
              style={{ width: `${fullContextProgress}%` }}
            />
            {thresholdMarkers.map((marker) => {
              const isActive = contextUsage?.threshold_level === marker.level;
              return (
                <div
                  key={marker.level}
                  className="absolute inset-y-0"
                  style={{ left: `${marker.percent}%` }}
                >
                  <div
                    className={clsx(
                      'absolute top-1/2 h-4 -translate-x-1/2 -translate-y-1/2 rounded-full border transition-all duration-300',
                      isActive
                        ? 'w-1.5 border-white bg-slate-700 shadow-md shadow-slate-400/60'
                        : 'w-px border-transparent bg-white/80'
                    )}
                  />
                  {isActive ? (
                    <div className="absolute bottom-full mb-2 -translate-x-1/2">
                      <div className={clsx(
                        'rounded-full border px-2 py-0.5 text-[10px] font-semibold shadow-sm',
                        styles.chip
                      )}>
                        {marker.percent}%
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
          <div className="relative mt-2 h-4 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">
            {thresholdMarkers.map((marker) => {
              const isActive = contextUsage?.threshold_level === marker.level;
              const label = marker.level.slice(0, 1);
              return (
                <span
                  key={`${marker.level}-label`}
                  className={clsx(
                    'absolute top-0 -translate-x-1/2 transition-colors duration-300',
                    isActive ? 'text-slate-700' : 'text-slate-400'
                  )}
                  style={{ left: `${marker.percent}%` }}
                >
                  {label}
                </span>
              );
            })}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2.5 text-sm">
          <div className="rounded-2xl border border-white/60 bg-white/55 px-3 py-2.5 shadow-sm shadow-slate-200/30">
            <div className="flex items-center gap-2 text-slate-400">
              <Activity className="h-3.5 w-3.5" />
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em]">Current</span>
            </div>
            <div className="mt-1 font-semibold text-slate-700">
              {formatTokenCount(contextUsage?.input_tokens)}
            </div>
          </div>

          <div className="rounded-2xl border border-white/60 bg-white/55 px-3 py-2.5 shadow-sm shadow-slate-200/30">
            <div className="flex items-center gap-2 text-slate-400">
              <ShieldAlert className="h-3.5 w-3.5" />
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em]">Compression Limit</span>
            </div>
            <div className="mt-1 font-semibold text-slate-700">
              {formatTokenCount(contextUsage?.threshold_tokens)}
            </div>
          </div>

          <div className="rounded-2xl border border-white/60 bg-white/55 px-3 py-2.5 shadow-sm shadow-slate-200/30">
            <div className="flex items-center gap-2 text-slate-400">
              <Layers3 className="h-3.5 w-3.5" />
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em]">Model Window</span>
            </div>
            <div className="mt-1 font-semibold text-slate-700">
              {formatTokenCount(contextUsage?.max_context_tokens)}
            </div>
          </div>

          <div className="rounded-2xl border border-white/60 bg-white/55 px-3 py-2.5 shadow-sm shadow-slate-200/30">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
              Remaining
            </div>
            <div className="mt-1 font-semibold text-slate-700">
              {formatTokenCount(contextUsage?.remaining_tokens)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
