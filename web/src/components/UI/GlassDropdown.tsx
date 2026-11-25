import React, { useState, useRef, useEffect } from 'react';
import { clsx } from 'clsx';
import { ChevronDown } from 'lucide-react';

export interface DropdownOption {
  value: string;
  label: string;
}

interface GlassDropdownProps {
  options: DropdownOption[];
  value: string;
  onChange: (value: string) => void;
  label?: string;
  disabled?: boolean;
  className?: string;
}

export const GlassDropdown: React.FC<GlassDropdownProps> = ({
  options,
  value,
  onChange,
  label,
  disabled = false,
  className
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  
  const selectedOption = options.find(opt => opt.value === value);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;
    
    switch (e.key) {
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (isOpen && highlightedIndex >= 0) {
          onChange(options[highlightedIndex].value);
          setIsOpen(false);
        } else {
          setIsOpen(!isOpen);
          setHighlightedIndex(options.findIndex(opt => opt.value === value));
        }
        break;
      case 'Escape':
        setIsOpen(false);
        buttonRef.current?.focus();
        break;
      case 'ArrowDown':
        e.preventDefault();
        if (!isOpen) {
          setIsOpen(true);
          setHighlightedIndex(options.findIndex(opt => opt.value === value));
        } else {
          setHighlightedIndex(prev => 
            prev < options.length - 1 ? prev + 1 : 0
          );
        }
        break;
      case 'ArrowUp':
        e.preventDefault();
        if (isOpen) {
          setHighlightedIndex(prev => 
            prev > 0 ? prev - 1 : options.length - 1
          );
        }
        break;
      case 'Tab':
        if (isOpen) {
          setIsOpen(false);
        }
        break;
    }
  };

  const handleOptionClick = (optionValue: string) => {
    onChange(optionValue);
    setIsOpen(false);
    buttonRef.current?.focus();
  };

  return (
    <div ref={containerRef} className={clsx("relative", className)}>
      {label && (
        <label className="block text-xs font-medium text-slate-500 mb-1">
          {label}
        </label>
      )}
      
      <button
        ref={buttonRef}
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={label}
        className={clsx(
          "w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg text-sm text-left",
          "bg-white/20 backdrop-blur-sm",
          "border border-white/30",
          "transition-all duration-200 ease-out",
          "shadow-sm",
          disabled 
            ? "opacity-50 cursor-not-allowed" 
            : "hover:bg-white/40 hover:border-white/50 cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-400/50 focus:border-blue-300/60"
        )}
      >
        <span className="truncate text-slate-700 font-medium">
          {selectedOption?.label || 'Select'}
        </span>
        <ChevronDown 
          size={16} 
          className={clsx(
            "text-slate-500 shrink-0 transition-transform duration-200",
            isOpen && "rotate-180"
          )}
        />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div 
          role="listbox"
          aria-activedescendant={highlightedIndex >= 0 ? `option-${highlightedIndex}` : undefined}
          className={clsx(
            "absolute z-50 w-full mt-1 py-1 rounded-lg",
            "bg-white/90 backdrop-blur-md",
            "border border-white/40",
            "shadow-lg shadow-slate-900/10",
            "animate-dropdown-in"
          )}
        >
          {options.map((option, index) => (
            <div
              key={option.value}
              id={`option-${index}`}
              role="option"
              aria-selected={option.value === value}
              onClick={() => handleOptionClick(option.value)}
              onMouseEnter={() => setHighlightedIndex(index)}
              className={clsx(
                "px-3 py-2 text-sm cursor-pointer transition-colors duration-100",
                option.value === value 
                  ? "bg-blue-500/20 text-blue-700 font-medium"
                  : "text-slate-600",
                highlightedIndex === index && option.value !== value && "bg-slate-100/80",
                "hover:bg-slate-100/80"
              )}
            >
              {option.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
