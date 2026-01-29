/**
 * Message Handlers for Bridge Communication
 * Extracted from Run.tsx for maintainability
 */
import type { CommittedItem, FileContent, TaskProgress, RagStatusInfo, CheckpointMode } from '../hooks/types.js';

// ========== TYPES ==========
export interface MessageHandlerContext {
    // State setters
    setModelName: (name: string) => void;
    setStatus: (status: string | null) => void;
    setIsLoading: (loading: boolean) => void;
    setMessages: React.Dispatch<React.SetStateAction<{ role: string; content: string }[]>>;
    setRagStatus: (status: RagStatusInfo | null) => void;
    setIsSystemReady: (ready: boolean) => void;
    setSystemStatus: (status: 'idle' | 'running' | 'completed') => void;
    setAgents: React.Dispatch<React.SetStateAction<AgentInfo[]>>;
    setPlanContent: (content: string) => void;
    setIsPlanComplete: (complete: boolean) => void;
    setTaskProgress: (progress: TaskProgress | null) => void;
    setCommittedItems: React.Dispatch<React.SetStateAction<CommittedItem[]>>;
    setCheckpointMode: (mode: CheckpointMode) => void;
    setPreviousInput: (input: string) => void;
    setShowMainUI: (show: boolean) => void;
    setParsedPlan: (plan: string[]) => void;
    
    // Refs
    ragStatusRef: React.MutableRefObject<RagStatusInfo | null>;
    bridgeRef: React.MutableRefObject<any>;
    taskProgressRef: React.MutableRefObject<TaskProgress | null>;
    activeFileContentRef: React.MutableRefObject<FileContent | null>;
    lastCodeResultIsErrorRef: React.MutableRefObject<boolean>;
    isInterruptedRef: React.MutableRefObject<boolean>;
    
    // Helpers
    ensureHeader: (items: CommittedItem[], agentName: string, taskNum?: number) => CommittedItem[];
    genUniqueId: (prefix: string) => string;
    handleCheckpointInfo: (payload: any) => void;
    exitIfDirectArgs: () => void;  // Exit app if direct args were used
}

export interface AgentInfo {
    name: string;
    status: 'active' | 'complete';
    statusText: string;
    isStreaming?: boolean;
}

// ========== INDIVIDUAL HANDLERS ==========

/** Handle bridge ready event */
export function handleReadyMessage(ctx: MessageHandlerContext): void {
    if (ctx.ragStatusRef.current?.status === 'done') {
        setTimeout(() => {
            if (ctx.bridgeRef.current) {
                ctx.bridgeRef.current.stdin.write(JSON.stringify({ command: 'check_checkpoint' }) + "\n");
            }
        }, 500);
    }
}

/** Handle model initialization */
export function handleInitMessage(ctx: MessageHandlerContext, payload: any): void {
    if (payload?.model) ctx.setModelName(payload.model);
}

/** Handle status updates */
export function handleStatusMessage(ctx: MessageHandlerContext, payload: any): void {
    ctx.setStatus(payload.text);
    ctx.setIsLoading(payload.loading);
}

/** Handle log messages */
export function handleLogMessage(ctx: MessageHandlerContext, payload: any): void {
    ctx.setMessages(prev => {
        const lastMsg = prev[prev.length - 1];
        if (lastMsg?.role === 'assistant') {
            return [...prev.slice(0, -1), { ...lastMsg, content: lastMsg.content + payload.text + "\n" }];
        }
        return [...prev, { role: 'assistant', content: payload.text + "\n" }];
    });
}

/** Handle done event */
export function handleDoneMessage(ctx: MessageHandlerContext): void {
    ctx.setIsLoading(false);
    ctx.setStatus(null);
    // Re-check for checkpoints after run completes
    if (ctx.bridgeRef.current) {
        ctx.bridgeRef.current.stdin.write(JSON.stringify({ command: 'check_checkpoint' }) + "\n");
    }
    // Exit if direct args were used
    ctx.exitIfDirectArgs();
}

/** Handle error messages */
export function handleErrorMessage(ctx: MessageHandlerContext, payload: any): void {
    const errorMsg = payload.traceback 
        ? `Error: ${payload.message}\n\n${payload.traceback}`
        : `Error: ${payload.message}`;
    ctx.setMessages(prev => [...prev, { role: 'system', content: errorMsg }]);
    console.error(`\n[Python Error]\n${payload.traceback || payload.message}\n`);
    ctx.setIsLoading(false);
    // Exit if direct args were used
    ctx.exitIfDirectArgs();
}

