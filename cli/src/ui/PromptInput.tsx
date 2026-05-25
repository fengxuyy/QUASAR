import React, { useState, useEffect, useRef } from 'react';
import { Box, Text, useStdout, useInput } from 'ink';
import { truncateText } from '../utils/helpers.js';
import { registerAnimationSubscriber } from './animationTick.js';
import type { ContextUsage } from '../hooks/types.js';
import { cliTheme } from './theme.js';
import { matchingBackslashCommands } from '../utils/commandRegistry.js';

// Star spinner frames (from cli-spinners)
const STAR_SPINNER = {
    interval: 70,
    frames: ["\u2736", "\u2738", "\u2739", "\u273a", "\u2739", "\u2737"]
};

/**
 * Self-contained spinner so its rapid state updates don't cause the parent
 * PromptInput (and the shortcuts bar) to re-render and flash on every tick.
 */
const StarSpinner: React.FC<{ isLoading: boolean }> = ({ isLoading }) => {
    const [frame, setFrame] = useState(0);

    useEffect(() => {
        if (!isLoading) {
            setFrame(0);
            return;
        }
        const advance = () => setFrame(prev => (prev + 1) % STAR_SPINNER.frames.length);
        return registerAnimationSubscriber(advance);
    }, [isLoading]);

    const icon = isLoading ? STAR_SPINNER.frames[frame] : '✴';
    return <Text color={cliTheme.ink.primary} bold>{icon} </Text>;
};

interface PromptInputProps {
    onSubmit: (value: string) => void;
    isLoading: boolean;
    taskProgress?: { current: number; total: number } | null;
    contextUsage?: ContextUsage | null;
    checkpointPrompt?: boolean;
    allowCheckpointSteering?: boolean;
    completedRunPrompt?: boolean;
    confirmDeleteArchive?: boolean;
    revertConfirm?: boolean;
    revertTargetTask?: number | null;
    startRequestConfirm?: boolean;
    pendingSubmitPreview?: string;
    planAwaitingConfirm?: boolean;
    prefillRevision?: number;
    prefillText?: string;
    previousInput?: string;
    showInterruptWarning?: boolean;
    showExitWarning?: boolean;
}

