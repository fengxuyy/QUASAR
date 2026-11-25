import React from 'react';
import { clsx } from 'clsx';

interface ToggleSwitchProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  label?: string;
  disabled?: boolean;
}

export const ToggleSwitch: React.FC<ToggleSwitchProps> = ({ enabled, onChange, label, disabled }) => {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={clsx(
        "relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-blue-300 focus:ring-offset-2 focus:ring-offset-transparent",
        enabled 
          ? "bg-gradient-to-r from-blue-500 to-purple-500" 
          : "bg-slate-300/60 backdrop-blur-sm",
        disabled && "opacity-50 cursor-not-allowed pointer-events-none"
      )}
      role="switch"
      aria-checked={enabled}
      aria-label={label}
    >
      <span
        className={clsx(
          "pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition-all duration-300 ease-out",
          enabled ? "translate-x-6" : "translate-x-1"
        )}
        style={{ marginTop: '4px' }}
      />
    </button>
  );
};
