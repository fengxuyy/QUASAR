import fs from 'fs';
import path from 'path';
import { resolveWorkspaceDir } from './envDefaults.js';
import { CLI_COMMANDS } from './commandRegistry.js';

export type ReportKind = 'execution-overview' | 'usage-report';

interface ReportDef {
    kind: ReportKind;
    command: string;
    title: string;
    fileName: string;
}

export interface LoadedReport {
    kind: ReportKind;
    title: string;
    fileName: string;
    content: string;
    sourcePath?: string;
    error?: string;
}

const REPORT_DEFS: Record<ReportKind, ReportDef> = {
    'execution-overview': {
        kind: 'execution-overview',
        command: CLI_COMMANDS.find(command => command.id === 'execution-overview')?.command || '\\execution-overview',
        title: 'Execution Overview',
        fileName: 'execution_overview.md',
    },
    'usage-report': {
        kind: 'usage-report',
        command: CLI_COMMANDS.find(command => command.id === 'usage-report')?.command || '\\usage-report',
        title: 'Usage Report',
        fileName: 'usage_report.md',
    },
};

const MAX_REPORT_CHARS = 180_000;

export function normalizeReportCommand(input: string | undefined): ReportKind | null {
    const command = (input || '').trim().toLowerCase();
    if (command === '\\execution-overview' || command === 'execution-overview') {
        return 'execution-overview';
    }
    if (command === '\\usage-report' || command === 'usage-report') {
        return 'usage-report';
    }
    return null;
}

function latestArchiveRun(workspaceDir: string): string | null {
    const archiveDir = path.join(workspaceDir, 'quasar_archive');
    if (!fs.existsSync(archiveDir)) return null;

    const runs = fs.readdirSync(archiveDir)
        .map(name => path.join(archiveDir, name))
        .filter(runPath => {
            try {
                return fs.statSync(runPath).isDirectory();
            } catch {
                return false;
            }
        })
        .sort((a, b) => {
            try {
                return fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs;
            } catch {
                return b.localeCompare(a);
            }
        });

    return runs[0] || null;
}

function reportCandidates(workspaceDir: string, fileName: string): string[] {
    const candidates = [
        path.join(workspaceDir, 'quasar_logs', fileName),
        path.join(workspaceDir, 'logs', fileName),
        path.join(workspaceDir, fileName),
    ];

    const latestRun = latestArchiveRun(workspaceDir);
    if (latestRun) {
        candidates.push(path.join(latestRun, 'quasar_logs', fileName));
    }

    return candidates;
}

export function loadReport(kind: ReportKind): LoadedReport {
    const def = REPORT_DEFS[kind];
    const workspaceDir = resolveWorkspaceDir();

    for (const candidate of reportCandidates(workspaceDir, def.fileName)) {
        if (!fs.existsSync(candidate)) continue;
        try {
            let content = fs.readFileSync(candidate, 'utf-8');
            if (content.length > MAX_REPORT_CHARS) {
                content = content.slice(0, MAX_REPORT_CHARS) + '\n\n... [Report truncated for CLI display]';
            }
            return {
                kind,
                title: def.title,
                fileName: def.fileName,
                content,
                sourcePath: candidate,
            };
        } catch (error) {
            return {
                kind,
                title: def.title,
                fileName: def.fileName,
                content: `Could not read ${def.fileName}.`,
                sourcePath: candidate,
                error: error instanceof Error ? error.message : String(error),
            };
        }
    }

    return {
        kind,
        title: def.title,
        fileName: def.fileName,
        content: `No ${def.fileName} found in the current workspace logs.`,
        error: 'Report file not found.',
    };
}

export function reportCommandHelp(): string {
    return Object.values(REPORT_DEFS).map(def => def.command).join(', ');
}
