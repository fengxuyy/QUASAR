import type { ContextUsage } from '../hooks/useQuasarBridge';

export type ContextUsageTone = 'neutral' | 'safe' | 'warning' | 'danger';

export function formatTokenCount(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return '--';
  }
  return Math.round(value).toLocaleString();
}

export function formatUsagePercent(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return '--';
  }

  const rounded = Math.round(value * 10) / 10;
  if (Number.isInteger(rounded)) {
    return `${rounded.toFixed(0)}%`;
  }
  return `${rounded.toFixed(1)}%`;
}

export function getContextUsageTone(snapshot: ContextUsage | null | undefined): ContextUsageTone {
  if (!snapshot?.is_supported_model || snapshot.usage_percent == null) {
    return 'neutral';
  }
  if (snapshot.usage_percent >= 100) {
    return 'danger';
  }
  if (snapshot.usage_percent >= 75) {
    return 'warning';
  }
  return 'safe';
}

export function getContextUsageProgress(snapshot: ContextUsage | null | undefined): number {
  if (!snapshot?.is_supported_model || snapshot.usage_percent == null) {
    return 0;
  }
  return Math.max(0, Math.min(snapshot.usage_percent, 100));
}
