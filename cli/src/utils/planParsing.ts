/**
 * Utilities to normalize strategist plan/replan text for CLI panels.
 */

const PLAN_BLOCK_REGEX = /<PLAN>\s*([\s\S]*?)\s*<\/PLAN>/i;
const TASK_LINE_REGEX = /^(?:\s*#+\s*)?(?:\*\*)?\s*Task\s+\d+\s*[:：]/i;
const TRAILING_SECTION_REGEX = /^(?:\s*#+\s*)?(?:\*\*)?\s*(?:Next Steps?|Notes?|Summary|Conclusion)\s*[:：]/i;
const TRAILING_PROMPT_REGEX = /^Please\s+/i;

/**
 * Extract the displayable plan body from strategist output.
 * Prefers content inside <PLAN>...</PLAN>, then falls back to task-line slicing.
 */
export function normalizePlanText(rawText: string): string {
    const text = (rawText || '').replace(/\r\n/g, '\n').trim();
    if (!text) return '';

    const tagged = text.match(PLAN_BLOCK_REGEX);
    const source = tagged?.[1]?.trim() || text;
    const lines = source.split('\n');

    // If we can find explicit task lines, keep only the task section and trim common trailers.
    const firstTaskIndex = lines.findIndex(line => TASK_LINE_REGEX.test(line.trim()));
    if (firstTaskIndex >= 0) {
        const sliced = lines.slice(firstTaskIndex);
        const endIndex = sliced.findIndex((line, idx) => {
            if (idx === 0) return false;
            const trimmed = line.trim();
            return TRAILING_SECTION_REGEX.test(trimmed) || TRAILING_PROMPT_REGEX.test(trimmed);
        });
        const taskLines = endIndex >= 0 ? sliced.slice(0, endIndex) : sliced;
        const normalized = taskLines.join('\n').trim();
        if (normalized) return normalized;
    }

    return source.trim();
}
