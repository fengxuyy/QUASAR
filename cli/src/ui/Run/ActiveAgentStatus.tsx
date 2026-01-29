/**
 * Active agent status display with spinner
 */
import React from 'react';
import { Box, Text } from 'ink';
import Spinner from 'ink-spinner';
import type { AgentInfo } from '../../hooks/types.js';
import { INDENT_EVALUATOR, INDENT_AGENT } from '../../utils/constants.js';
import TriangleSpinner from './TriangleSpinner.js';
import chalk from 'chalk';

const SpinnerComponent = Spinner as any;

interface ActiveAgentStatusProps {
    agent: AgentInfo;
    leftMargin: number;
    isEvaluator?: boolean;
}

const ActiveAgentStatus: React.FC<ActiveAgentStatusProps> = ({ agent, leftMargin, isEvaluator = false }) => {
    const indent = isEvaluator ? leftMargin + INDENT_EVALUATOR : leftMargin + INDENT_AGENT;
    
    // Check for API error states
    const isApiRetrying = agent.statusText?.includes('API Error - Retrying');
    const isApiFailed = agent.statusText?.startsWith('✗ API Error');
    
    // API retry always uses dots spinner, API failed shows no spinner (static error)
    if (isApiFailed) {
        return (
            <Box marginLeft={indent} paddingX={1}>
                <Text>
                    <Text>{chalk.ansi256(253)('L ')}</Text>
                    <Text color="red" bold>✗ API Error</Text>
                    <Text color="gray"> (see logs/conversation.md)</Text>
                </Text>
            </Box>
        );
    }
    
    // Determine if this is a panel-related status that needs the triangle spinner
    // API retry always uses dots spinner instead of triangle
    // "Analysing/Analyzing Request" should use dots spinner, not triangle
    const isAnalysingRequest = agent.statusText?.toLowerCase().includes('analysing') || 
                               agent.statusText?.toLowerCase().includes('analyzing');
    const isPanelStatus = !isApiRetrying && !isAnalysingRequest && (
        agent.name === 'strategist' || 
        agent.name === 'evaluator' || 
        (agent.name === 'operator' && (
            agent.statusText?.toLowerCase().includes('writing')
        )));

    const statusColor = isApiRetrying ? "yellow" : (isPanelStatus ? "cyan" : "blue");

    return (
        <Box marginLeft={indent} paddingX={1}>
            <Text>
                <Text>{chalk.ansi256(253)('L ')}</Text>
                {!agent.isStreaming && (
                    <Text color={statusColor}>
                        {isPanelStatus ? <TriangleSpinner /> : <SpinnerComponent type="dots" />}
                        {' '}
                    </Text>
                )}
                <Text color={agent.isStreaming ? "white" : statusColor} bold={!agent.isStreaming}>
                    {agent.statusText}
                </Text>
            </Text>
        </Box>
    );
};

export default ActiveAgentStatus;
