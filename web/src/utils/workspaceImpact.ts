import { parseStatusWithFileLinks } from './fileLinkUtils';
import type { BridgeMessage } from './messageHelpers';

export type WorkspaceImpactKind = 'read' | 'edit' | 'execute' | 'error' | 'reference';

export interface WorkspaceImpactItem {
  path: string;
  displayName: string;
  kind: WorkspaceImpactKind;
  count: number;
  lastStatus: string;
  lastTask: number | null;
  isError: boolean;
}

type MutableWorkspaceImpactItem = WorkspaceImpactItem & {
  kindCounts: Record<WorkspaceImpactKind, number>;
  lastSeen: number;
};

const KIND_PRIORITY: WorkspaceImpactKind[] = ['edit', 'execute', 'read', 'reference'];

function normalizeWorkspaceImpactPath(path: string): string {
  const trimmedPath = path.trim();

  if (!trimmedPath || trimmedPath === '.' || trimmedPath === 'workspace') {
    return '.';
  }

  return trimmedPath.replace(/^\.?\/+/, '').replace(/\/+$/, '');
}

function getPathDisplayName(path: string): string {
  const normalizedPath = normalizeWorkspaceImpactPath(path);

  if (normalizedPath === '.') {
    return 'workspace';
  }

  const segments = normalizedPath.split('/');
  return segments[segments.length - 1] || normalizedPath;
}

function inferImpactKind(status: string, isError: boolean): WorkspaceImpactKind {
  if (isError) {
    return 'error';
  }

  const normalizedStatus = status.trim().toLowerCase();

  if (/^(read|reading|listed|listing)\b/.test(normalizedStatus)) {
    return 'read';
  }

  if (/^(edit|edited|editing|wrote|writing|created|creating|deleted|deleting|renamed|renaming|moved|moving)\b/.test(normalizedStatus)) {
    return 'edit';
  }

  if (/^(executed|executing|analyzed|analyzing)\b/.test(normalizedStatus)) {
    return 'execute';
  }

  return 'reference';
}

function dominantKind(
  kindCounts: Record<WorkspaceImpactKind, number>,
  isError: boolean
): WorkspaceImpactKind {
  if (isError && kindCounts.error > 0) {
    return 'error';
  }

  let selected: WorkspaceImpactKind = 'reference';
  let selectedCount = kindCounts.reference;

  for (const kind of KIND_PRIORITY) {
    if (kindCounts[kind] > selectedCount) {
      selected = kind;
      selectedCount = kindCounts[kind];
    }
  }

  return selected;
}

function statusFileReferences(status: string): Array<{ path: string; displayName: string }> {
  return parseStatusWithFileLinks(status)
    .filter((segment) => segment.type === 'file' && !!segment.filePath)
    .map((segment) => {
      const path = normalizeWorkspaceImpactPath(segment.filePath || '');
      return {
        path,
        displayName: segment.content || getPathDisplayName(path),
      };
    });
}

function addImpact(
  items: Map<string, MutableWorkspaceImpactItem>,
  reference: { path: string; displayName: string },
  kind: WorkspaceImpactKind,
  status: string,
  taskNumber: number | null,
  isError: boolean,
  index: number
) {
  if (!reference.path) {
    return;
  }

  const existing = items.get(reference.path);

  if (existing) {
    existing.count += 1;
    existing.kindCounts[kind] += 1;
    existing.lastStatus = status;
    existing.lastTask = taskNumber;
    existing.isError = existing.isError || isError;
    existing.kind = dominantKind(existing.kindCounts, existing.isError);
    existing.lastSeen = index;
    return;
  }

  const kindCounts: Record<WorkspaceImpactKind, number> = {
    read: 0,
    edit: 0,
    execute: 0,
    error: 0,
    reference: 0,
  };
  kindCounts[kind] = 1;

  items.set(reference.path, {
    path: reference.path,
    displayName: reference.displayName || getPathDisplayName(reference.path),
    kind,
    count: 1,
    lastStatus: status,
    lastTask: taskNumber,
    isError,
    kindCounts,
    lastSeen: index,
  });
}

export function extractWorkspaceImpacts(messages: BridgeMessage[]): WorkspaceImpactItem[] {
  const items = new Map<string, MutableWorkspaceImpactItem>();
  let currentTaskNumber: number | null = null;

  messages.forEach((message, index) => {
    if (message.type === 'task_progress') {
      const nextTaskNumber = message.payload?.current;
      if (typeof nextTaskNumber === 'number') {
        currentTaskNumber = nextTaskNumber;
      }
      return;
    }

    const status =
      message.type === 'agent_event' && typeof message.payload?.status === 'string'
        ? message.payload.status.trim()
        : '';

    if (!status) {
      return;
    }

    const references = statusFileReferences(status);
    if (references.length === 0) {
      return;
    }

    const isError = message.payload?.is_error === true;
    const kind = inferImpactKind(status, isError);
    const taskNumber =
      typeof message._taskNum === 'number' ? message._taskNum : currentTaskNumber;

    references.forEach((reference) => {
      addImpact(items, reference, kind, status, taskNumber, isError, index);
    });
  });

  return Array.from(items.values())
    .sort((left, right) => {
      if (right.count !== left.count) {
        return right.count - left.count;
      }
      return right.lastSeen - left.lastSeen;
    })
    .map((item) => ({
      path: item.path,
      displayName: item.displayName,
      kind: item.kind,
      count: item.count,
      lastStatus: item.lastStatus,
      lastTask: item.lastTask,
      isError: item.isError,
    }));
}
