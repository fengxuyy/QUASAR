import React from 'react';
import { Box, Text, useStdout } from 'ink';

interface BannerProps {
    modelName?: string;
    pmgConfigured?: boolean;
}

const Banner: React.FC<BannerProps> = ({ modelName, pmgConfigured }) => {
    const { stdout } = useStdout();

    
    // Exact ASCII from src/cli_utils.py - each line is separate for truncation
    const logoLines = [
        '    ██████    █████  █████   █████████    █████████    █████████   ███████████',
        '  ███░░░░███ ░░███  ░░███   ███░░░░░███  ███░░░░░███  ███░░░░░███ ░░███░░░░░███',
        ' ███    ░░███ ░███   ░███  ░███    ░███ ░███    ░░░  ░███    ░███  ░███    ░███',
        '░███     ░███ ░███   ░███  ░███████████ ░░█████████  ░███████████  ░██████████',
        '░███   ██░███ ░███   ░███  ░███░░░░░███  ░░░░░░░░███ ░███░░░░░███  ░███░░░░░███',
        '░░███ ░░████  ░███   ░███  ░███    ░███  ███    ░███ ░███    ░███  ░███    ░███',
        ' ░░░██████░██ ░░████████   █████   █████░░█████████  █████   █████ █████   █████',
        '   ░░░░░░ ░░   ░░░░░░░░   ░░░░░   ░░░░░  ░░░░░░░░░  ░░░░░   ░░░░░ ░░░░░   ░░░░░'
    ];
    
    // Box padding (4 * 2) + border (2) = 10 chars overhead
    const paddingX = 4;
    const borderX = 2;
    const overheadX = (paddingX * 2) + borderX;

    const terminalWidth = stdout?.columns || 100;
    // Calculate Box width (outer width)
    const availableWidth = Math.max(20, terminalWidth - 14);
    
    // Calculate left margin to center-align (same as PromptInput)
    const leftMargin = Math.max(0, Math.floor((terminalWidth - availableWidth) / 2));
    
    // Calculate max content width (inner width)
    const maxContentWidth = availableWidth - overheadX;
    
    // Calculate the actual logo width (longest line, capped by available content space)
    // Ensure we don't pass negative length if screen is super small
    const safeContentWidth = Math.max(0, maxContentWidth);
    const logoWidth = Math.min(logoLines[0].length, safeContentWidth);
    
    // Truncate each line from the right to fit available width safely
    const truncatedLogo = logoLines.map(line => {
        if (line.length > safeContentWidth) {
            return line.substring(0, safeContentWidth);
        }
        return line;
    }).join('\n');
    
    const subtitle = 'Quantum Universal Autonomous System for Atomistic Research';
    const truncatedSubtitle = subtitle.length > safeContentWidth 
        ? subtitle.substring(0, Math.max(0, safeContentWidth - 3)) + '...'
        : subtitle;
    
    // Generate separator line to match logo width
    const separatorLine = '─'.repeat(logoWidth);

	return (
		<Box flexDirection="column" marginLeft={leftMargin}>
            <Box borderStyle="round" borderColor="cyan" paddingX={4} paddingY={1} width={availableWidth} justifyContent="center">
                <Box flexDirection="column" alignItems="center">
                    <Text color="cyan" bold>{truncatedLogo}</Text>
                    <Text>{'\n'}</Text>
                    <Text color="white">{truncatedSubtitle}</Text>
                    
                    {(modelName || pmgConfigured) && (
                        <Box flexDirection="column" marginTop={1} alignItems="flex-start" width={logoWidth}>
                            <Text dimColor>{separatorLine}</Text>
                            {modelName && (
                                <Box>
                                    <Text dimColor>Model: </Text>
                                    <Text color="cyan">{
                                        ('Model: ' + modelName).length > logoWidth 
                                            ? modelName.substring(0, logoWidth - 10) + '...'
                                            : modelName
                                    }</Text>
                                </Box>
                            )}
                            {pmgConfigured && (
                                <Box>
                                    <Text dimColor>{
                                        'Materials Project API: Configured'.length > logoWidth
                                            ? 'Materials Project API: Configured'.substring(0, logoWidth - 3) + '...'
                                            : 'Materials Project API: '
                                    }</Text>
                                    {'Materials Project API: Configured'.length <= logoWidth && (
                                        <Text color="green">Configured</Text>
                                    )}
                                </Box>
                            )}
                            <Text dimColor>{separatorLine}</Text>
                        </Box>
                    )}
                </Box>
            </Box>
		</Box>
	);
};

export default Banner;

