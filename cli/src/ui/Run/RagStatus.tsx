/**
 * RAG initialization status display
 */
import React from 'react';
import { Box, Text, useStdout } from 'ink';
import type { RagStatusInfo } from '../../hooks/types.js';
import DotsSpinner from './DotsSpinner.js';
import { cliTheme } from '../theme.js';

interface RagStatusProps {
    ragStatus: RagStatusInfo;
    leftMargin: number;
    availableWidth: number;
}

const RagStatus: React.FC<RagStatusProps> = ({ ragStatus, leftMargin, availableWidth }) => {
    const { stdout } = useStdout();
    const terminalWidth = stdout?.columns || 100;
    const panelWidth = Math.max(30, availableWidth || Math.max(20, terminalWidth - 14));
    const progressWidth = Math.max(12, Math.min(32, panelWidth - 28));
    const progressRatio = ragStatus.progress && ragStatus.progress.total > 0
        ? ragStatus.progress.current / ragStatus.progress.total
        : 0;
    const progressCurrent = Math.max(0, Math.min(progressWidth, Math.round(progressRatio * progressWidth)));
    const borderColor = ragStatus.status === 'error'
        ? cliTheme.ink.danger
        : ragStatus.status === 'done'
            ? cliTheme.ink.success
            : cliTheme.ink.primary;

    return (
        <Box
            flexDirection="column"
            marginLeft={leftMargin}
            paddingX={1}
            borderStyle="round"
            borderColor={borderColor}
            width={panelWidth}
        >
            <Box>
                {ragStatus.status === 'done' ? (
                    <Text color={cliTheme.ink.success} bold>{cliTheme.glyph.success} </Text>
                ) : ragStatus.status === 'error' ? (
                    <Text color={cliTheme.ink.danger} bold>{cliTheme.glyph.error} </Text>
                ) : (
                    <Text color={cliTheme.ink.primary}><DotsSpinner /> </Text>
                )}
                <Text color={borderColor} bold>{ragStatus.message}</Text>
            </Box>
            {ragStatus.status !== 'done' && ragStatus.detail && (
                <Box marginLeft={3}>
                    <Text dimColor>{ragStatus.detail} </Text>
                    {ragStatus.progress && (
                        <Text>
                            <Text color={cliTheme.ink.primary}>
                                {'━'.repeat(progressCurrent)}
                            </Text>
                            <Text dimColor>
                                {'━'.repeat(progressWidth - progressCurrent)}
                            </Text>
                            <Text dimColor> {ragStatus.progress.current}/{ragStatus.progress.total}</Text>
                        </Text>
                    )}
                </Box>
            )}
        </Box>
    );
};

export default RagStatus;
