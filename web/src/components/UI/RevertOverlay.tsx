import { RotateCcw, Loader2 } from 'lucide-react';

interface RevertOverlayProps {
  isVisible: boolean;
  targetTask?: number;
}

/**
 * Full-screen overlay displayed when the system is reverting to a previous task.
 * Blocks all user interaction during the revert operation.
 */
export function RevertOverlay({ isVisible, targetTask }: RevertOverlayProps) {
  if (!isVisible) return null;

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
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center mb-4 mx-auto">
            <RotateCcw size={24} className="text-white animate-spin" style={{ animationDuration: '2s' }} />
          </div>

          {/* Title */}
          <h3 className="text-lg font-semibold text-slate-800 mb-2 text-center">
            Reverting to Task {targetTask}
          </h3>
          
          {/* Progress bar */}
          <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden mb-3">
            <div 
              className="h-full bg-gradient-to-r from-amber-400 via-orange-400 to-amber-400 rounded-full"
              style={{
                animation: 'shimmer 1.5s ease-in-out infinite',
                backgroundSize: '200% 100%',
              }}
            />
          </div>

          {/* Subtitle */}
          <div className="flex items-center justify-center gap-2 text-sm text-slate-500">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>Restoring checkpoint state</span>
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
