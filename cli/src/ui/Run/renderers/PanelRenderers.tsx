/**
 * Panel Renderer Components
 * Extracted from StaticItemRenderer.tsx for maintainability
 */
import React from 'react';
import { Box, Text } from 'ink';
import { formatLines, TextSegment } from '../../../utils/formatting.js';
import { getVisualLength } from '../../../utils/helpers.js';
import { INDENT_AGENT, INDENT_EVALUATOR, OFFSET_PLAN, OFFSET_TASK, OFFSET_SUMMARY, OFFSET_RESUME } from '../../../utils/constants.js';
import { RenderLine, processSummaryLine, ProcessedLine, wrapText } from './lineRenderer.js';
import { cliTheme } from '../../theme.js';

interface PanelProps {
    leftMargin: number;
    terminalWidth: number;
    availableWidth: number;
}

// ========== UTILITY FUNCTIONS ==========

/**
 * Generate panel border strings
 */
export function createPanelBorders(title: string, panelWidth: number, color: string = 'cyan'): { top: string; bottom: string } {
    const titleLen = title.length;
    const topRepeat = Math.max(0, panelWidth - titleLen - 5);
    return {
        top: `╭─ ${title} ` + '─'.repeat(topRepeat) + '╮',
        bottom: '╰' + '─'.repeat(Math.max(0, panelWidth - 2)) + '╯'
    };
}

/**
 * Process lines for panel display with formatting and wrapping
 */
export function processLinesForPanel(
    lines: string[], 
    contentWidth: number, 
    stripTaskPrefix: boolean = false
): ProcessedLine[] {
    const formattedLines = formatLines(lines, stripTaskPrefix);
    const allProcessedLines: ProcessedLine[] = [];
    
    for (let i = 0; i < formattedLines.length; i++) {
        const line = formattedLines[i];
        
        // Add empty line before headers if required (Markdown spacing)
        if (line.addEmptyBefore) {
            allProcessedLines.push({
                plainText: '',
                segments: [],
                isHeader: false,
                isTask: false
            });
        }
        
        const originalLine = line.originalLine;
        const wrapped = processSummaryLine(originalLine, contentWidth, stripTaskPrefix, line.inCodeBlock);
        
        for (const w of wrapped) {
            allProcessedLines.push({
                ...w,
                isTask: line.isTask || line.isTaskContinuation || w.isTask,
                isHeader: line.isHeader || w.isHeader
            });
        }
    }
    
    return allProcessedLines;
}

// ========== PANEL COMPONENTS ==========

interface PlanPanelProps extends PanelProps {
    planContent: string;
    isPlanComplete: boolean;
    isContinuation: boolean;
    id: string;
}

/**
 * Execution Plan Panel
 */
export function PlanPanel({ planContent, isPlanComplete, isContinuation, id, leftMargin, terminalWidth, availableWidth }: PlanPanelProps): React.ReactElement {
    const planParentOffset = OFFSET_PLAN + 3;
    const bannerAvailableWidth = Math.max(20, terminalWidth - 14);
    const planPanelWidth = Math.max(10, bannerAvailableWidth - planParentOffset);
    const planContentWidth = Math.max(5, planPanelWidth - 4);
    
    const allLines = planContent.split('\n');
    const allProcessedLines = processLinesForPanel(allLines, planContentWidth, false);
    
    const panelColor = cliTheme.ink.primary;
    const { top: topBorder, bottom: bottomBorder } = createPanelBorders(`${cliTheme.glyph.active} Execution Plan`, planPanelWidth);
    
    return (
        <Box key={id} marginLeft={leftMargin + INDENT_AGENT + 2} paddingX={1} flexDirection="column">
            {!isContinuation && <Text color={panelColor}>{topBorder}</Text>}
            {allProcessedLines.map((line, idx) => (
                <Text key={idx}>
                    <Text color={panelColor}>│ </Text>
                    <RenderLine segments={line.segments} isHeader={line.isHeader} isTask={line.isTask} />
                    <Text color={panelColor}>{' '.repeat(Math.max(0, planContentWidth - getVisualLength(line.plainText)))} │</Text>
                </Text>
            ))}
            {isPlanComplete && <Text color={panelColor}>{bottomBorder}</Text>}
        </Box>
    );
}

interface EvaluationSummaryPanelProps extends PanelProps {
    content: string;
    id: string;
}

