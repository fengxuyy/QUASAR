import fs from 'node:fs';
import path from 'node:path';

const sanitizeSettings = (
  settings: unknown,
  allowedKeys: ReadonlySet<string>
): Record<string, string> => {
  if (!settings || typeof settings !== 'object' || Array.isArray(settings)) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(settings as Record<string, unknown>).filter(
      ([key, value]) => allowedKeys.has(key) && typeof value === 'string'
    )
  ) as Record<string, string>;
};

export const loadPersistedSettings = (
  filePath: string,
  allowedKeys: ReadonlySet<string>
): Record<string, string> | null => {
  if (!fs.existsSync(filePath)) {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    return sanitizeSettings(parsed, allowedKeys);
  } catch {
    return null;
  }
};

export const savePersistedSettings = (
  filePath: string,
  settings: Record<string, string>,
  allowedKeys: ReadonlySet<string>
): void => {
  const persistedSettings = sanitizeSettings(settings, allowedKeys);
  const tempPath = `${filePath}.tmp`;

  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  try {
    fs.writeFileSync(tempPath, `${JSON.stringify(persistedSettings, null, 2)}\n`, {
      encoding: 'utf-8',
      mode: 0o600,
    });
    fs.renameSync(tempPath, filePath);
    fs.chmodSync(filePath, 0o600);
  } finally {
    if (fs.existsSync(tempPath)) {
      fs.unlinkSync(tempPath);
    }
  }
};
