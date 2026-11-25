import React, { useState } from 'react';
import { Globe, Code, Maximize2, Minimize2 } from 'lucide-react';

interface HtmlViewerProps {
  content: string;
  fileName?: string;
  fileUrl?: string;
}

export const HtmlViewer: React.FC<HtmlViewerProps> = ({ content, fileName, fileUrl }) => {
  const [viewMode, setViewMode] = useState<'preview' | 'source'>('preview');
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Create a blob URL for the HTML content to render in iframe
  const blobUrl = React.useMemo(() => {
    // If we have a direct file URL, use that
    if (fileUrl) return fileUrl;
    
    // Otherwise create a blob from content
    const blob = new Blob([content], { type: 'text/html' });
    return URL.createObjectURL(blob);
  }, [content, fileUrl]);

  // Cleanup blob URL on unmount
  React.useEffect(() => {
    return () => {
      if (!fileUrl && blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  }, [blobUrl, fileUrl]);

  if (isFullscreen) {
    return (
      <div className="fixed inset-0 z-50 bg-white">
        {/* Fullscreen Header */}
        <div className="flex items-center justify-between p-3 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center gap-2">
            <Globe size={18} className="text-blue-500" />
            <span className="font-medium text-slate-700">{fileName || 'HTML Document'}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center bg-white rounded-lg p-0.5 shadow-sm border border-slate-200">
              <button
                onClick={() => setViewMode('preview')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                  viewMode === 'preview'
                    ? 'bg-blue-500 text-white shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                <Globe size={14} />
                Preview
              </button>
              <button
                onClick={() => setViewMode('source')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                  viewMode === 'source'
                    ? 'bg-blue-500 text-white shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                <Code size={14} />
                Source
              </button>
            </div>
            <button
              onClick={() => setIsFullscreen(false)}
              className="p-2 rounded-lg hover:bg-slate-200 transition-colors text-slate-600"
              title="Exit Fullscreen"
            >
              <Minimize2 size={18} />
            </button>
          </div>
        </div>
        
        {/* Content */}
        <div className="h-[calc(100vh-57px)]">
          {viewMode === 'preview' ? (
            <iframe
              src={blobUrl}
              className="w-full h-full border-0"
              title={fileName || 'HTML Preview'}
              sandbox="allow-scripts allow-same-origin"
            />
          ) : (
            <pre className="w-full h-full overflow-auto scrollbar-glass p-4 bg-slate-900 text-slate-100 font-mono text-sm">
              {content}
            </pre>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full font-sans">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Globe size={20} className="text-blue-500" />
          <span className="font-medium text-slate-700">
            {fileName || 'HTML Document'}
          </span>
        </div>
        
        <div className="flex items-center gap-2">
          {/* View Mode Toggle */}
          <div className="flex items-center bg-slate-100 rounded-lg p-0.5">
            <button
              onClick={() => setViewMode('preview')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                viewMode === 'preview'
                  ? 'bg-white text-blue-600 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              <Globe size={14} />
              Preview
            </button>
            <button
              onClick={() => setViewMode('source')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                viewMode === 'source'
                  ? 'bg-white text-blue-600 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              <Code size={14} />
              Source
            </button>
          </div>
          
          {/* Fullscreen Button */}
          <button
            onClick={() => setIsFullscreen(true)}
            className="p-2 rounded-lg hover:bg-slate-100 transition-colors text-slate-500"
            title="Fullscreen"
          >
            <Maximize2 size={18} />
          </button>
        </div>
      </div>
      
      {/* Content */}
      <div className="flex-1 overflow-hidden border border-slate-200 rounded-2xl bg-white shadow-inner">
        {viewMode === 'preview' ? (
          <iframe
            src={blobUrl}
            className="w-full h-full border-0 rounded-2xl"
            title={fileName || 'HTML Preview'}
            sandbox="allow-scripts allow-same-origin"
          />
        ) : (
          <pre className="w-full h-full overflow-auto scrollbar-glass p-4 bg-slate-900 text-slate-100 font-mono text-sm rounded-2xl">
            {content}
          </pre>
        )}
      </div>
    </div>
  );
};
