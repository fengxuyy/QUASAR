import React, { useState, useEffect, useRef, memo } from 'react';
import { CheckCircle, Cpu, Gauge, Sparkles } from 'lucide-react';
import { clsx } from 'clsx';
import { ToggleSwitch } from '../UI/ToggleSwitch';
import { SlidingSegment } from '../UI/SlidingSegment';
import {
  getStoredSettings,
  mergeSettingsPreservingMaskedValues,
  setStoredSettings,
} from '../../utils/settingsStorage';

// Memoized text input component to prevent focus loss on parent re-renders
interface TextInputFieldProps {
  fieldKey: string;
  label: string;
  placeholder: string;
  type?: string;
  description?: string;
  value: string;
  disabled: boolean;
  onBlur: (key: string, value: string) => void;
}

const TextInputField = memo(({ 
  fieldKey, 
  label, 
  placeholder, 
  type, 
  description, 
  value: externalValue, 
  disabled, 
  onBlur 
}: TextInputFieldProps) => {
  // Use local state for input value to prevent focus loss
  const [localValue, setLocalValue] = useState(externalValue);
  const inputRef = useRef<HTMLInputElement>(null);
  
  // Sync local value with external value only when external value changes
  // and input is not focused
  useEffect(() => {
    if (document.activeElement !== inputRef.current) {
      setLocalValue(externalValue);
    }
  }, [externalValue]);

  const handleBlur = () => {
    onBlur(fieldKey, localValue);
  };

  return (
    <div>
      <label htmlFor={`setting-${fieldKey}`} className="block text-sm font-semibold text-slate-700 mb-1.5">
        {label}
      </label>
      <input
        ref={inputRef}
        id={`setting-${fieldKey}`}
        type={type || 'text'}
        value={localValue}
        onChange={(e) => setLocalValue(e.target.value)}
        onBlur={handleBlur}
        placeholder={placeholder}
        disabled={disabled}
        className={clsx(
          "w-full glass-text-input rounded-lg px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 transition-all",
          disabled && "opacity-50 cursor-not-allowed bg-slate-100/30"
        )}
      />
      {description && (
        <p className="text-xs text-slate-400 mt-1">{description}</p>
      )}
    </div>
  );
});

interface SettingsPanelProps {
  className?: string;
  isRunning: boolean;
  isLoading?: boolean;
  hasCheckpoint: boolean;
  sendSettings: (settings: Record<string, string>) => void;
}

interface SettingField {
  key: string;
  label: string;
  placeholder: string;
  defaultValue?: string;
  type?: string; // 'text' | 'password' | 'toggle' | 'sliding'
  options?: string[];
  description?: string;
}

interface SettingCategory {
  title: string;
  icon: React.ReactNode;
  fields: SettingField[];
}

// Agent scope definitions for Model Configuration slider
const MODEL_SCOPES = ['Global', 'Strategist', 'Operator', 'Evaluator'] as const;
type ModelScope = typeof MODEL_SCOPES[number];

const MODEL_SCOPE_KEYS: Record<ModelScope, { model: string; apiKey: string; baseUrl: string }> = {
  Global:     { model: 'MODEL',            apiKey: 'MODEL_API_KEY',            baseUrl: 'OPENAI_API_BASE' },
  Strategist: { model: 'STRATEGIST_MODEL', apiKey: 'STRATEGIST_MODEL_API_KEY', baseUrl: 'STRATEGIST_API_BASE_URL' },
  Operator:   { model: 'OPERATOR_MODEL',   apiKey: 'OPERATOR_MODEL_API_KEY',   baseUrl: 'OPERATOR_API_BASE_URL' },
  Evaluator:  { model: 'EVALUATOR_MODEL',  apiKey: 'EVALUATOR_MODEL_API_KEY',  baseUrl: 'EVALUATOR_API_BASE_URL' },
};

const MODEL_SCOPE_DESCRIPTIONS: Record<ModelScope, string> = {
  Global:     'Shared by all agents unless overridden',
  Strategist: 'Planning agent override; falls back to Global',
  Operator:   'Execution agent override; falls back to Global',
  Evaluator:  'Evaluation agent override; falls back to Global',
};

