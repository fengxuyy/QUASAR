export const COMMAND_PREFIX = '\\';

export type CliCommandId = 'settings' | 'refresh' | 'execution-overview' | 'usage-report' | 'revert';

export interface CliCommandDefinition {
    id: CliCommandId;
    command: string;
    description: string;
}

export interface ParsedCliCommand {
    id: CliCommandId;
    command: string;
    args: string[];
}

export const CLI_COMMANDS: CliCommandDefinition[] = [
    {
        id: 'settings',
        command: '\\settings',
        description: 'Open system settings',
    },
    {
        id: 'refresh',
        command: '\\refresh',
        description: 'Clear the screen and reload checkpoint state',
    },
    {
        id: 'execution-overview',
        command: '\\execution-overview',
        description: 'Show execution_overview.md',
    },
    {
        id: 'usage-report',
        command: '\\usage-report',
        description: 'Show usage_report.md',
    },
    {
        id: 'revert',
        command: '\\revert',
        description: 'Revert to a task, e.g. \\revert 2',
    },
];

export function parseCliCommand(input: string | undefined): ParsedCliCommand | null {
    const trimmed = (input || '').trim();
    if (!trimmed) return null;

    const [rawCommand, ...args] = trimmed.split(/\s+/);
    const normalizedCommand = rawCommand.toLowerCase();
    const matched = CLI_COMMANDS.find(def => def.command === normalizedCommand);
    const id = matched?.id ?? null;

    if (!id) return null;
    if (id !== 'revert' && args.length > 0) return null;

    return {
        id,
        command: matched?.command ?? normalizedCommand,
        args,
    };
}

export function normalizeBackslashCommand(input: string | undefined): CliCommandId | null {
    return parseCliCommand(input)?.id ?? null;
}

export function matchingBackslashCommands(input: string): CliCommandDefinition[] {
    if (!input.startsWith(COMMAND_PREFIX)) return [];
    const command = input.trim().toLowerCase();
    return CLI_COMMANDS.filter(def => def.command.startsWith(command));
}

export function commandHelpList(): string {
    return CLI_COMMANDS.map(def => def.command).join(', ');
}
