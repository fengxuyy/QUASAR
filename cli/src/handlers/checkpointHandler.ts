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

function normalizeHistoryAgentName(agentName: unknown, fallback: 'operator' | 'evaluator' | 'strategist'): 'operator' | 'evaluator' | 'strategist' {
    if (agentName === 'operator' || agentName === 'evaluator' || agentName === 'strategist') {
        return agentName;
    }
    return fallback;
}

interface BuildHistoryTimelineOptions {
    idPrefix: string;
    defaultAgentName?: 'operator' | 'evaluator' | 'strategist';
    taskNum?: number;
    includeEvaluatorHeader?: boolean;
}

/**
 * Convert checkpoint-history timeline entries into the same committed item types
 * the runtime renderer already understands.
 */
export function buildCommittedTimelineItems(historyItems: any[], options: BuildHistoryTimelineOptions): CommittedItem[] {
    const committedItems: CommittedItem[] = [];
    const defaultAgentName = options.defaultAgentName ?? 'operator';
    let evaluatorHeaderShown = false;
    let pendingCodeResult: CommittedItem | null = null;

    const ensureEvaluatorHeader = (idx: number) => {
        if (options.includeEvaluatorHeader === false || evaluatorHeaderShown) return;
        evaluatorHeaderShown = true;
        committedItems.push({
            id: `${options.idPrefix}-evaluator-header-${idx}`,
            type: 'evaluator-header',
            content: 'evaluator',
            agentName: 'evaluator',
            taskNum: options.taskNum
        });
    };

    const flushPendingCodeResult = () => {
        if (!pendingCodeResult) return;
        committedItems.push(pendingCodeResult);
        pendingCodeResult = null;
    };

    const isInterruptReasonTool = (item: any): boolean => (
        item?.type === 'tool' &&
        typeof item?.content === 'string' &&
        item.content.trim().toLowerCase() === 'interrupted execution' &&
        typeof item?.output === 'string' &&
        item.output.trim().length > 0
    );

    for (let idx = 0; idx < historyItems.length; idx++) {
        const item = historyItems[idx];
        const itemType = item?.type;
        const agentName = normalizeHistoryAgentName(item?.agent, defaultAgentName);
        const isError = item?.isError === true;

        if (itemType === 'evaluation-failed') {
            flushPendingCodeResult();
            ensureEvaluatorHeader(idx);
            committedItems.push({
                id: `${options.idPrefix}-evaluator-status-${idx}`,
                type: 'evaluator-status',
                content: item?.content ?? 'Evaluation Failed',
                agentName: 'evaluator',
                taskNum: options.taskNum
            });

            if (item?.summary) {
                committedItems.push({
                    id: `${options.idPrefix}-evaluation-summary-${idx}`,
                    type: 'evaluation-summary',
                    content: item.summary,
                    agentName: 'evaluator',
                    taskNum: options.taskNum
                });
            }
            continue;
        }

        if (agentName === 'evaluator') {
            ensureEvaluatorHeader(idx);
        }

        if (itemType === 'tool' || itemType === 'log' || itemType === 'model-text') {
            if (itemType !== 'tool') {
                flushPendingCodeResult();
            }
            committedItems.push({
                id: `${options.idPrefix}-${itemType}-${idx}`,
                type: itemType,
                content: item?.content ?? '',
                agentName,
                isError,
                taskNum: options.taskNum
            });

            if (itemType === 'tool' && pendingCodeResult && pendingCodeResult.agentName === agentName) {
                committedItems.push(pendingCodeResult);
                pendingCodeResult = null;
            }
            if (itemType === 'tool' && isInterruptReasonTool(item)) {
                committedItems.push({
                    id: `${options.idPrefix}-interrupt-reason-${idx}`,
                    type: 'interrupt-reason',
                    content: item.output,
                    agentName,
                    isError: true,
                    taskNum: options.taskNum
                });
            }
            continue;
        }

        if (itemType === 'code-result') {
            pendingCodeResult = {
                id: `${options.idPrefix}-code-result-${idx}`,
                type: 'code-result',
                content: item?.content,
                agentName,
                isError,
                taskNum: options.taskNum
            };
            continue;
        }

        flushPendingCodeResult();
    }

    flushPendingCodeResult();
    return committedItems;
}

/**
 * Build committed items from checkpoint history
 */
