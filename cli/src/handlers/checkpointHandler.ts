/**
 * Checkpoint Handler - Logic for handling checkpoint restoration
 * Extracted from Run.tsx for maintainability
 */
import type { CommittedItem, TaskProgress, CheckpointMode } from '../hooks/types.js';
import { cleanTaskDescription } from '../utils/stateHelpers.js';
import { normalizePlanText } from '../utils/planParsing.js';

export interface CheckpointHandlerContext {
    setParsedPlan: (plan: string[]) => void;
    setCommittedItems: React.Dispatch<React.SetStateAction<CommittedItem[]>>;
    setTaskProgress: (progress: TaskProgress | null) => void;
    taskProgressRef: React.MutableRefObject<TaskProgress | null>;
    setCheckpointMode: (mode: CheckpointMode) => void;
    setPreviousInput: (input: string) => void;
    setIsLoading: (loading: boolean) => void;
    bridgeRef: React.MutableRefObject<any>;
    /** Set to true when the evaluator was actively running at checkpoint time, so
     *  handleSystemStatusMessage can pre-populate the agents list instead of leaving
     *  the dynamic section blank during the evaluator's LLM inference gap. */
    resumingWithEvaluatorRef: React.MutableRefObject<boolean>;
}

/**
 * Build committed items from checkpoint history
 */
export function buildHistoryItems(history: any): CommittedItem[] {
    const newItems: CommittedItem[] = [];
    
    const addPlanItem = (id: string, planText: string) => {
        newItems.push({
            id,
            type: 'plan',
            content: {
                planContent: planText,
                isPlanComplete: true,
                isContinuation: false,
                committedPlanLines: planText.split('\n').length
            },
            agentName: 'strategist'
        });
    };

    // Build plan items
    const finalPlanRaw = (history.plan?.length > 0)
        ? history.plan.join('\n\n')
        : (history.full_plan_text || '');
    const initialPlanRaw = history.initial_plan_text || '';
    const finalPlanContent = normalizePlanText(finalPlanRaw);
    const initialPlanContent = normalizePlanText(initialPlanRaw);
    
    if (finalPlanContent || initialPlanContent) {
        newItems.push({ id: 'strategist-header', type: 'agent-header', content: 'strategist', agentName: 'strategist' });
        
        if (history.is_replan) {
            if (initialPlanContent) {
                newItems.push({ id: 'strategist-initial-complete', type: 'tool', content: 'Created Initial Replan', agentName: 'strategist' });
            }

            // Show only the reviewed plan. If final equals initial, use whichever is available.
            if (finalPlanContent) {
                addPlanItem('checkpoint-history-plan', finalPlanContent);
            } else if (initialPlanContent) {
                addPlanItem('checkpoint-history-plan', initialPlanContent);
            }

            newItems.push({ id: 'strategist-complete', type: 'tool', content: 'Reviewed Replan', agentName: 'strategist' });
        } else {
            if (initialPlanContent) {
                newItems.push({ id: 'strategist-initial-complete', type: 'tool', content: 'Created Initial Plan', agentName: 'strategist' });
            }

            // Show only the reviewed plan. If final equals initial, use whichever is available.
            if (finalPlanContent) {
                addPlanItem('checkpoint-history-plan', finalPlanContent);
            } else if (initialPlanContent) {
                addPlanItem('checkpoint-history-plan', initialPlanContent);
            }

            newItems.push({ id: 'strategist-complete', type: 'tool', content: 'Reviewed Plan', agentName: 'strategist' });
        }
    }
    
    const completedCount = history.completed_steps?.length || 0;
    
    // Build completed task items
    for (let i = 0; i < completedCount; i++) {
        const taskNum = i + 1;
        newItems.push({ id: `operator-header-task${taskNum}-history`, type: 'agent-header', content: 'operator', agentName: 'operator' });
        
        // For completed tasks, keep only a compact header panel in restore view.
        // Full step-by-step details are available via `quasar history`.
        if (history.plan && history.plan.length >= taskNum) {
            const rawTask = history.plan[i];
            if (rawTask) {
                const cleanDescription = cleanTaskDescription(rawTask);
                newItems.push({
                    id: `operator-task-panel-${taskNum}-history`,
                    type: 'active-task-panel', 
                    content: { description: cleanDescription, taskNum },
                    agentName: 'operator'
                });
            }
        }
        
        const summary = history.step_results?.[String(i)];
        if (summary) {
            newItems.push({ id: `evaluation-summary-task${taskNum}-history`, type: 'evaluation-summary', content: summary, agentName: 'evaluator' });
        }
    }
    
    // Build remaining (in-progress) task items
    const currentTaskNum = completedCount + 1;
    const remainingOpItems = history.operator_items_by_task?.[String(completedCount)] || [];
    
    if (remainingOpItems.length > 0) {
        newItems.push({ id: `operator-header-task${currentTaskNum}-history`, type: 'agent-header', content: 'operator', agentName: 'operator' });
        
        if (history.plan && history.plan.length >= currentTaskNum) {
            const rawTask = history.plan[currentTaskNum - 1];
            if (rawTask) {
                const cleanDescription = cleanTaskDescription(rawTask);
                newItems.push({
                    id: `operator-task-panel-${currentTaskNum}-history`,
                    type: 'active-task-panel', 
                    content: { description: cleanDescription, taskNum: currentTaskNum },
                    agentName: 'operator'
                });
            }
        }

        for (let j = 0; j < remainingOpItems.length; j++) {
            const item = remainingOpItems[j];
            newItems.push({ 
                id: `operator-item-task${currentTaskNum}-${j}-history`, 
                type: item.type as any, 
                content: item.content, 
                agentName: 'operator',
                isError: item.isError
            });
        }
        
        // Also show evaluator items for in-progress task (e.g., failed evaluation feedback)
        const remainingEvalItems = history.evaluator_items_by_task?.[String(completedCount)] || [];
        if (remainingEvalItems.length > 0) {
            newItems.push({ id: `evaluator-header-task${currentTaskNum}-history`, type: 'evaluator-header', content: 'evaluator', agentName: 'evaluator' });
            
            for (let j = 0; j < remainingEvalItems.length; j++) {
                const item = remainingEvalItems[j];
                newItems.push({ 
                    id: `evaluator-item-task${currentTaskNum}-${j}-history`, 
                    type: item.type as any, 
                    content: item.content, 
                    agentName: 'evaluator',
                    isError: item.isError
                });
            }
        }
    }
    
    return newItems;
}

