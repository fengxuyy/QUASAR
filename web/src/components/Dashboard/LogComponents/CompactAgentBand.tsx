import React from 'react';
import { clsx } from 'clsx';
import { agentConfig } from './constants';
import type { AgentType } from './constants';

interface CompactAgentBandProps {
  activeAgent?: AgentType | null;
  selectedAgent?: AgentType | null;
  onAgentSelect?: (agent: AgentType | null) => void;
  /** Optional trailing control (e.g. Terminate) integrated into the band on mobile. */
  endSlot?: React.ReactNode;
}

const AGENT_THEME: Record<
  AgentType,
  {
    ring: string;
    ringSoft: string;
    glow: string;
    wash: string;
    washSelected: string;
    accent: string;
    label: string;
    pulse: string;
  }
> = {
  strategist: {
    ring: 'from-violet-400 via-indigo-400 to-fuchsia-400',
    ringSoft: 'from-violet-200/80 via-indigo-100 to-white',
    glow: 'shadow-[0_8px_22px_-8px_rgba(139,92,246,0.55)]',
    wash: 'from-violet-50/70 via-white/40 to-transparent',
    washSelected: 'from-violet-100/90 via-indigo-50/70 to-white/50',
    accent: 'bg-violet-500',
    label: 'text-violet-700',
    pulse: 'bg-violet-400',
  },
  operator: {
    ring: 'from-sky-400 via-blue-500 to-cyan-400',
    ringSoft: 'from-sky-200/80 via-blue-100 to-white',
    glow: 'shadow-[0_8px_22px_-8px_rgba(59,130,246,0.5)]',
    wash: 'from-sky-50/70 via-white/40 to-transparent',
    washSelected: 'from-sky-100/90 via-blue-50/70 to-white/50',
    accent: 'bg-blue-500',
    label: 'text-blue-700',
    pulse: 'bg-sky-400',
  },
  evaluator: {
    ring: 'from-emerald-400 via-teal-500 to-cyan-400',
    ringSoft: 'from-emerald-200/80 via-teal-100 to-white',
    glow: 'shadow-[0_8px_22px_-8px_rgba(16,185,129,0.5)]',
    wash: 'from-emerald-50/70 via-white/40 to-transparent',
    washSelected: 'from-emerald-100/90 via-teal-50/70 to-white/50',
    accent: 'bg-emerald-500',
    label: 'text-emerald-700',
    pulse: 'bg-emerald-400',
  },
};

