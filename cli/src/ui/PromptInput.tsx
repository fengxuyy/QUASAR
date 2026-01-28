import React, { useState, useEffect } from 'react';
import { Box, Text, useStdout, useInput } from 'ink';
import { truncateText } from '../utils/helpers.js';

// Star spinner frames (from cli-spinners)
const STAR_SPINNER = {
    interval: 70,
    frames: ["\u2736", "\u2738", "\u2739", "\u273a", "\u2739", "\u2737"]
};

interface PromptInputProps {
    onSubmit: (value: string) => void;
    isLoading: boolean;
    taskProgress?: { current: number; total: number } | null;
    checkpointPrompt?: boolean;
    completedRunPrompt?: boolean;
    previousInput?: string;
    showInterruptWarning?: boolean;
    showExitWarning?: boolean;
}

const PromptInput: React.FC<PromptInputProps> = ({ onSubmit, isLoading, taskProgress, checkpointPrompt, completedRunPrompt, previousInput, showInterruptWarning, showExitWarning }) => {
    const [query, setQuery] = useState('');
    const [lastQuery, setLastQuery] = useState('');
    const [cursorPosition, setCursorPosition] = useState(0);
    const [spinnerFrame, setSpinnerFrame] = useState(0);
    const { stdout } = useStdout();
    const terminalWidth = stdout?.columns || 100;

    // Star spinner animation when loading
    useEffect(() => {
        if (!isLoading) {
            setSpinnerFrame(0);
            return;
        }
        
        const timer = setInterval(() => {
            setSpinnerFrame(prev => (prev + 1) % STAR_SPINNER.frames.length);
        }, STAR_SPINNER.interval);
        
        return () => clearInterval(timer);
    }, [isLoading]);

    // Get current spinner icon
    const starIcon = isLoading ? STAR_SPINNER.frames[spinnerFrame] : '✴';

    // Available width (terminal - margin for border/padding)
    const availableWidth = Math.max(20, terminalWidth - 14);
    
    // Use full available width for banner box (stretch)
    const bannerBoxWidth = availableWidth;

    // Left margin to center-align with banner's left border
    const leftMargin = Math.max(0, Math.floor((terminalWidth - bannerBoxWidth) / 2));
    
    // Generate separator line to match full banner box width
    const separatorLine = '─'.repeat(bannerBoxWidth);

    // Calculate max width for input text (accounting for star icon and task progress)
    const taskProgressWidth = taskProgress && taskProgress.total > 0 
        ? `Task ${taskProgress.current}/${taskProgress.total}`.length + 2 // +2 for spacing
        : 0;
    const inputTextMaxWidth = Math.max(10, bannerBoxWidth - 4 - taskProgressWidth); // -4 for star icon and spacing

    // Handle paste events using useInput
    // Note: This will intercept ALL input, so we need to handle both paste and typing
    useInput((input, key) => {
        if (isLoading) return;
        
        // Handle Enter key - submit
        if (key.return) {
            if (query.trim()) {
                setLastQuery(query);
                const submitValue = query;
                setQuery('');
                setCursorPosition(0);
                onSubmit(submitValue);
            }
            return;
        }
        
        // Handle left arrow - move cursor left
        if (key.leftArrow) {
            setCursorPosition(prev => Math.max(0, prev - 1));
            return;
        }
        
        // Handle right arrow - move cursor right
        if (key.rightArrow) {
            setCursorPosition(prev => Math.min(query.length, prev + 1));
            return;
        }
        
        // Handle backspace/delete - delete character before cursor
        // On Mac, the "delete" key sends backspace, so we handle both
        if (key.backspace || key.delete) {
            if (cursorPosition > 0) {
                setQuery(prev => prev.slice(0, cursorPosition - 1) + prev.slice(cursorPosition));
                setCursorPosition(prev => prev - 1);
            }
            return;
        }
        
        // Handle Ctrl+C or other special keys
        if (key.ctrl && input === 'c') {
            return; // Let it pass through or handle exit
        }
        
        // Detect paste: when input.length > 1, it's a paste event
        if (input.length > 1) {
            // Clean the pasted input - remove control characters and normalize
            const cleanedInput = input
                .replace(/\r\n/g, ' ')
                .replace(/\r/g, ' ')
                .replace(/\n/g, ' ')
                .replace(/[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]/g, '') // Remove control chars
                .trim();
            
            if (cleanedInput) {
                // Insert pasted text at cursor position
                setQuery(prev => prev.slice(0, cursorPosition) + cleanedInput + prev.slice(cursorPosition));
                setCursorPosition(prev => prev + cleanedInput.length);
            }
            return;
        }
        
        // Single character input - insert at cursor position
        if (input && input.length === 1) {
            setQuery(prev => prev.slice(0, cursorPosition) + input + prev.slice(cursorPosition));
            setCursorPosition(prev => prev + 1);
        }
    }, { isActive: !isLoading });

    // Determine placeholder text based on mode
    const placeholderText = completedRunPrompt
        ? "Previous run completed. Improve results? (yes/no)"
        : checkpointPrompt 
            ? "Resume from checkpoint? (yes/no)"
            : "Type your request here...";
    
    // Truncate placeholder if needed
    const truncatedPlaceholder = truncateText(placeholderText, inputTextMaxWidth);
    const firstChar = truncatedPlaceholder[0];
    const restPlaceholder = truncatedPlaceholder.slice(1);

    // Truncate loading text if needed
    const loadingText = previousInput || lastQuery;
    const truncatedLoadingText = truncateText(loadingText, inputTextMaxWidth);

    return (
        <Box flexDirection="column" marginLeft={leftMargin} marginY={2}>
            <Text dimColor>{separatorLine}</Text>
            <Box width={bannerBoxWidth} paddingX={1} justifyContent="space-between">
                <Box>
                    <Text>
                        <Text color="cyan" bold>{starIcon} </Text>
                        {isLoading ? (
                            <Text>{truncatedLoadingText}</Text>
                        ) : (
                            <>
                                {query === '' ? (
                                    <>
                                        <Text inverse>{firstChar}</Text>
                                        <Text dimColor>{restPlaceholder}</Text>
                                    </>
                                ) : (
                                    <>
                                        <Text>{query.slice(0, cursorPosition)}</Text>
                                        <Text inverse> </Text>
                                        <Text>{query.slice(cursorPosition)}</Text>
                                    </>
                                )}
                            </>
                        )}
                    </Text>
                </Box>
                <Box>
                    {taskProgress && taskProgress.total > 0 ? (
                        <Text dimColor>{`Task ${taskProgress.current}/${taskProgress.total}`}</Text>
                    ) : null}
                </Box>
            </Box>
            <Text dimColor>{separatorLine}</Text>
            {(checkpointPrompt || completedRunPrompt) && previousInput && (
                <Box paddingX={1}>
                    <Text dimColor>Previous Input: </Text>
                    <Text color="yellow">{truncateText(previousInput, inputTextMaxWidth - 16)}</Text>
                </Box>
            )}
            {showInterruptWarning ? (
                <Box paddingX={1}>
                    <Text color="yellow">⚠ Press ESC again to interrupt</Text>
                </Box>
            ) : showExitWarning ? (
                <Box paddingX={1}>
                    <Text color="yellow">⚠ Press Ctrl+C again to exit</Text>
                </Box>
            ) : (
                <Box paddingX={1}>
                    <Text dimColor>Shortcuts: ESC interrupt · Ctrl+D/Ctrl+C exit</Text>
                </Box>
            )}
        </Box>
    );
};

export default PromptInput;
