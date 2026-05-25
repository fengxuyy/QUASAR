import React from 'react';
import { Box, Text, Static } from 'ink';
import Spinner from 'ink-spinner';
import ExecutionPlanPanel from './ExecutionPlanPanel.js';
import { cliChalk, cliTheme } from './theme.js';

interface HistoryItem {
    type: 'tool' | 'log';
    content: string;
}

interface AgentInfo {
    name: string;
    status: 'active' | 'complete';
    statusText: string;
    history?: HistoryItem[];
    isStreaming?: boolean;
}



interface AgentTreeProps {
    systemStatus: 'idle' | 'running' | 'completed';
    agents: AgentInfo[];
    planContent: string | null;
    isPlanComplete: boolean;
    committedPlanLines: string[];
}

const SpinnerComponent = Spinner as any;

// Collect all static (committed) history items across agents for Static rendering
interface StaticHistoryItem {
    id: string;
    agentName: string;
    type: 'header' | 'tool' | 'log' | 'evaluator-header';
    content: string;
    indent: number;
}

const AgentTree: React.FC<AgentTreeProps> = ({ 
    systemStatus, 
    agents, 
    planContent, 
    isPlanComplete,
    committedPlanLines
}) => {
    // Don't render if system is idle
    if (systemStatus === 'idle') {
        return null;
    }

    // Separate agents by hierarchy: top-level and evaluator (child of operator)
    const topLevelAgents = agents.filter(a => a.name !== 'system' && a.name !== 'evaluator');
    const evaluatorAgent = agents.find(a => a.name === 'evaluator');

    // Build static history items for <Static> rendering
    // This prevents re-rendering of committed content and allows scrolling
    const staticItems: StaticHistoryItem[] = [];

    for (const agent of topLevelAgents) {
        // Agent header (only add once when agent has history or is complete)
        if (agent.history && agent.history.length > 0) {
            // Check if we already added this agent's header
            const hasHeader = staticItems.some(item => item.id === `header-${agent.name}`);
            if (!hasHeader) {
                staticItems.push({
                    id: `header-${agent.name}`,
                    agentName: agent.name,
                    type: 'header',
                    content: capitalizeFirst(agent.name),
                    indent: 0
                });
            }
        }

        // Add committed history items
        if (agent.history) {
            for (let i = 0; i < agent.history.length; i++) {
                const item = agent.history[i];
                staticItems.push({
                    id: `${agent.name}-history-${i}`,
                    agentName: agent.name,
                    type: item.type,
                    content: item.content,
                    indent: 2
                });
            }
        }

        // Add evaluator's committed history under operator
        if (agent.name === 'operator' && evaluatorAgent) {
            if (evaluatorAgent.history && evaluatorAgent.history.length > 0) {
                // Evaluator header
                const hasEvalHeader = staticItems.some(item => item.id === 'header-evaluator');
                if (!hasEvalHeader) {
                    staticItems.push({
                        id: 'header-evaluator',
                        agentName: 'evaluator',
                        type: 'evaluator-header',
                        content: capitalizeFirst(evaluatorAgent.name),
                        indent: 2
                    });
                }

                for (let i = 0; i < evaluatorAgent.history.length; i++) {
                    const item = evaluatorAgent.history[i];
                    staticItems.push({
                        id: `evaluator-history-${i}`,
                        agentName: 'evaluator',
                        type: item.type,
                        content: item.content,
                        indent: 4
                    });
                }
            }
        }
    }

    return (
        <Box flexDirection="column">
            {/* Static content - committed history that won't re-render */}
            <Static items={staticItems}>
                {(item) => (
                    <Box key={item.id} marginLeft={item.indent}>
                        {item.type === 'header' && (
                            <Text>{cliChalk.accentBold(`${cliTheme.glyph.agent} ${item.content}`)}</Text>
                        )}
                        {item.type === 'evaluator-header' && (
                            <Text>
                                <Text>{cliChalk.muted(`${cliTheme.glyph.branch} `)}</Text>
                                <Text>{cliChalk.accentBold(`${cliTheme.glyph.agent} ${item.content}`)}</Text>
                            </Text>
                        )}
                        {item.type === 'tool' && (
                            <Text color={cliTheme.ink.success} bold>{cliTheme.glyph.success} {item.content}</Text>
                        )}
                        {item.type === 'log' && (
                            <Text>{item.content}</Text>
                        )}
                    </Box>
                )}
            </Static>

            {/* Dynamic content - currently active/streaming agents */}
            {topLevelAgents.map((agent) => (
                <Box key={agent.name} flexDirection="column">
                    {/* Agent Name - only show if no history yet (not in Static) */}
                    {(!agent.history || agent.history.length === 0) && (
                        <Box>
                            <Text>{cliChalk.accentBold(`${cliTheme.glyph.agent} ${capitalizeFirst(agent.name)}`)}</Text>
                        </Box>
                    )}
                    
                    {/* Execution Plan Panel (only for strategist) */}
                    {agent.name === 'strategist' && planContent && (
                        <Box marginLeft={1}>
                            <ExecutionPlanPanel 
                                content={planContent} 
                                isComplete={isPlanComplete}
                                committedLines={committedPlanLines}
                            />
                        </Box>
                    )}

                    {/* Agent Status - only show if actively working (not complete) */}
                    {agent.status !== 'complete' && (
                        <Box marginLeft={2}>
                            <Text>
                                {!agent.isStreaming && <Text color={cliTheme.ink.blue}><SpinnerComponent type="dots" /> </Text>}
                                <Text color={agent.isStreaming ? cliTheme.ink.text : cliTheme.ink.blue} bold={!agent.isStreaming}>
                                    {agent.statusText}
                                </Text>
                            </Text>
                        </Box>
                    )}

                    {/* Completed agent status */}
                    {agent.status === 'complete' && (
                        <Box marginLeft={2}>
                            <Text color={cliTheme.ink.success} bold>{cliTheme.glyph.success} {agent.statusText.replace('Creating', 'Created')}</Text>
                        </Box>
                    )}

                    {/* Show Evaluator as child of Operator - dynamic part only */}
                    {agent.name === 'operator' && evaluatorAgent && (
                        <Box marginLeft={2} flexDirection="column">
                            {/* Evaluator header - only if no history yet */}
                            {(!evaluatorAgent.history || evaluatorAgent.history.length === 0) && (
                                <Box>
                                    <Text>{cliChalk.muted(`${cliTheme.glyph.branch} `)}</Text>
                                    <Text>{cliChalk.accentBold(`${cliTheme.glyph.agent} ${capitalizeFirst(evaluatorAgent.name)}`)}</Text>
                                </Box>
                            )}
                            
                            {/* Evaluator Status - only if active */}
                            {evaluatorAgent.status !== 'complete' && (
                                <Box marginLeft={2}>
                                    <Text>
                                        {!evaluatorAgent.isStreaming && <Text color={cliTheme.ink.blue}><SpinnerComponent type="dots" /> </Text>}
                                        <Text color={evaluatorAgent.isStreaming ? cliTheme.ink.text : cliTheme.ink.blue} bold={!evaluatorAgent.isStreaming}>
                                            {evaluatorAgent.statusText}
                                        </Text>
                                    </Text>
                                </Box>
                            )}

                            {/* Evaluator completed status */}
                            {evaluatorAgent.status === 'complete' && (
                                <Box marginLeft={2}>
                                    {evaluatorAgent.statusText.includes('Failed') ? (
                                        <Text color={cliTheme.ink.danger} bold>{cliTheme.glyph.error} {evaluatorAgent.statusText}</Text>
                                    ) : (
                                        <Text color={cliTheme.ink.success} bold>{cliTheme.glyph.success} {evaluatorAgent.statusText.replace('Creating', 'Created')}</Text>
                                    )}
                                </Box>
                            )}
                        </Box>
                    )}
                </Box>
            ))}
        </Box>
    );
};

function capitalizeFirst(str: string): string {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

export default AgentTree;