/** Handle RAG status updates */
export function handleRagStatusMessage(ctx: MessageHandlerContext, payload: any): void {
    ctx.setRagStatus(payload);
    ctx.ragStatusRef.current = payload;
}

/** Handle system ready event */
export function handleSystemReadyMessage(ctx: MessageHandlerContext): void {
    ctx.setIsSystemReady(true);
}

/** Handle system status changes */
export function handleSystemStatusMessage(ctx: MessageHandlerContext, payload: any): void {
    if (payload.status === 'running') {
        ctx.setSystemStatus('running');
        ctx.setAgents([]);
        ctx.setPlanContent('');
        ctx.setIsPlanComplete(false);
        ctx.setTaskProgress(null);
    } else if (payload.status === 'completed') {
        ctx.setSystemStatus('completed');
        ctx.setAgents(prev => prev.map(a => ({ ...a, status: 'complete' as const })));
    }
}

/** Handle agent lifecycle events */
export function handleAgentEventMessage(ctx: MessageHandlerContext, payload: any): void {
    const { agent, event, status: agentStatusText, is_error: payloadIsError } = payload;
    const currentTaskNum = ctx.taskProgressRef.current?.current;
    
    if (event === 'step_complete') {
        ctx.activeFileContentRef.current = null;
        
        // Use is_error from payload if provided, otherwise check for execute_python errors
        const isExecuteCodeTool = agentStatusText?.toLowerCase().includes('executed');
        let toolIsError = payloadIsError === true;
        
        // Fallback: for execute_python, also check lastCodeResultIsErrorRef
        if (!toolIsError && isExecuteCodeTool) {
            toolIsError = ctx.lastCodeResultIsErrorRef.current;
        }
        
        if (isExecuteCodeTool) {
            ctx.lastCodeResultIsErrorRef.current = false;
        }
        
        ctx.setCommittedItems(prev => {
            const items = ctx.ensureHeader(prev, agent, currentTaskNum);
            
            const newToolItem = { 
                id: ctx.genUniqueId(`${agent}-tool`), 
                type: 'tool' as const, 
                content: agentStatusText, 
                agentName: agent,
                isError: toolIsError
            };
            
            // Special case: "Reviewed Plan" or "Created Replan" should add the plan box BEFORE the milestone
            // Order: "Created Initial Plan" -> plan box -> "Reviewed Plan"
            if (agent === 'strategist' && (agentStatusText === 'Reviewed Plan' || agentStatusText === 'Created Replan')) {
                // Check if plan box already exists (e.g., from checkpoint history)
                const hasPlan = items.some(item => 
                    item.id === 'execution-plan-complete' || 
                    item.id === 'checkpoint-history-plan' ||
                    (item.type === 'plan' && item.agentName === 'strategist')
                );
                
                if (!hasPlan && payload.output) {
                    // Create plan box from the output content
                    const planContent = payload.output;
                    const planItem = {
                        id: 'execution-plan-complete',
                        type: 'plan' as const,
                        content: { 
                            planContent: planContent, 
                            isPlanComplete: true, 
                            isContinuation: false 
                        },
                        agentName: 'strategist'
                    };
                    return [...items, planItem, newToolItem];
                }
            }
            
            return [...items, newToolItem];
        });
    } else if (event === 'log') {
        ctx.setCommittedItems(prev => {
            const items = ctx.ensureHeader(prev, agent, currentTaskNum);
            const isEvaluatorSummary = agent === 'evaluator' && 
                agentStatusText && 
                !agentStatusText.includes('Evaluation Passed') &&
                !agentStatusText.includes('Evaluation Failed') &&
                !agentStatusText.startsWith('Evaluating');
            
            const itemType = isEvaluatorSummary ? 'evaluation-summary' : 'log';
            return [...items, { id: ctx.genUniqueId(`${agent}-log`), type: itemType, content: agentStatusText, agentName: agent }];
        });
    } else if (event === 'start') {
        ctx.setCommittedItems(prev => ctx.ensureHeader(prev, agent, currentTaskNum));
    } else if (event === 'complete') {
        // Only add agent-status item if there's actual status text
        // (strategist sends empty completion event to mark state transition)
        if (agentStatusText && agentStatusText.trim()) {
            ctx.setCommittedItems(prev => {
                const items = ctx.ensureHeader(prev, agent, currentTaskNum);
                const statusType = agent === 'evaluator' ? 'evaluator-status' : 'agent-status';
                return [...items, { id: ctx.genUniqueId(`${agent}-complete`), type: statusType, content: agentStatusText, agentName: agent }];
            });
        }
    }
    
    // Update agents list
    ctx.setAgents(prev => {
        const existing = prev.find(a => a.name === agent);
        const update = (a: AgentInfo): AgentInfo => ({
            ...a,
            status: event === 'complete' ? 'complete' : (event === 'log' ? a.status : 'active'),
            statusText: ['update', 'start', 'complete'].includes(event) ? agentStatusText : a.statusText,
            isStreaming: a.isStreaming && event === 'start' ? false : false
        });
        
        if (existing) {
            return prev.map(a => a.name === agent ? update(a) : a);
        }
        return [...prev, { name: agent, status: event === 'complete' ? 'complete' : 'active', statusText: agentStatusText, isStreaming: false }];
    });
}

