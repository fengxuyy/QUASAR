import React from 'react';
import { Box, Text, useStdout } from 'ink';
import chalk from 'chalk';

import { highlightPython } from '../utils/pythonHighlighter.js';
import { getVisualLength } from '../utils/helpers.js';

interface CodeSnippetPanelProps {
    name: string;
    content: string;
    parentLeftOffset?: number;
    isComplete?: boolean;
    isContinuation?: boolean;
}

const CodeSnippetPanel: React.FC<CodeSnippetPanelProps> = ({ 
    name, 
    content, 
    parentLeftOffset = 0,
    isComplete = true,
    isContinuation = false
}) => {
    const { stdout } = useStdout();
    const terminalWidth = stdout?.columns || 100;
    
    // Aligns with Banner and ExecutionPlanPanel
    const bannerAvailableWidth = Math.max(20, terminalWidth - 14);
    const panelWidth = Math.max(10, bannerAvailableWidth - parentLeftOffset);
    const contentWidth = Math.max(5, panelWidth - 4);
    
    // Process code lines - simple wrapping
    // Trim trailing empty lines to avoid empty line at bottom of panel
    const rawLines = content.split('\n');
    let lastNonEmptyIdx = rawLines.length - 1;
    while (lastNonEmptyIdx >= 0 && !rawLines[lastNonEmptyIdx].trim()) {
        lastNonEmptyIdx--;
    }
    const allLines = rawLines.slice(0, lastNonEmptyIdx + 1);
    const processedLines: string[] = [];
    
    for (const line of allLines) {
        // Replace tabs with 4 spaces for consistent alignment
        const cleanLine = line.replace(/\t/g, '    ');
        
        if (getVisualLength(cleanLine) <= contentWidth) {
            processedLines.push(cleanLine);
        } else {
            // Check if this is a comment
            const commentMatch = cleanLine.match(/^(\s*)#\s*/);
            const commentPrefix = commentMatch ? `${commentMatch[1]}# ` : '';
            
            // Simple wrapping for code
            let remaining = cleanLine;
            let isFirstWrap = true;
            
            while (getVisualLength(remaining) > 0) {
                // Calculate effective width for this segment
                // If it's a wrapped comment (not the first segment), we'll add the prefix
                // so we need to subtract prefix length from available width
                const currentPrefix = (!isFirstWrap && commentPrefix) ? commentPrefix : '';
                const effectiveWidth = contentWidth - getVisualLength(currentPrefix);
                
                // Find visual break point
                let visualPos = 0;
                let actualPos = 0;
                while (actualPos < remaining.length && visualPos < effectiveWidth) {
                    const char = remaining[actualPos];
                    const charWidth = getVisualLength(char);
                    if (visualPos + charWidth > effectiveWidth) break;
                    visualPos += charWidth;
                    actualPos++;
                }
                
                processedLines.push(currentPrefix + remaining.slice(0, actualPos));
                remaining = remaining.slice(actualPos);
                isFirstWrap = false;
            }
        }
    }

    const topBorder = chalk.cyan(`╭─ ${name} ` + '─'.repeat(Math.max(0, panelWidth - 5 - getVisualLength(name))) + '╮');
    const bottomBorder = chalk.cyan('╰' + '─'.repeat(Math.max(0, panelWidth - 2)) + '╯');

    return (
        <Box flexDirection="column" marginTop={isContinuation ? 0 : 1} marginBottom={0} paddingBottom={0}>
            {!isContinuation && <Text>{topBorder}</Text>}
            {processedLines.map((line, idx) => {
                const padding = ' '.repeat(Math.max(0, contentWidth - getVisualLength(line)));
                // Highlight the line
                const highlighted = highlightPython(line);
                const lineContent = chalk.cyan('│ ') + highlighted + padding + chalk.cyan(' │');
                return (
                    <Text key={idx}>{lineContent}</Text>
                );
            })}
            {isComplete && <Text>{bottomBorder}</Text>}
        </Box>
    );
};

export default CodeSnippetPanel;