/**
 * Evaluation Summary Panel
 */
export function EvaluationSummaryPanel({ content, id, leftMargin, terminalWidth, availableWidth }: EvaluationSummaryPanelProps): React.ReactElement {
    const summaryParentOffset = OFFSET_SUMMARY + 3;
    const summaryPanelWidth = Math.max(30, availableWidth - summaryParentOffset);
    const summaryContentWidth = Math.max(20, summaryPanelWidth - 4);
    
    const panelColor = cliTheme.ink.success;
    const { top: summaryTopBorder, bottom: summaryBottomBorder } = createPanelBorders(`${cliTheme.glyph.success} Evaluation Summary`, summaryPanelWidth);
    
    const summaryLines = content.split('\n');
    const filteredLines: string[] = [];
    for (const line of summaryLines) {
        if (line.includes('New Files Created for Task')) break;
        filteredLines.push(line);
    }
    while (filteredLines.length > 0 && filteredLines[filteredLines.length - 1].trim() === '') {
        filteredLines.pop();
    }
    
    const processedSummaryLines = processLinesForPanel(filteredLines, summaryContentWidth, false);
    
    return (
        <Box key={id} marginLeft={leftMargin + INDENT_EVALUATOR + 2} paddingX={1} flexDirection="column">
            <Text color={panelColor}>{summaryTopBorder}</Text>
            {processedSummaryLines.map((line, idx) => (
                <Text key={idx}>
                    <Text color={panelColor}>│ </Text>
                    <RenderLine segments={line.segments} isHeader={line.isHeader} isTask={line.isTask} />
                    <Text color={panelColor}>{' '.repeat(Math.max(0, summaryContentWidth - getVisualLength(line.plainText)))} │</Text>
                </Text>
            ))}
            <Text color={panelColor}>{summaryBottomBorder}</Text>
        </Box>
    );
}

interface InterruptReasonPanelProps extends PanelProps {
    content: string;
    id: string;
}

/**
 * Interrupt Reason Panel
 */
export function InterruptReasonPanel({ content, id, leftMargin, terminalWidth, availableWidth }: InterruptReasonPanelProps): React.ReactElement {
    const reasonParentOffset = OFFSET_PLAN + 3;
    const reasonPanelWidth = Math.max(30, availableWidth - reasonParentOffset);
    const reasonContentWidth = Math.max(20, reasonPanelWidth - 4);
    const panelColor = cliTheme.ink.danger;
    const { top: topBorder, bottom: bottomBorder } = createPanelBorders(`${cliTheme.glyph.error} Interrupt Reason`, reasonPanelWidth);
    const processedLines = processLinesForPanel(content.split('\n'), reasonContentWidth, false);

    return (
        <Box key={id} marginLeft={leftMargin + INDENT_AGENT + 2} paddingX={1} flexDirection="column">
            <Text color={panelColor}>{topBorder}</Text>
            {processedLines.map((line, idx) => (
                <Text key={idx}>
                    <Text color={panelColor}>│ </Text>
                    <RenderLine segments={line.segments} isHeader={line.isHeader} isTask={line.isTask} />
                    <Text color={panelColor}>{' '.repeat(Math.max(0, reasonContentWidth - getVisualLength(line.plainText)))} │</Text>
                </Text>
            ))}
            <Text color={panelColor}>{bottomBorder}</Text>
        </Box>
    );
}

interface FinalSummaryPanelProps extends PanelProps {
    content: string;
    id: string;
}

/**
 * Final Summary Panel (Run Summary)
 */
export function FinalSummaryPanel({ content, id, leftMargin, terminalWidth, availableWidth }: FinalSummaryPanelProps): React.ReactElement {
    const summaryParentOffset = OFFSET_PLAN;
    const bannerAvailableWidth = Math.max(20, terminalWidth - 14);
    const summaryPanelWidth = Math.max(10, bannerAvailableWidth - summaryParentOffset);
    const summaryContentWidth = Math.max(5, summaryPanelWidth - 4);
    
    const allLines = content.split('\n');
    const allProcessedLines = processLinesForPanel(allLines, summaryContentWidth, false);
    
    const panelColor = cliTheme.ink.success;
    const { top: topBorder, bottom: bottomBorder } = createPanelBorders(`${cliTheme.glyph.success} Run Summary`, summaryPanelWidth);
    
    return (
        <Box key={id} marginLeft={leftMargin + INDENT_AGENT - 1} paddingX={1} flexDirection="column" marginTop={1}>
            <Text color={panelColor}>{topBorder}</Text>
            {allProcessedLines.map((line, idx) => (
                <Text key={idx}>
                    <Text color={panelColor}>│ </Text>
                    <RenderLine segments={line.segments} isHeader={line.isHeader} isTask={line.isTask} />
                    <Text color={panelColor}>{' '.repeat(Math.max(0, summaryContentWidth - getVisualLength(line.plainText)))} │</Text>
                </Text>
            ))}
            <Text color={panelColor}>{bottomBorder}</Text>
        </Box>
    );
}