const SETTING_CATEGORIES: SettingCategory[] = [
  {
    title: 'Model Configuration',
    icon: <Cpu size={20} />,
    fields: [], // Rendered via custom slider UI
  },
  {
    title: 'Execution Settings',
    icon: <Gauge size={20} />,
    fields: [
      { 
        key: 'ACCURACY', 
        label: 'Accuracy Mode', 
        placeholder: 'standard',
        defaultValue: 'standard',
        type: 'sliding',
        options: ['eco', 'standard', 'pro', 'adaptive'],
        description: 'eco: Fast · standard: Balanced · pro: Publication-grade · adaptive: Dynamic'
      },
      { 
        key: 'GRANULARITY', 
        label: 'Granularity', 
        placeholder: 'adaptive',
        defaultValue: 'adaptive',
        type: 'sliding',
        options: ['low', 'medium', 'high', 'adaptive'],
        description: 'Controls task decomposition depth (adaptive: dynamic)'
      },
      {
        key: 'CONTEXT_THRESHOLD',
        label: 'Context Compression Threshold',
        placeholder: 'medium',
        defaultValue: 'medium',
        type: 'sliding',
        options: ['low', 'medium', 'hard'],
        description: 'low: compress at 20% · medium: 40% · hard: 60% of model context'
      },
      { 
        key: 'NUM_CORES', 
        label: 'Number of Cores Override', 
        placeholder: 'Auto-detect',
        type: 'text',
        description: 'Leave blank to auto-detect available physical cores'
      },
    ]
  },
  {
    title: 'Features',
    icon: <Sparkles size={20} />,
    fields: [
      { 
        key: 'ENABLE_RAG', 
        label: 'Enable RAG', 
        placeholder: 'true',
        defaultValue: 'true',
        type: 'toggle',
        description: 'Use documentation retrieval to augment agent responses'
      },
      { 
        key: 'PMG_MAPI_KEY', 
        label: 'Materials Project API Key', 
        placeholder: 'Your MAPI key', 
        type: 'password',
        description: 'Required to query the Materials Project database'
      },
      {
        key: 'AUTO_IMPROVE_CYCLES',
        label: 'Automatic Auto-Improve Cycles',
        placeholder: '0',
        defaultValue: '0',
        type: 'text',
        description: 'Number of automatic follow-up auto-improve runs after a successful user-started run'
      },
      { 
        key: 'EXIT_ON_COMPLETION', 
        label: 'Exit on Completion', 
        placeholder: 'false',
        defaultValue: 'false',
        type: 'toggle',
        description: 'Shut down server when execution finishes (useful for SLURM jobs)'
      },
      {
        key: 'AUTO_CONFIRM_PLAN',
        label: 'Auto-Confirm Plan',
        placeholder: 'false',
        defaultValue: 'false',
        type: 'toggle',
        description: 'Automatically approve execution plans without manual review'
      },
    ]
  },
];

