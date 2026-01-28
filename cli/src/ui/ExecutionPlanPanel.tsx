/**
 * Execution Plan Panel
 * Displays execution plan content with markdown formatting in a bordered panel
 */
import React from 'react';
import { Box, Text, useStdout } from 'ink';
import chalk from 'chalk';
import { formatLine, parseStyledSegments, getPlainTextFromSegments, TextSegment } from '../utils/formatting.js';
import { getVisualLength } from '../utils/helpers.js';

interface ExecutionPlanPanelProps {
    content: string;
    isComplete: boolean;
    committedLines?: string[];
    parentLeftOffset?: number; 
    isContinuation?: boolean;
}

// Render a segment with appropriate styling using chalk
function renderStyledText(segments: TextSegment[], isHeader: boolean, isTask: boolean): string {
    if (isHeader) {
        const plainText = segments.map(s => s.text).join('');
        return chalk.gray.bold(plainText);
    }
    
    if (isTask) {
        return segments.map((seg, i) => {
            let prefix = '';
            if (i > 0 && seg.style !== 'normal') {
                const prevSeg = segments[i - 1];
                if (prevSeg.text && !/\s$/.test(prevSeg.text)) {
                    if (!/[(\[{"'`]$/.test(prevSeg.text)) {
                        prefix = ' ';
                    }
                }
            }
            
            // Highlight "Guidance:" in cyan
            if (seg.text.toLowerCase().includes('guidance:')) {
                return prefix + chalk.cyan.bold(seg.text);
            }
            
            // Respect the segment's own style - only bold if segment was marked as bold
            switch (seg.style) {
                case 'code':
                    return prefix + chalk.magenta.bold(seg.text);
                case 'bold':
                    return prefix + chalk.cyan.bold(seg.text);
                default:
                    // Normal text stays normal - no automatic bold
                    return prefix + seg.text;
            }
        }).join('');
    }
    
    return segments.map((seg, i) => {
        let prefix = '';
        if (i > 0 && seg.style !== 'normal') {
            const prevSeg = segments[i - 1];
            if (prevSeg.text && !/\s$/.test(prevSeg.text)) {
                if (!/[(\[{"'`]$/.test(prevSeg.text)) {
                    prefix = ' ';
                }
            }
        }
        
        switch (seg.style) {
            case 'code':
                return prefix + chalk.magenta.bold(seg.text);
            case 'bold':
                return prefix + chalk.cyan.bold(seg.text);
            case 'italic':
                return prefix + chalk.gray.italic(seg.text);
            default:
                return seg.text;
        }
    }).join('');
}

// Render line component
function RenderLine({ segments, isHeader, isTask }: { segments: TextSegment[]; isHeader: boolean; isTask: boolean }) {
    const styledText = renderStyledText(segments, isHeader, isTask);
    return <Text>{styledText}</Text>;
}

const ExecutionPlanPanel: React.FC<ExecutionPlanPanelProps> = ({ 
    content, 
    isComplete, 
    committedLines, 
    parentLeftOffset = 0,
    isContinuation = false
}) => {
    const { stdout } = useStdout();
    const terminalWidth = stdout?.columns || 100;
    
    // Calculate panel dimensions - match Banner alignment
    const bannerAvailableWidth = Math.max(20, terminalWidth - 14);
    const panelWidth = Math.max(10, bannerAvailableWidth - parentLeftOffset);
    const contentWidth = Math.max(5, panelWidth - 4);
    
    // Process all content lines
    const allLines = content.split('\n').filter(line => line.trim());
    
    // Process and wrap lines
    const processLine = (line: string, stripTaskPrefix: boolean = false): { plainText: string; segments: TextSegment[]; isHeader: boolean; isTask: boolean; addEmptyBefore: boolean }[] => {
        const formatted = formatLine(line, stripTaskPrefix);
        
        if (formatted.plainText.length <= contentWidth) {
            return [formatted];
        }
        
        // Complex wrapping preserving segments
        const results: { plainText: string; segments: TextSegment[]; isHeader: boolean; isTask: boolean; addEmptyBefore: boolean }[] = [];
        let currentSegments: TextSegment[] = [];
        let currentLength = 0;
        let isFirst = true;

        const pushLine = () => {
            const plainText = getPlainTextFromSegments(currentSegments);
            results.push({
                plainText,
                isHeader: isFirst ? formatted.isHeader : false,
                isTask: formatted.isTask,
                addEmptyBefore: isFirst ? formatted.addEmptyBefore : false,
                segments: currentSegments
            });
            currentSegments = [];
            currentLength = 0;
            isFirst = false;
        };

        for (const segment of formatted.segments) {
            let segText = segment.text;
            
            let spacePrefix = 0;
            if (currentSegments.length > 0 && segment.style !== 'normal') {
                const prevSeg = currentSegments[currentSegments.length - 1];
                if (prevSeg.text && !/\s$/.test(prevSeg.text)) {
                    if (!/[(\[{"'`]$/.test(prevSeg.text)) {
                        spacePrefix = 1;
                    }
                }
            }
            
            while (currentLength + spacePrefix + segText.length > contentWidth) {
                const available = contentWidth - currentLength - spacePrefix;
                let breakPoint = available;
                
                const lastSpace = segText.lastIndexOf(' ', breakPoint);
                if (lastSpace > 0) {
                    breakPoint = lastSpace;
                } else if (currentLength === 0 && spacePrefix === 0) {
                    breakPoint = contentWidth;
                } else {
                    pushLine();
                    spacePrefix = 0;
                    continue;
                }
                
                const firstPart = segText.slice(0, breakPoint);
                const restPart = segText.slice(breakPoint + 1);
                
                if (firstPart) {
                    currentSegments.push({ text: firstPart, style: segment.style });
                    currentLength += spacePrefix + firstPart.length;
                }
                
                pushLine();
                segText = restPart;
                spacePrefix = 0;
            }
            
            if (segText) {
                currentSegments.push({ text: segText, style: segment.style });
                currentLength += spacePrefix + segText.length;
            }
        }
        
        if (currentSegments.length > 0) {
            pushLine();
        }

        return results;
    };
    
    // Process all lines
    const processedLines: { plainText: string; segments: TextSegment[]; isHeader: boolean; isTask: boolean; addEmptyBefore: boolean }[] = [];
    for (const line of allLines) {
        processedLines.push(...processLine(line));
    }
    
    const topBorder = chalk.cyan('╭─ Execution Plan ' + '─'.repeat(Math.max(0, panelWidth - 19)) + '╮');
    const bottomBorder = chalk.cyan('╰' + '─'.repeat(Math.max(0, panelWidth - 2)) + '╯');
    
    return (
        <Box flexDirection="column" marginTop={0}>
            {!isContinuation && <Text>{topBorder}</Text>}
            {processedLines.map((line, idx) => (
                <React.Fragment key={idx}>
                    {line.addEmptyBefore && idx > 0 && (
                        <Text>
                            <Text color="cyan">│ </Text>
                            <Text>{' '.repeat(contentWidth)}</Text>
                            <Text color="cyan"> │</Text>
                        </Text>
                    )}
                    <Text>
                        <Text color="cyan">│ </Text>
                        <RenderLine segments={line.segments} isHeader={line.isHeader} isTask={line.isTask} />
                        <Text color="cyan">{' '.repeat(Math.max(0, contentWidth - getVisualLength(line.plainText)))} │</Text>
                    </Text>
                </React.Fragment>
            ))}
            {isComplete && <Text>{bottomBorder}</Text>}
        </Box>
    );
};

export default ExecutionPlanPanel;
