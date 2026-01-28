/**
 * Line Renderer Components
 * Extracted from StaticItemRenderer.tsx for maintainability
 */
import React from 'react';
import { Text } from 'ink';
import chalk from 'chalk';
import { formatLine, TextSegment } from '../../../utils/formatting.js';

interface RenderLineProps {
    segments: TextSegment[];
    isHeader: boolean;
    isTask: boolean;
}

/**
 * Build styled text string from segments with proper spacing
 */
function buildStyledText(
    segments: TextSegment[], 
    styleMapper: (seg: TextSegment, prefix: string) => string
): string {
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
        return styleMapper(seg, prefix);
    }).join('');
}

/**
 * Render line with styling - handles headers, tasks, and normal text
 */
export function RenderLine({ segments, isHeader, isTask }: RenderLineProps): React.ReactElement {
    if (isHeader) {
        const plainText = segments.map(s => s.text).join('');
        return <Text bold color="gray">{plainText}</Text>;
    }
    
    if (isTask) {
        const styledText = buildStyledText(segments, (seg, prefix) => {
            // Highlight "Guidance:" in cyan
            if (seg.text.toLowerCase().includes('guidance:')) {
                return prefix + chalk.cyan.bold(seg.text);
            }
            
            switch (seg.style) {
                case 'code':
                    return prefix + chalk.magenta.bold(seg.text);
                case 'bold':
                    return prefix + chalk.cyan.bold(seg.text);
                default:
                    return prefix + seg.text;
            }
        });
        return <Text>{styledText}</Text>;
    }
    
    const styledText = buildStyledText(segments, (seg, prefix) => {
        switch (seg.style) {
            case 'code':
                return prefix + chalk.magenta.bold(seg.text);
            case 'bold':
                return prefix + chalk.cyan.bold(seg.text);
            case 'italic':
                return prefix + chalk.gray.italic(seg.text);
            default:
                return prefix + seg.text;
        }
    });
    
    return <Text>{styledText}</Text>;
}

export interface ProcessedLine {
    plainText: string;
    segments: TextSegment[];
    isHeader: boolean;
    isTask: boolean;
}

/**
 * Process summary line with wrapping
 */
export function processSummaryLine(
    line: string, 
    contentWidth: number, 
    stripTaskPrefix: boolean = false, 
    inCodeBlock: boolean = false
): ProcessedLine[] {
    const formatted = formatLine(line, stripTaskPrefix, inCodeBlock);
    
    if (formatted.plainText.length <= contentWidth) {
        return [formatted];
    }
    
    const results: ProcessedLine[] = [];
    let currentSegments: TextSegment[] = [];
    let currentLength = 0;
    let isFirst = true;
    
    const pushLine = () => {
        const plainText = currentSegments.map((seg, i) => {
            let prefix = '';
            if (i > 0 && seg.style !== 'normal') {
                const prevSeg = currentSegments[i - 1];
                if (prevSeg.text && !/\s$/.test(prevSeg.text)) {
                    if (!/[(\[{"'`]$/.test(prevSeg.text)) {
                        prefix = ' ';
                    }
                }
            }
            return prefix + seg.text;
        }).join('');
        
        results.push({
            plainText,
            isHeader: isFirst ? formatted.isHeader : false,
            isTask: formatted.isTask,
            segments: currentSegments
        });
        currentSegments = [];
        currentLength = 0;
        isFirst = false;
    };
    
    for (const segment of formatted.segments) {
        let segText = segment.text;
        
        let prefixLen = 0;
        if (currentSegments.length > 0 && segment.style !== 'normal') {
            const prevSeg = currentSegments[currentSegments.length - 1];
            if (prevSeg.text && !/\s$/.test(prevSeg.text)) {
                if (!/[(\[{"'`]$/.test(prevSeg.text)) {
                    prefixLen = 1;
                }
            }
        }
        
        while (currentLength + prefixLen + segText.length > contentWidth) {
            const available = contentWidth - currentLength - prefixLen;
            let breakPoint = available;
            const lastSpace = segText.lastIndexOf(' ', breakPoint);
            
            if (lastSpace > 0) {
                breakPoint = lastSpace;
            } else if (currentLength === 0) {
                breakPoint = contentWidth;
            } else {
                pushLine();
                prefixLen = 0;
                continue;
            }
            
            const firstPart = segText.slice(0, breakPoint);
            const restPart = segText.slice(breakPoint + 1);
            
            if (firstPart) {
                currentSegments.push({ text: firstPart, style: segment.style });
                currentLength += prefixLen + firstPart.length;
            }
            
            pushLine();
            segText = restPart;
            prefixLen = 0;
        }
        
        if (segText) {
            currentSegments.push({ text: segText, style: segment.style });
            currentLength += prefixLen + segText.length;
        }
    }
    
    if (currentSegments.length > 0) {
        pushLine();
    }
    
    return results;
}

/**
 * Wrap text to a given width with word boundaries
 */
export function wrapText(text: string, maxWidth: number): string[] {
    const words = text.split(' ');
    const lines: string[] = [];
    let currentLine = '';
    
    for (const word of words) {
        if (currentLine.length + word.length + 1 <= maxWidth) {
            currentLine = currentLine ? currentLine + ' ' + word : word;
        } else {
            if (currentLine) lines.push(currentLine);
            currentLine = word;
        }
    }
    if (currentLine) lines.push(currentLine);
    
    return lines;
}
