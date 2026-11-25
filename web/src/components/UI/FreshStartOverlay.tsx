import { RefreshCw, Trash2, Loader2 } from 'lucide-react';

interface FreshStartOverlayProps {
  isVisible: boolean;
  isClearingArchive?: boolean;
  preserveWorkspace?: boolean;
}

/**
 * Full-screen overlay displayed when starting fresh or clearing archive.
 * Blocks all user interaction during the operation.
 */
export function FreshStartOverlay({ isVisible, isClearingArchive, preserveWorkspace }: FreshStartOverlayProps) {
  if (!isVisible) return null;

  const Icon = isClearingArchive ? Trash2 : RefreshCw;
  const title = isClearingArchive
    ? 'Clearing Everything'
    : preserveWorkspace
      ? 'Clearing Checkpoint'
      : 'Starting Fresh';
  const subtitle = isClearingArchive 
    ? 'Removing workspace and archives' 
    : preserveWorkspace
      ? 'Keeping workspace files'
      : 'Cleaning workspace';
  const gradientColors = isClearingArchive 
    ? 'from-red-400 via-rose-400 to-red-400' 
    : 'from-blue-400 via-cyan-400 to-blue-400';
  const iconBgColors = isClearingArchive 
    ? 'from-red-500 to-rose-500' 
    : 'from-blue-500 to-cyan-500';

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 animate-fade-in">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />
      
      {/* Modal */}
      <div 
        className="relative w-full max-w-sm rounded-2xl overflow-hidden"
        style={{
          background: 'rgba(255, 255, 255, 0.95)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          border: '1px solid rgba(255, 255, 255, 0.5)',
          boxShadow: '0 25px 50px rgba(0, 0, 0, 0.15)'
        }}
      >
        <div className="p-6">
          {/* Icon */}
          <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${iconBgColors} flex items-center justify-center mb-4 mx-auto`}>
            <Icon size={24} className="text-white animate-spin" style={{ animationDuration: '2s' }} />
          </div>

          {/* Title */}
          <h3 className="text-lg font-semibold text-slate-800 mb-2 text-center">
            {title}
          </h3>
          
          {/* Progress bar */}
          <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden mb-3">
            <div 
              className={`h-full bg-gradient-to-r ${gradientColors} rounded-full`}
              style={{
                animation: 'shimmer 1.5s ease-in-out infinite',
                backgroundSize: '200% 100%',
              }}
            />
          </div>

          {/* Subtitle */}
          <div className="flex items-center justify-center gap-2 text-sm text-slate-500">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>{subtitle}</span>
          </div>
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
