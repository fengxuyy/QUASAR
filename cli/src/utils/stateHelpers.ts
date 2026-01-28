/**
 * State Helper Utilities
 * Extracted from Run.tsx for maintainability
 */
import type { CommittedItem, TaskProgress, FileContent } from '../hooks/types.js';

/**
 * Clean task description - removes markdown artifacts and Task N: prefix
 */
export function cleanTaskDescription(rawTask: string): string {
    // Take first line
    let text = rawTask.split('\n')[0].trim();
    
    // Strip ALL bold markers first (both ** and single *)
    text = text.replace(/\*\*/g, '').replace(/^\*|\*$/g, '');
    
    // Strip the Task N: prefix
    const taskRegex = /^(?:#+\s*)?Task\s+\d+[:：]\s*/i;
    text = text.replace(taskRegex, '').trim();
    
    // Clean up any remaining markdown artifacts
    text = text.replace(/^#+\s*/, '').trim();

    return text;
}

/**
 * State values for a fresh start / state reset
 */
export interface FreshStartState {
    previousInput: string;
    taskProgress: TaskProgress | null;
    committedItems: CommittedItem[];
    bannerCommitted: boolean;
    planContent: string;
    isPlanComplete: boolean;
    agents: any[];
    activeFileContent: FileContent | null;
    systemStatus: 'idle' | 'running' | 'completed';
    itemIdCounter: number;
}

/**
 * Get initial fresh start state values
 */
export function getFreshStartState(): FreshStartState {
    return {
        previousInput: '',
        taskProgress: null,
        committedItems: [],
        bannerCommitted: false,
        planContent: '',
        isPlanComplete: false,
        agents: [],
        activeFileContent: null,
        systemStatus: 'idle',
        itemIdCounter: 0
    };
}

/**
 * Apply fresh start state to setters
 */
export function applyFreshStartState(
    setters: {
        setPreviousInput: (input: string) => void;
        setTaskProgress: (progress: TaskProgress | null) => void;
        taskProgressRef: React.MutableRefObject<TaskProgress | null>;
        setCommittedItems: React.Dispatch<React.SetStateAction<CommittedItem[]>>;
        setBannerCommitted: (committed: boolean) => void;
        setPlanContent: (content: string) => void;
        setIsPlanComplete: (complete: boolean) => void;
        setAgents: React.Dispatch<React.SetStateAction<any[]>>;
        activeFileContentRef: React.MutableRefObject<FileContent | null>;
        setSystemStatus: (status: 'idle' | 'running' | 'completed') => void;
        itemIdCounterRef: React.MutableRefObject<number>;
    }
): void {
    const state = getFreshStartState();
    setters.setPreviousInput(state.previousInput);
    setters.setTaskProgress(state.taskProgress);
    setters.taskProgressRef.current = state.taskProgress;
    setters.setCommittedItems(state.committedItems);
    setters.setBannerCommitted(state.bannerCommitted);
    setters.setPlanContent(state.planContent);
    setters.setIsPlanComplete(state.isPlanComplete);
    setters.setAgents(state.agents);
    setters.activeFileContentRef.current = state.activeFileContent;
    setters.setSystemStatus(state.systemStatus);
    setters.itemIdCounterRef.current = state.itemIdCounter;
}

/**
 * State values for interrupt reset (partial reset)
 */
export function applyInterruptResetState(
    setters: {
        setIsLoading: (loading: boolean) => void;
        setStatus: (status: string | null) => void;
        setShowMainUI: (show: boolean) => void;
        setIsSystemReady: (ready: boolean) => void;
        setCheckpointMode: (mode: any) => void;
        setSystemStatus: (status: 'idle' | 'running' | 'completed') => void;
        setAgents: React.Dispatch<React.SetStateAction<any[]>>;
        setPlanContent: (content: string) => void;
        setIsPlanComplete: (complete: boolean) => void;
        setTaskProgress: (progress: TaskProgress | null) => void;
        isInterruptedRef: React.MutableRefObject<boolean>;
    }
): void {
    setters.setIsLoading(false);
    setters.setStatus(null);
    setters.setShowMainUI(false);
    setters.setIsSystemReady(false);
    setters.setCheckpointMode('checking');
    setters.setSystemStatus('idle');
    setters.setAgents([]);
    setters.setPlanContent('');
    setters.setIsPlanComplete(false);
    setters.setTaskProgress(null);
    setters.isInterruptedRef.current = false;
}
