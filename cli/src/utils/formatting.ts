/**
 * Markdown/LaTeX formatting utilities
 * Extracted from ExecutionPlanPanel.tsx
 */

// Text segment with styling info
export interface TextSegment {
    text: string;
    style: 'normal' | 'code' | 'bold' | 'italic' | 'task';
}

// Superscript and subscript maps
const SUPERSCRIPT_MAP: Record<string, string> = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹', '-': '⁻'
};

const SUBSCRIPT_MAP: Record<string, string> = {
    '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
    '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉', '-': '₋'
};

// LaTeX symbol map
const SYMBOL_MAP: Record<string, string> = {
    '\\\\times': '×', '\\\\approx': '≈', '\\\\le': '≤', '\\\\ge': '≥',
    '\\\\pm': '±', '\\\\rightarrow': '→', '\\\\leftarrow': '←', '\\\\to': '→',
    '\\\\sim': '∼', '\\\\AA': 'Å',
    '\\\\alpha': 'α', '\\\\beta': 'β', '\\\\gamma': 'γ', '\\\\delta': 'δ',
    '\\\\theta': 'θ', '\\\\mu': 'μ', '\\\\pi': 'π', '\\\\rho': 'ρ',
    '\\\\sigma': 'σ', '\\\\omega': 'ω', '\\\\Gamma': 'Γ', '\\\\Delta': 'Δ',
    '\\\\Theta': 'Θ', '\\\\Lambda': 'Λ', '\\\\Sigma': 'Σ', '\\\\Phi': 'Φ',
    '\\\\Psi': 'Ψ', '\\\\Omega': 'Ω', '\\\\epsilon': 'ε', '\\\\varepsilon': 'ε',
    '\\\\lambda': 'λ', '\\\\nu': 'ν', '\\\\eta': 'η', '\\\\tau': 'τ',
    '\\\\phi': 'ϕ', '\\\\psi': 'ψ', '\\\\nabla': '∇', '\\\\partial': '∂',
    '\\\\cdot': '·', '\\\\hbar': 'ħ', '\\\\infty': '∞', '\\\\Ohm': 'Ω'
};

/**
 * Parse line into styled segments
 */
export function parseStyledSegments(line: string): TextSegment[] {
    const segments: TextSegment[] = [];
    const markers: { start: number; end: number; style: TextSegment['style'] }[] = [];
    
    // Find inline code segments
    let codeRegex = /`([^`]+)`/g;
    let match;
    while ((match = codeRegex.exec(line)) !== null) {
        markers.push({ start: match.index, end: match.index + match[0].length, style: 'code' });
    }
    
    // Find bold segments (not overlapping with code)
    // First try paired **...**
    let boldRegex = /\*\*([^*]+)\*\*/g;
    while ((match = boldRegex.exec(line)) !== null) {
        const overlaps = markers.some(m => 
            (match!.index >= m.start && match!.index < m.end) ||
            (match!.index + match![0].length > m.start && match!.index + match![0].length <= m.end)
        );
        if (!overlaps) {
            markers.push({ start: match.index, end: match.index + match[0].length, style: 'bold' });
        }
    }
    
    // Handle unclosed ** at start of line (rest of line is bold)
    const unclosedBoldMatch = line.match(/^\*\*([^*]*)$/);
    if (unclosedBoldMatch && !markers.some(m => m.start === 0)) {
        markers.push({ start: 0, end: line.length, style: 'bold' });
    }
    
    // Sort markers by start position
    markers.sort((a, b) => a.start - b.start);
    
    // Build segments
    let lastIndex = 0;
    for (const marker of markers) {
        // Add normal text before this marker
        if (marker.start > lastIndex) {
            const normalText = line.slice(lastIndex, marker.start);
            if (normalText) {
                segments.push({ text: normalText, style: 'normal' });
            }
        }
        
        // Extract the styled content (removing markers)
        const fullMatch = line.slice(marker.start, marker.end);
        let content: string;
        if (marker.style === 'code') {
            content = fullMatch.replace(/`([^`]+)`/, '$1');
        } else if (marker.style === 'bold') {
            // Handle both paired **...** and unclosed **...
            if (fullMatch.endsWith('**')) {
                content = fullMatch.replace(/\*\*([^*]+)\*\*/, '$1');
            } else {
                // Unclosed bold - just strip the leading **
                content = fullMatch.replace(/^\*\*/, '');
            }
        } else {
            content = fullMatch;
        }
        
        segments.push({ text: content, style: marker.style });
        lastIndex = marker.end;
    }
    
    // Add remaining text
    if (lastIndex < line.length) {
        segments.push({ text: line.slice(lastIndex), style: 'normal' });
    }
    
    return segments.length > 0 ? segments : [{ text: line, style: 'normal' }];
}