const PromptInput: React.FC<PromptInputProps> = ({ onSubmit, isLoading, taskProgress, contextUsage, checkpointPrompt, allowCheckpointSteering, completedRunPrompt, confirmDeleteArchive, revertConfirm, revertTargetTask, startRequestConfirm, pendingSubmitPreview, planAwaitingConfirm, prefillRevision, prefillText, previousInput, showInterruptWarning, showExitWarning }) => {
    const [query, setQuery] = useState('');
    const [lastQuery, setLastQuery] = useState('');
    const [cursorPosition, setCursorPosition] = useState(0);
    const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
    // Ref so that useInput callbacks always read the latest cursor position
    // (avoids stale closure that scrambles pasted text)
    const cursorPositionRef = useRef(0);
    const { stdout } = useStdout();
    const terminalWidth = stdout?.columns || 100;

    // Available width (terminal - margin for border/padding)
    const availableWidth = Math.max(20, terminalWidth - 14);
    
    // Use full available width for banner box (stretch)
    const bannerBoxWidth = availableWidth;

    // Left margin to center-align with banner's left border
    const leftMargin = Math.max(0, Math.floor((terminalWidth - bannerBoxWidth) / 2));
    
    const tokenUsageLabel = contextUsage?.is_supported_model
        ? `Ctx ${Math.round(contextUsage.usage_percent ?? 0)}%`
        : 'Ctx --';
    const hasTaskProgress = !!(taskProgress && taskProgress.total > 0);
    const taskProgressLabel = hasTaskProgress ? `Task ${taskProgress?.current}/${taskProgress?.total}` : '';
    const rightStatusWidth =
        tokenUsageLabel.length +
        (hasTaskProgress ? taskProgressLabel.length + 2 : 0);
    const inputTextMaxWidth = Math.max(10, bannerBoxWidth - 4 - rightStatusWidth); // -4 for star icon and spacing
    const tokenUsageColor = !contextUsage?.is_supported_model
        ? cliTheme.ink.muted
        : (contextUsage.usage_percent ?? 0) >= 100
            ? cliTheme.ink.danger
            : (contextUsage.usage_percent ?? 0) >= 75
                ? cliTheme.ink.warning
                : cliTheme.ink.success;

    const promptBorderColor = confirmDeleteArchive || revertConfirm
        ? cliTheme.ink.danger
        : planAwaitingConfirm || startRequestConfirm
            ? cliTheme.ink.warning
            : checkpointPrompt || completedRunPrompt
                ? cliTheme.ink.accent
                : isLoading
                    ? cliTheme.ink.primary
                    : cliTheme.ink.blue;

    const commandHasArgs = /^\\\S+\s+/.test(query);
    const showCommandSuggestions = !isLoading && query.startsWith('\\') && !commandHasArgs;
    const commandSuggestions = showCommandSuggestions ? matchingBackslashCommands(query) : [];
    const activeCommandIndex = Math.min(selectedCommandIndex, Math.max(0, commandSuggestions.length - 1));
    const selectedCommand = commandSuggestions[activeCommandIndex];
    const completeSelectedCommand = () => {
        if (!selectedCommand) return;
        setQuery(selectedCommand.command);
        const len = selectedCommand.command.length;
        cursorPositionRef.current = len;
        setCursorPosition(len);
    };

    // Keep cursorPositionRef in sync so useInput callbacks always see the latest value
    useEffect(() => {
        cursorPositionRef.current = cursorPosition;
    }, [cursorPosition]);

    useEffect(() => {
        setSelectedCommandIndex(0);
    }, [query]);

    // Prefill input (e.g. after user declines reviewed plan and returns to compose)
    useEffect(() => {
        if (prefillRevision && prefillRevision > 0) {
            const text = prefillText ?? '';
            setQuery(text);
            const len = text.length;
            setCursorPosition(len);
            cursorPositionRef.current = len;
        }
    }, [prefillRevision, prefillText]);

    // A checkpoint resume starts as an empty steering box, never prefilled with
    // the original run request.
    useEffect(() => {
        if (checkpointPrompt) {
            setQuery('');
            setLastQuery('');
            setCursorPosition(0);
            cursorPositionRef.current = 0;
        }
    }, [checkpointPrompt]);

    // Handle paste events using useInput
    // Note: This will intercept ALL input, so we need to handle both paste and typing
    useInput((input, key) => {
        if (isLoading) return;
        
        // Always read the ref so we never use a stale closure value
        const pos = cursorPositionRef.current;

        // Handle Enter key - submit
        if (key.return) {
            if (showCommandSuggestions && !selectedCommand) {
                return;
            }
            if (showCommandSuggestions && selectedCommand) {
                const exactCommand = selectedCommand.command === query.trim().toLowerCase();
                if (!exactCommand) {
                    completeSelectedCommand();
                    return;
                }
            }
            if (query.trim() || completedRunPrompt || checkpointPrompt) {
                setLastQuery(query);
                const submitValue = query;
                setQuery('');
                cursorPositionRef.current = 0;
                setCursorPosition(0);
                onSubmit(submitValue);
            }
            return;
        }

        if (showCommandSuggestions && selectedCommand && key.tab) {
            completeSelectedCommand();
            return;
        }

        if (showCommandSuggestions && commandSuggestions.length > 0 && (key.upArrow || key.downArrow)) {
            setSelectedCommandIndex(prev => {
                if (key.upArrow) {
                    return prev <= 0 ? commandSuggestions.length - 1 : prev - 1;
                }
                return prev >= commandSuggestions.length - 1 ? 0 : prev + 1;
            });
            return;
        }
        
        // Handle left arrow - move cursor left
        if (key.leftArrow) {
            setCursorPosition(prev => {
                const next = Math.max(0, prev - 1);
                cursorPositionRef.current = next;
                return next;
            });
            return;
        }
        
        // Handle right arrow - move cursor right
        if (key.rightArrow) {
            setCursorPosition(prev => {
                const next = Math.min(query.length, prev + 1);
                cursorPositionRef.current = next;
                return next;
            });
            return;
        }
        
        // Handle backspace/delete - delete character before cursor
        // On Mac, the "delete" key sends backspace, so we handle both
        if (key.backspace || key.delete) {
            if (pos > 0) {
                setQuery(prev => prev.slice(0, pos - 1) + prev.slice(pos));
                const next = pos - 1;
                cursorPositionRef.current = next;
                setCursorPosition(next);
            }
            return;
        }
        
        // Handle Ctrl+C or other special keys
        if (key.ctrl && input === 'c') {
            return; // Let it pass through or handle exit
        }
        
        // Detect paste: when input.length > 1, it's a paste event.
        // We MUST use cursorPositionRef here because terminals can split a
        // paste into multiple rapid useInput calls - each must see the
        // position left by the previous chunk, not a stale closure value.
        if (input.length > 1) {
            // Clean the pasted input - remove control characters and normalize
            const cleanedInput = input
                .replace(/\r\n/g, ' ')
                .replace(/\r/g, ' ')
                .replace(/\n/g, ' ')
                .replace(/[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]/g, '') // Remove control chars
                .trim();
            
            if (cleanedInput) {
                const insertPos = cursorPositionRef.current;
                setQuery(prev => prev.slice(0, insertPos) + cleanedInput + prev.slice(insertPos));
                const next = insertPos + cleanedInput.length;
                cursorPositionRef.current = next;
                setCursorPosition(next);
            }
            return;
        }
        
        // Single character input - insert at cursor position
        if (input && input.length === 1) {
            setQuery(prev => prev.slice(0, pos) + input + prev.slice(pos));
            const next = pos + 1;
            cursorPositionRef.current = next;
            setCursorPosition(next);
        }
    }, { isActive: !isLoading });

    // Determine placeholder text based on mode
    const placeholderText = confirmDeleteArchive
        ? "⚠ This will DELETE all archives! Type 'yes' to confirm or 'no' to cancel"
        : revertConfirm
            ? `Revert to Task ${revertTargetTask ?? '?'}? Type 'yes' to confirm or 'no' to cancel`
            : completedRunPrompt
            ? "Previous results found. Enter to auto-improve (or 'no' to start fresh)"
            : startRequestConfirm
                ? "Submit this request? (yes/no)"
                : planAwaitingConfirm
                    ? "Proceed with this plan? (yes/no, or describe changes)"
                    : checkpointPrompt
                        ? allowCheckpointSteering
                            ? "Resume: Enter to continue, type instructions to steer, or 'no' to start fresh"
                            : "Resume: Enter to continue, or type 'no' to start fresh"
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
            <Box
                width={bannerBoxWidth}
                borderStyle="round"
                borderColor={promptBorderColor}
                paddingX={1}
                justifyContent="space-between"
            >
                <Box>
                    <Text>
                        <StarSpinner isLoading={isLoading} />
                        {isLoading ? (
                            <Text>{truncatedLoadingText}</Text>
                        ) : (
                            <>
                                {query === '' ? (
                                    <>
                                        <Text inverse>{firstChar || ' '}</Text>
                                        <Text dimColor>{restPlaceholder}</Text>
                                    </>
                                ) : (
                                    <>
                                        <Text>{query.slice(0, cursorPosition)}</Text>
                                        {cursorPosition < query.length ? (
                                            <>
                                                <Text inverse>{query[cursorPosition]}</Text>
                                                <Text>{query.slice(cursorPosition + 1)}</Text>
                                            </>
                                        ) : (
                                            <Text inverse> </Text>
                                        )}
                                    </>
                                )}
                            </>
                        )}
                    </Text>
                </Box>
                <Box>
                    <Text color={tokenUsageColor as any} dimColor={!contextUsage?.is_supported_model}>
                        {tokenUsageLabel}
                    </Text>
                    {hasTaskProgress ? (
                        <>
                            <Text dimColor>  │  </Text>
                            <Text color={cliTheme.ink.accent}>{taskProgressLabel}</Text>
                        </>
                    ) : null}
                </Box>
            </Box>
            {revertConfirm ? (
                <Box paddingX={1} marginTop={1}>
                    <Text color={cliTheme.ink.warning}>This deletes checkpoints and task folders after Task {revertTargetTask ?? '?'}</Text>
                </Box>
            ) : startRequestConfirm && pendingSubmitPreview ? (
                <Box paddingX={1} marginTop={1}>
                    <Text dimColor>Request to send: </Text>
                    <Text color={cliTheme.ink.warning}>{truncateText(pendingSubmitPreview, inputTextMaxWidth - 18)}</Text>
                </Box>
            ) : null}
            {showInterruptWarning ? (
                <Box paddingX={1} marginTop={1}>
                    <Text color={cliTheme.ink.warning}>⚠ Press ESC again to interrupt</Text>
                </Box>
            ) : showExitWarning ? (
                <Box paddingX={1} marginTop={1}>
                    <Text color={cliTheme.ink.warning}>⚠ Press Ctrl+C again to exit</Text>
                </Box>
            ) : showCommandSuggestions ? (
                <Box paddingX={1} marginTop={1} flexDirection="column">
                    <Text color={cliTheme.ink.accent} bold>Commands</Text>
                    {commandSuggestions.length > 0 ? (
                        commandSuggestions.map((command, index) => {
                            const isSelected = index === activeCommandIndex;
                            const availableDescriptionWidth = Math.max(16, bannerBoxWidth - command.command.length - 10);
                            return (
                                <Text key={command.id}>
                                    <Text color={isSelected ? cliTheme.ink.primary : cliTheme.ink.muted}>
                                        {isSelected ? '› ' : '  '}
                                    </Text>
                                    <Text color={isSelected ? cliTheme.ink.text : cliTheme.ink.muted} bold={isSelected}>
                                        {command.command}
                                    </Text>
                                    <Text dimColor>  {truncateText(command.description, availableDescriptionWidth)}</Text>
                                </Text>
                            );
                        })
                    ) : (
                        <Text color={cliTheme.ink.warning}>No matching commands</Text>
                    )}
                    <Text dimColor>Up/Down select · Tab complete · Enter run</Text>
                </Box>
            ) : (
                <Box paddingX={1} marginTop={1}>
                    <Text dimColor>ESC interrupt · Ctrl+D/Ctrl+C exit</Text>
                </Box>
            )}
        </Box>
    );
};

export default PromptInput;
