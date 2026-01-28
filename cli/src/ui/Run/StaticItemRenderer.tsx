/**
 * Renderer for Static committed items
 * Refactored to use extracted renderer components
 */
import React from 'react';
import { Box } from 'ink';
import CodeSnippetPanel from '../CodeSnippetPanel.js';
import { OFFSET_PLAN, INDENT_AGENT } from '../../utils/constants.js';
import type { CommittedItem } from '../../hooks/types.js';

// Import extracted renderers
import {
    PlanPanel,
    EvaluationSummaryPanel,
    FinalSummaryPanel,
    ActiveTaskPanel,
    CheckpointResumePanel,
    CodeResultPanel,
    AgentHeaderRenderer,
    EvaluatorHeaderRenderer,
    ToolRenderer,
    LogRenderer,
    AgentStatusRenderer,
    EvaluatorStatusRenderer,
    ModelTextRenderer,
    BannerRenderer
} from './renderers/index.js';

interface StaticItemRendererProps {
    item: CommittedItem & { _resizeKey?: string };
    leftMargin: number;
    terminalWidth: number;
    availableWidth: number;
}

/**
 * Main renderer component for committed items
 * Delegates to specialized renderer components based on item type
 */
const StaticItemRenderer: React.FC<StaticItemRendererProps> = ({ item, leftMargin, terminalWidth, availableWidth }) => {
    const key = item._resizeKey || item.id;
    
    switch (item.type) {
        case 'banner':
            return (
                <BannerRenderer 
                    id={key}
                    modelName={item.content.modelName} 
                    pmgConfigured={item.content.pmgConfigured} 
                />
            );
            
        case 'agent-header':
            return (
                <AgentHeaderRenderer 
                    id={key}
                    agentName={item.content}
                    leftMargin={leftMargin}
                    terminalWidth={terminalWidth}
                />
            );
            
        case 'evaluator-header':
            return (
                <EvaluatorHeaderRenderer 
                    id={key}
                    agentName={item.content}
                    leftMargin={leftMargin}
                    terminalWidth={terminalWidth}
                />
            );
            
        case 'tool':
            return (
                <ToolRenderer 
                    id={key}
                    content={item.content}
                    agentName={item.agentName!}
                    isError={item.isError === true}
                    leftMargin={leftMargin}
                    terminalWidth={terminalWidth}
                />
            );
        
        case 'log':
            return (
                <LogRenderer 
                    id={key}
                    content={item.content}
                    agentName={item.agentName!}
                    leftMargin={leftMargin}
                    terminalWidth={terminalWidth}
                />
            );
        
        case 'checkpoint-resume':
            return (
                <CheckpointResumePanel 
                    id={key}
                    taskNum={item.content.taskNum}
                    totalTasks={item.content.totalTasks}
                    leftMargin={leftMargin}
                    terminalWidth={terminalWidth}
                    availableWidth={availableWidth}
                />
            );
        
        case 'evaluation-summary':
            return (
                <EvaluationSummaryPanel 
                    id={key}
                    content={typeof item.content === 'string' ? item.content : ''}
                    leftMargin={leftMargin}
                    terminalWidth={terminalWidth}
                    availableWidth={availableWidth}
                />
            );
        
        case 'plan':
            return (
                <PlanPanel 
                    id={key}
                    planContent={item.content.planContent || ''}
                    isPlanComplete={item.content.isPlanComplete}
                    isContinuation={item.content.isContinuation}
                    leftMargin={leftMargin}
                    terminalWidth={terminalWidth}
                    availableWidth={availableWidth}
                />
            );
            
        case 'code-snippet':
            return (
                <Box key={key} marginLeft={leftMargin + INDENT_AGENT - 1} paddingX={1}>
                    <CodeSnippetPanel 
                        name={item.content.name} 
                        content={item.content.content}
                        isComplete={item.content.isComplete}
                        isContinuation={item.content.isContinuation}
                        parentLeftOffset={OFFSET_PLAN}
                    />
                </Box>
            );
            
        case 'agent-status':
            return (
                <AgentStatusRenderer 
                    id={key}
                    content={item.content}
                    leftMargin={leftMargin}
                    terminalWidth={terminalWidth}
                />
            );
            
        case 'evaluator-status':
            return (
                <EvaluatorStatusRenderer 
                    id={key}
                    content={item.content}
                    leftMargin={leftMargin}
                    terminalWidth={terminalWidth}
                />
            );
            
        case 'active-task-panel':
            return (
                <ActiveTaskPanel 
                    id={key}
                    description={item.content.description}
                    taskNum={item.content.taskNum}
                    leftMargin={leftMargin}
                    terminalWidth={terminalWidth}
                    availableWidth={availableWidth}
                />
            );
        
        case 'final-summary':
            return (
                <FinalSummaryPanel 
                    id={key}
                    content={typeof item.content === 'string' ? item.content : ''}
                    leftMargin={leftMargin}
                    terminalWidth={terminalWidth}
                    availableWidth={availableWidth}
                />
            );

        case 'code-result':
            return (
                <CodeResultPanel 
                    id={key}
                    output={typeof item.content === 'object' ? item.content.output : ''}
                    filePath={typeof item.content === 'object' ? item.content.filePath : ''}
                    isError={item.isError === true}
                    leftMargin={leftMargin}
                    terminalWidth={terminalWidth}
                    availableWidth={availableWidth}
                />
            );
        
        case 'model-text':
            return (
                <ModelTextRenderer 
                    id={key}
                    content={typeof item.content === 'string' ? item.content : ''}
                    agentName={item.agentName!}
                    leftMargin={leftMargin}
                    terminalWidth={terminalWidth}
                />
            );

        default:
            return null;
    }
};

export default StaticItemRenderer;
