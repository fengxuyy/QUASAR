/**
 * Active agent status display with spinner
 */
import React from 'react';
import { Box, Text } from 'ink';
import type { AgentInfo } from '../../hooks/types.js';
import { INDENT_EVALUATOR, INDENT_AGENT } from '../../utils/constants.js';
import TriangleSpinner from './TriangleSpinner.js';
import DotsSpinner from './DotsSpinner.js';
import { cliTheme } from '../theme.js';

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
                    <Text color={cliTheme.ink.muted}>{cliTheme.glyph.branch} </Text>
                    <Text color={cliTheme.ink.danger} bold>{cliTheme.glyph.error} API Error</Text>
                    <Text color={cliTheme.ink.muted}> (see quasar_logs/conversation.md)</Text>
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

    const statusColor = isApiRetrying ? cliTheme.ink.warning : (isPanelStatus ? cliTheme.ink.primary : cliTheme.ink.blue);

    return (
        <Box marginLeft={indent} paddingX={1}>
            <Text>
                <Text color={cliTheme.ink.muted}>{cliTheme.glyph.branch} </Text>
                {!agent.isStreaming && (
                    <Text color={statusColor}>
                        {isPanelStatus ? <TriangleSpinner /> : <DotsSpinner />}
                        {' '}
                    </Text>
                )}
                <Text color={agent.isStreaming ? cliTheme.ink.text : statusColor} bold={!agent.isStreaming}>
                    {agent.statusText}
                </Text>
            </Text>
        </Box>
    );
};

export default ActiveAgentStatus;
