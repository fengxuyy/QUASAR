import chalk from 'chalk';

/**
 * Basic regex-based Python syntax highlighter
 */
export function highlightPython(code: string): string {
    if (!code) return '';

    // Define color palette
    const colors = {
        keyword: chalk.blueBright,
        builtin: chalk.cyan,
        string: chalk.green,
        comment: chalk.gray,
        number: chalk.yellow,
        function: chalk.yellowBright,
        decorator: chalk.magenta,
        operator: chalk.white,
    };

    // Use a token-based approach with regex
    // The order matters for overlapping patterns
    const tokens = [
        // Comments
        { regex: /#.*$/gm, color: colors.comment },
        // Multi-line strings (simplified, single line for now)
        { regex: /f?r?(['"]{3})[\s\S]*?\1/g, color: colors.string },
        // Regular strings
        { regex: /f?r?(['"])(?:(?!\1).|\\\1)*\1/g, color: colors.string },
        // Keywords
        { regex: /\b(def|class|if|else|elif|for|while|try|except|finally|with|as|import|from|return|yield|pass|break|continue|in|is|not|and|or|lambda|global|nonlocal|del|assert|async|await)\b/g, color: colors.keyword },
        // Builtins (common ones)
        { regex: /\b(print|len|range|enumerate|zip|map|filter|list|dict|set|tuple|str|int|float|bool|type|id|super|self|cls|True|False|None)\b/g, color: colors.builtin },
        // Numbers
        { regex: /\b\d+(\.\d*)?\b/g, color: colors.number },
        // Functions
        { regex: /\b([a-zA-Z_]\w*)(?=\s*\()/g, color: colors.function },
        // Decorators
        { regex: /@[a-zA-Z_]\w*/g, color: colors.decorator },
    ];

    // Build a map of positions to styling
    const mask = new Array(code.length).fill(null);

    tokens.forEach(({ regex, color }) => {
        let match;
        // Reset lastIndex for global regex
        regex.lastIndex = 0;
        while ((match = regex.exec(code)) !== null) {
            const start = match.index;
            const end = start + match[0].length;
            
            // Only apply if not already masked (e.g., inside a string/comment)
            let conflict = false;
            for (let i = start; i < end; i++) {
                if (mask[i]) {
                    conflict = true;
                    break;
                }
            }
            
            if (!conflict) {
                for (let i = start; i < end; i++) {
                    mask[i] = color;
                }
            }
        }
    });

    // Reconstruct the string with chalk colors
    let result = '';
    let currentPos = 0;
    
    while (currentPos < code.length) {
        const color = mask[currentPos];
        let endPos = currentPos + 1;
        while (endPos < code.length && mask[endPos] === color) {
            endPos++;
        }
        
        const chunk = code.slice(currentPos, endPos);
        result += color ? color(chunk) : chunk;
        currentPos = endPos;
    }

    return result;
}
