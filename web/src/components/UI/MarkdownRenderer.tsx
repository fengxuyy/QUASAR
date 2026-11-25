import React, { type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { withAuthUrl } from '../../utils/apiAuth';

interface MarkdownRendererProps {
  content: string;
  className?: string;
  basePath?: string;
  resolveImageUrl?: (src: string, basePath?: string) => string;
}

interface ComponentProps {
  children?: ReactNode;
  className?: string;
  href?: string;
}

const CodeBlock = ({ content }: { content: string }) => (
  <pre className="my-2 max-w-full overflow-x-auto rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm scrollbar-glass">
    <code>{content.replace(/\n$/, '')}</code>
  </pre>
);

export const MarkdownRenderer = React.memo<MarkdownRendererProps>(({ content, className = '', basePath, resolveImageUrl }) => {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      className={`markdown-content min-w-0 max-w-full break-words ${className}`}
      components={{
        // Style code blocks
        code: ({ className, children, node }: any) => {
          const match = /language-(\w+)/.exec(className || '');
          const content = Array.isArray(children) ? children.join('') : String(children);
          
          // Improved detection: if it has a language match or contains newlines, 
          // it should be a code block, not inline.
          const isInline = !match && !content.includes('\n') && node?.parent?.tagName !== 'pre';
          
          if (isInline) {
            return (
              <code className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-sm font-mono">
                {children}
              </code>
            );
          }
          
          return <CodeBlock content={content} />;
        },
        // Style pre for code blocks - handled by SyntaxHighlighter now
        pre: ({ children }: ComponentProps) => (
          <div className="my-2 max-w-full overflow-x-auto rounded-lg scrollbar-glass">
            {children}
          </div>
        ),
        // Style paragraphs
        p: ({ children }: ComponentProps) => (
          <p className="mb-2 last:mb-0">{children}</p>
        ),
        // Style headers
        h1: ({ children }: ComponentProps) => (
          <h1 className="text-xl font-bold text-slate-800 mb-2">{children}</h1>
        ),
        h2: ({ children }: ComponentProps) => (
          <h2 className="text-lg font-semibold text-slate-800 mb-2">{children}</h2>
        ),
        h3: ({ children }: ComponentProps) => (
          <h3 className="text-base font-semibold text-slate-800 mb-1">{children}</h3>
        ),
        // Style lists
        ul: ({ children }: ComponentProps) => (
          <ul className="list-disc list-inside mb-2 space-y-1">{children}</ul>
        ),
        ol: ({ children }: ComponentProps) => (
          <ol className="list-decimal list-inside mb-2 space-y-1">{children}</ol>
        ),
        li: ({ children }: ComponentProps) => (
          <li className="text-slate-700">{children}</li>
        ),
        // Style links
        a: ({ children, href }: ComponentProps) => (
          <a 
            href={href} 
            className="break-all text-blue-500 underline hover:text-blue-600"
            target="_blank"
            rel="noopener noreferrer"
          >
            {children}
          </a>
        ),
        // Style blockquotes
        blockquote: ({ children }: ComponentProps) => (
          <blockquote className="border-l-4 border-purple-300 pl-4 py-1 my-2 text-slate-600 italic">
            {children}
          </blockquote>
        ),
        // Style images
        img: ({ src, alt, ...props }: any) => {
          let finalSrc = src;
          if (src && !src.startsWith('http://') && !src.startsWith('https://') && !src.startsWith('data:')) {
            if (resolveImageUrl) {
              finalSrc = resolveImageUrl(src, basePath);
            } else if (basePath) {
              const parts = basePath.split('/');
              parts.pop();
              const dir = parts.join('/');
              const cleanSrc = src.replace(/^\.\//, '');
              const relativePath = dir ? `${dir}/${cleanSrc}` : cleanSrc;
              finalSrc = withAuthUrl(`/api/files/raw?path=${encodeURIComponent(relativePath)}`);
            }
          }
          if (typeof finalSrc === 'string') {
            finalSrc = withAuthUrl(finalSrc);
          }
          return (
            <img 
              src={finalSrc} 
              alt={alt} 
              className="max-w-full h-auto rounded-lg my-4" 
              {...props} 
            />
          );
        },
        // Style tables
        table: ({ children }: ComponentProps) => (
          <div className="overflow-x-auto scrollbar-glass my-2">
            <table className="min-w-full border-collapse">
              {children}
            </table>
          </div>
        ),
        th: ({ children }: ComponentProps) => (
          <th className="border border-slate-300 bg-slate-100 px-3 py-1 text-left font-semibold text-slate-700">
            {children}
          </th>
        ),
        td: ({ children }: ComponentProps) => (
          <td className="border border-slate-200 px-3 py-1 text-slate-600">
            {children}
          </td>
        ),
        // Style horizontal rules
        hr: () => (
          <hr className="my-4 border-slate-200" />
        ),
        // Style strong/bold
        strong: ({ children }: ComponentProps) => (
          <strong className="font-semibold text-slate-800">{children}</strong>
        ),
        // Style emphasis/italic
        em: ({ children }: ComponentProps) => (
          <em className="italic text-slate-700">{children}</em>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
});

MarkdownRenderer.displayName = 'MarkdownRenderer';