export function buildHistoryItems(history: any): CommittedItem[] {
    const newItems: CommittedItem[] = [];
    const reviewedPlanLabel = history.is_replan ? 'Reviewed Replan' : 'Reviewed Plan';
    const revisedPlanLabel = history.is_replan
        ? 'Revised Replan from user feedback'
        : 'Revised Plan from user feedback';
    
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

    const addFinalPlanSequence = (
        finalLabel: 'Reviewed Plan' | 'Reviewed Replan' | 'Revised Plan from user feedback' | 'Revised Replan from user feedback',
        planText: string
    ) => {
        const isUserRevisedPlan =
            finalLabel === revisedPlanLabel ||
            history.final_plan_update_status === 'Revising plan from user feedback';

        if (isUserRevisedPlan) {
            newItems.push({
                id: 'strategist-reviewed-complete',
                type: 'tool',
                content: reviewedPlanLabel,
                agentName: 'strategist'
            });
        }

        newItems.push({
            id: 'strategist-complete',
            type: 'tool',
            content: finalLabel,
            agentName: 'strategist'
        });

        addPlanItem('checkpoint-history-plan', planText);
    };

    // Build plan items
    const finalPlanRaw = (history.plan?.length > 0)
        ? history.plan.join('\n\n')
        : (history.full_plan_text || '');
    const initialPlanRaw = history.initial_plan_text || '';
    const finalPlanContent = normalizePlanText(finalPlanRaw);
    const initialPlanContent = normalizePlanText(initialPlanRaw);
    const userRevisedSnapshots: string[] = history.user_revised_plan_texts || [];
    const isUserRevisedPlan =
        history.final_plan_status === revisedPlanLabel ||
        history.final_plan_update_status === 'Revising plan from user feedback';

    const appendStrategistPlanMilestones = () => {
        if (userRevisedSnapshots.length > 0) {
            if (isUserRevisedPlan) {
                newItems.push({
                    id: 'strategist-reviewed-complete',
                    type: 'tool',
                    content: reviewedPlanLabel,
                    agentName: 'strategist'
                });
            }
            userRevisedSnapshots.forEach((raw, idx) => {
                const isLast = idx === userRevisedSnapshots.length - 1;
                const planText =
                    isLast && finalPlanContent ? finalPlanContent : normalizePlanText(raw);
                newItems.push({
                    id: `strategist-revised-history-${idx}`,
                    type: 'tool',
                    content: revisedPlanLabel,
                    agentName: 'strategist'
                });
                addPlanItem(`checkpoint-history-plan-revised-${idx}`, planText);
            });
            return;
        }
        if (finalPlanContent) {
            addFinalPlanSequence(
                history.final_plan_status || reviewedPlanLabel,
                finalPlanContent
            );
        } else if (initialPlanContent) {
            addFinalPlanSequence(
                history.final_plan_status || reviewedPlanLabel,
                initialPlanContent
            );
        }
    };
    
    const strategistItems = buildCommittedTimelineItems(history.strategist_items || [], {
        idPrefix: 'strategist-history',
        defaultAgentName: 'strategist',
        includeEvaluatorHeader: false
    });

    if (strategistItems.length > 0 || finalPlanContent || initialPlanContent) {
        newItems.push({ id: 'strategist-header', type: 'agent-header', content: 'strategist', agentName: 'strategist' });
        newItems.push(...strategistItems);
        
        if (history.is_replan) {
            if (initialPlanContent) {
                newItems.push({ id: 'strategist-initial-complete', type: 'tool', content: 'Created Initial Replan', agentName: 'strategist' });
            }

            appendStrategistPlanMilestones();
        } else {
            if (initialPlanContent) {
                newItems.push({ id: 'strategist-initial-complete', type: 'tool', content: 'Created Initial Plan', agentName: 'strategist' });
            }

            appendStrategistPlanMilestones();
        }
    }
    
    const completedCount = history.completed_steps?.length || 0;
    
    // Build completed task items
    for (let i = 0; i < completedCount; i++) {
        const taskNum = i + 1;
        newItems.push({ id: `operator-header-task${taskNum}-history`, type: 'agent-header', content: 'operator', agentName: 'operator', taskNum });
        
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
                    agentName: 'operator',
                    taskNum
                });
            }
        }
        
        const summary = history.step_results?.[String(i)];
        if (summary) {
            newItems.push({ id: `evaluation-summary-task${taskNum}-history`, type: 'evaluation-summary', content: summary, agentName: 'evaluator', taskNum });
        }
    }
    
    // Build remaining (in-progress) task items
    const currentTaskNum = completedCount + 1;
    const orderedTaskItems = history.ordered_items_by_task?.[String(completedCount)] || [];
    const remainingOpItems = history.operator_items_by_task?.[String(completedCount)] || [];
    const remainingEvalItems = history.evaluator_items_by_task?.[String(completedCount)] || [];
    const remainingTaskItems = orderedTaskItems.length > 0
        ? orderedTaskItems
        : [...remainingOpItems, ...remainingEvalItems];
    
    if (remainingTaskItems.length > 0) {
        newItems.push({ id: `operator-header-task${currentTaskNum}-history`, type: 'agent-header', content: 'operator', agentName: 'operator', taskNum: currentTaskNum });
        
        if (history.plan && history.plan.length >= currentTaskNum) {
            const rawTask = history.plan[currentTaskNum - 1];
            if (rawTask) {
                const cleanDescription = cleanTaskDescription(rawTask);
                newItems.push({
                    id: `operator-task-panel-${currentTaskNum}-history`,
                    type: 'active-task-panel', 
                    content: { description: cleanDescription, taskNum: currentTaskNum },
                    agentName: 'operator',
                    taskNum: currentTaskNum
                });
            }
        }

        newItems.push(
            ...buildCommittedTimelineItems(remainingTaskItems, {
                idPrefix: `task${currentTaskNum}-history`,
                defaultAgentName: 'operator',
                taskNum: currentTaskNum
            })
        );
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
