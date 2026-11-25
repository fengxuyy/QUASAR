import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { clsx } from 'clsx';

interface SlidingSegmentProps {
  options: string[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
  disabled?: boolean;
}

export const SlidingSegment: React.FC<SlidingSegmentProps> = ({ 
  options, 
  value, 
  onChange,
  className,
  disabled
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [indicatorStyle, setIndicatorStyle] = useState({ left: 0, width: 0 });

  const updateIndicator = useCallback(() => {
    if (!containerRef.current) return;

    const activeIndex = options.indexOf(value);
    const buttons = containerRef.current.querySelectorAll('button');
    const activeButton = buttons[activeIndex] as HTMLElement | undefined;

    if (!activeButton) {
      setIndicatorStyle((prev) => (
        prev.left === 0 && prev.width === 0 ? prev : { left: 0, width: 0 }
      ));
      return;
    }

    const nextStyle = {
      left: activeButton.offsetLeft,
      width: activeButton.offsetWidth,
    };

    setIndicatorStyle((prev) => (
      prev.left === nextStyle.left && prev.width === nextStyle.width
        ? prev
        : nextStyle
    ));
  }, [options, value]);

  useLayoutEffect(() => {
    updateIndicator();
  }, [updateIndicator]);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const handleResize = () => {
      updateIndicator();
    };

    window.addEventListener('resize', handleResize);

    const observer = typeof ResizeObserver === 'undefined'
      ? null
      : new ResizeObserver(handleResize);

    if (observer) {
      observer.observe(containerRef.current);
      containerRef.current.querySelectorAll('button').forEach((button) => {
        observer.observe(button);
      });
    }

    return () => {
      window.removeEventListener('resize', handleResize);
      observer?.disconnect();
    };
  }, [options, updateIndicator]);

  return (
    <div 
      ref={containerRef}
      className={clsx(
        "relative flex w-full min-w-0 overflow-hidden p-1 bg-slate-100/80 backdrop-blur-sm rounded-xl border border-slate-200/50",
        className,
        disabled && "opacity-60 pointer-events-none"
      )}
    >
      {/* Sliding Indicator */}
      <div 
        className="absolute bottom-1 top-1 rounded-lg bg-white shadow-sm border border-slate-200 transition-all duration-300 ease-out"
        style={{
          left: indicatorStyle.left,
          width: indicatorStyle.width,
        }}
      />
      
      {options.map((option) => (
        <button
          type="button"
          key={option}
          onClick={() => !disabled && onChange(option)}
          disabled={disabled}
          className={clsx(
            "relative z-10 min-w-0 flex-1 px-2 py-1.5 text-[11px] font-semibold capitalize leading-tight transition-colors duration-200 rounded-lg sm:px-4 sm:text-xs",
            value === option 
              ? "text-blue-600" 
              : "text-slate-500 hover:text-slate-700",
            disabled && "cursor-not-allowed"
          )}
        >
          {option}
        </button>
      ))}
    </div>
  );
};