export const CompactAgentBand: React.FC<CompactAgentBandProps> = ({
  activeAgent,
  selectedAgent,
  onAgentSelect,
  endSlot,
}) => {
  const handleAgentClick = (agent: AgentType) => {
    if (onAgentSelect) {
      onAgentSelect(selectedAgent === agent ? null : agent);
    }
  };

  return (
    <div className="relative border-b border-white/30 bg-gradient-to-b from-white/50 to-white/20 backdrop-blur-sm">
      <div className="pointer-events-none absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-white/90 to-transparent" />

      <div className={clsx('flex items-stretch', endSlot && 'max-lg:pr-0')}>
        <div className="grid min-w-0 flex-1 grid-cols-3">
          {agentConfig.map(({ id, name, role, logo }, index) => {
            const isActive = activeAgent === id;
            const isSelected = selectedAgent === id;
            const isFirst = index === 0;
            const isLast = index === agentConfig.length - 1;
            const theme = AGENT_THEME[id];
            const isLit = isActive || isSelected;

            return (
              <button
                key={id}
                type="button"
                onClick={() => handleAgentClick(id)}
                aria-pressed={isSelected}
                aria-label={`${name} — ${role}${isActive ? ', active' : ''}${isSelected ? ', filtering log' : ''}`}
                className={clsx(
                  'group relative flex min-w-0 flex-col items-center justify-center overflow-hidden px-1.5 py-2 transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] sm:items-stretch sm:px-3 sm:py-2.5',
                  !isLast && 'border-r border-white/25',
                  isFirst && 'rounded-tl-2xl',
                  isLast && !endSlot && 'rounded-tr-2xl',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300/70 focus-visible:ring-inset',
                  !isLit && 'hover:bg-white/35',
                )}
              >
                {/* Ambient wash */}
                <div
                  className={clsx(
                    'pointer-events-none absolute inset-0 bg-gradient-to-br opacity-0 transition-opacity duration-500',
                    theme.wash,
                    isActive && !isSelected && 'opacity-100',
                    isSelected && theme.washSelected,
                    isSelected && 'opacity-100',
                    !isLit && 'group-hover:opacity-60',
                  )}
                />

                {/* Selected hairline accent */}
                <div
                  className={clsx(
                    'pointer-events-none absolute inset-x-4 top-0 h-[2px] rounded-full transition-all duration-500',
                    theme.accent,
                    isSelected ? 'opacity-100 scale-x-100' : 'opacity-0 scale-x-50',
                  )}
                />

                <div className="relative z-10 flex w-full min-w-0 items-center justify-center gap-1.5 sm:justify-start sm:gap-2.5">
                  {/* Portrait with gradient ring — compact on mobile */}
                  <div className="relative shrink-0">
                    <div
                      className={clsx(
                        'rounded-[0.7rem] p-px transition-all duration-500 sm:rounded-[0.8rem] sm:p-[1.5px]',
                        isLit
                          ? `bg-gradient-to-br ${theme.ring} ${theme.glow}`
                          : `bg-gradient-to-br ${theme.ringSoft}`,
                        isActive && 'scale-[1.03]',
                      )}
                    >
                      <div
                        className={clsx(
                          'relative h-6 w-6 overflow-hidden rounded-[0.62rem] bg-white sm:h-8 sm:w-8 sm:rounded-[0.7rem]',
                          'ring-1 ring-inset ring-white/70',
                        )}
                      >
                        <img
                          src={logo}
                          alt=""
                          width={64}
                          height={64}
                          draggable={false}
                          className={clsx(
                            'h-full w-full object-cover object-top transition-all duration-500',
                            isLit ? 'opacity-100 saturate-100' : 'opacity-80 saturate-75 group-hover:opacity-95 group-hover:saturate-100',
                          )}
                        />
                        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-slate-900/10 via-transparent to-white/10" />
                      </div>
                    </div>

                    {/* Live status pip */}
                    <span
                      className={clsx(
                        'absolute -bottom-0.5 -right-0.5 flex h-2 w-2 items-center justify-center rounded-full bg-white shadow-sm ring-1 ring-white transition-all duration-300 sm:h-2.5 sm:w-2.5',
                        isActive ? 'opacity-100 scale-100' : 'opacity-0 scale-75',
                      )}
                      aria-hidden
                    >
                      <span className={clsx('h-1 w-1 rounded-full sm:h-1.5 sm:w-1.5', theme.pulse, isActive && 'animate-pulse')} />
                    </span>
                  </div>

                  {/* Identity copy — role labels desktop only (no PLAN/EXEC on mobile) */}
                  <div className="min-w-0 flex-1 text-left">
                    <div
                      className={clsx(
                        'truncate text-[11px] font-semibold tracking-tight transition-colors duration-300 sm:text-[12px]',
                        isSelected ? theme.label : isActive ? 'text-slate-800' : 'text-slate-600 group-hover:text-slate-800',
                      )}
                    >
                      {name}
                    </div>
                    <div
                      className={clsx(
                        'mt-0.5 hidden truncate text-[10px] font-medium uppercase tracking-[0.16em] transition-colors duration-300 sm:block',
                        isSelected ? 'text-slate-500' : 'text-slate-400 group-hover:text-slate-500',
                      )}
                    >
                      {role}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {endSlot && (
          <div className="flex shrink-0 items-center border-l border-white/25 bg-white/35 px-1.5 max-lg:flex lg:hidden">
            {endSlot}
          </div>
        )}
      </div>

      {selectedAgent && (
        <div className="border-t border-white/20 bg-white/40 px-3 py-1.5 text-center text-[10px] font-medium tracking-wide text-slate-500">
          Filtering ·{' '}
          <span className="font-semibold capitalize text-slate-700">{selectedAgent}</span>
          <span className="text-slate-400"> · click again to show all</span>
        </div>
      )}
    </div>
  );
};
