import React, { useState, useMemo } from 'react';
import { clsx } from 'clsx';
import { CheckCircle2, AlertCircle, ChevronDown, ChevronUp, Terminal, FileText, Folder, FolderOpen, ListTodo, ArrowRight, MessageSquare } from 'lucide-react';
import { MarkdownRenderer } from '../../UI/MarkdownRenderer';
import { agentSubPanelThemes } from './constants';
import { parseStatusWithFileLinks, type StatusSegment } from '../../../utils/fileLinkUtils';
import { useNavigation } from '../../../contexts/NavigationContext';
import { isPlanStatus, normalizePlanStatus, parseTasksFromPlanText } from '../../../utils/planHelpers';

const MARKDOWN_OUTPUT_RENDER_LIMIT = 80000;

// Custom diff renderer for edit_file output - GitHub-style colored diff
const DiffRenderer: React.FC<{ content: string }> = ({ content }) => {
  // Extract content from ```diff ... ``` if present
  const diffMatch = content.match(/```diff\n([\s\S]*?)\n```/);
  const diffContent = diffMatch ? diffMatch[1] : content;
  
  const lines = diffContent.split('\n');
  
  return (
    <div className="font-mono text-xs rounded-lg overflow-hidden border border-slate-200">
      {lines.map((line, idx) => {
        const isAdded = line.startsWith('+');
        const isRemoved = line.startsWith('-');
        
        return (
          <div 
            key={idx} 
            className={clsx(
              "px-3 py-0.5 border-l-4",
              isAdded && "bg-green-50 border-green-400 text-green-800",
              isRemoved && "bg-red-50 border-red-400 text-red-800",
              !isAdded && !isRemoved && "bg-slate-50 border-slate-200 text-slate-600"
            )}
          >
            <span className={clsx(
              "inline-block w-4 mr-2 text-center font-bold",
              isAdded && "text-green-600",
              isRemoved && "text-red-600"
            )}>
              {isAdded ? '+' : isRemoved ? '−' : ' '}
            </span>
            <span>{isAdded || isRemoved ? line.slice(2) : line}</span>
          </div>
        );
      })}
    </div>
  );
};

interface ParsedPathItem {
  path: string;
  suffix?: string;
}

