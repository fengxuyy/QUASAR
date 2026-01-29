/**
 * Status Renderer Components
 * Extracted from StaticItemRenderer.tsx for maintainability
 */
import React from 'react';
import { Box, Text } from 'ink';
import chalk from 'chalk';
import { truncateText, getVisualLength, capitalizeFirst } from '../../../utils/helpers.js';
import { INDENT_EVALUATOR, INDENT_AGENT, OFFSET_PLAN, OFFSET_SUMMARY } from '../../../utils/constants.js';
import Banner from '../../Banner.js';

interface BaseRendererProps {
    leftMargin: number;
    terminalWidth: number;
    id: string;
}

// ========== HEADER RENDERERS ==========

interface AgentHeaderRendererProps extends BaseRendererProps {
    agentName: string;
}

/**
 * Agent Header (e.g. "¤ Strategist")
 */
export function AgentHeaderRenderer({ agentName, id, leftMargin }: AgentHeaderRendererProps): React.ReactElement {
    return (
        <Box key={id} marginLeft={leftMargin} paddingX={1} marginTop={1}>
            <Text>{chalk.ansi256(99).bold(`¤ ${capitalizeFirst(agentName)}`)}</Text>
        </Box>
    );
}

/**
 * Evaluator Header with tree branch
 */
export function EvaluatorHeaderRenderer({ agentName, id, leftMargin }: AgentHeaderRendererProps): React.ReactElement {
    return (
        <Box key={id} marginLeft={leftMargin + INDENT_AGENT} paddingX={1}>
            <Text>{chalk.ansi256(253)('L ')}</Text>
            <Text>{chalk.ansi256(99).bold(`¤ ${capitalizeFirst(agentName)}`)}</Text>
        </Box>
    );
}

// ========== TOOL & LOG RENDERERS ==========

interface ToolRendererProps extends BaseRendererProps {
    content: string;
    agentName: string;
    isError: boolean;
}

/**
 * Tool execution status (e.g. "✓ Searched web for...")
 */
export function ToolRenderer({ content, agentName, isError, id, leftMargin, terminalWidth }: ToolRendererProps): React.ReactElement {
    const toolIndent = agentName === 'evaluator' ? leftMargin + INDENT_EVALUATOR : leftMargin + INDENT_AGENT;
    const bannerWidth = Math.max(20, terminalWidth - 14);
    const parentOffset = agentName === 'evaluator' ? OFFSET_SUMMARY : OFFSET_PLAN;
    const toolMaxWidth = Math.max(10, bannerWidth - parentOffset - 4 - 2);
    const isPanelTool = content.toLowerCase().includes('wrote');
    const isExecuteTool = content.toLowerCase().includes('executed');
    
    let toolColor: string;
    let icon: string;
    let displayContent = content;
    
    // "Reviewed Plan" and "Created Replan" should show with triangle (like current status indicator)
    const isReviewedPlan = content === 'Reviewed Plan' || content === 'Created Replan';
    
    if (isError && isExecuteTool) {
        toolColor = 'red';
        icon = '▲';
        displayContent = 'Error ' + content;
    } else if (isError) {
        toolColor = 'red';
        icon = '✗';
    } else if (isPanelTool || isExecuteTool || isReviewedPlan) {
        toolColor = 'cyan';
        icon = '▲';
    } else {
        toolColor = 'green';
        icon = '✓';
    }
    
    return (
        <Box key={id} marginLeft={toolIndent} paddingX={1}>
            <Text>{isError ? chalk.red('L ') : chalk.ansi256(253)('L ')}</Text>
            <Text color={toolColor as any} bold>{icon} {truncateText(displayContent, toolMaxWidth)}</Text>
        </Box>
    );
}

interface LogRendererProps extends BaseRendererProps {
    content: string;
    agentName: string;
}

/**
 * Log line renderer
 */