/**
 * Check if strategist content already exists in committed items
 */
export function hasStrategistContent(items: CommittedItem[]): boolean {
    return items.some(item => 
        item.id === 'strategist-header' || 
        item.id === 'execution-plan-complete' ||
        item.id === 'checkpoint-history-plan' ||
        (item.type === 'agent-header' && item.agentName === 'strategist') ||
        (item.type === 'plan' && item.agentName === 'strategist')
    );
}

/**
 * Handle checkpoint info message and determine mode
 */
export function handleCheckpointInfo(ctx: CheckpointHandlerContext, payload: any): void {
    const restartFromEnv = ['true', '1', 'yes', 'on'].includes((process.env.IF_RESTART || '').toLowerCase());
    
    if (payload?.history) {
        const history = payload.history;
        if (history.plan && history.plan.length > 0) {
            ctx.setParsedPlan(history.plan);
        }
        
        ctx.setCommittedItems(prev => {
            if (hasStrategistContent(prev)) return prev;
            const newItems = buildHistoryItems(history);
            return [...prev, ...newItems];
        });

        // If the evaluator had already made tool calls at checkpoint time it was
        // actively running.  Flag this so handleSystemStatusMessage can restore
        // the evaluator spinner immediately after clearing agents on resume,
        // bridging the gap during the evaluator's silent LLM-inference phase.
        const completedCount = history.completed_steps?.length || 0;
        const remainingEvalItems = history.evaluator_items_by_task?.[String(completedCount)] || [];
        if (remainingEvalItems.length > 0) {
            ctx.resumingWithEvaluatorRef.current = true;
        }
        
        if (history.current_task && history.total_tasks) {
            const progress = { current: history.current_task, total: history.total_tasks };
            ctx.setTaskProgress(progress);
            ctx.taskProgressRef.current = progress;
        }
    }
    
    if (restartFromEnv) {
        if (payload?.exists) {
            ctx.setCheckpointMode('auto-resume');
            ctx.setPreviousInput(payload.previous_input || '');
            ctx.setIsLoading(true);
            setTimeout(() => {
                if (ctx.bridgeRef.current) {
                // IMPORTANT: restart: false to preserve checkpoint and resume from it
                    // restart: true would delete the checkpoint!
                    ctx.bridgeRef.current.stdin.write(JSON.stringify({ command: 'prompt', content: '', restart: false }) + "\n");
                }
            }, 100);
        } else {
            ctx.setCheckpointMode('error');
        }
    } else {
        if (payload?.exists) {
            ctx.setCheckpointMode('prompt');
            ctx.setPreviousInput(payload.previous_input || '');
        } else {
            ctx.setCheckpointMode('normal');
        }
    }
}