function parseBulletPathList(content?: string): ParsedPathItem[] | null {
  if (!content) return null;
  const lines = content
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return null;

  const items: ParsedPathItem[] = [];
  for (const line of lines) {
    const match = line.match(/^-\s+`([^`]+)`(?:\s+(.*))?$/);
    if (!match) return null;
    items.push({
      path: match[1],
      suffix: match[2]?.trim() || undefined,
    });
  }
  return items;
}

const MultiPathListRenderer: React.FC<{
  items: ParsedPathItem[];
  kind: 'files' | 'directories';
  archiveId?: string | null;
}> = ({ items, kind, archiveId }) => {
  const { navigateToFile } = useNavigation();

  return (
    <ul className="space-y-1 text-xs">
      {items.map((item, idx) => (
        <li key={`${item.path}-${idx}`} className="flex items-center gap-2 text-slate-700">
          {kind === 'directories' ? (
            <Folder size={13} className="shrink-0 text-amber-500" />
          ) : (
            <FileText size={13} className="shrink-0 text-sky-500" />
          )}
          {kind === 'files' ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                navigateToFile(item.path, archiveId);
              }}
              className="truncate font-mono text-left text-sky-700 underline decoration-sky-400/70 underline-offset-2 transition-colors hover:text-sky-900"
              title={`View ${item.path} in Workspace`}
            >
              {item.path}
            </button>
          ) : (
            <span className="truncate font-mono text-slate-700">{item.path}</span>
          )}
          {item.suffix ? (
            <span className="shrink-0 text-slate-400">{item.suffix}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
};

interface StepCompleteEntryProps {
  status: string;
  output?: string;
  hasOutput: boolean;
  isError?: boolean;
  colorClass: string;
  agentName?: string;
  outputType?: 'code' | 'markdown' | 'text';
  archiveId?: string | null;
  /** Shown above collapsible plan/output (e.g. plan revision user request). */
  userFeedback?: string;
  /** Overrides the small caps label above the collapsible body (default: Code Output / Result Content). */
  outputSectionLabel?: string;
}

// Component to render status with clickable file links
const StatusWithFileLinks: React.FC<{ 
  segments: StatusSegment[]; 
  className?: string;
  isError?: boolean;
  archiveId?: string | null;
}> = ({ segments, className, isError, archiveId }) => {
  const { navigateToFile } = useNavigation();
  
  return (
    <span className={className}>
      {segments.map((segment, idx) => {
        if (segment.type === 'file' && segment.filePath) {
          return (
            <button
              key={idx}
              onClick={(e) => {
                e.stopPropagation();
                navigateToFile(segment.filePath!, archiveId);
              }}
              className={clsx(
                "italic transition-colors cursor-pointer px-0.5 font-bold underline underline-offset-2 decoration-sky-400/80",
                "text-sky-700 hover:text-sky-800"
              )}
              title={`View ${segment.filePath} in Workspace`}
            >
              {segment.content}
            </button>
          );
        }
        if (segment.type === 'italic') {
          return (
            <span
              key={idx}
              className={clsx(
                "italic px-0.5",
                isError ? "text-red-900 font-bold" : "text-green-800 font-bold"
              )}
            >
              {segment.content}
            </span>
          );
        }
        return <span key={idx}>{segment.content}</span>;
      })}
    </span>
  );
};

export const StepCompleteEntry: React.FC<StepCompleteEntryProps> = ({ 
  status, output, hasOutput, isError, colorClass, agentName = 'unknown', outputType = 'text', archiveId,
  userFeedback,
  outputSectionLabel,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const normalizedStatus = normalizePlanStatus(status);
  
  // Detect direct code execution (not allowed) - status contains -c flag
  // This indicates code was passed directly instead of executing a file
  const isDirectCodeExecution = status.includes('-c') || (status.toLowerCase().startsWith('executed') && status.includes('"') && !status.includes('.py') && !status.includes('.sh'));
  
  // Override isError if this is direct code execution
  const effectiveIsError = isError || isDirectCodeExecution;
  
  // Check if this is a plan entry (initial, reviewed, or replan)
  const isPlanEntry = isPlanStatus(status);
  
  // Parse tasks from output for plan entries
  const parsedTasks = useMemo(() => {
    if (isPlanEntry && output) {
      return parseTasksFromPlanText(output);
    }
    return [];
  }, [isPlanEntry, output]);
  
  // Detect output type from status if not explicitly provided
  const parsedPathItems = useMemo(() => {
    const statusLower = normalizedStatus.toLowerCase();
    if (!statusLower.startsWith('listed ') && !statusLower.startsWith('read ')) {
      return null;
    }
    return parseBulletPathList(output);
  }, [normalizedStatus, output]);

  const pathListKind: 'files' | 'directories' | null = useMemo(() => {
    if (!parsedPathItems) return null;
    const statusLower = normalizedStatus.toLowerCase();
    if (statusLower.startsWith('listed ')) return 'directories';
    if (statusLower.startsWith('read ')) return 'files';
    return null;
  }, [normalizedStatus, parsedPathItems]);

  const detectOutputType = (): 'code' | 'markdown' | 'text' | 'diff' | 'paths' => {
    if (pathListKind && parsedPathItems) return 'paths';
    if (outputType !== 'text') return outputType;
    const statusLower = normalizedStatus.toLowerCase();
    if (statusLower.startsWith('edited')) return 'diff';
    if (isPlanEntry || statusLower.startsWith('executed') || statusLower.startsWith('analyzed') || statusLower.includes('evaluation')) return 'markdown';
    return 'text';
  };
  
  const detectedType = detectOutputType();
  const subTheme = agentSubPanelThemes[agentName] || agentSubPanelThemes.unknown;

  // Render output based on type
  const renderOutput = () => {
    if (!output) return null;
    const shouldRenderPlain = output.length > MARKDOWN_OUTPUT_RENDER_LIMIT && !isPlanEntry && detectedType !== 'diff';

    if (shouldRenderPlain) {
      return (
        <pre className="whitespace-pre-wrap break-words font-mono text-xs text-slate-700">
          {output}
        </pre>
      );
    }
    
    // Special rendering for plan entries (initial or reviewed) with parsed tasks
    if (isPlanEntry && parsedTasks.length > 0) {
      return (
        <div className="space-y-2 bg-purple-50/50 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <ListTodo size={14} className="text-purple-500" />
            <span className="text-sm font-medium text-purple-700">Tasks:</span>
          </div>
          {parsedTasks.map((task: string, idx: number) => (
            <div key={idx} className="flex items-start gap-2">
              <ArrowRight size={14} className="text-purple-400 mt-1 flex-shrink-0" />
              <div className="text-sm text-slate-700 flex-1">
                <MarkdownRenderer content={task} />
              </div>
            </div>
          ))}
        </div>
      );
    }
    
    if (detectedType === 'paths' && parsedPathItems && pathListKind) {
      return (
        <MultiPathListRenderer
          items={parsedPathItems}
          kind={pathListKind}
          archiveId={archiveId}
        />
      );
    }

    if (detectedType === 'diff') {
      return <DiffRenderer content={output} />;
    }
    
    if (detectedType === 'code') {
      const codeMarkdown = '```python\n' + output + '\n```';
      return (
        <div className="rounded-lg">
          <MarkdownRenderer content={codeMarkdown} />
        </div>
      );
    }
    
    if (detectedType === 'markdown' || detectedType === 'text') {
      return (
        <div className={clsx(
          "prose prose-sm prose-slate max-w-none",
          effectiveIsError && "prose-red"
        )}>
          <MarkdownRenderer content={output} />
        </div>
      );
    }
    
    return null;
  };
  
  return (
    <div className="border-b border-white/10 bg-slate-50/30">
      <div 
        className={clsx(
          "flex items-center gap-3 py-2 px-4",
          hasOutput && "cursor-pointer hover:bg-slate-100/50 transition-colors"
        )}
        onClick={() => hasOutput && setIsExpanded(!isExpanded)}
      >
        <div className={`w-6 h-6 rounded-lg bg-gradient-to-br ${effectiveIsError ? 'from-red-500 to-red-600' : colorClass} flex items-center justify-center flex-shrink-0`}>
          {effectiveIsError ? <AlertCircle size={14} className="text-white" /> : <CheckCircle2 size={14} className="text-white" />}
        </div>
        <div className="flex-1 flex items-center gap-2 min-w-0">
          <StatusWithFileLinks 
            segments={parseStatusWithFileLinks(normalizedStatus)}
            className={clsx(
              "text-sm font-bold",
              effectiveIsError ? "text-red-500" : "text-green-600"
            )}
            isError={effectiveIsError}
            archiveId={archiveId}
          />
        </div>
        {hasOutput && (
          <button className="text-slate-400 hover:text-slate-600 transition-colors">
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        )}
      </div>
      {hasOutput && isExpanded && (
        <div className="px-4 pb-3">
          {userFeedback ? (
            <div
              className={clsx(
                'ml-11 mb-3 min-w-0 max-w-full rounded-lg border p-3',
                subTheme.bg,
                subTheme.border
              )}
            >
              <div className="flex items-center gap-2 mb-2">
                <MessageSquare size={14} className={subTheme.icon} strokeWidth={2} />
                <span className={clsx('text-xs font-bold uppercase tracking-wider', subTheme.text)}>
                  User request
                </span>
              </div>
              <p className="text-sm text-slate-700 whitespace-pre-wrap break-words leading-relaxed">
                {userFeedback}
              </p>
            </div>
          ) : null}
          {/* For plan entries, render without the extra wrapper since renderOutput provides its own styling */}
          {isPlanEntry && parsedTasks.length > 0 ? (
            <div className="ml-11">
              {renderOutput()}
            </div>
          ) : (
            <div className={clsx(
              "ml-11 min-w-0 max-w-full overflow-x-hidden space-y-2 rounded-lg p-3 border",
              effectiveIsError ? "bg-red-50/50 border-red-100" : `${subTheme.bg} ${subTheme.border}`
            )}>
              <div className="flex items-center gap-2 mb-1">
                {detectedType === 'code' ? (
                  <Terminal size={14} className={effectiveIsError ? "text-red-500" : subTheme.icon} />
                ) : pathListKind === 'directories' ? (
                  <FolderOpen size={14} className={effectiveIsError ? "text-red-500" : subTheme.icon} />
                ) : (
                  <FileText size={14} className={effectiveIsError ? "text-red-500" : subTheme.icon} />
                )}
                <span className={clsx(
                  "text-xs font-bold uppercase tracking-wider",
                  effectiveIsError ? "text-red-700" : subTheme.text
                )}>
                  {outputSectionLabel ||
                    (detectedType === 'code'
                      ? 'Code Output'
                      : pathListKind === 'directories'
                        ? 'Directories'
                        : pathListKind === 'files'
                          ? 'Files'
                          : 'Result Content')}
                </span>
              </div>
              {renderOutput()}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
