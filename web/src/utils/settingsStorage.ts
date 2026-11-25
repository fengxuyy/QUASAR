const STORAGE_KEY = 'quasar-settings';
export const SENSITIVE_SETTING_MASK = '********';
export const RETIRED_SETTING_KEYS = new Set([
  'QUASAR_QE_PATH',
  'QUASAR_ORCA_PATH',
  'QUASAR_LAMMPS_PATH',
  'QUASAR_RASPA_PATH',
  'QUASAR_XTB_PATH',
]);

function isStringRecord(value: unknown): value is Record<string, string> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function sanitizeSettings(settings: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(settings).filter(
      ([key, value]) => typeof value === 'string' && !RETIRED_SETTING_KEYS.has(key)
    )
  );
}

function forStorage(settings: Record<string, string>): Record<string, string> {
  const sanitized = sanitizeSettings(settings);
  // Never persist the mask sentinel — it is not a real secret.
  return Object.fromEntries(
    Object.entries(sanitized).filter(([, value]) => value !== SENSITIVE_SETTING_MASK)
  );
}

export function getStoredSettings(): Record<string, string> {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) {
      return {};
    }

    const parsed: unknown = JSON.parse(saved);
    if (!isStringRecord(parsed)) {
      return {};
    }

    const stored = forStorage(parsed);
    if (JSON.stringify(stored) !== JSON.stringify(parsed)) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
    }
    return stored;
  } catch {
    return {};
  }
}

export function setStoredSettings(settings: Record<string, string>): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(forStorage(settings)));
}

export function mergeSettingsPreservingMaskedValues(
  currentSettings: Record<string, string>,
  incomingSettings: Record<string, string>
): Record<string, string> {
  const merged = sanitizeSettings(currentSettings);

  Object.entries(sanitizeSettings(incomingSettings)).forEach(([key, value]) => {
    if (
      value === SENSITIVE_SETTING_MASK &&
      merged[key] &&
      merged[key] !== SENSITIVE_SETTING_MASK
    ) {
      return;
    }
    merged[key] = value;
  });

  return sanitizeSettings(merged);
}

export function mergeStoredSettings(
  incomingSettings: Record<string, string>,
  options: { ignoreEmptyStrings?: boolean } = {}
): Record<string, string> {
  const { ignoreEmptyStrings = false } = options;
  const filteredIncoming = Object.fromEntries(
    Object.entries(incomingSettings).filter(([, value]) => {
      if (typeof value !== 'string') {
        return false;
      }
      return !ignoreEmptyStrings || value !== '';
    })
  );

  const merged = mergeSettingsPreservingMaskedValues(
    getStoredSettings(),
    filteredIncoming
  );
  setStoredSettings(merged);
  return merged;
}

export function hasConfiguredApiKey(
  settings: Record<string, string>,
  options: { allowServerMask?: boolean } = {}
): boolean {
  const key = (settings.MODEL_API_KEY || '').trim();
  if (!key) return false;
  if (key === SENSITIVE_SETTING_MASK) {
    return options.allowServerMask === true;
  }
  return true;
}
