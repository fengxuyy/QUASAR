/**
 * Run Command - Main CLI execution component
 * Refactored to use extracted hooks and modules
 */
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Box, useApp, useStdout, Static, useInput } from 'ink';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';

// UI Components
import PromptInput from '../ui/PromptInput.js';
import Banner from '../ui/Banner.js';
import { RagStatus, ActiveAgentStatus, StaticItemRenderer } from '../ui/Run/index.js';

// Hooks and Types
import { 
    AgentInfo, 
    CommittedItem, 
    RagStatusInfo, 
    TaskProgress, 
    FileContent,
    CheckpointMode,
    SystemStatus 
} from '../hooks/types.js';

// Utils
import { generateUniqueId } from '../utils/helpers.js';
import { cleanTaskDescription, applyFreshStartState, applyInterruptResetState } from '../utils/stateHelpers.js';

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
    const [modelName, setModelName] = useState<string>(process.env.MODEL || "");
    const [pmgConfigured, setPmgConfigured] = useState(!!process.env.PMG_MAPI_KEY);
    const [isResizing, setIsResizing] = useState(false);
    
    const [ragStatus, setRagStatus] = useState<RagStatusInfo | null>(null);
    const ragStatusRef = useRef<RagStatusInfo | null>(null);
    const [isSystemReady, setIsSystemReady] = useState(false);
    const [showMainUI, setShowMainUI] = useState(false);
    
    const [systemStatus, setSystemStatus] = useState<SystemStatus>('idle');
    const [agents, setAgents] = useState<AgentInfo[]>([]);
    
    const [planContent, setPlanContent] = useState<string>('');
    const [isPlanComplete, setIsPlanComplete] = useState(false);
    
    const activeFileContentRef = useRef<FileContent | null>(null);
    const lastCodeResultIsErrorRef = useRef<boolean>(false);
    
    const [taskProgress, setTaskProgress] = useState<TaskProgress | null>(null);
    const taskProgressRef = useRef<TaskProgress | null>(null);
    
    const [committedItems, setCommittedItems] = useState<CommittedItem[]>([]);
    const [bannerCommitted, setBannerCommitted] = useState(false);
    
    const [checkpointMode, setCheckpointMode] = useState<CheckpointMode>('checking');
    const [previousInput, setPreviousInput] = useState<string>('');
    
    const [escPressedOnce, setEscPressedOnce] = useState(false);
    const [showInterruptWarning, setShowInterruptWarning] = useState(false);
    const isInterruptedRef = useRef(false);
    const escTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    
    const [exitPressedOnce, setExitPressedOnce] = useState(false);
    const [showExitWarning, setShowExitWarning] = useState(false);
    const exitTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    
    const [resizeCounter, setResizeCounter] = useState(0);
    const [staticKey, setStaticKey] = useState(0);
    const bridgeRef = useRef<any>(null);
    const resizeTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const [bridgeRestartCounter, setBridgeRestartCounter] = useState(0);
    
    const itemIdCounterRef = useRef<number>(0);

    const [parsedPlan, setParsedPlan] = useState<string[]>([]);
    const parsedPlanRef = useRef<string[]>([]);

    // ========== HELPERS ==========
    const genUniqueId = useCallback((prefix: string) => 
        generateUniqueId(prefix, itemIdCounterRef), []);
    
    const ensureHeader = useCallback((items: CommittedItem[], agentName: string, taskNum?: number): CommittedItem[] => {
        if (agentName === 'operator' && taskNum !== undefined) {
            const headerId = `${agentName}-header-task${taskNum}`;
            if (items.some(item => item.id === headerId)) return items;
            
            const lastItem = items[items.length - 1];
            if (lastItem && lastItem.agentName === 'operator' && taskNum == 1) return items;
            if (taskNum == 1 && items.some(item => item.id === `${agentName}-header`)) return items;
            
            const newItems: CommittedItem[] = [...items, { id: headerId, type: 'agent-header', content: agentName, agentName }];
            
            if (parsedPlanRef.current && parsedPlanRef.current.length >= taskNum) {
                const rawTask = parsedPlanRef.current[taskNum - 1];
                if (rawTask) {
                    const cleanDescription = cleanTaskDescription(rawTask);
                    newItems.push({
                        id: `${agentName}-task-panel-${taskNum}`,
                        type: 'active-task-panel', 
                        content: { description: cleanDescription, taskNum },
                        agentName
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
                return [...items, { id: headerId, type: 'evaluator-header', content: agentName, agentName }];
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
            setIsLoading,
            bridgeRef
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

    // Show main UI after RAG init
    useEffect(() => {
        if (ragStatus?.status === 'done') {
            const timer = setTimeout(() => {
                setShowMainUI(true);
                if (bridgeRef.current) {
                    bridgeRef.current.stdin.write(JSON.stringify({ command: 'check_checkpoint' }) + "\n");
                }
            }, 1000);
            return () => clearTimeout(timer);
        }
    }, [ragStatus?.status]);

    // Commit banner when model is set
    useEffect(() => {
        if (modelName && !bannerCommitted) {
            setBannerCommitted(true);
            setCommittedItems(prev => {
                if (prev.some(item => item.id === 'banner')) return prev;
                return [...prev, { id: 'banner', type: 'banner', content: { modelName, pmgConfigured } }];
            });
        }
    }, [modelName, pmgConfigured, bannerCommitted]);

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
            stdio: ['pipe', 'pipe', 'inherit'],
            env: { ...process.env, SKIP_RAG: bridgeRestartCounter > 0 ? 'true' : 'false' }
        });

        bridgeRef.current = child;

        // Track if direct args were used
        const directArgsUsed = args.length > 0;

        // Create message handler context
        const ctx: MessageHandlerContext = {
            setModelName,
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
            setCommittedItems,
            setCheckpointMode,
            setPreviousInput,
            setShowMainUI,
            setParsedPlan,
            ragStatusRef,
            bridgeRef,
            taskProgressRef,
            activeFileContentRef,
            lastCodeResultIsErrorRef,
            isInterruptedRef,
            ensureHeader,
            genUniqueId,
            handleCheckpointInfo,
            exitIfDirectArgs: () => {
                if (directArgsUsed) {
                    setTimeout(() => exit(), 500);
                }
            }
        };
        
        const handleBridgeMessage = createMessageHandler(ctx);

        child.stdout.on('data', (data) => {
            const lines = data.toString().split('\n');
            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    handleBridgeMessage(JSON.parse(line));
                } catch (e) {}
            }
        });

        child.on('error', (err) => {
            setMessages(prev => [...prev, { role: 'system', content: `Bridge Error: ${err.message}` }]);
        });

        return () => { child.kill(); };
    }, [bridgeRestartCounter, ensureHeader, genUniqueId, handleCheckpointInfo]);

    // Direct prompt mode
    useEffect(() => {
        if (args.length > 0) {
            setTimeout(() => handleSubmit(args.join(' ')), 1000);
        }
    }, []);

    // ========== HANDLERS ==========
    const handleSubmit = async (input: string) => {
        if (input.trim().toLowerCase() === 'exit') {
            exit();
            return;
        }

        if (checkpointMode === 'prompt') {
            const answer = input.trim().toLowerCase();
            if (answer === 'yes') {
                setCheckpointMode('auto-resume');
                setIsLoading(true);
                if (bridgeRef.current) {
                    bridgeRef.current.stdin.write(JSON.stringify({ command: 'prompt', content: '', restart: true }) + "\n");
                }
            } else if (answer === 'no') {
                process.stdout.write('\x1B[2J\x1B[3J\x1B[H');
                applyFreshStartState({
                    setPreviousInput, setTaskProgress, taskProgressRef, setCommittedItems,
                    setBannerCommitted, setPlanContent, setIsPlanComplete, setAgents,
                    activeFileContentRef, setSystemStatus, itemIdCounterRef
                });
                setStaticKey(prev => prev + 1);
                if (bridgeRef.current) {
                    bridgeRef.current.stdin.write(JSON.stringify({ command: 'fresh_start' }) + "\n");
                }
            }
            return;
        }

        if (checkpointMode === 'completed-run-prompt') {
            const answer = input.trim().toLowerCase();
            if (answer === 'yes') {
                if (bridgeRef.current) {
                    bridgeRef.current.stdin.write(JSON.stringify({ command: 'archive_and_continue' }) + "\n");
                }
            } else if (answer === 'no') {
                process.stdout.write('\x1B[2J\x1B[3J\x1B[H');
                applyFreshStartState({
                    setPreviousInput, setTaskProgress, taskProgressRef, setCommittedItems,
                    setBannerCommitted, setPlanContent, setIsPlanComplete, setAgents,
                    activeFileContentRef, setSystemStatus, itemIdCounterRef
                });
                setStaticKey(prev => prev + 1);
                if (bridgeRef.current) {
                    bridgeRef.current.stdin.write(JSON.stringify({ command: 'fresh_start' }) + "\n");
                }
            }
            return;
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
    };
    
    // Determine if we're in non-interactive mode (direct prompt passed)
    const isInteractive = args.length === 0;
    
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
                    bridgeRef.current.kill('SIGKILL');
                    bridgeRef.current = null;
                }
                
                applyInterruptResetState({
                    setIsLoading, setStatus, setShowMainUI, setIsSystemReady,
                    setCheckpointMode, setSystemStatus, setAgents, setPlanContent,
                    setIsPlanComplete, setTaskProgress, isInterruptedRef
                });
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

    const staticItems = useMemo(() => 
        committedItems.map(item => ({ ...item, _resizeKey: `${item.id}-r${resizeCounter}` })),
        [committedItems, resizeCounter]
    );

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
                <RagStatus ragStatus={ragStatus} leftMargin={leftMargin} />
            )}

            {/* Dynamic content when main UI is shown */}
            {showMainUI && (
                <>
                    {/* Active agent statuses */}
                    {activeAgents.filter(a => a.name !== 'evaluator' && !(a.name === 'operator' && evaluatorAgent?.status === 'active')).map(agent => (
                        <ActiveAgentStatus key={`active-${agent.name}`} agent={agent} leftMargin={leftMargin} />
                    ))}

                    {/* Active evaluator */}
                    {evaluatorAgent?.status === 'active' && (
                        <ActiveAgentStatus agent={evaluatorAgent} leftMargin={leftMargin} isEvaluator />
                    )}

                    {/* Input Area */}
                    {isSystemReady && checkpointMode !== 'error' && checkpointMode !== 'checking' && (
                        <Box marginTop={0}>
                            <PromptInput 
                                onSubmit={handleSubmit} 
                                isLoading={isLoading} 
                                taskProgress={taskProgress}
                                checkpointPrompt={checkpointMode === 'prompt'}
                                completedRunPrompt={checkpointMode === 'completed-run-prompt'}
                                previousInput={previousInput}
                                showInterruptWarning={showInterruptWarning}
                                showExitWarning={showExitWarning}
                            />
                        </Box>
                    )}
                </>
            )}
        </Box>
    );
};

export default Run;
