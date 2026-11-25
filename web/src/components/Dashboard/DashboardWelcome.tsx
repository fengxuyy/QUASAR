import React from 'react';
import {
  Atom,
  Boxes,
  Activity,
  AudioLines,
  ArrowRight,
} from 'lucide-react';

interface DashboardWelcomeProps {
  /** Fills the main input with a suggested prompt. */
  onSuggest: (prompt: string) => void;
}

interface WorkflowTemplate {
  engine: string;
  badgeColor: string;
  title: string;
  description: string;
  prompt: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}

const TEMPLATES: WorkflowTemplate[] = [
  {
    engine: 'Adsorption',
    badgeColor: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700',
    title: 'CO₂ Adsorption in Mg-MOF-74',
    description: 'Compute 298 K adsorption isotherms and uptake from a relaxed framework.',
    prompt:
      'Compute the CO₂ adsorption isotherm of Mg-MOF-74 at 298 K, starting from a relaxed framework.',
    icon: Boxes,
  },
  {
    engine: 'DFT',
    badgeColor: 'border-indigo-500/25 bg-indigo-500/10 text-indigo-700',
    title: 'Multi-Stage DFT Relaxation',
    description: 'Pre-optimize the geometry, then run a single-point DFT calculation with PBE.',
    prompt:
      'Relax the geometry of my structure, then run a single-point DFT calculation with the PBE functional.',
    icon: Atom,
  },
  {
    engine: 'Molecular dynamics',
    badgeColor: 'border-cyan-500/25 bg-cyan-500/10 text-cyan-700',
    title: 'NPT Water Box Dynamics',
    description: 'Build a 1000-molecule box, run 100 ps of NPT at 300 K, report the density.',
    prompt:
      'Build a 1000-molecule water box and run 100 ps of NPT molecular dynamics at 300 K, then report the equilibrated density.',
    icon: Activity,
  },
  {
    engine: 'Vibrations',
    badgeColor: 'border-violet-500/25 bg-violet-500/10 text-violet-700',
    title: 'Vibrational IR Spectrum',
    description: 'Optimize the structure and compute normal modes and IR-active frequencies.',
    prompt:
      'Optimize caffeine and compute its IR spectrum; summarize the main vibrational modes.',
    icon: AudioLines,
  },
];

/**
 * Empty dashboard state.
 *
 * Both bands are positioned from the SAME anchor the floating DynamicInput
 * uses (--quasar-welcome-input-top, input centered on it): the title band
 * ends half a lane above that line and the template band starts half a lane
 * below it — so the input can never overlap either at any viewport height.
 */
export const DashboardWelcome: React.FC<DashboardWelcomeProps> = ({ onSuggest }) => {
  return (
    <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
      {/* Title band — bottom edge is exactly half a lane above the input's center line */}
      <div
        className="absolute inset-x-0 top-0 flex flex-col items-center justify-end px-3 text-center sm:px-10 lg:px-16"
        style={{
          height:
            'calc(var(--quasar-welcome-input-top, 50%) - var(--quasar-welcome-input-lane, 8rem) / 2)',
          paddingBottom: 'var(--quasar-welcome-gap-title, 1.5rem)',
        }}
      >
        <h1 className="motion-reveal max-w-3xl text-[1.35rem] font-bold leading-[1.15] tracking-[-0.03em] text-slate-900 [text-wrap:balance] sm:text-4xl sm:leading-[1.06] md:text-[2.75rem]">
          Start an autonomous <span className="quasar-gradient-text">computation</span>.
        </h1>
      </div>

      {/* Template band — top edge is exactly half a lane below the input's center line */}
      <div
        className="absolute inset-x-0 bottom-0 flex flex-col items-center justify-start overflow-y-auto overscroll-contain px-3 pb-4 scrollbar-glass sm:px-10 lg:px-16"
        style={{
          top:
            'calc(var(--quasar-welcome-input-top, 50%) + var(--quasar-welcome-input-lane, 8rem) / 2)',
          paddingTop: 'var(--quasar-welcome-gap-templates, 1.5rem)',
        }}
      >
        <div className="mx-auto grid w-full max-w-lg grid-cols-2 gap-2.5 sm:max-w-5xl sm:gap-3 lg:grid-cols-4">
          {TEMPLATES.map((template) => {
            const IconComponent = template.icon;
            return (
              <button
                key={template.title}
                type="button"
                onClick={() => onSuggest(template.prompt)}
                className="group pointer-events-auto relative flex min-h-0 flex-col justify-between rounded-xl border border-slate-200/80 bg-white/75 p-2.5 text-left shadow-sm shadow-indigo-100/30 backdrop-blur-xl transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] hover:-translate-y-0.5 hover:border-indigo-300 hover:bg-white hover:shadow-lg hover:shadow-indigo-500/10 active:scale-[0.99] sm:p-4"
              >
                <div className="min-w-0">
                  <div className="flex items-start justify-between gap-1.5 sm:items-center sm:gap-2">
                    <span
                      className={`inline-flex max-w-[calc(100%-1.25rem)] truncate rounded-md border px-1.5 py-0.5 font-mono text-[8.5px] font-semibold uppercase tracking-[0.06em] sm:max-w-none sm:px-2 sm:text-[9.5px] sm:tracking-[0.08em] ${template.badgeColor}`}
                    >
                      {template.engine}
                    </span>
                    <IconComponent
                      size={14}
                      className="mt-0.5 shrink-0 text-slate-400 transition-colors duration-300 group-hover:text-indigo-600 sm:mt-0"
                    />
                  </div>
                  <h3 className="mt-1.5 line-clamp-2 text-[12px] font-bold leading-snug tracking-[-0.01em] text-slate-900 sm:mt-3 sm:line-clamp-none sm:text-[13.5px] sm:leading-tight">
                    {template.title}
                  </h3>
                  <p className="mt-1.5 hidden text-[11.5px] leading-[1.4] text-slate-500 line-clamp-2 sm:block">
                    {template.description}
                  </p>
                </div>

                <div className="mt-2 hidden items-center gap-1 text-[11px] font-semibold text-indigo-600 opacity-80 transition-all duration-300 group-hover:opacity-100 sm:mt-4 sm:flex">
                  <span>Load template</span>
                  <ArrowRight
                    size={12}
                    className="transition-transform duration-300 group-hover:translate-x-1"
                  />
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
