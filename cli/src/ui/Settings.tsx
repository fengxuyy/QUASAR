/**
 * Interactive Settings Panel - allows viewing and editing environment variables
 * Shown when user types \settings in the CLI input
 */
import React, { useState, useEffect } from 'react';
import { Box, Text, useStdout, useInput } from 'ink';
import fs from 'fs';

import { checkpointDbPath, checkpointSettingsPath, ENV_VAR_DEFS, EnvVarDef } from '../utils/envDefaults.js';
import { cliTheme } from './theme.js';

// Initialize state from process.env, falling back to defaults and checking checkpoint
function initValues(): { vals: Record<string, string>, hasCheckpoint: boolean } {
    const vals: Record<string, string> = {};
    let hasCheckpoint = false;
    let checkpointSettings: Record<string, any> = {};

    try {
        const workspaceDir = process.env.HOME || '/workspace';
        const settingsPath = checkpointSettingsPath(workspaceDir);
        
        // Only load if both the checkpoint DB and settings file exist
        if (fs.existsSync(checkpointDbPath(workspaceDir)) && fs.existsSync(settingsPath)) {
            hasCheckpoint = true;
            const content = fs.readFileSync(settingsPath, 'utf-8');
            checkpointSettings = JSON.parse(content);
            
            // Extract MODEL from _usage_stats if needed
            if (!checkpointSettings.MODEL && checkpointSettings._usage_stats?.model_name) {
                checkpointSettings.MODEL = checkpointSettings._usage_stats.model_name;
            }
        }
    } catch (e) {
        // Silently ignore if file doesn't exist or is invalid
    }

    for (const def of ENV_VAR_DEFS) {
        // Priority: checkpoint settings > process.env > default value
        const val = hasCheckpoint && checkpointSettings[def.key] !== undefined
            ? checkpointSettings[def.key]
            : process.env[def.key];
            
        vals[def.key] = val || def.defaultValue || '';
    }
    return { vals, hasCheckpoint };
}

interface SettingsProps {
    onExit: () => void;
    sendToBridge: (msg: object) => void;
    highlightMissing?: string[];
    isActive?: boolean;
}

/** One terminal column: normal char, caret on that char, or trailing caret (no extra glyph). */
type EditCell =
    | { kind: 'char'; ch: string; atCursor: boolean }
    | { kind: 'trail' };

function buildEditCells(value: string, cursor: number): EditCell[] {
    const out: EditCell[] = [];
    for (let i = 0; i < value.length; i++) {
        out.push({ kind: 'char', ch: value[i], atCursor: cursor === i });
    }
    if (cursor >= value.length) {
        out.push({ kind: 'trail' });
    }
    return out;
}

function renderEditCells(cells: EditCell[], valWidth: number): React.ReactNode {
    const clipped =
        cells.length > valWidth ? cells.slice(cells.length - valWidth) : cells;
    const pad = Math.max(0, valWidth - clipped.length);
    return (
        <>
            {clipped.map((cell, idx) =>
                cell.kind === 'trail' ? (
                    <Text key={`c-${idx}`} dimColor inverse>
                        {' '}
                    </Text>
                ) : cell.atCursor ? (
                    <Text key={`c-${idx}`} dimColor inverse>
                        {cell.ch}
                    </Text>
                ) : (
                    <Text key={`c-${idx}`} color={cliTheme.ink.warning}>
                        {cell.ch}
                    </Text>
                ),
            )}
            {pad > 0 ? <Text color={cliTheme.ink.warning}>{' '.repeat(pad)}</Text> : null}
        </>
    );
}

