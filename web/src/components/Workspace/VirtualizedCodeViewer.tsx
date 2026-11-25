import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { getLanguageFromFilename } from '../../utils/fileHelpers';

interface VirtualizedCodeViewerProps {
  content: string;
  filename: string;
  className?: string;
}

const LINE_HEIGHT = 20;
const BUFFER_LINES = 50; // Lines to render above/below viewport
const HIGHLIGHT_THRESHOLD = 200000; // Skip highlighting above 200KB

// Lightweight Prism-style token highlighting via regex
// This avoids the heavy react-syntax-highlighter component entirely
const TOKEN_PATTERNS: Record<string, Array<[RegExp, string]>> = {
  python: [
    [/^(#.*)$/gm, 'comment'],
    [/("""[\s\S]*?"""|'''[\s\S]*?''')/g, 'string'],
    [/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, 'string'],
    [/\b(def|class|import|from|return|if|elif|else|for|while|try|except|finally|with|as|yield|lambda|not|and|or|is|in|pass|break|continue|raise|del|global|nonlocal|assert|async|await|True|False|None)\b/g, 'keyword'],
    [/\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/g, 'number'],
    [/\b(self|cls)\b/g, 'builtin'],
    [/(@\w+)/g, 'decorator'],
  ],
  javascript: [
    [/(\/\/.*$)/gm, 'comment'],
    [/(\/\*[\s\S]*?\*\/)/g, 'comment'],
    [/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/g, 'string'],
    [/\b(const|let|var|function|return|if|else|for|while|do|switch|case|break|continue|try|catch|finally|throw|new|delete|typeof|instanceof|in|of|class|extends|import|export|default|from|async|await|yield|true|false|null|undefined|this|super|void)\b/g, 'keyword'],
    [/\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/g, 'number'],
    [/\b(console|document|window|Array|Object|String|Number|Boolean|Promise|Map|Set|RegExp|JSON|Math)\b/g, 'builtin'],
  ],
  typescript: [
    [/(\/\/.*$)/gm, 'comment'],
    [/(\/\*[\s\S]*?\*\/)/g, 'comment'],
    [/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/g, 'string'],
    [/\b(const|let|var|function|return|if|else|for|while|do|switch|case|break|continue|try|catch|finally|throw|new|delete|typeof|instanceof|in|of|class|extends|import|export|default|from|async|await|yield|true|false|null|undefined|this|super|void|interface|type|enum|implements|namespace|abstract|declare|readonly|as|is|keyof|infer|never|unknown|any)\b/g, 'keyword'],
    [/\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/g, 'number'],
    [/\b(console|document|window|Array|Object|String|Number|Boolean|Promise|Map|Set|RegExp|JSON|Math|React)\b/g, 'builtin'],
  ],
  json: [
    [/("(?:[^"\\]|\\.)*")(\s*:)/g, 'attr-name'],
    [/("(?:[^"\\]|\\.)*")/g, 'string'],
    [/\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/g, 'number'],
    [/\b(true|false|null)\b/g, 'keyword'],
  ],
  yaml: [
    [/(#.*)$/gm, 'comment'],
    [/^(\s*[\w.-]+)(\s*:)/gm, 'attr-name'],
    [/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, 'string'],
    [/\b(true|false|null|yes|no|on|off)\b/gi, 'keyword'],
    [/\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/g, 'number'],
  ],
  bash: [
    [/(#.*)$/gm, 'comment'],
    [/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, 'string'],
    [/\b(if|then|else|elif|fi|for|while|do|done|case|esac|function|return|in|select|until|local|export|source|alias|unalias|cd|echo|exit|set|unset|readonly|shift|eval|exec|trap|wait)\b/g, 'keyword'],
    [/(\$\{?\w+\}?)/g, 'builtin'],
  ],
  html: [
    [/(<!--[\s\S]*?-->)/g, 'comment'],
    [/(<\/?[\w-]+)/g, 'keyword'],
    [/(\/?>)/g, 'keyword'],
    [/(\w+)(\s*=)/g, 'attr-name'],
    [/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, 'string'],
  ],
  css: [
    [/(\/\*[\s\S]*?\*\/)/g, 'comment'],
    [/([.#][\w-]+)/g, 'selector'],
    [/([\w-]+)(\s*:)/g, 'attr-name'],
    [/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, 'string'],
    [/\b(\d+\.?\d*(?:px|em|rem|%|vh|vw|s|ms)?)\b/g, 'number'],
    [/\b(inherit|initial|unset|none|auto|flex|grid|block|inline|relative|absolute|fixed|sticky)\b/g, 'keyword'],
  ],
  sql: [
    [/(--.*$)/gm, 'comment'],
    [/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, 'string'],
    [/\b(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TABLE|INDEX|VIEW|JOIN|LEFT|RIGHT|INNER|OUTER|ON|AND|OR|NOT|IN|IS|NULL|AS|ORDER|BY|GROUP|HAVING|LIMIT|OFFSET|UNION|ALL|DISTINCT|INTO|VALUES|SET|BEGIN|COMMIT|ROLLBACK|TRANSACTION|PRIMARY|KEY|FOREIGN|REFERENCES|CONSTRAINT|DEFAULT|CHECK|UNIQUE|CASCADE|EXISTS|BETWEEN|LIKE|COUNT|SUM|AVG|MIN|MAX)\b/gi, 'keyword'],
    [/\b(\d+\.?\d*)\b/g, 'number'],
  ],
};

// Map fileHelpers language identifiers to our token patterns
const LANG_ALIAS: Record<string, string> = {
  'javascript': 'javascript',
  'typescript': 'typescript',
  'python': 'python',
  'json': 'json',
  'yaml': 'yaml',
  'bash': 'bash',
  'html': 'html',
  'css': 'css',
  'sql': 'sql',
  'text': '',
  'markdown': '',
  'xml': 'html',
  'dockerfile': 'bash',
};

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function highlightLine(line: string, lang: string): string {
  const escaped = escapeHtml(line);
  const patterns = TOKEN_PATTERNS[lang];
  if (!patterns) return escaped;

  // Track which character positions are already highlighted
  const chars = escaped.split('');
  const tagged = new Array(chars.length).fill(false);
  const result: Array<{ start: number; end: number; cls: string }> = [];

  for (const [pattern, cls] of patterns) {
    // Reset regex lastIndex
    const re = new RegExp(pattern.source, pattern.flags);
    let match;
    while ((match = re.exec(escaped)) !== null) {
      const start = match.index;
      const end = start + match[0].length;
      // Check if any part of this match overlaps with an existing highlight
      let overlaps = false;
      for (let i = start; i < end; i++) {
        if (tagged[i]) { overlaps = true; break; }
      }
      if (!overlaps) {
        result.push({ start, end, cls });
        for (let i = start; i < end; i++) tagged[i] = true;
      }
      if (!pattern.global) break;
    }
  }

  if (result.length === 0) return escaped;

  // Sort by start position and build output
  result.sort((a, b) => a.start - b.start);
  let output = '';
  let pos = 0;
  for (const { start, end, cls } of result) {
    if (start > pos) output += escaped.substring(pos, start);
    output += `<span class="tok-${cls}">${escaped.substring(start, end)}</span>`;
    pos = end;
  }
  if (pos < escaped.length) output += escaped.substring(pos);
  return output;
}

export const VirtualizedCodeViewer: React.FC<VirtualizedCodeViewerProps> = React.memo(({ content, filename, className = '' }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [containerHeight, setContainerHeight] = useState(600);

  const lang = useMemo(() => {
    const langId = getLanguageFromFilename(filename);
    return LANG_ALIAS[langId] || '';
  }, [filename]);

  const lines = useMemo(() => content.split('\n'), [content]);
  const totalLines = lines.length;
  const totalHeight = totalLines * LINE_HEIGHT;

  const shouldHighlight = content.length < HIGHLIGHT_THRESHOLD && lang !== '';

  // Highlight all lines in one pass (memoized)
  const highlightedLines = useMemo(() => {
    if (!shouldHighlight) return null;
    return lines.map(line => highlightLine(line, lang));
  }, [lines, shouldHighlight, lang]);

  // Observe container size
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver(entries => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height);
      }
    });
    obs.observe(el);
    setContainerHeight(el.clientHeight);
    return () => obs.disconnect();
  }, []);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, []);

  // Calculate visible range
  const startLine = Math.max(0, Math.floor(scrollTop / LINE_HEIGHT) - BUFFER_LINES);
  const visibleCount = Math.ceil(containerHeight / LINE_HEIGHT) + 2 * BUFFER_LINES;
  const endLine = Math.min(totalLines, startLine + visibleCount);

  const gutterWidth = Math.max(3, String(totalLines).length);

  // Build visible lines
  const visibleLines = useMemo(() => {
    const items: string[] = [];
    for (let i = startLine; i < endLine; i++) {
      const lineNum = `<span class="code-gutter">${String(i + 1).padStart(gutterWidth)}</span>`;
      const lineContent = highlightedLines
        ? highlightedLines[i]
        : escapeHtml(lines[i]);
      items.push(`<div class="code-line" style="position:absolute;top:${i * LINE_HEIGHT}px;height:${LINE_HEIGHT}px;line-height:${LINE_HEIGHT}px;white-space:pre;width:100%">${lineNum}${lineContent}</div>`);
    }
    return items.join('');
  }, [startLine, endLine, highlightedLines, lines, gutterWidth]);

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className={`virtualized-code-viewer ${className}`}
      style={{
        overflow: 'auto',
        height: '100%',
        width: '100%',
        position: 'relative',
        fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
        fontSize: '13px',
      }}
    >
      <div
        style={{
          height: totalHeight,
          position: 'relative',
          minWidth: 'fit-content',
        }}
        dangerouslySetInnerHTML={{ __html: visibleLines }}
      />
      <style>{`
        .virtualized-code-viewer .code-gutter {
          display: inline-block;
          min-width: ${gutterWidth + 1}ch;
          padding-right: 1.5ch;
          text-align: right;
          color: #94a3b8;
          user-select: none;
          pointer-events: none;
        }
        .virtualized-code-viewer .code-line {
          padding-left: 0.5ch;
          padding-right: 2ch;
          box-sizing: border-box;
        }
        .virtualized-code-viewer .code-line:hover {
          background: rgba(59, 130, 246, 0.06);
        }
        /* Token colors - inspired by One Light / Prism light theme */
        .virtualized-code-viewer .tok-keyword { color: #a626a4; font-weight: 500; }
        .virtualized-code-viewer .tok-string { color: #50a14f; }
        .virtualized-code-viewer .tok-comment { color: #a0a1a7; font-style: italic; }
        .virtualized-code-viewer .tok-number { color: #986801; }
        .virtualized-code-viewer .tok-builtin { color: #c18401; }
        .virtualized-code-viewer .tok-decorator { color: #4078f2; }
        .virtualized-code-viewer .tok-attr-name { color: #e45649; }
        .virtualized-code-viewer .tok-selector { color: #e45649; }
      `}</style>
    </div>
  );
});

VirtualizedCodeViewer.displayName = 'VirtualizedCodeViewer';
