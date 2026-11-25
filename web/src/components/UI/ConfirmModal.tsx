import React from 'react';
import { AlertTriangle, X } from 'lucide-react';

interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
  onCancel: () => void;
  variant?: 'danger' | 'warning' | 'info';
  disableBackdropCancel?: boolean;
  hideCloseButton?: boolean;
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
  isOpen,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  onConfirm,
  onCancel,
  variant = 'warning',
  disableBackdropCancel = false,
  hideCloseButton = false
}) => {
  if (!isOpen) return null;

  const variantStyles = {
    danger: 'from-red-500 to-orange-500',
    warning: 'from-amber-500 to-orange-500',
    info: 'from-blue-500 to-purple-500'
  };

  const buttonStyles = {
    danger: 'bg-red-500 hover:bg-red-600',
    warning: 'bg-amber-500 hover:bg-amber-600',
    info: 'bg-blue-500 hover:bg-blue-600'
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 animate-fade-in sm:items-center sm:p-4">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/30 backdrop-blur-sm"
        onClick={disableBackdropCancel ? undefined : onCancel}
      />
      
      {/* Modal — bottom sheet on phones, centered card on larger screens */}
      <div 
        className="relative w-full max-w-md overflow-hidden rounded-t-3xl sm:rounded-2xl"
        style={{
          background: 'rgba(255, 255, 255, 0.9)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          border: '1px solid rgba(255, 255, 255, 0.5)',
          boxShadow: '0 25px 50px rgba(0, 0, 0, 0.15)',
          paddingBottom: 'max(0px, env(safe-area-inset-bottom))',
        }}
      >
        {!hideCloseButton && (
          <button
            onClick={onCancel}
            className="absolute right-4 top-4 rounded-lg p-1 text-slate-400 transition-colors hover:bg-slate-100/50 hover:text-slate-600"
          >
            <X size={20} />
          </button>
        )}

        <div className="p-5 sm:p-6">
          {/* Icon */}
          <div className={`mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ${variantStyles[variant]}`}>
            <AlertTriangle size={24} className="text-white" />
          </div>

          {/* Title */}
          <h3 className="mb-2 pr-8 text-lg font-semibold text-slate-800">{title}</h3>
          
          {/* Message */}
          <p className="mb-6 text-sm text-slate-600">{message}</p>

          {/* Actions */}
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:gap-3">
            <button
              onClick={onCancel}
              className="min-h-[44px] flex-1 rounded-xl bg-slate-100 px-4 py-2.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-200"
            >
              {cancelText}
            </button>
            <button
              onClick={onConfirm}
              className={`min-h-[44px] flex-1 rounded-xl px-4 py-2.5 text-sm font-medium text-white transition-colors ${buttonStyles[variant]}`}
            >
              {confirmText}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