export const SettingsPanel: React.FC<SettingsPanelProps> = ({
  className,
  isRunning,
  isLoading = false,
  hasCheckpoint,
  sendSettings,
}) => {
  const getInitialValues = (): Record<string, string> => {
    const savedSettings = getStoredSettings();
    if (Object.keys(savedSettings).length > 0) {
      return savedSettings;
    }
    
    const defaults: Record<string, string> = {};
    SETTING_CATEGORIES.forEach(cat => {
      cat.fields.forEach(field => {
        if (field.defaultValue) {
          defaults[field.key] = field.defaultValue;
        }
      });
    });
    return defaults;
  };

  const [values, setValues] = useState<Record<string, string>>(getInitialValues);
  const [showSaved, setShowSaved] = useState(false);
  const [modelScope, setModelScope] = useState<ModelScope>('Global');

  // Save settings to localStorage and sync with server
  const saveSettings = (newValues: Record<string, string>) => {
    try {
      setStoredSettings(newValues);
      console.log('Settings auto-saved:', Object.keys(newValues));

      // Sync with server via bridge
      sendSettings(newValues);
      
      setShowSaved(true);
      setTimeout(() => setShowSaved(false), 1500);
    } catch (e) {
      console.error('Failed to save settings:', e);
    }
  };

  // Handle text input blur - updates state AND saves
  const handleTextInputBlur = (key: string, value: string) => {
    if ((values[key] || '') === (value || '')) return;
    const newValues = { ...values, [key]: value };
    setValues(newValues);
    saveSettings(newValues);
  };

  // Handle immediate changes (toggles, sliders) - updates state AND saves immediately
  const handleImmediateChange = (key: string, value: string) => {
    if ((values[key] || '') === (value || '')) return;
    const newValues = { ...values, [key]: value };
    setValues(newValues);
    saveSettings(newValues);
  };

  useEffect(() => {
    // Fetch initial settings from server to preload environment variables
    const fetchServerSettings = async () => {
      try {
        const response = await fetch('/api/settings');
        if (response.ok) {
          const serverSettings = await response.json();
          
          if (Object.keys(serverSettings).length > 0) {
            setValues(prev => {
              // Server values populate the form, but masked secrets must not
              // replace real credentials already stored by this browser.
              const merged = mergeSettingsPreservingMaskedValues(
                prev,
                serverSettings
              );
              setStoredSettings(merged);
              return merged;
            });
          }
        }
      } catch (e) {
        console.error('Failed to fetch settings from server:', e);
      }
    };

    fetchServerSettings();
  }, []);

  const renderField = (field: SettingField) => {
    const { key, label, placeholder, type, options, description, defaultValue } = field;

    // Toggle for boolean fields
    if (type === 'toggle') {
      const isEnabled = (values[key] || defaultValue) === 'true';
      return (
        <div key={key} className="flex items-center justify-between py-0.5">
          <div className="flex-1">
            <label className="block text-sm font-semibold text-slate-700">
              {label}
            </label>
            {description && (
              <p className="text-xs text-slate-400 mt-0.5">{description}</p>
            )}
          </div>
          <ToggleSwitch
            enabled={isEnabled}
            onChange={(enabled) => handleImmediateChange(key, enabled ? 'true' : 'false')}
            label={label}
            disabled={isRunning || isLoading}
          />
        </div>
      );
    }

    // Sliding segment for options
    if (type === 'sliding' && options) {
      // ACCURACY and GRANULARITY are locked when checkpoint exists
      const isModeSetting = key === 'ACCURACY' || key === 'GRANULARITY';
      const isDisabled = isRunning || isLoading || (isModeSetting && hasCheckpoint);
      
      return (
        <div key={key} className="min-w-0">
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">
            {label}
            {isModeSetting && hasCheckpoint && !isRunning && !isLoading && (
              <span className="ml-2 text-xs text-amber-500 font-normal">(locked - start fresh to change)</span>
            )}
          </label>
          <SlidingSegment
            value={values[key] || defaultValue || ''}
            options={options}
            onChange={(val) => handleImmediateChange(key, val)}
            disabled={isDisabled}
          />
          {description && (
            <p className="text-xs text-slate-400 mt-1">{description}</p>
          )}
        </div>
      );
    }

    // Text input (default) - use memoized component to prevent focus loss
    return (
      <TextInputField
        key={key}
        fieldKey={key}
        label={label}
        placeholder={placeholder}
        type={type}
        description={description}
        value={values[key] || ''}
        disabled={isRunning || isLoading}
        onBlur={handleTextInputBlur}
      />
    );
  };

  // Shared card wrapper — full natural height on mobile (page scrolls);
  // on md+ cards stretch in a multi-column grid and scroll internally if needed.
  const CARD_CLASS =
    'group/card relative flex min-w-0 flex-col rounded-2xl border border-slate-200/80 bg-white/75 p-4 shadow-sm backdrop-blur-xl transition-all duration-300 sm:p-5 ' +
    'hover:border-indigo-300 hover:bg-white hover:shadow-md ' +
    'md:min-h-0 md:overflow-y-auto md:scrollbar-glass';

  const renderCategoryCard = (category: SettingCategory, children: React.ReactNode) => (
    <div key={category.title} className={CARD_CLASS}>
      <div className="mb-3 flex flex-shrink-0 items-center gap-2.5 sm:mb-4 sm:gap-3">
        <div className="rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 p-2 text-white shadow-md shadow-indigo-500/20 sm:p-2.5">
          {category.icon}
        </div>
        <h3 className="text-[15px] font-extrabold tracking-tight text-slate-900 sm:text-base">
          {category.title}
        </h3>
      </div>
      {children}
    </div>
  );

  // Model Configuration panel content
  const renderModelConfigContent = () => {
    const keys = MODEL_SCOPE_KEYS[modelScope];
    const isGlobal = modelScope === 'Global';
    
    const scopeFields: SettingField[] = [
      {
        key: keys.model,
        label: 'Model Name',
        placeholder: isGlobal ? 'Required (e.g. gemini-4-neon, gemini-4-hydrogen)' : 'Same as Global',
        description: isGlobal ? 'Provider model identifier (e.g. gemini-4-neon, gemini-4-carbon, gemini-4-hydrogen)' : MODEL_SCOPE_DESCRIPTIONS[modelScope],
      },
      {
        key: keys.apiKey,
        label: 'API Key',
        placeholder: isGlobal ? 'Your API key' : 'Same as Global',
        type: 'password',
        description: isGlobal ? 'Provider API key (Gemini, Claude, Grok, OpenAI)' : 'Blank = inherit Global key',
      },
      {
        key: keys.baseUrl,
        label: 'Custom API Base URL',
        placeholder: isGlobal ? 'https://api.openai.com/v1' : 'Same as Global',
        description: isGlobal ? 'Custom OpenAI-compatible endpoint (optional)' : 'Blank = inherit Global URL',
      },
    ];

    return (
      <>
        <div className="mb-4">
          <SlidingSegment
            value={modelScope}
            options={[...MODEL_SCOPES]}
            onChange={(val) => setModelScope(val as ModelScope)}
          />
        </div>
        <div className="space-y-4">
          {scopeFields.map(renderField)}
        </div>
      </>
    );
  };

  return (
    <div className={clsx('h-full min-h-0 w-full animate-fade-in', className)}>
      {/*
        Mobile: page scrolls; each section is full natural height (not equal-height
        folded cards). Desktop: multi-column grid with stretch + internal scroll.
      */}
      <div className="flex h-full min-h-0 flex-col overflow-y-auto overscroll-contain rounded-none border-0 border-slate-200/80 bg-white/75 p-4 shadow-sm backdrop-blur-2xl scrollbar-glass sm:rounded-2xl sm:border sm:p-6 md:overflow-hidden md:p-8">
        {/* Enterprise Header */}
        <div className="mb-4 flex flex-shrink-0 flex-col justify-between gap-3 border-b border-slate-200/60 pb-4 sm:mb-6 sm:flex-row sm:items-center sm:gap-4 sm:pb-5">
          <div className="min-w-0">
            <h2 className="text-xl font-extrabold tracking-[-0.03em] text-slate-900 sm:text-2xl md:text-3xl">
              Platform <span className="quasar-gradient-text">Settings</span>
            </h2>
            <p className="mt-1 text-xs font-medium text-slate-500">
              Configure runtime engines, API keys, and execution parameters.
              {(isRunning || isLoading) && (
                <span className="ml-2 inline-flex items-center gap-1 font-bold text-amber-600">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                  Locked during {isLoading ? 'initialization' : 'execution'}
                </span>
              )}
            </p>
          </div>
          {showSaved && (
            <div className="flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-4 py-2 text-xs font-bold text-emerald-700 animate-fade-in shadow-xs">
              <CheckCircle size={15} className="text-emerald-500" />
              Settings Synced
            </div>
          )}
        </div>

        <div
          className={clsx(
            'grid grid-cols-1 content-start gap-3 pb-2',
            // Desktop: fill remaining height, stretch equal columns, scroll inside cards
            'md:min-h-0 md:flex-1 md:content-stretch md:items-stretch md:gap-4 md:overflow-hidden md:pb-0',
          )}
          style={{
            // 1 col on narrow phones; auto multi-col once there's room
            gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 18rem), 1fr))',
          }}
        >
          {SETTING_CATEGORIES.map((category) =>
            category.title === 'Model Configuration'
              ? renderCategoryCard(category, renderModelConfigContent())
              : renderCategoryCard(
                  category,
                  <div className="space-y-3.5 sm:space-y-4">{category.fields.map(renderField)}</div>,
                ),
          )}
        </div>
      </div>
    </div>
  );
};
