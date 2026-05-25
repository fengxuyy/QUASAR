/**
 * Run Command - Main CLI execution component
 * Refactored to use extracted hooks and modules
 */
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Box, Text, useApp, useStdout, Static, useInput } from 'ink';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';

// UI Components
import PromptInput from '../ui/PromptInput.js';
import Banner from '../ui/Banner.js';
import Settings from '../ui/Settings.js';
import { RagStatus, ActiveAgentStatus, StaticItemRenderer } from '../ui/Run/index.js';
import TriangleSpinner from '../ui/Run/TriangleSpinner.js';

// Hooks and Types
import { 
    AgentInfo, 
    CommittedItem, 
    ContextUsage,
    RagStatusInfo, 
    TaskProgress, 
    FileContent,
    CheckpointMode,
    SystemStatus 
} from '../hooks/types.js';

// Utils
import { generateUniqueId, truncateText } from '../utils/helpers.js';
import { cleanTaskDescription, applyFreshStartState, applyInterruptResetState } from '../utils/stateHelpers.js';
import { INDENT_AGENT } from '../utils/constants.js';
import { cliTheme } from '../ui/theme.js';
import { loadReport, normalizeReportCommand } from '../utils/reportFiles.js';
import { parseCliCommand } from '../utils/commandRegistry.js';

// Handlers
import { createMessageHandler, type MessageHandlerContext } from '../handlers/messageHandlers.js';
import { handleCheckpointInfo as handleCheckpointInfoFn } from '../handlers/checkpointHandler.js';



interface RunProps {
    args: string[];
    flags: any;
}

