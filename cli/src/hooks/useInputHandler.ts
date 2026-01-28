/**
 * Hook for ESC interrupt and Ctrl+C exit handling
 */
import { useState, useRef, useCallback } from 'react';
import { useInput } from 'ink';
import type { AgentInfo, CommittedItem } from './types.js';

interface InputHandlerOptions {
    isLoading: boolean;
    agents: AgentInfo[];
    bridgeRef: React.MutableRefObject<any>;
    onInterrupt: () => void;
    onExit: () => void;
    onCommitItem: (updater: (prev: CommittedItem[]) => CommittedItem[]) => void;
}

interface InputHandlerResult {
    showInterruptWarning: boolean;
    showExitWarning: boolean;
}

export function useInputHandler({
    isLoading,
    agents,
    bridgeRef,
    onInterrupt,
    onExit,
    onCommitItem
}: InputHandlerOptions): InputHandlerResult {
    const [escPressedOnce, setEscPressedOnce] = useState(false);
    const [showInterruptWarning, setShowInterruptWarning] = useState(false);
    const [exitPressedOnce, setExitPressedOnce] = useState(false);
    const [showExitWarning, setShowExitWarning] = useState(false);
    
    const escTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const exitTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    useInput((input, key) => {
        // Handle Ctrl+C and Ctrl+D - only exit when NOT loading (idle state)
        if ((key.ctrl && input === 'c') || input === '\x04') {
            if (!isLoading) {
                if (exitPressedOnce) {
                    if (exitTimeoutRef.current) {
                        clearTimeout(exitTimeoutRef.current);
                        exitTimeoutRef.current = null;
                    }
                    setExitPressedOnce(false);
                    setShowExitWarning(false);
                    onExit();
                } else {
                    setExitPressedOnce(true);
                    setShowExitWarning(true);
                    
                    if (exitTimeoutRef.current) {
                        clearTimeout(exitTimeoutRef.current);
                    }
                    exitTimeoutRef.current = setTimeout(() => {
                        setExitPressedOnce(false);
                        setShowExitWarning(false);
                    }, 3000);
                }
            }
            return;
        }
        
        // ESC handling - only when system is loading/running
        if (!isLoading) {
            if (escPressedOnce) {
                setEscPressedOnce(false);
                setShowInterruptWarning(false);
            }
            return;
        }
        
        if (key.escape) {
            if (escPressedOnce) {
                if (escTimeoutRef.current) {
                    clearTimeout(escTimeoutRef.current);
                    escTimeoutRef.current = null;
                }
                setEscPressedOnce(false);
                setShowInterruptWarning(false);
                
                // Commit "Run Interrupted" status for the active agent
                onCommitItem(prev => {
                    const activeAgent = agents.find(a => a.status === 'active');
                    if (activeAgent) {
                        return [...prev, {
                            id: `interrupt-${Date.now()}`,
                            type: 'log',
                            content: '✗ Run Interrupted',
                            agentName: activeAgent.name
                        }];
                    }
                    return prev;
                });
                
                // Kill the bridge process
                if (bridgeRef.current) {
                    bridgeRef.current.kill('SIGKILL');
                    bridgeRef.current = null;
                }
                
                onInterrupt();
            } else {
                setEscPressedOnce(true);
                setShowInterruptWarning(true);
                
                if (escTimeoutRef.current) {
                    clearTimeout(escTimeoutRef.current);
                }
                escTimeoutRef.current = setTimeout(() => {
                    setEscPressedOnce(false);
                    setShowInterruptWarning(false);
                }, 3000);
            }
        }
    });

    return {
        showInterruptWarning,
        showExitWarning
    };
}