/** Handle plan streaming */
export function handlePlanStreamMessage(ctx: MessageHandlerContext, payload: any): void {
    const newPlanContent = payload.content;
    const isPlanDone = payload.is_complete;
    const parsedPlan = payload.parsed_plan;
    
    if (parsedPlan && parsedPlan.length > 0) {
        ctx.setParsedPlan(parsedPlan);
    }
    
    ctx.setPlanContent(newPlanContent);
    ctx.setIsPlanComplete(isPlanDone);
    
    // Note: Plan box is added from step_complete "Reviewed Plan" event, not here
    // This ensures proper ordering: "Created Initial Plan" -> plan box -> "Reviewed Plan"
}

/** Handle task progress updates */
export function handleTaskProgressMessage(ctx: MessageHandlerContext, payload: any): void {
    if (payload?.current !== undefined && payload?.total !== undefined) {
        const progress = { current: payload.current, total: payload.total };
        ctx.setTaskProgress(progress);
        ctx.taskProgressRef.current = progress;
    }
}

/** Handle file content for code snippets */
export function handleFileContentMessage(ctx: MessageHandlerContext, payload: any): void {
    if (payload?.name && payload?.content) {
        const content = { name: payload.name, content: payload.content };
        const currentTaskNum = ctx.taskProgressRef.current?.current;
        
        const lastContent = ctx.activeFileContentRef.current;
        const isDuplicate = lastContent && 
            lastContent.name === content.name && 
            lastContent.content === content.content;
        
        ctx.activeFileContentRef.current = content;
        
        if (!isDuplicate) {
            ctx.setCommittedItems(prev => {
                const items = ctx.ensureHeader(prev, 'operator', currentTaskNum);
                return [...items, {
                    id: `code-snippet-${Date.now()}`,
                    type: 'code-snippet',
                    content: { name: content.name, content: content.content, isComplete: true, isContinuation: false },
                    agentName: 'operator'
                }];
            });
        }
    }
}

/** Handle completed run detection */
export function handleCompletedRunInfoMessage(ctx: MessageHandlerContext, payload: any): void {
    ctx.setShowMainUI(true);
    if (payload?.exists) {
        ctx.setCheckpointMode('completed-run-prompt');
        ctx.setPreviousInput(payload.previous_input || '');
        
        if (payload.summary) {
            ctx.setCommittedItems(prev => {
                const summaryContent = payload.summary;
                const hasFinalSummary = prev.some(item => 
                    (item.id === 'final-summary' || item.id === 'completed-run-summary') &&
                    item.type === 'final-summary' &&
                    (item.content === summaryContent || item.content?.substring(0, 100) === summaryContent?.substring(0, 100))
                );
                if (hasFinalSummary) return prev;
                return [
                    ...prev,
                    {
                        id: 'completed-run-summary',
                        type: 'final-summary',
                        content: summaryContent,
                        agentName: 'system'
                    }
                ];
            });
        }
    }
}

/** Handle archive complete */
export function handleArchiveCompleteMessage(ctx: MessageHandlerContext, payload: any): void {
    if (payload?.success) {
        ctx.setCheckpointMode('normal');
    }
}