const Settings: React.FC<SettingsProps> = ({ onExit, sendToBridge, highlightMissing, isActive = true }) => {
    const { stdout } = useStdout();
    const terminalWidth = stdout?.columns || 100;
    const availableWidth = Math.max(20, terminalWidth - 14);
    const leftMargin = Math.max(0, Math.floor((terminalWidth - availableWidth) / 2));

    const [selectedIndex, setSelectedIndex] = useState(0);
    const [startIndex, setStartIndex] = useState(0);
    const MAX_VISIBLE = 10;
    
    const [editMode, setEditMode] = useState(false);
    /** value + cursor index (0 … value.length) for free-text env vars */
    const [edit, setEdit] = useState({ value: '', cursor: 0 });
    
    // Snapshot of values and checkpoint status at open time
    const initialData = useState(() => initValues())[0];
    const [values, setValues] = useState<Record<string, string>>(initialData.vals);
    const hasCheckpoint = initialData.hasCheckpoint;
    const initialValues = initialData.vals;

    const keyWidth = Math.max(...ENV_VAR_DEFS.map(v => v.key.length));
    const panelWidth = Math.min(availableWidth - 2, keyWidth + 40);
    const contentWidth = panelWidth - 4;

    const topBorder = '╭─ Settings ' + '─'.repeat(Math.max(0, panelWidth - 13)) + '╮';
    const bottomBorder = '╰' + '─'.repeat(Math.max(0, panelWidth - 2)) + '╯';
    const divider = '├' + '─'.repeat(Math.max(0, panelWidth - 2)) + '┤';

    // Helper to update both state and process.env
    const setValue = (key: string, val: string) => {
        setValues(prev => ({ ...prev, [key]: val }));
        if (val === '') {
            delete process.env[key];
        } else {
            process.env[key] = val;
        }
    };

    useInput((input, key) => {
        if (editMode) {
            if (key.escape) {
                setEditMode(false);
                setEdit({ value: '', cursor: 0 });
                return;
            }
            if (key.return) {
                const def = ENV_VAR_DEFS[selectedIndex];
                setValue(def.key, edit.value.trim());
                setEditMode(false);
                setEdit({ value: '', cursor: 0 });
                return;
            }
            if (key.leftArrow) {
                setEdit(e => ({ ...e, cursor: Math.max(0, e.cursor - 1) }));
                return;
            }
            if (key.rightArrow) {
                setEdit(e => ({ ...e, cursor: Math.min(e.value.length, e.cursor + 1) }));
                return;
            }
            // Ink maps Mac ⌫ (0x7f) to key.delete, not key.backspace; treat both as delete-before-cursor.
            if (key.backspace || key.delete) {
                setEdit(e => {
                    if (e.cursor <= 0) return e;
                    return {
                        value: e.value.slice(0, e.cursor - 1) + e.value.slice(e.cursor),
                        cursor: e.cursor - 1,
                    };
                });
                return;
            }
            if (input && !key.ctrl && !key.meta) {
                setEdit(e => ({
                    value: e.value.slice(0, e.cursor) + input + e.value.slice(e.cursor),
                    cursor: e.cursor + input.length,
                }));
            }
            return;
        }

        // Navigation mode
        if (key.escape) {
            // Send changed env vars to Python bridge
            const updates: Record<string, string> = {};
            for (const def of ENV_VAR_DEFS) {
                const current = values[def.key] || '';
                const initial = initialValues[def.key] || '';
                if (current !== initial) {
                    updates[def.key] = current;
                }
            }
            if (Object.keys(updates).length > 0) {
                sendToBridge({ command: 'update_env', updates });
            }
            onExit();
            return;
        }
        if (key.upArrow) {
            const next = Math.max(0, selectedIndex - 1);
            setSelectedIndex(next);
            if (next < startIndex) setStartIndex(next);
            return;
        }
        if (key.downArrow) {
            const next = Math.min(ENV_VAR_DEFS.length - 1, selectedIndex + 1);
            setSelectedIndex(next);
            if (next >= startIndex + MAX_VISIBLE) setStartIndex(next - MAX_VISIBLE + 1);
            return;
        }

        // Cycle options helper
        const cycleOption = (dir: number) => {
            const def = ENV_VAR_DEFS[selectedIndex];
            if (!def.options) return;
            // Lock accuracy and granularity if checkpoint exists
            if (hasCheckpoint && (def.key === 'ACCURACY' || def.key === 'GRANULARITY')) return;
            
            const current = (values[def.key] || def.options[0]).toLowerCase();
            const idx = def.options.findIndex(o => o.toLowerCase() === current);
            const nextIdx = (idx + dir + def.options.length) % def.options.length;
            setValue(def.key, def.options[nextIdx]);
        };

        if (key.return) {
            const def = ENV_VAR_DEFS[selectedIndex];
            if (def.options) {
                cycleOption(1);
            } else {
                const v = values[def.key] || '';
                setEdit({ value: v, cursor: v.length });
                setEditMode(true);
            }
            return;
        }
        if (key.leftArrow) {
            cycleOption(-1);
            return;
        }
        if (key.rightArrow) {
            cycleOption(1);
            return;
        }
    }, { isActive });

    // Build each row with fixed-width content
    const renderRow = (def: EnvVarDef, idx: number) => {
        const isSelected = isActive && idx === selectedIndex;
        const isEditing = isSelected && editMode;
        const val = values[def.key] || '';
        const keyPadded = def.key.padEnd(keyWidth);

        // Build the value string (fixed width = contentWidth - keyWidth - 3)
        const valWidth = contentWidth - keyWidth - 3;
        const isMissing = highlightMissing?.includes(def.key) && !val;

        // For option fields, render each option as separate colored Text elements
        if (def.options && !isEditing) {
            const current = (val || def.options[0]).toLowerCase();
            const optParts = def.options.map(o => ({
                text: o.toLowerCase() === current ? `[${o}]` : ` ${o} `,
                isActive: o.toLowerCase() === current,
            }));
            const totalOptLen = optParts.reduce((sum, p) => sum + p.text.length, 0) + (optParts.length - 1); // spaces between
            const pad = Math.max(0, valWidth - totalOptLen);
            
            const isLocked = hasCheckpoint && (def.key === 'ACCURACY' || def.key === 'GRANULARITY');

            return (
                <Text key={def.key}>
                    <Text color={cliTheme.ink.primary}>│ </Text>
                    {isSelected ? <Text inverse bold>{keyPadded}</Text> : <Text bold>{keyPadded}</Text>}
                    <Text dimColor> : </Text>
                    {optParts.map((p, i) => (
                        <React.Fragment key={i}>
                            {i > 0 && <Text> </Text>}
                            {p.isActive ? (
                                <Text color={isLocked ? cliTheme.ink.muted : cliTheme.ink.accent} bold>{p.text}</Text>
                            ) : (
                                <Text dimColor>{p.text}</Text>
                            )}
                        </React.Fragment>
                    ))}
                    <Text>{' '.repeat(pad)}</Text>
                    <Text color={cliTheme.ink.primary}> │</Text>
                </Text>
            );
        }

        let valStr = '';
        let editCells: EditCell[] | null = null;

        if (isEditing) {
            editCells = buildEditCells(edit.value, edit.cursor);
        } else if (def.isSensitive && val) {
            valStr = 'Set'.padEnd(valWidth);
        } else if (!val) {
            valStr = isMissing ? '(REQUIRED)'.padEnd(valWidth) : '(not set)'.padEnd(valWidth);
        } else {
            valStr = val.length > valWidth
                ? val.substring(0, valWidth - 3) + '...'
                : val.padEnd(valWidth);
        }

        // Determine color
        const valColor = isEditing ? cliTheme.ink.warning
            : isMissing ? cliTheme.ink.danger
            : (def.isSensitive && val) ? cliTheme.ink.success
            : !val ? cliTheme.ink.muted
            : cliTheme.ink.primary;

        return (
            <Text key={def.key}>
                <Text color={cliTheme.ink.primary}>│ </Text>
                {isMissing 
                    ? (isSelected ? <Text inverse bold color={cliTheme.ink.danger}>{keyPadded}</Text> : <Text bold color={cliTheme.ink.danger}>{keyPadded}</Text>)
                    : (isSelected ? <Text inverse bold>{keyPadded}</Text> : <Text bold>{keyPadded}</Text>)}
                <Text dimColor> : </Text>
                {editCells ? (
                    renderEditCells(editCells, valWidth)
                ) : (
                    <Text color={valColor as any}>{valStr}</Text>
                )}
                <Text color={cliTheme.ink.primary}> │</Text>
            </Text>
        );
    };

    const visibleDefs = isActive ? ENV_VAR_DEFS.slice(startIndex, startIndex + MAX_VISIBLE) : ENV_VAR_DEFS;

    return (
        <Box flexDirection="column" marginLeft={leftMargin} paddingX={1} marginY={1}>
            <Text color={cliTheme.ink.primary}>{topBorder}</Text>
            {isActive && (
                <>
                    <Text>
                        <Text color={cliTheme.ink.primary}>│ </Text>
                        {startIndex > 0 ? (
                            <Text dimColor italic bold>
                                {` ↑ ${startIndex} more above `.padStart(Math.floor(contentWidth / 2) + 6).padEnd(contentWidth)}
                            </Text>
                        ) : (
                            <Text>{' '.repeat(contentWidth)}</Text>
                        )}
                        <Text color={cliTheme.ink.primary}> │</Text>
                    </Text>
                </>
            )}
            
            {visibleDefs.map((def, idx) => renderRow(def, isActive ? startIndex + idx : idx))}
            
            {isActive && (
                <>
                    <Text>
                        <Text color={cliTheme.ink.primary}>│ </Text>
                        {startIndex + MAX_VISIBLE < ENV_VAR_DEFS.length ? (
                            <Text dimColor italic bold>
                                {` ↓ ${ENV_VAR_DEFS.length - (startIndex + MAX_VISIBLE)} more below `.padStart(Math.floor(contentWidth / 2) + 7).padEnd(contentWidth)}
                            </Text>
                        ) : (
                            <Text>{' '.repeat(contentWidth)}</Text>
                        )}
                        <Text color={cliTheme.ink.primary}> │</Text>
                    </Text>
                    <Text color={cliTheme.ink.primary}>{divider}</Text>
                    <Text>
                        <Text color={cliTheme.ink.primary}>│ </Text>
                        {editMode ? (
                            <Text dimColor>{'Type value · ←→ cursor · Enter confirm · ESC cancel'.padEnd(contentWidth)}</Text>
                        ) : (
                            <Text dimColor>{'↑↓ Navigate · Enter/←→ Edit · ESC back'.padEnd(contentWidth)}</Text>
                        )}
                        <Text color={cliTheme.ink.primary}> │</Text>
                    </Text>
                    <Text>
                        <Text color={cliTheme.ink.primary}>│ </Text>
                        <Text dimColor>{'Changes apply to current session'.padEnd(contentWidth)}</Text>
                        <Text color={cliTheme.ink.primary}> │</Text>
                    </Text>
                    {hasCheckpoint && (
                        <Text>
                            <Text color={cliTheme.ink.primary}>│ </Text>
                            <Text color={cliTheme.ink.danger}>{'ACCURACY/GRANULARITY locked during checkpoint resume'.padEnd(contentWidth)}</Text>
                            <Text color={cliTheme.ink.primary}> │</Text>
                        </Text>
                    )}
                </>
            )}
            <Text color={cliTheme.ink.primary}>{bottomBorder}</Text>
        </Box>
    );
};

export default Settings;
