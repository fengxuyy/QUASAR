/**
 * Status Renderer Components
 * Extracted from StaticItemRenderer.tsx for maintainability
 */
import React from 'react';
import { Box, Text } from 'ink';
import { truncateText, getVisualLength, capitalizeFirst } from '../../../utils/helpers.js';
import { INDENT_EVALUATOR, INDENT_AGENT, OFFSET_PLAN, OFFSET_SUMMARY } from '../../../utils/constants.js';
import Banner from '../../Banner.js';
import { cliChalk, cliTheme } from '../../theme.js';

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
 * Agent Header (e.g. "◆ Strategist")
 */
export function AgentHeaderRenderer({ agentName, id, leftMargin }: AgentHeaderRendererProps): React.ReactElement {
    return (
        <Box key={id} marginLeft={leftMargin} marginTop={1}>
            <Text>{cliChalk.accentBold(`${cliTheme.glyph.agent} ${capitalizeFirst(agentName)}`)}</Text>
        </Box>
    );
}

/**
 * Evaluator Header with tree branch
 */
export function EvaluatorHeaderRenderer({ agentName, id, leftMargin }: AgentHeaderRendererProps): React.ReactElement {
    return (
        <Box key={id} marginLeft={leftMargin + INDENT_AGENT} paddingX={1}>
            <Text>{cliChalk.muted(`${cliTheme.glyph.branch} `)}</Text>
            <Text>{cliChalk.accentBold(`${cliTheme.glyph.agent} ${capitalizeFirst(agentName)}`)}</Text>
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
    
    let toolColor: string;
    let icon: string;
    let displayContent = content;
    
    if (isError) {
        toolColor = cliTheme.ink.danger;
        icon = cliTheme.glyph.error;
    } else {
        toolColor = cliTheme.ink.success;
        icon = cliTheme.glyph.success;
    }
    
    return (
        <Box key={id} marginLeft={toolIndent} paddingX={1}>
            <Text>{isError ? cliChalk.danger(`${cliTheme.glyph.branch} `) : cliChalk.muted(`${cliTheme.glyph.branch} `)}</Text>
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
            <Text>{cliChalk.muted(`${cliTheme.glyph.branch} `)}</Text>
            {isApiError ? (
                <>
                    <Text color={cliTheme.ink.danger} bold>{cliTheme.glyph.error} API Error</Text>
                    <Text color={cliTheme.ink.muted}> (see quasar_logs/conversation.md)</Text>
                </>
            ) : isInterrupt ? (
                <Text color={cliTheme.ink.danger} bold>{truncateText(content, logMaxWidth)}</Text>
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
            <Text>{cliChalk.muted(`${cliTheme.glyph.branch} `)}</Text>
            <Text color={cliTheme.ink.success} bold>{cliTheme.glyph.success} {content.replace('Creating', 'Created')}</Text>
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
    const statusColor = isRetry ? cliTheme.ink.warning : (isFinalFailure || isFailure ? cliTheme.ink.danger : cliTheme.ink.success);
    const icon = isRetry ? cliTheme.glyph.retry : (isFailure ? cliTheme.glyph.error : cliTheme.glyph.success);
    
    return (
        <Box key={id} marginLeft={leftMargin + INDENT_EVALUATOR} paddingX={1}>
            <Text>{cliChalk.muted(`${cliTheme.glyph.branch} `)}</Text>
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
                <Text key={idx} color={cliTheme.ink.muted}>{line}</Text>
            ))}
        </Box>
    );
}

// ========== BANNER RENDERER ==========

interface BannerRendererProps {
    id: string;
}

/**
 * Banner renderer (delegates to Banner component)
 */
export function BannerRenderer({ id }: BannerRendererProps): React.ReactElement {
    return (
        <Box key={id} flexDirection="column">
            <Banner />
        </Box>
    );
}