interface ReportPanelProps extends PanelProps {
    title: string;
    content: string;
    sourcePath?: string;
    isError?: boolean;
    id: string;
}

/**
 * Markdown report panel for local run artifacts.
 */
export function ReportPanel({ title, content, sourcePath, isError, id, leftMargin, availableWidth }: ReportPanelProps): React.ReactElement {
    const reportPanelWidth = Math.max(40, availableWidth - OFFSET_RESUME);
    const reportContentWidth = Math.max(24, reportPanelWidth - 4);
    const panelColor = isError ? cliTheme.ink.danger : cliTheme.ink.blue;
    const { top: topBorder, bottom: bottomBorder } = createPanelBorders(`${cliTheme.glyph.info} ${title}`, reportPanelWidth);
    const displaySourcePath = sourcePath?.replace(`${process.cwd()}/`, '');
    const sourceLine = displaySourcePath ? [`Source: ${displaySourcePath}`, ''] : [];
    const processedLines = processLinesForPanel([...sourceLine, ...content.split('\n')], reportContentWidth, false);

    return (
        <Box key={id} marginLeft={leftMargin} paddingX={1} flexDirection="column" marginTop={1}>
            <Text color={panelColor}>{topBorder}</Text>
            {processedLines.map((line, idx) => (
                <Text key={idx}>
                    <Text color={panelColor}>│ </Text>
                    <RenderLine segments={line.segments} isHeader={line.isHeader} isTask={line.isTask} />
                    <Text color={panelColor}>{' '.repeat(Math.max(0, reportContentWidth - getVisualLength(line.plainText)))} │</Text>
                </Text>
            ))}
            <Text color={panelColor}>{bottomBorder}</Text>
        </Box>
    );
}

interface ActiveTaskPanelProps extends PanelProps {
    description: string;
    taskNum: number;
    id: string;
}

/**
 * Active Task Panel (Task Header)
 */
