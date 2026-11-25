import React from 'react';
import { QuasarField } from '../Background/QuasarField';

interface GlassLayoutProps {
  children: React.ReactNode;
}

export const GlassLayout: React.FC<GlassLayoutProps> = ({ children }) => {
  return (
    <div
      data-qp-theme="light"
      className="qp-root relative flex h-[100dvh] w-full items-stretch justify-center overflow-hidden bg-[color:var(--qp-bg)] p-0 sm:p-3 md:p-4 lg:p-6 2xl:p-8 transition-colors duration-500"
    >
      {/* Deep-field motion background */}
      <QuasarField
        variant="panel"
        appearance="light"
        className="pointer-events-none absolute inset-0 z-0 h-full w-full opacity-80"
      />

      {/* Soft atmospheric volumes */}
      <div className="qp-aurora pointer-events-none absolute inset-0 z-0" aria-hidden="true" />

      {/* Film grain — keeps the field from reading as flat CGI */}
      <div className="qp-grain pointer-events-none fixed inset-0 z-[1] opacity-55" aria-hidden="true" />

      <div className="relative z-10 mx-auto flex h-full min-h-0 w-full max-w-[1680px] flex-col">
        <div className="quasar-shell motion-reveal relative flex min-h-0 w-full min-w-0 flex-1 flex-col gap-0 overflow-hidden rounded-none border-0 border-slate-200/80 bg-white/80 p-0 shadow-none backdrop-blur-2xl ring-0 ring-slate-900/5 sm:gap-3 sm:rounded-[1.5rem] sm:border sm:bg-white/65 sm:p-2.5 sm:shadow-[0_24px_80px_rgba(15,23,42,0.10)] sm:ring-1 md:flex-row md:gap-4 md:rounded-[2rem] md:p-3 lg:gap-5 lg:p-4 xl:gap-6">
          {children}
        </div>
      </div>
    </div>
  );
};
