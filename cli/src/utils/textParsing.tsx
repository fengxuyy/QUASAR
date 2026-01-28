/**
 * Text processing utilities for rendering
 * Extracted from StaticItemRenderer.tsx
 */
import type { TextSegment } from './formatting.js';
import { formatLine, formatLines } from './formatting.js';
import { getVisualLength } from './helpers.js';

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
        return [{
            plainText: formatted.plainText,
            segments: formatted.segments,
            isHeader: formatted.isHeader,
            isTask: formatted.isTask
        }];
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
 * Process multiple lines with formatting
 */
export function processFormattedLines(
    lines: string[], 
    contentWidth: number, 
    stripTaskPrefix: boolean = false
): ProcessedLine[] {
    const formattedLines = formatLines(lines, stripTaskPrefix);
    const allProcessedLines: ProcessedLine[] = [];
    
    for (let i = 0; i < formattedLines.length; i++) {
        const line = formattedLines[i];
        const originalLine = lines[i];
        
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

/**
 * Render line with styling - returns JSX for Ink components
 */
import React from 'react';
import { Text } from 'ink';
import chalk from 'chalk';

export function renderStyledLine({ segments, isHeader, isTask }: { segments: TextSegment[]; isHeader: boolean; isTask: boolean }) {
    if (isHeader) {
        const plainText = segments.map(s => s.text).join('');
        return <Text bold color="gray">{plainText}</Text>;
    }
    
    if (isTask) {
        const hasGuidance = segments.some(seg => seg.text.toLowerCase().includes('guidance:'));
        
        const styledText = segments.map((seg, i) => {
            let prefix = '';
            if (i > 0 && seg.style !== 'normal') {
                const prevSeg = segments[i - 1];
                if (prevSeg.text && !/\s$/.test(prevSeg.text)) {
                    if (!/[(\[{"'`]$/.test(prevSeg.text)) {
                        prefix = ' ';
                    }
                }
            }
            
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
        }).join('');
        return <Text>{styledText}</Text>;
    }
    
    const styledText = segments.map((seg, i) => {
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
                return prefix + seg.text;
        }
    }).join('');
    
    return <Text>{styledText}</Text>;
}

export { getVisualLength };