export function ActiveTaskPanel({ description, taskNum, id, leftMargin, availableWidth }: ActiveTaskPanelProps): React.ReactElement {
    const taskParentOffset = OFFSET_TASK;
    const taskPanelWidth = Math.max(30, availableWidth - taskParentOffset); 
    const taskContentWidth = Math.max(20, taskPanelWidth - 4);
    
    const taskTopBorder = `╭─ Task ${taskNum} ` + '─'.repeat(Math.max(0, taskPanelWidth - 10 - String(taskNum).length)) + '╮';
    const taskBottomBorder = '╰' + '─'.repeat(Math.max(0, taskPanelWidth - 2)) + '╯';
    
    // Clean the description
    let descText = description
        .replace(/\*\*/g, '')
        .replace(/^\*|\*$/g, '')
        .replace(/^#+\s*/gm, '')
        .replace(/^Task\s+\d+[:：]\s*/i, '')
        .trim();
    
    const wrappedLines = wrapText(descText, taskContentWidth);
    
    return (
        <Box key={id} marginLeft={leftMargin + taskParentOffset - 1} width={taskPanelWidth} flexDirection="column">
            <Text color={cliTheme.ink.warning}>{taskTopBorder}</Text>
            {wrappedLines.map((line, idx) => (
                <Box key={idx} flexDirection="row">
                    <Text color={cliTheme.ink.warning}>│ </Text>
                    <Text bold>{line}</Text>
                    <Text color={cliTheme.ink.warning}>{' '.repeat(Math.max(0, taskContentWidth - getVisualLength(line)))} │</Text>
                </Box>
            ))}
            <Text color={cliTheme.ink.warning}>{taskBottomBorder}</Text>
        </Box>
    );
}

interface CheckpointResumePanelProps extends PanelProps {
    taskNum: number;
    totalTasks: number;
    id: string;
}

/**
 * Checkpoint Resume Panel
 */
export function CheckpointResumePanel({ taskNum, totalTasks, id, leftMargin, availableWidth }: CheckpointResumePanelProps): React.ReactElement {
    const resumeParentOffset = OFFSET_RESUME;
    const resumePanelWidth = Math.max(30, availableWidth - resumeParentOffset);
    const hasTotal = totalTasks > 0;
    const resumeText = hasTotal 
        ? `Resuming from checkpoint (Task ${taskNum}/${totalTasks})`
        : `Resuming from checkpoint`;
    const resumeContentWidth = 2 + resumeText.length;
    const resumeTopBorder = '╭' + '─'.repeat(resumePanelWidth - 2) + '╮';
    const resumeBottomBorder = '╰' + '─'.repeat(resumePanelWidth - 2) + '╯';
    const resumePadding = Math.max(0, resumePanelWidth - 4 - resumeContentWidth);
    
    return (
        <Box key={id} marginLeft={leftMargin} paddingX={1} flexDirection="column" marginTop={1}>
            <Text color={cliTheme.ink.warning}>{resumeTopBorder}</Text>
            <Text>
                <Text color={cliTheme.ink.warning}>│ </Text>
                <Text color={cliTheme.ink.warning} bold>{cliTheme.glyph.retry} {resumeText}</Text>
                <Text color={cliTheme.ink.warning}>{' '.repeat(resumePadding)} │</Text>
            </Text>
            <Text color={cliTheme.ink.warning}>{resumeBottomBorder}</Text>
        </Box>
    );
}

interface CodeResultPanelProps extends PanelProps {
    output: string;
    filePath: string;
    isError: boolean;
    id: string;
}

/**
 * Extract code blocks from output
 */
function extractCodeBlocks(output: string): string[] {
    const lines = output.split('\n');
    const codeBlocks: string[] = [];
    let inCodeBlock = false;
    let currentBlock: string[] = [];
    let skipUntilCodeBlock = false;
    
    for (const line of lines) {
        if (line.includes('**Execution Result:**') || 
            line.includes('**Output:**') || 
            line.includes('**Error Output:**') ||
            line.includes('**Warnings / Logs:**') ||
            line.includes('**Files Created:**') ||
            line.includes('**Files Deleted:**') ||
            line.includes('**File System:**') ||
            line.trim().startsWith('>') ||
            line.includes('Code executed')) {
            skipUntilCodeBlock = true;
            continue;
        }
        
        if (/^\s*```/.test(line)) {
            if (inCodeBlock) {
                if (currentBlock.length > 0) {
                    codeBlocks.push(currentBlock.join('\n'));
                }
                currentBlock = [];
            } else {
                skipUntilCodeBlock = false;
            }
            inCodeBlock = !inCodeBlock;
            continue;
        }
        
        if (inCodeBlock && !skipUntilCodeBlock) {
            currentBlock.push(line);
        }
    }
    
    if (inCodeBlock && currentBlock.length > 0) {
        codeBlocks.push(currentBlock.join('\n'));
    }
    
    return codeBlocks;
}

/**
 * Extract file system changes from output
 */
function extractFileSystemChanges(output: string): string {
    const lines = output.split('\n');
    let fileSystemSection = '';
    let inFileSystemSection = false;
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        
        if (line.includes('**Files Created:**') || 
            line.includes('**Files Deleted:**') || 
            line.includes('**File System:**')) {
            inFileSystemSection = true;
            fileSystemSection += line + '\n';
            continue;
        }
        
        if (inFileSystemSection && (
            line.includes('**Execution Result:**') ||
            line.includes('**Output:**') ||
            line.includes('**Error Output:**') ||
            line.includes('**Warnings / Logs:**') ||
            /^\s*```/.test(line)
        )) {
            break;
        }
        
        if (inFileSystemSection) {
            if (line.trim()) {
                fileSystemSection += line + '\n';
            }
        }
    }
    
    return fileSystemSection.trim();
}

/**
 * Code Execution Result Panel
 */
