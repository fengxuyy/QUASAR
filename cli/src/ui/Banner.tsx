import React from 'react';
import { Box, Text, useStdout } from 'ink';
import { cliChalk, cliTheme } from './theme.js';

const Banner: React.FC = () => {
    const { stdout } = useStdout();

    
    // Exact ASCII logo, padded to a fixed width so the letter geometry stays locked.
    const logoLines = [
        '    ██████    █████  █████   █████████    █████████    █████████   ███████████',
        '  ███░░░░███ ░░███  ░░███   ███░░░░░███  ███░░░░░███  ███░░░░░███ ░░███░░░░░███',
        ' ███    ░░███ ░███   ░███  ░███    ░███ ░███    ░░░  ░███    ░███  ░███    ░███',
        '░███     ░███ ░███   ░███  ░███████████ ░░█████████  ░███████████  ░██████████ ',
        '░███   ██░███ ░███   ░███  ░███░░░░░███  ░░░░░░░░███ ░███░░░░░███  ░███░░░░░███',
        '░░███ ░░████  ░███   ░███  ░███    ░███  ███    ░███ ░███    ░███  ░███    ░███',
        ' ░░░██████░██ ░░████████   █████   █████░░█████████  █████   █████ █████   █████',
        '   ░░░░░░ ░░   ░░░░░░░░   ░░░░░   ░░░░░  ░░░░░░░░░  ░░░░░   ░░░░░ ░░░░░   ░░░░░'
    ];
    
    const paddingX = 4;
    const borderX = 2;
    const overheadX = (paddingX * 2) + borderX;

    const terminalWidth = stdout?.columns || 100;
    const availableWidth = Math.max(20, terminalWidth - 14);
    
    // Calculate left margin to center-align (same as PromptInput)
    const leftMargin = Math.max(0, Math.floor((terminalWidth - availableWidth) / 2));
    
    // Calculate max content width (inner width)
    const maxContentWidth = availableWidth - overheadX;
    
    const logoWidth = Math.max(...logoLines.map(line => line.length));
    const safeContentWidth = Math.max(0, maxContentWidth);
    const logoContentWidth = Math.min(logoWidth, safeContentWidth);
    
    // Pad first, then truncate. Padding keeps rows from drifting when centered.
    const truncatedLogo = logoLines.map(line =>
        line.padEnd(logoWidth).substring(0, logoContentWidth)
    );
    
    const subtitle = 'Quantum Universal Autonomous System for Atomistic Research';
    const truncatedSubtitle = subtitle.length > safeContentWidth 
        ? subtitle.substring(0, Math.max(0, safeContentWidth - 3)) + '...'
        : subtitle;
    
    const version = 'v0.4.0';
    const innerWidth = Math.max(0, availableWidth - borderX);
    const paddedLine = (content = '') => {
        const safeContent = content.substring(0, Math.max(0, innerWidth - paddingX * 2));
        return `${' '.repeat(paddingX)}${safeContent.padEnd(Math.max(0, innerWidth - paddingX * 2))}${' '.repeat(paddingX)}`;
    };
    const centerLine = (content: string) => {
        const maxTextWidth = Math.max(0, innerWidth - paddingX * 2);
        const safeContent = content.length > maxTextWidth
            ? content.substring(0, maxTextWidth)
            : content;
        const left = Math.floor((maxTextWidth - safeContent.length) / 2);
        const right = Math.max(0, maxTextWidth - safeContent.length - left);
        return `${' '.repeat(paddingX + left)}${safeContent}${' '.repeat(right + paddingX)}`;
    };
    const centeredSubtitle = () => {
        const maxTextWidth = Math.max(0, innerWidth - paddingX * 2);
        const brandPrefix = `${cliTheme.glyph.brand} `;
        const fullText = `${brandPrefix}${truncatedSubtitle}`;
        const safeText = fullText.length > maxTextWidth
            ? fullText.substring(0, maxTextWidth)
            : fullText;
        const hasBrandPrefix = safeText.startsWith(brandPrefix);
        const body = hasBrandPrefix ? safeText.substring(brandPrefix.length) : safeText;
        const left = Math.floor((maxTextWidth - safeText.length) / 2);
        const right = Math.max(0, maxTextWidth - safeText.length - left);
        return (
            <>
                {' '.repeat(paddingX + left)}
                {hasBrandPrefix && cliChalk.accentBold(brandPrefix)}
                {body}
                {' '.repeat(right + paddingX)}
            </>
        );
    };
    const framedLine = (content = '') => (
        <Text>
            {cliChalk.accentBold('│')}
            {content}
            {cliChalk.accentBold('│')}
        </Text>
    );

	return (
		<Box flexDirection="column" marginLeft={leftMargin}>
            <Text>{cliChalk.accentBold(`╭${'─'.repeat(innerWidth)}╮`)}</Text>
            {framedLine(paddedLine())}
            {truncatedLogo.map((line, index) => {
                const maxTextWidth = Math.max(0, innerWidth - paddingX * 2);
                const leftPad = Math.floor((maxTextWidth - line.length) / 2);
                const rightPad = Math.max(0, maxTextWidth - line.length - leftPad);
                return (
                    <Text key={index}>
                        {cliChalk.accentBold('│')}
                        {' '.repeat(paddingX + leftPad)}
                        {cliChalk.accentBold(line)}
                        {' '.repeat(rightPad + paddingX)}
                        {cliChalk.accentBold('│')}
                    </Text>
                );
            })}
            {framedLine(paddedLine())}
            <Text>
                {cliChalk.accentBold('│')}
                {centeredSubtitle()}
                {cliChalk.accentBold('│')}
            </Text>
            <Text>
                {cliChalk.accentBold('│')}
                {centerLine(version)}
                {cliChalk.accentBold('│')}
            </Text>
            {framedLine(paddedLine())}
            <Text>{cliChalk.accentBold(`╰${'─'.repeat(innerWidth)}╯`)}</Text>
		</Box>
	);
};

export default Banner;
