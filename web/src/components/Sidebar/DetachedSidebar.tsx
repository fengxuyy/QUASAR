import React, { useRef, useEffect, useState, useCallback } from 'react';
import { LayoutDashboard, Settings, FolderTree, History, Terminal } from 'lucide-react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import logo from '../../assets/logo-mark.png';
import { CircleProgress } from '../UI/CircleProgress';
import { useIsMobileLayout } from '../../hooks/useMediaQuery';

interface DetachedSidebarProps {
  className?: string;
  activeTab: 'dashboard' | 'settings' | 'workspace' | 'history' | 'terminal';
  onTabChange: (tab: 'dashboard' | 'settings' | 'workspace' | 'history' | 'terminal') => void;
  isRunning?: boolean;
  taskProgress?: { current: number; total: number } | null;
}

const NAV_ITEMS = [
  { id: 'dashboard' as const, icon: LayoutDashboard, label: 'Dashboard' },
  { id: 'history' as const, icon: History, label: 'History' },
  { id: 'workspace' as const, icon: FolderTree, label: 'Workspace' },
  { id: 'terminal' as const, icon: Terminal, label: 'Terminal' },
  { id: 'settings' as const, icon: Settings, label: 'Settings' },
];

export const DetachedSidebar: React.FC<DetachedSidebarProps> = ({
  className,
  activeTab,
  onTabChange,
  isRunning = false,
  taskProgress = null,
}) => {
  const navRef = useRef<HTMLDivElement>(null);
  const isMobile = useIsMobileLayout();
  const [indicatorStyle, setIndicatorStyle] = useState({
    top: 0,
    left: 0,
    height: 0,
    width: 0,
  });

  const updateIndicator = useCallback(() => {
    if (!navRef.current) return;
    const activeIndex = NAV_ITEMS.findIndex((item) => item.id === activeTab);
    const buttons = navRef.current.querySelectorAll('button');
    if (buttons[activeIndex]) {
      const button = buttons[activeIndex] as HTMLElement;
      setIndicatorStyle({
        top: button.offsetTop,
        left: button.offsetLeft,
        height: button.offsetHeight,
        width: button.offsetWidth,
      });
    }
  }, [activeTab]);

  useEffect(() => {
    updateIndicator();
  }, [updateIndicator, isMobile]);

  useEffect(() => {
    window.addEventListener('resize', updateIndicator);
    return () => window.removeEventListener('resize', updateIndicator);
  }, [updateIndicator]);

  const statusTitle =
    taskProgress && taskProgress.total > 0
      ? `Task ${taskProgress.current} of ${taskProgress.total}${isRunning ? '' : ' (paused)'}`
      : isRunning
        ? 'Running'
        : 'Idle';

  return (
    <div
      className={twMerge(
        'glass-panel motion-reveal relative flex overflow-hidden',
        // Mobile: bottom tab bar
        'order-last w-full shrink-0 flex-row items-center gap-1 rounded-none border-x-0 border-b-0 px-1.5 py-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))]',
        // Desktop: full-height vertical rail (not content-height compact)
        'md:order-none md:h-full md:w-[5.25rem] md:shrink-0 md:flex-col md:items-center md:gap-0 md:self-stretch md:rounded-[1.65rem] md:border md:px-3 md:py-6',
        className,
      )}
    >
      <div className="pointer-events-none absolute inset-x-3 top-0 hidden h-px bg-gradient-to-r from-transparent via-white/90 to-transparent md:block" />
      <div className="pointer-events-none absolute inset-y-8 right-0 hidden w-px bg-gradient-to-b from-transparent via-white/50 to-transparent md:block" />

      {/* Brand — compact mark on mobile, full lockup on desktop */}
      <a
        href="https://github.com/fengxuyy/QUASAR-CHEM"
        target="_blank"
        rel="noopener noreferrer"
        className="group flex shrink-0 cursor-pointer flex-col items-center md:mb-10"
        aria-label="QUASAR on GitHub"
      >
        <div className="flex h-8 w-8 items-center justify-center transition-transform duration-700 ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:-translate-y-0.5 group-hover:scale-[1.04] md:h-12 md:w-12 md:rounded-[1.15rem] md:border md:border-white/70 md:bg-white/65 md:shadow-lg md:shadow-indigo-200/40">
          <img src={logo} alt="Quasar Logo" className="h-full w-full object-contain" />
        </div>
        <span className="mt-2 hidden text-xs font-bold bg-clip-text text-transparent bg-gradient-to-r from-[#4f72e8] to-[#6f4fe4] transition-opacity group-hover:opacity-80 md:block">
          QUASAR
        </span>
      </a>

      <nav
        ref={navRef}
        className={clsx(
          'relative flex min-w-0 items-center',
          // Mobile: distribute labeled tabs across remaining width
          'flex-1 flex-row justify-around',
          // Desktop: stacked icons with breathing room; grow so status can sit at bottom
          'md:w-full md:flex-1 md:flex-col md:justify-start md:gap-3',
        )}
        aria-label="Primary"
      >
        {/* Sliding indicator */}
        <div
          className="pointer-events-none absolute rounded-[1.1rem] border border-white/75 bg-white/72 shadow-lg shadow-indigo-200/50 transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] md:left-1/2 md:w-12 md:-translate-x-1/2"
          style={
            isMobile
              ? {
                  top: indicatorStyle.top,
                  left: indicatorStyle.left,
                  height: indicatorStyle.height,
                  width: indicatorStyle.width,
                }
              : {
                  top: indicatorStyle.top,
                  height: indicatorStyle.height,
                }
          }
        />

        {NAV_ITEMS.map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => onTabChange(id)}
            className={clsx(
              'relative z-10 flex flex-col items-center justify-center rounded-[1.1rem] transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] focus:outline-none focus:ring-2 focus:ring-indigo-300/60 active:scale-95',
              // Mobile: labeled tab targets
              'min-h-[44px] min-w-0 flex-1 gap-0.5 px-1 py-1',
              // Desktop: original icon-only rail buttons
              'md:min-h-0 md:min-w-0 md:flex-none md:gap-0 md:p-3',
              activeTab === id
                ? 'text-[#4a5fe4] drop-shadow-sm'
                : 'text-slate-400 hover:bg-white/45 hover:text-slate-600 md:hover:-translate-y-0.5',
            )}
            title={label}
            aria-label={label}
            aria-current={activeTab === id ? 'page' : undefined}
          >
            <Icon size={isMobile ? 20 : 24} />
            <span
              className={clsx(
                'max-w-full truncate text-[9px] font-semibold leading-none tracking-wide md:hidden',
                activeTab === id ? 'text-[#4a5fe4]' : 'text-slate-400',
              )}
            >
              {label === 'Dashboard' ? 'Home' : label}
            </span>
          </button>
        ))}
      </nav>

      {/* Status ring. Desktop: pin to bottom of rail. */}
      <div className="flex shrink-0 items-center gap-1 md:mt-auto md:flex-col md:gap-2 md:pt-4">
        <div
          className="flex items-center justify-center rounded-xl border border-white/60 bg-white/50 p-1.5 shadow-inner shadow-white/50 md:rounded-[1.1rem] md:p-2"
          title={statusTitle}
        >
          <CircleProgress
            current={taskProgress?.current ?? 0}
            total={taskProgress?.total ?? 1}
            size={isMobile ? 24 : 28}
            strokeWidth={2.5}
          >
            <div
              className={clsx(
                'h-2 w-2 rounded-full shadow-custom transition-colors duration-300 md:h-2.5 md:w-2.5',
                isRunning
                  ? 'animate-pulse bg-green-400'
                  : taskProgress && taskProgress.total > 0
                    ? 'bg-amber-400'
                    : 'bg-slate-300',
              )}
            />
          </CircleProgress>
        </div>
      </div>
    </div>
  );
};