const Run: React.FC<RunProps> = ({ args, flags }) => {
    const { exit } = useApp();
    const { stdout } = useStdout();
    const terminalWidth = stdout?.columns || 100;
    const availableWidth = Math.max(20, terminalWidth - 14);
    const leftMargin = Math.max(0, Math.floor((terminalWidth - availableWidth) / 2));
    
    // ========== STATE ==========
    const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
    const [status, setStatus] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [isResizing, setIsResizing] = useState(false);
    const [settingsMode, setSettingsMode] = useState(false);
    const [missingVars, setMissingVars] = useState<string[]>([]);
    
    const [ragStatus, setRagStatus] = useState<RagStatusInfo | null>(null);
    const ragStatusRef = useRef<RagStatusInfo | null>(null);
    const [isSystemReady, setIsSystemReady] = useState(false);
    const [showMainUI, setShowMainUI] = useState(false);
    
    const [systemStatus, setSystemStatus] = useState<SystemStatus>('idle');
    const [agents, setAgents] = useState<AgentInfo[]>([]);
    
    const [planContent, setPlanContent] = useState<string>('');
    const [isPlanComplete, setIsPlanComplete] = useState(false);
    
    const activeFileContentRef = useRef<FileContent | null>(null);
    
    const [taskProgress, setTaskProgress] = useState<TaskProgress | null>(null);
    const taskProgressRef = useRef<TaskProgress | null>(null);
    const [contextUsage, setContextUsage] = useState<ContextUsage | null>(null);
    
    const [committedItems, setCommittedItems] = useState<CommittedItem[]>([]);
    const [bannerCommitted, setBannerCommitted] = useState(false);
    
    const [checkpointMode, setCheckpointMode] = useState<CheckpointMode>('checking');
    const [previousInput, setPreviousInput] = useState<string>('');
    const [allowCheckpointSteering, setAllowCheckpointSteering] = useState(false);
    const [pendingStartPrompt, setPendingStartPrompt] = useState('');
    const [pendingRevertTask, setPendingRevertTask] = useState<number | null>(null);
    const [checkpointModeBeforeRevert, setCheckpointModeBeforeRevert] = useState<CheckpointMode>('normal');
    const skipStartConfirmOnceRef = useRef(false);
    const hasCompletedFirstInteractivePromptRef = useRef(false);
    const [isPeriodicCheckinActive, setIsPeriodicCheckinActiveState] = useState(false);
    const [periodicCheckinToolCall, setPeriodicCheckinToolCall] = useState<{ content: string; isError: boolean } | null>(null);
    const isPeriodicCheckinActiveRef = useRef(false);
    const resumingWithEvaluatorRef = useRef(false);
    
    const [escPressedOnce, setEscPressedOnce] = useState(false);
    const [showInterruptWarning, setShowInterruptWarning] = useState(false);
    const isInterruptedRef = useRef(false);
    const escTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const [cleanupStatus, setCleanupStatus] = useState<{ status: string; message: string } | null>(null);
    
    const [exitPressedOnce, setExitPressedOnce] = useState(false);
    const [showExitWarning, setShowExitWarning] = useState(false);
    const exitTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    
    const [resizeCounter, setResizeCounter] = useState(0);
    const [staticKey, setStaticKey] = useState(0);
    const bridgeRef = useRef<any>(null);
    const bridgeStdoutBufferRef = useRef<string>('');
    const resizeTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const [bridgeRestartCounter, setBridgeRestartCounter] = useState(0);
    
    const itemIdCounterRef = useRef<number>(0);

    const [parsedPlan, setParsedPlan] = useState<string[]>([]);
    const parsedPlanRef = useRef<string[]>([]);

    const [inputPrefillRevision, setInputPrefillRevision] = useState(0);
    const [inputPrefillText, setInputPrefillText] = useState('');
    const pendingFreshStartPrefillRef = useRef('');
    const bumpInputPrefill = useCallback((text: string) => {
        setInputPrefillText(text);
        setInputPrefillRevision((r) => r + 1);
    }, []);
    const queueFreshStartPrefill = useCallback((text: string) => {
        pendingFreshStartPrefillRef.current = text;
    }, []);
    const restorePendingFreshStartPrefill = useCallback(() => {
        const text = pendingFreshStartPrefillRef.current;
        pendingFreshStartPrefillRef.current = '';
        if (!text.trim()) return;
        setPreviousInput(text);
        bumpInputPrefill(text);
    }, [bumpInputPrefill]);

    const setIsPeriodicCheckinActive = useCallback((active: boolean) => {
        isPeriodicCheckinActiveRef.current = active;
        setIsPeriodicCheckinActiveState(active);
    }, []);

    // ========== HELPERS ==========
    const genUniqueId = useCallback((prefix: string) => 
        generateUniqueId(prefix, itemIdCounterRef), []);
    
    const ensureHeader = useCallback((items: CommittedItem[], agentName: string, taskNum?: number): CommittedItem[] => {
        if (agentName === 'operator' && taskNum !== undefined) {
            const headerId = `${agentName}-header-task${taskNum}`;
            // Checkpoint restore uses "*-history" suffix IDs; treat those as existing too.
            if (items.some(item => item.id === headerId || item.id.startsWith(`${headerId}-`))) return items;
            
            const lastItem = items[items.length - 1];
            if (lastItem && lastItem.agentName === 'operator' && taskNum == 1) return items;
            if (taskNum == 1 && items.some(item => item.id === `${agentName}-header`)) return items;
            
            const newItems: CommittedItem[] = [...items, { id: headerId, type: 'agent-header', content: agentName, agentName, taskNum }];
            
            if (parsedPlanRef.current && parsedPlanRef.current.length >= taskNum) {
                const rawTask = parsedPlanRef.current[taskNum - 1];
                if (rawTask) {
                    const cleanDescription = cleanTaskDescription(rawTask);
                    newItems.push({
                        id: `${agentName}-task-panel-${taskNum}`,
                        type: 'active-task-panel', 
                        content: { description: cleanDescription, taskNum },
                        agentName,
                        taskNum
                    });
                }
            }
            
            return newItems;
        }
        
        if (agentName === 'evaluator') {
            const evaluatorHeaderForThisTask = taskNum 
                ? items.some(item => item.type === 'evaluator-header' && item.id?.includes(`task${taskNum}`))
                : items.some(item => item.type === 'evaluator-header');
            
            if (!evaluatorHeaderForThisTask) {
                const headerId = taskNum ? `evaluator-header-task${taskNum}` : `evaluator-header-${Date.now()}`;
                return [...items, { id: headerId, type: 'evaluator-header', content: agentName, agentName, taskNum }];
            }
            return items;
        }
        
        const headerId = `${agentName}-header`;
        if (items.some(item => item.id === headerId)) return items;
        return [...items, { id: headerId, type: 'agent-header', content: agentName, agentName }];
    }, []);

    useEffect(() => {
        parsedPlanRef.current = parsedPlan;
    }, [parsedPlan]);

    // Checkpoint handler callback
    const handleCheckpointInfo = useCallback((payload: any) => {
        handleCheckpointInfoFn({
            setParsedPlan,
            setCommittedItems,
            setTaskProgress,
            taskProgressRef,
            setCheckpointMode,
            setPreviousInput,
            setAllowCheckpointSteering,
            setIsLoading,
            bridgeRef,
            resumingWithEvaluatorRef
        }, payload);
    }, []);

    // ========== EFFECTS ==========
    
    // Clear screen on mount
    const hasClearedScreen = useRef(false);
    useEffect(() => {
        if (!hasClearedScreen.current) {
            process.stdout.write('\x1B[2J\x1B[0;0H');
            hasClearedScreen.current = true;
        }
    }, []);

    // Show main UI after RAG init. If RAG errors, still allow checkpoint resume.
    useEffect(() => {
        if (ragStatus?.status === 'done' || ragStatus?.status === 'error') {
            const timer = setTimeout(() => {
                setShowMainUI(true);
                if (bridgeRef.current) {
                    bridgeRef.current.stdin.write(JSON.stringify({ command: 'check_checkpoint' }) + "\n");
                }
            }, 1000);
            return () => clearTimeout(timer);
        }
    }, [ragStatus?.status]);

    // If RAG is disabled, the bridge sends system_ready without any rag_status.
    // Do the checkpoint check from system_ready so resume is not gated on RAG.
    useEffect(() => {
        if (isSystemReady && !ragStatus && !showMainUI) {
            setShowMainUI(true);
            if (bridgeRef.current) {
                bridgeRef.current.stdin.write(JSON.stringify({ command: 'check_checkpoint' }) + "\n");
            }
        }
    }, [isSystemReady, ragStatus, showMainUI]);

    // Commit banner on mount
    useEffect(() => {
        if (!bannerCommitted) {
            setBannerCommitted(true);
            setCommittedItems(prev => {
                if (prev.some(item => item.id === 'banner')) return prev;
                return [...prev, { id: 'banner', type: 'banner', content: {} }];
            });
        }
    }, [bannerCommitted]);

    // Handle resize
    useEffect(() => {
        let lastWidth = process.stdout.columns;
        let lastHeight = process.stdout.rows;
        
        const handleResize = () => {
            const currentWidth = process.stdout.columns;
            const currentHeight = process.stdout.rows;
            
            if (currentWidth !== lastWidth || currentHeight !== lastHeight) {
                lastWidth = currentWidth;
                lastHeight = currentHeight;
                
                if (resizeTimeoutRef.current) clearTimeout(resizeTimeoutRef.current);
                
                resizeTimeoutRef.current = setTimeout(() => {
                    process.stdout.write('\x1B[2J\x1B[3J\x1B[H');
                    setCommittedItems(prev => {
                        const items = [...prev];
                        setTimeout(() => {
                            setCommittedItems(items);
                            setResizeCounter(rc => rc + 1);
                        }, 50);
                        return [];
                    });
                    setIsResizing(prev => !prev);
                }, 150);
            }
        };

        process.stdout.on('resize', handleResize);
        return () => {
            process.stdout.off('resize', handleResize);
            if (resizeTimeoutRef.current) clearTimeout(resizeTimeoutRef.current);
        };
    }, []);

    // ========== BRIDGE ==========
    useEffect(() => {
        let bridgePath = process.env.QUASAR_BRIDGE_PATH;
        
        if (!bridgePath) {
            const candidates = [
                path.resolve(process.cwd(), '../bridge.py'),
                path.resolve(process.cwd(), 'bridge.py'),
                '/app/bridge.py'
            ];
            for (const p of candidates) {
                if (fs.existsSync(p)) {
                    bridgePath = p;
                    break;
                }
            }
        }
        
        if (!bridgePath) {
            setMessages(prev => [...prev, { role: 'system', content: `Error: Could not find bridge.py` }]);
            return;
        }

        const child = spawn('python3', [bridgePath], {
            cwd: path.dirname(bridgePath),
            stdio: ['pipe', 'pipe', 'pipe'],
            env: { ...process.env, SKIP_RAG: bridgeRestartCounter > 0 ? 'true' : 'false' }
        });

        bridgeRef.current = child;

        // Track if direct args were used
        const directArgsUsed = args.length > 0;

        // Create message handler context
        const ctx: MessageHandlerContext = {
            setModelName: () => {},
            setStatus,
            setIsLoading,
            setMessages,
            setRagStatus,
            setIsSystemReady,
            setSystemStatus,
            setAgents,
            setPlanContent,
            setIsPlanComplete,
            setTaskProgress,
            setContextUsage,
            setCommittedItems,
            setCheckpointMode,
            setPreviousInput,
            setShowMainUI,
            setParsedPlan,
            setIsPeriodicCheckinActive,
            setPeriodicCheckinToolCall,
            setCleanupStatus,
            ragStatusRef,
            bridgeRef,
            taskProgressRef,
            activeFileContentRef,
            isInterruptedRef,
            isPeriodicCheckinActiveRef,
            resumingWithEvaluatorRef,
            ensureHeader,
            genUniqueId,
            handleCheckpointInfo,
            setStaticKey,
            setBannerCommitted,
            itemIdCounterRef,
            bumpInputPrefill,
            restorePendingFreshStartPrefill,
            exitIfDirectArgs: () => {
                if (directArgsUsed) {
                    setTimeout(() => exit(), 500);
                }
            }
        };
        
        const handleBridgeMessage = createMessageHandler(ctx);

        child.stdout.on('data', (data) => {
            bridgeStdoutBufferRef.current += data.toString();
            const lines = bridgeStdoutBufferRef.current.split('\n');
            bridgeStdoutBufferRef.current = lines.pop() || '';

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    handleBridgeMessage(JSON.parse(line));
                } catch (e) {}
            }
        });

        child.stderr?.on('data', (data: Buffer) => {
            // Suppress all library noise (warnings, HF, tokenizer, etc.).
            // Only surface genuine Python errors to avoid polluting the Ink UI.
            const errStr = data.toString().trim();
            if (errStr && (errStr.includes('Traceback') || errStr.includes('Error: '))) {
                handleBridgeMessage({ type: 'error', payload: { message: 'Bridge Error', traceback: errStr } });
            }
        });

        child.on('error', (err: Error) => {
            setMessages(prev => [...prev, { role: 'system', content: `Bridge Error: ${err.message}` }]);
        });

        return () => { child.kill(); };
    }, [bridgeRestartCounter, ensureHeader, genUniqueId, handleCheckpointInfo, restorePendingFreshStartPrefill]);

    // Direct prompt mode
    useEffect(() => {
        if (args.length > 0) {
            setTimeout(() => handleSubmit(args.join(' ')), 1000);
        }
    }, []);

    // ========== HELPERS ==========
    const sendToBridge = useCallback((msg: object) => {
        try {
            bridgeRef.current?.stdin?.write(JSON.stringify(msg) + '\n');
        } catch (e) {
            // bridge may not be ready
        }
    }, []);

    const appendSystemLog = useCallback((content: string, isError = false) => {
        setCommittedItems(prev => [
            ...prev,
            {
                id: genUniqueId(isError ? 'system-error' : 'system-log'),
                type: 'log',
                content,
                agentName: 'system',
                isError
            }
        ]);
    }, [genUniqueId]);

    // ========== HANDLERS ==========
    const handleSubmit = async (input: string) => {
        if (input.trim().toLowerCase() === 'exit') {
            exit();
            return;
        }

        if (checkpointMode === 'confirm-revert') {
            const answer = input.trim().toLowerCase();
            if (answer === 'yes' || answer === 'y') {
                if (!pendingRevertTask) {
                    setCheckpointMode('normal');
                    return;
                }
                setPreviousInput(`Reverting to Task ${pendingRevertTask}`);
                setIsLoading(true);
                setStatus(`Reverting to Task ${pendingRevertTask}...`);
                sendToBridge({ command: 'revert', target_task: pendingRevertTask });
                setPendingRevertTask(null);
            } else {
                setPendingRevertTask(null);
                setStatus(null);
                setCheckpointMode(checkpointModeBeforeRevert);
            }
            return;
        }

        const cliCommand = parseCliCommand(input);

        if (cliCommand?.id === 'settings') {
            setMissingVars([]);
            setSettingsMode(true);
            return;
        }

        if (cliCommand?.id === 'refresh') {
            process.stdout.write('\x1B[2J\x1B[3J\x1B[H');
            applyFreshStartState({
                setPreviousInput, setTaskProgress, taskProgressRef, setCommittedItems,
                setBannerCommitted, setPlanContent, setIsPlanComplete, setAgents,
                activeFileContentRef, setSystemStatus, itemIdCounterRef
            });
            hasCompletedFirstInteractivePromptRef.current = false;
            setParsedPlan([]);
            setStaticKey(prev => prev + 1);
            setIsPeriodicCheckinActive(false);
            setPeriodicCheckinToolCall(null);
            if (bridgeRef.current) {
                bridgeRef.current.stdin.write(JSON.stringify({ command: 'clear_checkpoint' }) + "\n");
            }
            return;
        }

        if (cliCommand?.id === 'revert') {
            const rawTarget = cliCommand.args[0];
            const targetTask = Number(rawTarget);
            if (cliCommand.args.length !== 1 || !Number.isInteger(targetTask) || targetTask < 1) {
                appendSystemLog('Usage: \\revert <task-number> (for example: \\revert 2)', true);
                return;
            }
            if (isLoading || systemStatus === 'running') {
                appendSystemLog('✗ Cannot revert while execution is running', true);
                return;
            }
            setPendingRevertTask(targetTask);
            setCheckpointModeBeforeRevert(checkpointMode);
            setCheckpointMode('confirm-revert');
            setStatus(null);
            return;
        }

        const reportKind = normalizeReportCommand(input);
        if (reportKind) {
            const report = loadReport(reportKind);
            setShowMainUI(true);
            setStatus(null);
            setCommittedItems(prev => [
                ...prev,
                {
                    id: genUniqueId(`report-${reportKind}`),
                    type: 'report-panel',
                    content: {
                        title: report.title,
                        content: report.error ? `${report.content}\n\n${report.error}` : report.content,
                        sourcePath: report.sourcePath
                    },
                    agentName: 'system',
                    isError: Boolean(report.error)
                }
            ]);
            return;
        }

        const model = process.env.MODEL;
        const apiKey = process.env.MODEL_API_KEY;
        const missing = [];
        if (!model) missing.push('MODEL');
        if (!apiKey) missing.push('MODEL_API_KEY');

        if (missing.length > 0 && checkpointMode !== 'plan-awaiting-confirm' && checkpointMode !== 'auto-resume') {
            setMissingVars(missing);
            setInputPrefillText(input);
            setInputPrefillRevision(prev => prev + 1);
            setSettingsMode(true);
            return;
        }

        // Prompt has officially passed validation interceptors.
        // Prune any stale prefill data to ensure it doesn't accidentally bleed into subsequent UI confirmations that remount the PromptInput.
        setInputPrefillText('');
        setInputPrefillRevision(0);

        if (checkpointMode === 'plan-awaiting-confirm') {
            const trimmedInput = input.trim();
            const answer = trimmedInput.toLowerCase();
            if (answer === 'yes') {
                if (bridgeRef.current) {
                    bridgeRef.current.stdin.write(JSON.stringify({ command: 'plan_confirm', action: 'confirm', feedback: '' }) + '\n');
                }
                setCheckpointMode('normal');
                setIsLoading(true);
                return;
            }
            if (answer === 'no') {
                if (bridgeRef.current) {
                    bridgeRef.current.stdin.write(JSON.stringify({ command: 'plan_confirm', action: 'decline', feedback: '' }) + '\n');
                }
                return;
            }
            if (trimmedInput) {
                if (bridgeRef.current) {
                    bridgeRef.current.stdin.write(JSON.stringify({
                        command: 'plan_confirm',
                        action: 'revise',
                        feedback: trimmedInput
                    }) + '\n');
                }
                setCheckpointMode('normal');
                setIsLoading(true);
            }
            return;
        }

        if (checkpointMode === 'prompt') {
            const trimmedInput = input.trim();
            const answer = trimmedInput.toLowerCase();
            if (answer === '' || answer === 'yes' || answer === 'y') {
                setCheckpointMode('auto-resume');
                setIsLoading(true);
                if (bridgeRef.current) {
                    // IMPORTANT: restart: false to preserve checkpoint and resume from it
                    // restart: true would delete the checkpoint!
                    bridgeRef.current.stdin.write(JSON.stringify({ command: 'prompt', content: '', restart: false }) + "\n");
                }
            } else if (answer === 'no' || answer === 'n') {
                queueFreshStartPrefill(previousInput);
                // Clear checkpoint but keep archives - use clear_checkpoint command
                // After clearing, bridge will check if archives exist and send appropriate response
                process.stdout.write('\x1B[2J\x1B[3J\x1B[H');
                applyFreshStartState({
                    setPreviousInput, setTaskProgress, taskProgressRef, setCommittedItems,
                    setBannerCommitted, setPlanContent, setIsPlanComplete, setAgents,
                    activeFileContentRef, setSystemStatus, itemIdCounterRef
                });
                hasCompletedFirstInteractivePromptRef.current = false;
                setParsedPlan([]);
                setStaticKey(prev => prev + 1);
                setIsPeriodicCheckinActive(false);
                setPeriodicCheckinToolCall(null);
                // Don't set checkpointMode here - let the bridge response determine it
                // based on whether archives exist
                if (bridgeRef.current) {
                    bridgeRef.current.stdin.write(JSON.stringify({ command: 'clear_checkpoint' }) + "\n");
                }
            } else {
                if (!allowCheckpointSteering) {
                    setStatus("Steering is only available when resuming operator work. Press Enter to continue, or type 'no' to start fresh.");
                    return;
                }
                setCheckpointMode('auto-resume');
                setIsLoading(true);
                setPreviousInput(trimmedInput);
                setStatus("Resuming from checkpoint...");
                if (bridgeRef.current) {
                    bridgeRef.current.stdin.write(JSON.stringify({ command: 'prompt', content: trimmedInput, restart: false }) + "\n");
                }
            }
            return;
        }

        if (checkpointMode === 'completed-run-prompt') {
            const answer = input.trim().toLowerCase();
            if (answer === 'yes') {
                // "yes" just transitions to normal mode to allow typing a new request
                setCheckpointMode('normal');
                return;
            } else if (answer === 'no') {
                // Ask for confirmation before deleting archives
                setCheckpointMode('confirm-delete-archive');
                return;
            } else {
                // Either empty string (auto-improve) or arbitrary text
                if (!input.trim()) {
                    setPreviousInput("Auto-improve");
                }
                // Transition to normal mode and fall through to prompt submission
                setCheckpointMode('normal');
                // Same submit path as improve/auto-improve — no second yes/no gate
                skipStartConfirmOnceRef.current = true;
            }
        }

        if (checkpointMode === 'confirm-delete-archive') {
            const answer = input.trim().toLowerCase();
            if (answer === 'yes') {
                queueFreshStartPrefill(previousInput);
                // User confirmed - proceed with fresh start (deletes archives)
                process.stdout.write('\x1B[2J\x1B[3J\x1B[H');
                applyFreshStartState({
                    setPreviousInput, setTaskProgress, taskProgressRef, setCommittedItems,
                    setBannerCommitted, setPlanContent, setIsPlanComplete, setAgents,
                    activeFileContentRef, setSystemStatus, itemIdCounterRef
                });
                hasCompletedFirstInteractivePromptRef.current = false;
                setParsedPlan([]);
                setCheckpointMode('normal');
                setStaticKey(prev => prev + 1);
                setIsPeriodicCheckinActive(false);
                setPeriodicCheckinToolCall(null);
                if (bridgeRef.current) {
                    bridgeRef.current.stdin.write(JSON.stringify({ command: 'fresh_start' }) + "\n");
                }
            } else {
                // User cancelled - go back to normal mode
                setCheckpointMode('normal');
            }
            return;
        }

        if (checkpointMode === 'confirm-start-prompt') {
            const answer = input.trim().toLowerCase();
            if (answer === 'yes') {
                const toSend = pendingStartPrompt;
                setPendingStartPrompt('');
                setCheckpointMode('normal');
                if (!toSend.trim()) {
                    return;
                }
                isInterruptedRef.current = false;
                setIsLoading(true);
                setStatus("Sending to backend...");
                if (bridgeRef.current) {
                    const restartFromEnv = ['true', '1', 'yes', 'on'].includes((process.env.IF_RESTART || '').toLowerCase());
                    bridgeRef.current.stdin.write(JSON.stringify({
                        command: 'prompt',
                        content: toSend,
                        restart: flags.restart || restartFromEnv
                    }) + "\n");
                }
                hasCompletedFirstInteractivePromptRef.current = true;
            } else if (answer === 'no') {
                const originalText = pendingStartPrompt;
                setPendingStartPrompt('');
                setStatus(null);
                setCheckpointMode('normal');
                // Restore the user's original request text so they don't lose it
                if (originalText.trim()) {
                    bumpInputPrefill(originalText);
                }
            }
            return;
        }

        const isInteractiveRun = args.length === 0;
        if (
            checkpointMode === 'normal' &&
            isInteractiveRun &&
            !skipStartConfirmOnceRef.current &&
            input.trim() &&
            !hasCompletedFirstInteractivePromptRef.current
        ) {
            setPendingStartPrompt(input);
            setCheckpointMode('confirm-start-prompt');
            return;
        }
        if (skipStartConfirmOnceRef.current) {
            skipStartConfirmOnceRef.current = false;
        }

        isInterruptedRef.current = false;
        setIsLoading(true);
        setStatus("Sending to backend...");
        
        if (bridgeRef.current) {
            const restartFromEnv = ['true', '1', 'yes', 'on'].includes((process.env.IF_RESTART || '').toLowerCase());
            bridgeRef.current.stdin.write(JSON.stringify({ 
                command: 'prompt', 
                content: input, 
                restart: flags.restart || restartFromEnv 
            }) + "\n");
        }
        if (isInteractiveRun && input.trim()) {
            hasCompletedFirstInteractivePromptRef.current = true;
        }
    };
    
    // Determine if we're in non-interactive mode (direct prompt passed)
    const isInlineCliCommand = args.length > 0 && parseCliCommand(args.join(' ')) !== null;
    const isInteractive = args.length === 0 || isInlineCliCommand;
    
    // Key handler - only active in interactive mode
    useInput((input, key) => {
        if ((key.ctrl && input === 'c') || input === '\x04') {
            if (!isLoading) {
                if (exitPressedOnce) {
                    if (exitTimeoutRef.current) clearTimeout(exitTimeoutRef.current);
                    setExitPressedOnce(false);
                    setShowExitWarning(false);
                    exit();
                } else {
                    setExitPressedOnce(true);
                    setShowExitWarning(true);
                    if (exitTimeoutRef.current) clearTimeout(exitTimeoutRef.current);
                    exitTimeoutRef.current = setTimeout(() => {
                        setExitPressedOnce(false);
                        setShowExitWarning(false);
                    }, 3000);
                }
            }
            return;
        }
        
        if (!isLoading) {
            if (escPressedOnce) {
                setEscPressedOnce(false);
                setShowInterruptWarning(false);
            }
            return;
        }
        
        if (key.escape) {
            if (escPressedOnce) {
                if (escTimeoutRef.current) clearTimeout(escTimeoutRef.current);
                setEscPressedOnce(false);
                setShowInterruptWarning(false);
                
                setCommittedItems(prev => {
                    const activeAgent = agents.find(a => a.status === 'active');
                    if (activeAgent) {
                        return [...prev, { id: `interrupt-${Date.now()}`, type: 'log', content: '✗ Run Interrupted', agentName: activeAgent.name }];
                    }
                    return prev;
                });
                
                if (bridgeRef.current) {
                    // First, send interrupt command to kill any running subprocesses (mpirun, etc.)
                    // This is critical because subprocesses run in their own process group and
                    // won't be killed when we SIGKILL the bridge process.
                    try {
                        if (bridgeRef.current.stdin) {
                            bridgeRef.current.stdin.write(JSON.stringify({ command: 'interrupt' }) + "\n");
                        }
                    } catch (e) {
                        // Ignore write errors - bridge may already be dead
                    }
                    
                    // Brief delay to allow subprocess cleanup, then kill the bridge
                    const bridgeToKill = bridgeRef.current;
                    bridgeRef.current = null;
                    setTimeout(() => {
                        try {
                            bridgeToKill.kill('SIGKILL');
                        } catch (e) {
                            // Ignore - process may already be dead
                        }
                    }, 150);
                }
                
                applyInterruptResetState({
                    setIsLoading, setStatus, setShowMainUI, setIsSystemReady,
                    setCheckpointMode, setSystemStatus, setAgents, setPlanContent,
                    setIsPlanComplete, setTaskProgress, isInterruptedRef
                });
                setIsPeriodicCheckinActive(false);
                setPeriodicCheckinToolCall(null);
                setBridgeRestartCounter(prev => prev + 1);
            } else {
                setEscPressedOnce(true);
                setShowInterruptWarning(true);
                if (escTimeoutRef.current) clearTimeout(escTimeoutRef.current);
                escTimeoutRef.current = setTimeout(() => {
                    setEscPressedOnce(false);
                    setShowInterruptWarning(false);
                }, 3000);
            }
        }
    }, { isActive: isInteractive });

    // ========== DERIVED STATE ==========
    const activeAgents = agents.filter(a => a.status === 'active');
    const evaluatorAgent = agents.find(a => a.name === 'evaluator');
    const showPeriodicCheckinStatus = isPeriodicCheckinActive;
    const periodicCheckinStatusText = periodicCheckinToolCall?.content || 'Awaiting Decision';
    const periodicCheckinStatusIsError = periodicCheckinToolCall?.isError ?? false;

    const staticItems = useMemo(() => {
        let hasRenderedBanner = false;
        return committedItems
            .filter(item => {
                if (item.type !== 'banner') return true;
                if (hasRenderedBanner) return false;
                hasRenderedBanner = true;
                return true;
            })
            .map(item => ({ ...item, _resizeKey: `${item.id}-r${resizeCounter}` }));
    }, [committedItems, resizeCounter]);

    // ========== RENDER ==========
    return (
        <Box flexDirection="column">
            {/* STATIC SECTION */}
            <Static key={`static-${staticKey}`} items={staticItems}>
                {(item) => (
                    <StaticItemRenderer 
                        key={item._resizeKey || item.id}
                        item={item}
                        leftMargin={leftMargin}
                        terminalWidth={terminalWidth}
                        availableWidth={availableWidth}
                    />
                )}
            </Static>

            {/* DYNAMIC SECTION */}
            
            {/* RAG Status */}
            {ragStatus && !showMainUI && (bridgeRestartCounter === 0 || ragStatus.status !== 'done') && (
                <RagStatus ragStatus={ragStatus} leftMargin={leftMargin} availableWidth={availableWidth} />
            )}

            {/* Dynamic content when main UI is shown */}
            {showMainUI && (
                <>
                    {/* Active agent statuses */}
                    {activeAgents.filter(a =>
                        a.name !== 'evaluator' &&
                        !(a.name === 'operator' && evaluatorAgent?.status === 'active') &&
                        // During periodic check-ins, transient status should replace
                        // the operator run-status row instead of rendering as a second line.
                        !(a.name === 'operator' && showPeriodicCheckinStatus)
                    ).map(agent => (
                        <ActiveAgentStatus key={`active-${agent.name}`} agent={agent} leftMargin={leftMargin} />
                    ))}

                    {/* Active evaluator */}
                    {evaluatorAgent?.status === 'active' && (
                        <ActiveAgentStatus agent={evaluatorAgent} leftMargin={leftMargin} isEvaluator />
                    )}

                    {/* Transient check-in status (overwrites in place, not committed) */}
                    {showPeriodicCheckinStatus && (
                        <Box marginLeft={leftMargin + INDENT_AGENT} paddingX={1}>
                            <Text>
                                <Text color={periodicCheckinStatusIsError ? cliTheme.ink.danger : cliTheme.ink.muted}>{cliTheme.glyph.branch} </Text>
                                {periodicCheckinToolCall ? (
                                    <Text color={periodicCheckinStatusIsError ? cliTheme.ink.danger : cliTheme.ink.success} bold>
                                        {periodicCheckinStatusIsError ? cliTheme.glyph.error : cliTheme.glyph.success}{' '}
                                        {truncateText(periodicCheckinStatusText, Math.max(20, terminalWidth - leftMargin - 10))}
                                    </Text>
                                ) : (
                                    <>
                                        <Text color={cliTheme.ink.primary}>
                                            <TriangleSpinner />{' '}
                                        </Text>
                                        <Text color={cliTheme.ink.primary} bold>
                                            {truncateText(periodicCheckinStatusText, Math.max(20, terminalWidth - leftMargin - 10))}
                                        </Text>
                                    </>
                                )}
                            </Text>
                        </Box>
                    )}

                    {/* Archiving status indicator */}
                    {cleanupStatus && (
                        <Box marginLeft={leftMargin + INDENT_AGENT} paddingX={1}>
                            <Text>
                                <Text color={cliTheme.ink.primary}>
                                    <TriangleSpinner />{' '}
                                </Text>
                                <Text color={cliTheme.ink.primary} bold>
                                    {cleanupStatus.message}
                                </Text>
                            </Text>
                        </Box>
                    )}

                    {/* Input Area / Settings */}
                    {isSystemReady && checkpointMode !== 'error' && checkpointMode !== 'checking' && (
                        settingsMode ? (
                            <Box flexDirection="column" width="100%">
                                <Settings 
                                    onExit={() => setSettingsMode(false)} 
                                    sendToBridge={sendToBridge} 
                                    highlightMissing={missingVars}
                                    isActive={settingsMode}
                                />
                            </Box>
                        ) : (
                            <Box marginTop={1}>
                                <PromptInput
                                    key={`prompt-${checkpointMode}-${inputPrefillRevision}`}
                                    onSubmit={handleSubmit} 
                                    isLoading={isLoading} 
                                    taskProgress={taskProgress}
                                    contextUsage={contextUsage}
                                    checkpointPrompt={checkpointMode === 'prompt'}
                                    allowCheckpointSteering={allowCheckpointSteering}
                                    completedRunPrompt={checkpointMode === 'completed-run-prompt'}
                                    confirmDeleteArchive={checkpointMode === 'confirm-delete-archive'}
                                    revertConfirm={checkpointMode === 'confirm-revert'}
                                    revertTargetTask={pendingRevertTask}
                                    startRequestConfirm={checkpointMode === 'confirm-start-prompt'}
                                    pendingSubmitPreview={pendingStartPrompt}
                                    planAwaitingConfirm={checkpointMode === 'plan-awaiting-confirm'}
                                    prefillRevision={inputPrefillRevision}
                                    prefillText={inputPrefillText}
                                    previousInput={previousInput}
                                    showInterruptWarning={showInterruptWarning}
                                    showExitWarning={showExitWarning}
                                />
                            </Box>
                        )
                    )}
                </>
            )}
        </Box>
    );
};

export default Run;