/**
 * Apply LaTeX transformations to text
 */
function applyLatexTransformations(text: string): string {
    let result = text;
    
    // General LaTeX cleanup (strip $ delimiters)
    result = result.replace(/\$/g, '');
    
    // Unwrap \text{...} -> ... and add space if needed
    const textBeforeUnwrap = result;
    result = result.replace(/\\text\{([^}]*)\}/g, (match, content, offset) => {
        if (offset > 0 && !/\s/.test(textBeforeUnwrap[offset - 1])) {
            return ' ' + content;
        }
        return content;
    });
    
    // Replace \bar{...} with combining overline
    result = result.replace(/\\bar\{([^}]*)\}/g, (_, content) => {
        return content.split('').map((ch: string) => ch + '\u0304').join('');
    });
    
    // Superscripts: ^{...} and ^N
    result = result.replace(/\^\{(-?\d+)\}/g, (_, num) => {
        return num.split('').map((d: string) => SUPERSCRIPT_MAP[d] || d).join('');
    });
    result = result.replace(/\^(-?\d+)/g, (_, num) => {
        return num.split('').map((d: string) => SUPERSCRIPT_MAP[d] || d).join('');
    });
    
    // Subscripts: _{...} and _N
    result = result.replace(/_\{(-?\d+)\}/g, (_, num) => {
        return num.split('').map((d: string) => SUBSCRIPT_MAP[d] || d).join('');
    });
    result = result.replace(/_(-?\d+)/g, (_, num) => {
        return num.split('').map((d: string) => SUBSCRIPT_MAP[d] || d).join('');
    });
    
    // Greek letters and symbols
    for (const [latex, unicode] of Object.entries(SYMBOL_MAP)) {
        result = result.replace(new RegExp(latex, 'g'), unicode);
    }
    
    // LaTeX subscripts - specific cases
    result = result.replace(/E_\{\\?text\{cut\}\}/g, 'Ecut');
    result = result.replace(/E_\{cut\}/g, 'Ecut');
    result = result.replace(/E_\{([^}]+)\}/g, 'E$1');
    result = result.replace(/(\w)_\{([^}]+)\}/g, '$1$2');
    
    // Scientific notation superscripts
    result = result.replace(/10\^?\{?-4\}?/g, '10⁻⁴');
    result = result.replace(/10\^?\{?-5\}?/g, '10⁻⁵');
    result = result.replace(/10\^?\{?-8\}?/g, '10⁻⁸');
    
    // Chemical formulas
    result = result.replace(/MoS2/g, 'MoS₂');
    result = result.replace(/CO2/g, 'CO₂');
    result = result.replace(/H2O/g, 'H₂O');
    
    // Units - ensure space before unit if preceded by number
    result = result.replace(/(\d)Å/g, '$1 Å');
    result = result.replace(/(\d)Ry/g, '$1 Ry');
    result = result.replace(/(\d)eV/g, '$1 eV');
    result = result.replace(/(\d)meV/g, '$1 meV');
    
    return result;
}

/**
 * Format markdown line for terminal display
 * Returns plain text, whether it's a header/task, and styled segments
 */