/** Handle fresh start complete */
export function handleFreshStartCompleteMessage(ctx: MessageHandlerContext, payload: any): void {
    // Fresh start complete - workspace AND archives are cleaned
    // Don't re-check for checkpoints - user wants a completely fresh start
    // The checkpointMode should already be set to 'normal' in Run.tsx
}

/** Handle clear checkpoint complete (keeps archives) */
export function handleClearCheckpointCompleteMessage(ctx: MessageHandlerContext, payload: any): void {
    // Checkpoint cleared, no archives exist
    // Set to normal mode so user can start a new request
    ctx.setCheckpointMode('normal');
}

/** Handle final summary */
export function handleFinalSummaryMessage(ctx: MessageHandlerContext, payload: any): void {
    if (payload?.content) {
        ctx.setCommittedItems(prev => {
            const summaryContent = payload.content;
            const hasFinalSummary = prev.some(item => 
                (item.id === 'final-summary' || item.id === 'completed-run-summary') &&
                item.type === 'final-summary' &&
                (item.content === summaryContent || item.content?.substring(0, 100) === summaryContent?.substring(0, 100))
            );
            if (hasFinalSummary) return prev;
            return [
                ...prev,
                {
                    id: 'final-summary',
                    type: 'final-summary',
                    content: summaryContent,
                    agentName: 'system'
                }
            ];
        });
    }
}

/** Handle code execution results */
export function handleCodeResultMessage(ctx: MessageHandlerContext, payload: any): void {
    if (payload?.output) {
        const isError = payload.success === false;
        const currentTaskNum = ctx.taskProgressRef.current?.current;
        ctx.lastCodeResultIsErrorRef.current = isError;
        ctx.setCommittedItems(prev => {
            const items = ctx.ensureHeader(prev, 'operator', currentTaskNum);
            return [...items, {
                id: ctx.genUniqueId('code-result'),
                type: 'code-result',
                content: {
                    output: payload.output,
                    filePath: payload.file_path || ''
                },
                agentName: 'operator',
                isError: isError
            }];
        });
    }
}

// ========== MAIN DISPATCHER ==========

/**
 * Main message handler that dispatches to individual handlers
 */
export function createMessageHandler(ctx: MessageHandlerContext) {
    return function handleBridgeMessage(msg: any): void {
        if (ctx.isInterruptedRef.current && msg.type !== 'checkpoint_info' && msg.type !== 'system_ready') {
            return;
        }

        switch (msg.type) {
            case 'ready':
                handleReadyMessage(ctx);
                break;
            case 'init':
                handleInitMessage(ctx, msg.payload);
                break;
            case 'status':
                handleStatusMessage(ctx, msg.payload);
                break;
            case 'log':
                handleLogMessage(ctx, msg.payload);
                break;
            case 'done':
                handleDoneMessage(ctx);
                break;
            case 'error':
                handleErrorMessage(ctx, msg.payload);
                break;
            case 'rag_status':
                handleRagStatusMessage(ctx, msg.payload);
                break;
            case 'system_ready':
                handleSystemReadyMessage(ctx);
                break;
            case 'system_status':
                handleSystemStatusMessage(ctx, msg.payload);
                break;
            case 'agent_event':
                handleAgentEventMessage(ctx, msg.payload);
                break;
            case 'plan_stream':
                handlePlanStreamMessage(ctx, msg.payload);
                break;
            case 'task_progress':
                handleTaskProgressMessage(ctx, msg.payload);
                break;
            case 'file_content':
                handleFileContentMessage(ctx, msg.payload);
                break;
            case 'checkpoint_info':
                ctx.setShowMainUI(true);
                ctx.setIsSystemReady(true);
                ctx.handleCheckpointInfo(msg.payload);
                break;
            case 'completed_run_info':
                handleCompletedRunInfoMessage(ctx, msg.payload);
                break;
            case 'archive_complete':
                handleArchiveCompleteMessage(ctx, msg.payload);
                break;
            case 'fresh_start_complete':
                handleFreshStartCompleteMessage(ctx, msg.payload);
                break;
            case 'clear_checkpoint_complete':
                handleClearCheckpointCompleteMessage(ctx, msg.payload);
                break;
            case 'final_summary':
                handleFinalSummaryMessage(ctx, msg.payload);
                break;
            case 'code_result':
                handleCodeResultMessage(ctx, msg.payload);
                break;
        }
    };
}
