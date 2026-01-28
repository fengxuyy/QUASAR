/**
 * Shared helper functions for CLI
 */

/**
 * Truncate text with ellipsis if it exceeds maxLength
 */
export function truncateText(text: string, maxLength: number): string {
    if (maxLength <= 3) return text.slice(0, maxLength);
    if (text.length <= maxLength) return text;
    return text.slice(0, maxLength - 3) + '...';
}

/**
 * Calculate visual length of a string (accounting for combining marks)
 */
export function getVisualLength(str: string): number {
    // Remove combining diacritical marks and count length
    return str.replace(/[\u0300-\u036f]/g, '').length;
}

/**
 * Capitalize first letter of a string
 */
export function capitalizeFirst(str: string): string {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Generate a unique ID with prefix
 */
export function generateUniqueId(prefix: string, counter: { current: number }): string {
    counter.current += 1;
    return `${prefix}-${Date.now()}-${counter.current}`;
}