export function formatLine(line: string, stripTaskPrefix: boolean = false, inCodeBlock: boolean = false): { 
    plainText: string; 
    isHeader: boolean; 
    isTask: boolean; 
    addEmptyBefore: boolean; 
    segments: TextSegment[] 
} {
    // If in code block, return as is with 'code' style (but preserving the whole line content)
    // We treat the whole line as code style
    if (inCodeBlock) {
        return {
            plainText: line,
            isHeader: false,
            isTask: false,
            addEmptyBefore: false,
            segments: [{ text: line, style: 'code' }]
        };
    }

    let text = line;
    let isHeader = false;
    let isTask = false;
    let addEmptyBefore = false;
    
    // Global cleanup of U+2800 to normal space
    text = text.replace(/\u2800/g, ' ');

    // Handle blockquotes (> text)
    // Strip the leading > and optional space for markdown blockquotes
    if (text.trim().startsWith('>')) {
        // Handle "> text" format (standard markdown blockquote)
        if (text.startsWith('> ')) {
            text = text.slice(2); // Remove "> "
        } else if (text.startsWith('>')) {
            text = text.slice(1); // Remove ">"
        }
    }

    // Handle task lines
    const taskRegex = /^[\u2800\s]*#+\s*(\*\*)?Task\s+\d+[:：]\s*(\*\*)?\s*/i;
    const taskMatch = text.match(taskRegex) || text.match(/^Task\s+\d+[:：]\s*/i);
    
    if (taskMatch) {
        isTask = true;
        addEmptyBefore = true;
        
        if (stripTaskPrefix) {
            // Strip the identified task prefix
            text = text.replace(taskMatch[0], '').trim();
            
            // Also strip trailing bold markers if they were part of the prefix wrap
            // e.g., "**Task 1: Description**" -> "Description**" -> "Description"
            if (text.endsWith('**') && !text.startsWith('**')) {
                text = text.slice(0, -2).trim();
            }
            
            // Ensure the description is bolded for segments
            if (!text.startsWith('**') && text.length > 0) {
                text = `**${text}**`;
            }
        }
    }
    
    // Handle headers (### Header) - always strip ### as it's for styling, not display
    if (text.match(/^[\u2800\s]*#{1,3}[\u2800\s]*/)) {
        isHeader = true;
        if (!isTask) {
            addEmptyBefore = true;
        }
        // Always strip the ### markers - they indicate style, not literal text
        text = text.replace(/^[\u2800\s]*#{1,3}[\u2800\s]*/, '');
    }
    
    // Handle bullet points
    if (text.match(/^\s*[-*]\s+/) && !text.match(/^\s*\*\*/)) {
        text = text.replace(/^\s*[-*]\s+/, '• ');
    }
    
    // Handle numbered lists
    text = text.replace(/^(\d+)\.\s+/, '$1. ');
    
    // Fix bullets: Replace "• " with "- " for consistency
    text = text.replace(/^\s*•\s+/gm, '- ');
    
    // Parse styled segments FIRST to identify code blocks
    const segments = parseStyledSegments(text);
    
    // Apply LaTeX transformations only to non-code segments
    const transformedSegments = segments.map(seg => {
        if (seg.style === 'code') {
            // Don't apply LaTeX transformations to code segments
            return seg;
        }
        // Apply LaTeX transformations to normal, bold, italic, and task segments
        return {
            ...seg,
            text: applyLatexTransformations(seg.text)
        };
    });
    
    // Calculate plain text (for width calculations)
    const plainText = transformedSegments.map((seg, i) => {
        let prefix = '';
        if (i > 0 && seg.style !== 'normal') {
            const prevSeg = transformedSegments[i - 1];
            if (prevSeg.text && !/\s$/.test(prevSeg.text)) {
                if (!/[(\[{"'`]$/.test(prevSeg.text)) {
                    prefix = ' ';
                }
            }
        }
        return prefix + seg.text;
    }).join('');
    
    return { plainText, isHeader, isTask, addEmptyBefore, segments: transformedSegments };
}

/**
 * Calculate the plain text from segments (for width calculations)
 */
export function getPlainTextFromSegments(segments: TextSegment[]): string {
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
        return prefix + seg.text;
    }).join('');
}

/**
 * Format multiple lines with task block tracking
 * Lines following a task header (until the next task or section) are marked as isTaskContinuation
 */
export function formatLines(lines: string[], stripTaskPrefix: boolean = false): Array<{
    plainText: string;
    isHeader: boolean;
    isTask: boolean;
    isTaskContinuation: boolean;
    addEmptyBefore: boolean;
    inCodeBlock: boolean;
    segments: TextSegment[];
}> {
    const results: Array<{
        plainText: string;
        isHeader: boolean;
        isTask: boolean;
        isTaskContinuation: boolean;
        addEmptyBefore: boolean;
        inCodeBlock: boolean;
        segments: TextSegment[];
    }> = [];
    
    let inTaskBlock = false;
    let inCodeBlock = false;
    
    for (const line of lines) {
        // Check for code block markers (``` with optional language identifier)
        // This handles both opening (```python) and closing (```) markers
        // We skip these lines entirely to omit the markers from display
        if (/^\s*```/.test(line)) {
            inCodeBlock = !inCodeBlock;
            continue; // Skip the marker line - don't add it to results
        }

        const formatted = formatLine(line, stripTaskPrefix, inCodeBlock);
        
        // Check if this line starts a new task block (only if not in code block)
        if (!inCodeBlock && formatted.isTask) {
            inTaskBlock = true;
            results.push({ ...formatted, isTaskContinuation: false, inCodeBlock });
        } 
        // Check if this line starts a new section (only if not in code block)
        else if (!inCodeBlock && (formatted.isHeader || line.trim().toLowerCase().startsWith('guidance:'))) {
            inTaskBlock = false;
            results.push({ ...formatted, isTaskContinuation: false, inCodeBlock });
        }
        // If we're in a task block, mark as continuation
        else if (inTaskBlock) {
            results.push({ ...formatted, isTaskContinuation: true, isTask: true, inCodeBlock });
        }
        // Regular line
        else {
            results.push({ ...formatted, isTaskContinuation: false, inCodeBlock });
        }
    }
    
    return results;
}
