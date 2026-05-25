import chalk from 'chalk';

/**
 * Terminal-friendly color palette for the CLI.
 *
 * Ink supports named terminal colors most reliably, while chalk lets us add a
 * little 256-color nuance for inline formatted text and symbols.
 */
export const cliTheme = {
    ink: {
        primary: 'cyan',
        accent: 'magenta',
        blue: 'blue',
        text: 'white',
        muted: 'gray',
        success: 'green',
        warning: 'yellow',
        danger: 'red',
    },
    glyph: {
        brand: '✦',
        agent: '◆',
        active: '◇',
        branch: '└─',
        branchMid: '├─',
        success: '✓',
        error: '✗',
        retry: '⟳',
        info: '•',
    },
} as const;

export const cliChalk = {
    primary: chalk.ansi256(81),
    primaryBold: chalk.ansi256(81).bold,
    accent: chalk.ansi256(141),
    accentBold: chalk.ansi256(141).bold,
    blue: chalk.ansi256(75),
    blueBold: chalk.ansi256(75).bold,
    text: chalk.ansi256(252),
    muted: chalk.ansi256(245),
    mutedItalic: chalk.ansi256(245).italic,
    success: chalk.ansi256(79),
    successBold: chalk.ansi256(79).bold,
    warning: chalk.ansi256(222),
    warningBold: chalk.ansi256(222).bold,
    danger: chalk.ansi256(203),
    dangerBold: chalk.ansi256(203).bold,
    code: chalk.ansi256(177).bold,
};

export type CliInkColor = typeof cliTheme.ink[keyof typeof cliTheme.ink];
