/**
 * RAG initialization status display
 */
import React from 'react';
import { Box, Text } from 'ink';
import Spinner from 'ink-spinner';
import type { RagStatusInfo } from '../../hooks/types.js';

const SpinnerComponent = Spinner as any;

interface RagStatusProps {
    ragStatus: RagStatusInfo;
    leftMargin: number;
}

const RagStatus: React.FC<RagStatusProps> = ({ ragStatus, leftMargin }) => {
    return (
        <Box flexDirection="column" marginLeft={leftMargin} paddingX={1}>
            <Box>
                {ragStatus.status === 'done' ? (
                    <Text color="green" bold>✓ </Text>
                ) : ragStatus.status === 'error' ? (
                    <Text color="red" bold>✗ </Text>
                ) : (
                    <Text color="cyan"><SpinnerComponent type="dots" /> </Text>
                )}
                <Text color="cyan" bold>{ragStatus.message}</Text>
            </Box>
            {ragStatus.status !== 'done' && ragStatus.detail && (
                <Box marginLeft={3}>
                    <Text dimColor>{ragStatus.detail} </Text>
                    {ragStatus.progress && (
                        <Text>
                            <Text color="cyan">
                                {'━'.repeat(Math.round((ragStatus.progress.current / ragStatus.progress.total) * 30))}
                            </Text>
                            <Text dimColor>
                                {'━'.repeat(30 - Math.round((ragStatus.progress.current / ragStatus.progress.total) * 30))}
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
