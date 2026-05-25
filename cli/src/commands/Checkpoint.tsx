import React from 'react';
import { Box, Text } from 'ink';
import fs from 'fs';
import path from 'path';
import { spawnSync } from 'child_process';
import { fileURLToPath } from 'url';
import { checkpointArtifactPath, checkpointDbPath, QUASAR_LOGS_DIR, resolveWorkspaceDir } from '../utils/envDefaults.js';
import { cliTheme } from '../ui/theme.js';

interface CheckpointProps {
    args: string[];
}

const WORKSPACE_DIR = resolveWorkspaceDir();
const CHECKPOINT_SIDE_CARS = ['checkpoints.sqlite', 'checkpoints.sqlite-shm', 'checkpoints.sqlite-wal', 'checkpoint_settings.json'];
const CLEAR_PRESERVED_ENTRIES = new Set(['quasar_archive', 'docs']);
const FRESH_PRESERVED_ENTRIES = new Set(['docs']);

function projectRoot(): string {
    const compiledRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
    const candidates = [process.cwd(), compiledRoot, '/app'];
    return candidates.find(candidate => fs.existsSync(path.join(candidate, 'bridge.py'))) || process.cwd();
}

function clearWorkspace(preservedEntries: Set<string>): void {
    fs.mkdirSync(WORKSPACE_DIR, { recursive: true });

    for (const entry of fs.readdirSync(WORKSPACE_DIR, { withFileTypes: true })) {
        if (entry.name.startsWith('.') || preservedEntries.has(entry.name)) {
            continue;
        }

        const entryPath = path.join(WORKSPACE_DIR, entry.name);
        fs.rmSync(entryPath, { recursive: true, force: true });
    }

    fs.mkdirSync(path.join(WORKSPACE_DIR, QUASAR_LOGS_DIR), { recursive: true });
}

function clearCheckpointArtifacts(): void {
    for (const fileName of CHECKPOINT_SIDE_CARS) {
        fs.rmSync(checkpointArtifactPath(WORKSPACE_DIR, fileName), { force: true });
        fs.rmSync(path.join(WORKSPACE_DIR, fileName), { force: true });
    }
}

function hasCheckpointArtifacts(): boolean {
    return CHECKPOINT_SIDE_CARS.some(fileName =>
        fs.existsSync(checkpointArtifactPath(WORKSPACE_DIR, fileName)) ||
        fs.existsSync(path.join(WORKSPACE_DIR, fileName))
    );
}

function isStrategistStageCheckpoint(): boolean {
    if (!fs.existsSync(checkpointDbPath(WORKSPACE_DIR))) {
        return false;
    }

    const root = projectRoot();
    const result = spawnSync('python3', ['-c', `
import os
import sys

sys.path.insert(0, ${JSON.stringify(root)})
os.environ["WORKSPACE_DIR"] = ${JSON.stringify(WORKSPACE_DIR)}

from src.checkpoint import checkpoint_is_strategist_stage

print("true" if checkpoint_is_strategist_stage() else "false")
`], {
        cwd: root,
        env: { ...process.env, WORKSPACE_DIR },
        encoding: 'utf-8',
    });

    if (result.error || result.status !== 0) {
        return false;
    }

    return result.stdout.trim().split(/\s+/).pop() === 'true';
}

function hasWorkspaceArtifacts(preservedEntries: Set<string>): boolean {
    if (!fs.existsSync(WORKSPACE_DIR)) {
        return false;
    }

    return fs.readdirSync(WORKSPACE_DIR, { withFileTypes: true }).some(entry => {
        return !entry.name.startsWith('.') && !preservedEntries.has(entry.name);
    });
}

const Checkpoint: React.FC<CheckpointProps> = ({ args }) => {
    const renderedResultRef = React.useRef<React.ReactElement | null>(null);
    if (renderedResultRef.current) {
        return renderedResultRef.current;
    }

    const subCommand = args[0];

    if (subCommand === 'clear') {
        try {
            const hadCheckpoint = hasCheckpointArtifacts();
            const strategistStage = isStrategistStageCheckpoint();
            if (strategistStage) {
                clearCheckpointArtifacts();
            } else {
                clearWorkspace(CLEAR_PRESERVED_ENTRIES);
            }
            renderedResultRef.current = (
                <Box flexDirection="column" padding={1}>
                    <Text color={cliTheme.ink.success}>
                        {hadCheckpoint ? `${cliTheme.glyph.success} Active checkpoint cleared.` : `${cliTheme.glyph.success} Workspace cleared.`}
                    </Text>
                    <Text dimColor>
                        {strategistStage ? 'Workspace files were preserved.' : 'Archived runs were preserved.'}
                    </Text>
                </Box>
            );
            return renderedResultRef.current;
        } catch (e) {
            renderedResultRef.current = <Box padding={1}><Text color={cliTheme.ink.danger}>{cliTheme.glyph.error} Failed to clear workspace: {(e as Error).message}</Text></Box>;
            return renderedResultRef.current;
        }
    }

    if (subCommand === 'fresh') {
        try {
            const hadWorkspaceState = hasWorkspaceArtifacts(FRESH_PRESERVED_ENTRIES);
            clearWorkspace(FRESH_PRESERVED_ENTRIES);
            renderedResultRef.current = (
                <Box flexDirection="column" padding={1}>
                    <Text color={cliTheme.ink.success}>
                        {hadWorkspaceState ? `${cliTheme.glyph.success} Workspace and archives cleared.` : `${cliTheme.glyph.success} Workspace already clean.`}
                    </Text>
                    <Text dimColor>Only docs and dotfiles were preserved.</Text>
                </Box>
            );
            return renderedResultRef.current;
        } catch (e) {
            renderedResultRef.current = <Box padding={1}><Text color={cliTheme.ink.danger}>{cliTheme.glyph.error} Failed to clear workspace and archive: {(e as Error).message}</Text></Box>;
            return renderedResultRef.current;
        }
    }

    renderedResultRef.current = (
        <Box padding={1}>
            <Text>Unknown checkpoint command. Use clear or fresh.</Text>
        </Box>
    );
    return renderedResultRef.current;
};

export default Checkpoint;