export function LogRenderer({ content, agentName, id, leftMargin, terminalWidth }: LogRendererProps): React.ReactElement {
    const logIndent = agentName === 'evaluator' ? leftMargin + INDENT_EVALUATOR : leftMargin + INDENT_AGENT;
    const logMaxWidth = Math.max(10, terminalWidth - logIndent - 2);
    const isInterrupt = content.includes('Run Interrupted');
    const isApiError = content.includes('API Error');
    
    return (
        <Box key={id} marginLeft={logIndent} paddingX={1}>
            <Text>{chalk.ansi256(253)('L ')}</Text>
            {isApiError ? (
                <>
                    <Text color="red" bold>✗ API Error</Text>
                    <Text color="gray"> (see logs/conversation.md)</Text>
                </>
            ) : isInterrupt ? (
                <Text color="red" bold>{truncateText(content, logMaxWidth)}</Text>
            ) : (
                <Text>{truncateText(content, logMaxWidth)}</Text>
            )}
        </Box>
    );
}

// ========== STATUS RENDERERS ==========

interface AgentStatusRendererProps extends BaseRendererProps {
    content: string;
}

/**
 * Agent completion status
 */
export function AgentStatusRenderer({ content, id, leftMargin }: AgentStatusRendererProps): React.ReactElement {
    return (
        <Box key={id} marginLeft={leftMargin + INDENT_AGENT} paddingX={1}>
            <Text>{chalk.ansi256(253)('L ')}</Text>
            <Text color="cyan" bold>▲ {content.replace('Creating', 'Created')}</Text>
        </Box>
    );
}

/**
 * Evaluator status with contextual coloring
 */
export function EvaluatorStatusRenderer({ content, id, leftMargin }: AgentStatusRendererProps): React.ReactElement {
    const isRetry = content.includes('Retry');
    const isFinalFailure = content.includes('Task Skipped');
    const isFailure = content.includes('Failed');
    const statusColor = isRetry ? 'yellow' : (isFinalFailure || isFailure ? 'red' : 'cyan');
    const icon = isRetry ? '⟳' : (isFailure ? '✗' : '▲');
    
    return (
        <Box key={id} marginLeft={leftMargin + INDENT_EVALUATOR} paddingX={1}>
            <Text>{chalk.ansi256(253)('L ')}</Text>
            <Text color={statusColor} bold>{icon} {content.replace('Creating', 'Created')}</Text>
        </Box>
    );
}

// ========== MODEL TEXT RENDERER ==========

interface ModelTextRendererProps extends BaseRendererProps {
    content: string;
    agentName: string;
}

/**
 * Model reasoning/answer text with wrapping
 */
export function ModelTextRenderer({ content, agentName, id, leftMargin, terminalWidth }: ModelTextRendererProps): React.ReactElement {
    const textIndent = agentName === 'evaluator' ? leftMargin + INDENT_EVALUATOR : leftMargin + INDENT_AGENT;
    const textMaxWidth = Math.max(10, terminalWidth - textIndent - 4);
    
    const lines = content.split('\n');
    const wrappedLines: string[] = [];
    
    for (const line of lines) {
        if (line.length <= textMaxWidth) {
            wrappedLines.push(line);
        } else {
            const words = line.split(' ');
            let currentLine = '';
            for (const word of words) {
                if (currentLine.length + word.length + 1 <= textMaxWidth) {
                    currentLine = currentLine ? currentLine + ' ' + word : word;
                } else {
                    if (currentLine) wrappedLines.push(currentLine);
                    currentLine = word;
                }
            }
            if (currentLine) wrappedLines.push(currentLine);
        }
    }
    
    return (
        <Box key={id} marginLeft={textIndent} paddingX={1} flexDirection="column">
            {wrappedLines.map((line, idx) => (
                <Text key={idx} dimColor>{line}</Text>
            ))}
        </Box>
    );
}

// ========== BANNER RENDERER ==========

interface BannerRendererProps {
    modelName: string;
    pmgConfigured: boolean;
    id: string;
}

/**
 * Banner renderer (delegates to Banner component)
 */
export function BannerRenderer({ modelName, pmgConfigured, id }: BannerRendererProps): React.ReactElement {
    return (
        <Box key={id} flexDirection="column">
            <Banner modelName={modelName} pmgConfigured={pmgConfigured} />
        </Box>
    );
}
