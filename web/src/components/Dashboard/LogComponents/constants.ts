
import strategistLogo from '../../../assets/strategist.png';
import executorLogo from '../../../assets/executor.png';
import evaluatorLogo from '../../../assets/evaluator.png';

export type AgentType = 'strategist' | 'operator' | 'evaluator';

export const agentColors: Record<string, string> = {
  strategist: 'from-purple-500 to-indigo-500',
  operator: 'from-blue-500 to-cyan-500',
  evaluator: 'from-emerald-500 to-teal-500',
  'unknown': 'from-slate-500 to-slate-600'
};

export const agentTextColors: Record<string, string> = {
  strategist: 'text-purple-600',
  operator: 'text-blue-600',
  evaluator: 'text-emerald-600'
};

export const agentBgColors: Record<string, string> = {
  strategist: 'bg-purple-50',
  operator: 'bg-blue-50',
  evaluator: 'bg-emerald-50'
};

export const agentSubPanelThemes: Record<string, { bg: string, text: string, icon: string, border: string }> = {
  strategist: { bg: 'bg-purple-50/50', text: 'text-purple-700', icon: 'text-purple-500', border: 'border-purple-100' },
  operator: { bg: 'bg-orange-50/50', text: 'text-orange-700', icon: 'text-orange-500', border: 'border-orange-100' },
  evaluator: { bg: 'bg-teal-50/50', text: 'text-teal-700', icon: 'text-teal-500', border: 'border-teal-100' },
  system: { bg: 'bg-slate-50/50', text: 'text-slate-700', icon: 'text-slate-500', border: 'border-slate-100' },
  unknown: { bg: 'bg-slate-50/50', text: 'text-slate-700', icon: 'text-slate-500', border: 'border-slate-100' },
};

export const agentConfig: { id: AgentType; name: string; role: string; logo: string }[] = [
  { id: 'strategist', name: 'Strategist', role: 'Planning', logo: strategistLogo },
  { id: 'operator', name: 'Operator', role: 'Execution', logo: executorLogo },
  { id: 'evaluator', name: 'Evaluator', role: 'Verification', logo: evaluatorLogo },
];