export function CodeResultPanel({ output, filePath, isError, id, leftMargin, terminalWidth, availableWidth }: CodeResultPanelProps): React.ReactElement {
    const codeResultParentOffset = OFFSET_PLAN + 3;
    const codeResultPanelWidth = Math.max(30, availableWidth - codeResultParentOffset);
    const codeResultContentWidth = Math.max(20, codeResultPanelWidth - 4);
    const borderColor = isError ? cliTheme.ink.danger : cliTheme.ink.blue;
    const headerText = isError ? `${cliTheme.glyph.error} Execution Error` : `${cliTheme.glyph.info} Execution Output`;
    
    const codeBlocks = extractCodeBlocks(output);
    const fileSystemChanges = extractFileSystemChanges(output);
    const limitLines = 30;
    
    const displayLines: ProcessedLine[] = [];
    let totalTruncatedLines = 0;
    
    for (const block of codeBlocks) {
        // Trim trailing empty lines from the block
        const blockLines = block.split('\n');
        let lastNonEmptyIdx = blockLines.length - 1;
        while (lastNonEmptyIdx >= 0 && !blockLines[lastNonEmptyIdx].trim()) {
            lastNonEmptyIdx--;
        }
        const trimmedLines = blockLines.slice(0, lastNonEmptyIdx + 1);
        const totalLines = trimmedLines.length;
        const isTruncated = totalLines > limitLines;
        const linesToShow = isTruncated ? trimmedLines.slice(0, limitLines) : trimmedLines;
        
        if (isTruncated) {
            totalTruncatedLines += (totalLines - limitLines);
        }
        
        for (const line of linesToShow) {
            const wrapped = processSummaryLine(line, codeResultContentWidth, false, true);
            for (const w of wrapped) {
                displayLines.push({
                    ...w,
                    isTask: false,
                    isHeader: false
                });
            }
        }
    }
    
    // Add truncation message
    if (totalTruncatedLines > 0) {
        const truncationMsg = `... (${totalTruncatedLines} more lines)`;
        const truncWrapped = processSummaryLine(truncationMsg, codeResultContentWidth, false, true);
        for (const w of truncWrapped) {
            displayLines.push({
                ...w,
                isTask: false,
                isHeader: false
            });
        }
    }
    
    // If no output, display file system changes
    if (displayLines.length === 0 && fileSystemChanges) {
        const fileSystemLines = fileSystemChanges.split('\n');
        for (const line of fileSystemLines) {
            if (line.trim()) {
                const wrapped = processSummaryLine(line, codeResultContentWidth, false, false);
                for (const w of wrapped) {
                    displayLines.push({
                        ...w,
                        isTask: false,
                        isHeader: false
                    });
                }
            }
        }
    }
    
    // If still no output but we have raw error message, show it
    if (displayLines.length === 0 && output && output.trim()) {
        // For simple error messages without code blocks, show the raw message
        const errorLines = output.split('\n').filter(line => line.trim());
        for (const line of errorLines) {
            // Skip markdown headers and formatting
            if (line.startsWith('**') || line.startsWith('```') || line.trim().startsWith('>')) {
                continue;
            }
            const wrapped = processSummaryLine(line, codeResultContentWidth, false, false);
            for (const w of wrapped) {
                displayLines.push({
                    ...w,
                    isTask: false,
                    isHeader: false
                });
            }
        }
    }
    
    const { top: codeTopBorder, bottom: codeBottomBorder } = createPanelBorders(headerText, codeResultPanelWidth);
    
    return (
        <Box key={id} marginLeft={leftMargin + INDENT_AGENT + 2} paddingX={1} flexDirection="column">
            <Text color={borderColor}>{codeTopBorder}</Text>
            {displayLines.length === 0 ? (
                <Text>
                    <Text color={borderColor}>│ </Text>
                    <Text color={cliTheme.ink.muted}>(No output)</Text>
                    <Text color={borderColor}>{' '.repeat(Math.max(0, codeResultContentWidth - 11))} │</Text>
                </Text>
            ) : (
                displayLines.map((line, idx) => (
                    <Text key={idx}>
                        <Text color={borderColor}>│ </Text>
                        <RenderLine segments={line.segments} isHeader={line.isHeader} isTask={line.isTask} />
                        <Text color={borderColor}>{' '.repeat(Math.max(0, codeResultContentWidth - getVisualLength(line.plainText)))} │</Text>
                    </Text>
                ))
            )}
            <Text color={borderColor}>{codeBottomBorder}</Text>
        </Box>
    );
}
