import React, { useMemo } from 'react';
import { clsx } from 'clsx';
import { AlertCircle, FileText, FolderTree, Map, Pencil, PlayCircle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useNavigation } from '../../contexts/NavigationContext';
import { extractWorkspaceImpacts } from '../../utils/workspaceImpact';
import type { WorkspaceImpactItem, WorkspaceImpactKind } from '../../utils/workspaceImpact';
import type { BridgeMessage } from '../../utils/messageHelpers';

interface WorkspaceImpactMapProps {
  messages: BridgeMessage[];
  archiveId?: string | null;
  className?: string;
}

const MAX_VISIBLE_IMPACTS = 12;

const KIND_STYLES: Record<WorkspaceImpactKind, {
  label: string;
  icon: LucideIcon;
  block: string;
  iconBox: string;
  text: string;
  chip: string;
}> = {
  read: {
    label: 'Read',
    icon: FolderTree,
    block: 'border-sky-200/70 bg-sky-50/80 hover:bg-sky-100/80',
    iconBox: 'bg-sky-100 text-sky-600',
    text: 'text-sky-800',
    chip: 'bg-sky-100 text-sky-700',
  },
  edit: {
    label: 'Edit',
    icon: Pencil,
    block: 'border-amber-200/80 bg-amber-50/85 hover:bg-amber-100/80',
    iconBox: 'bg-amber-100 text-amber-700',
    text: 'text-amber-800',
    chip: 'bg-amber-100 text-amber-700',
  },
  execute: {
    label: 'Run',
    icon: PlayCircle,
    block: 'border-emerald-200/80 bg-emerald-50/85 hover:bg-emerald-100/80',
    iconBox: 'bg-emerald-100 text-emerald-700',
    text: 'text-emerald-800',
    chip: 'bg-emerald-100 text-emerald-700',
  },
  error: {
    label: 'Error',
    icon: AlertCircle,
    block: 'border-rose-200/80 bg-rose-50/85 hover:bg-rose-100/80',
    iconBox: 'bg-rose-100 text-rose-700',
    text: 'text-rose-800',
    chip: 'bg-rose-100 text-rose-700',
  },
  reference: {
    label: 'Ref',
    icon: FileText,
    block: 'border-slate-200/80 bg-slate-50/85 hover:bg-slate-100/80',
    iconBox: 'bg-slate-100 text-slate-600',
    text: 'text-slate-700',
    chip: 'bg-slate-100 text-slate-600',
  },
};

function getBlockBasis(item: WorkspaceImpactItem, maxCount: number): string {
  if (item.count === maxCount && maxCount > 1) {
    return '44%';
  }
  if (item.count > 1) {
    return '34%';
  }
  return '28%';
}

export const WorkspaceImpactMap: React.FC<WorkspaceImpactMapProps> = ({
  messages,
  archiveId,
  className,
}) => {
  const { navigateToFile } = useNavigation();
  const impacts = useMemo(() => extractWorkspaceImpacts(messages), [messages]);
  const visibleImpacts = impacts.slice(0, MAX_VISIBLE_IMPACTS);
  const overflowCount = Math.max(0, impacts.length - visibleImpacts.length);
  const maxCount = Math.max(1, ...visibleImpacts.map((item) => item.count));

  return (
    <div className={clsx('w-full min-w-0 flex flex-col', className)}>
      <div className="glass-panel relative flex flex-1 flex-col overflow-hidden rounded-2xl border border-white/50 bg-white/60 p-4 backdrop-blur-xl">
        <div className="pointer-events-none absolute inset-x-4 top-0 h-px bg-gradient-to-r from-transparent via-white/90 to-transparent" />
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-indigo-100 text-indigo-600 shadow-sm">
              <Map className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                Workspace Impact
              </div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-2xl font-semibold leading-none text-slate-800">{impacts.length}</span>
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  {impacts.length === 1 ? 'Item' : 'Items'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {visibleImpacts.length === 0 ? (
          <div className="mt-4 flex flex-1 min-h-[11rem] items-center justify-center rounded-2xl border border-dashed border-slate-200/80 bg-white/50 px-4 text-center shadow-inner shadow-white/40">
            <div>
              <FileText className="mx-auto h-5 w-5 text-slate-300" />
              <div className="mt-2 text-sm font-semibold text-slate-500">No workspace impact yet</div>
            </div>
          </div>
        ) : (
          <>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {(['read', 'edit', 'execute', 'error'] as WorkspaceImpactKind[]).map((kind) => (
                <span
                  key={kind}
                  className={clsx('rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.12em]', KIND_STYLES[kind].chip)}
                >
                  {KIND_STYLES[kind].label}
                </span>
              ))}
            </div>

            <div className="mt-3 flex flex-1 min-h-[12rem] flex-wrap content-start gap-2 overflow-y-auto scrollbar-glass">
              {visibleImpacts.map((item) => {
                const styles = KIND_STYLES[item.kind];
                const Icon = styles.icon;

                return (
                  <button
                    key={item.path}
                    type="button"
                    onClick={() => navigateToFile(item.path, archiveId)}
                    className={clsx(
                      'group relative flex min-h-[5.25rem] min-w-[7.25rem] flex-col justify-between overflow-hidden rounded-2xl border p-3 text-left shadow-sm ring-1 ring-white/40 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-slate-200/60 focus:outline-none focus:ring-2 focus:ring-sky-300/70',
                      styles.block
                    )}
                    style={{
                      flexGrow: Math.max(1, item.count),
                      flexBasis: getBlockBasis(item, maxCount),
                    }}
                    title={`${item.lastStatus} · ${item.path}`}
                  >
                    <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-white/80" />
                    <div className="flex items-start justify-between gap-2">
                      <div className={clsx('flex h-7 w-7 shrink-0 items-center justify-center rounded-lg shadow-sm', styles.iconBox)}>
                        <Icon className="h-3.5 w-3.5" />
                      </div>
                      <div className={clsx('rounded-full px-2 py-0.5 text-[10px] font-bold shadow-sm', styles.chip)}>
                        {item.count}x
                      </div>
                    </div>

                    <div className="min-w-0">
                      <div className={clsx('truncate text-sm font-bold', styles.text)}>
                        {item.displayName}
                      </div>
                      <div className="mt-0.5 truncate text-[11px] font-medium text-slate-400">
                        {item.path}
                      </div>
                    </div>

                    <div className="mt-2 flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                      <span>{styles.label}</span>
                      {item.lastTask ? <span>T{item.lastTask}</span> : null}
                    </div>
                  </button>
                );
              })}

              {overflowCount > 0 ? (
                <div className="flex min-h-[5.25rem] min-w-[7.25rem] flex-1 items-center justify-center rounded-2xl border border-slate-200/70 bg-white/55 px-3 text-sm font-bold text-slate-500 shadow-sm">
                  +{overflowCount}
                </div>
              ) : null}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
