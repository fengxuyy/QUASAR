import { Archive, Loader2 } from 'lucide-react';

interface CleanupOverlayProps {
  isVisible: boolean;
}

/**
 * Full-screen overlay displayed when the system is archiving workspace files
 * after a run completes. Blocks all user interaction during cleanup.
 */
export function CleanupOverlay({ isVisible }: CleanupOverlayProps) {
  if (!isVisible) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="glass-panel px-8 py-6 rounded-2xl shadow-2xl border border-white/40 flex flex-col items-center gap-4 min-w-[280px]">
        {/* Icon and Title */}
        <div className="flex items-center gap-3">
          <Archive className="w-6 h-6 text-indigo-500" />
          <span className="text-lg font-semibold text-slate-700">Archiving Run</span>
        </div>
        
        {/* Animated Progress Bar */}
        <div className="w-full h-2 bg-slate-200/50 rounded-full overflow-hidden">
          <div 
            className="h-full bg-gradient-to-r from-indigo-500 via-purple-500 to-indigo-500 rounded-full animate-pulse"
            style={{
              animation: 'shimmer 1.5s ease-in-out infinite, pulse 2s ease-in-out infinite',
              backgroundSize: '200% 100%',
            }}
          />
        </div>
        
        {/* Subtitle */}
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Copying files to archive</span>
        </div>
      </div>
      
      {/* CSS Animation for shimmer effect */}
      <style>{`
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
    </div>
  );
}
