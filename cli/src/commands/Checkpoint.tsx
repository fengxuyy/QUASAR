import React from 'react';
import { Box, Text } from 'ink';
import fs from 'fs';
import path from 'path';
import { resolveWorkspaceDir } from '../utils/envDefaults.js';

interface CheckpointProps {
    args: string[];
}

const WORKSPACE_DIR = resolveWorkspaceDir();
const CHECKPOINT_SIDE_CARS = ['checkpoints.sqlite', 'checkpoints.sqlite-shm', 'checkpoints.sqlite-wal', 'checkpoint_settings.json'];
const CLEAR_PRESERVED_ENTRIES = new Set(['archive', 'docs']);
const FRESH_PRESERVED_ENTRIES = new Set(['docs']);

function clearWorkspace(preservedEntries: Set<string>): void {
    fs.mkdirSync(WORKSPACE_DIR, { recursive: true });

    for (const entry of fs.readdirSync(WORKSPACE_DIR, { withFileTypes: true })) {
        if (entry.name.startsWith('.') || preservedEntries.has(entry.name)) {
            continue;
        }

        const entryPath = path.join(WORKSPACE_DIR, entry.name);
        fs.rmSync(entryPath, { recursive: true, force: true });
    }

    fs.mkdirSync(path.join(WORKSPACE_DIR, 'logs'), { recursive: true });
}

function hasCheckpointArtifacts(): boolean {
    return CHECKPOINT_SIDE_CARS.some(fileName => fs.existsSync(path.join(WORKSPACE_DIR, fileName)));
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
    const subCommand = args[0];

    if (subCommand === 'clear') {
        try {
            const hadCheckpoint = hasCheckpointArtifacts();
            clearWorkspace(CLEAR_PRESERVED_ENTRIES);
            return (
                <Box flexDirection="column" padding={1}>
                    <Text color="green">
                        {hadCheckpoint ? '✔ Active checkpoint cleared.' : '✔ Workspace cleared.'}
                    </Text>
                    <Text dimColor>Archived runs were preserved.</Text>
                </Box>
            );
        } catch (e) {
            return <Box padding={1}><Text color="red">✖ Failed to clear workspace: {(e as Error).message}</Text></Box>;
        }
    }

    if (subCommand === 'fresh') {
        try {
            const hadWorkspaceState = hasWorkspaceArtifacts(FRESH_PRESERVED_ENTRIES);
            clearWorkspace(FRESH_PRESERVED_ENTRIES);
            return (
                <Box flexDirection="column" padding={1}>
                    <Text color="green">
                        {hadWorkspaceState ? '✔ Workspace and archives cleared.' : '✔ Workspace already clean.'}
                    </Text>
                    <Text dimColor>Only docs and dotfiles were preserved.</Text>
                </Box>
            );
        } catch (e) {
            return <Box padding={1}><Text color="red">✖ Failed to clear workspace and archive: {(e as Error).message}</Text></Box>;
        }
    }

    return (
        <Box padding={1}>
            <Text>Unknown checkpoint command. Use clear or fresh.</Text>
        </Box>
    );
};

export default Checkpoint;
