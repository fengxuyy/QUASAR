/**
 * Types for Run state management
 */

export interface AgentInfo {
    name: string;
    status: 'active' | 'complete';
    statusText: string;
    history?: {
        type: 'tool' | 'log';
        content: string;
    }[];
    isStreaming?: boolean;
}

export interface CommittedItem {
    id: string;
    type: 'banner' | 'agent-header' | 'tool' | 'log' | 'plan' | 'agent-status' | 
          'evaluator-header' | 'evaluator-status' | 'evaluation-summary' | 
          'checkpoint-resume' | 'code-snippet' | 'active-task-panel' | 'final-summary' | 'model-text' | 'code-result';
    content: any;
    agentName?: string;
    isError?: boolean;  // For styling tool messages red on error
}

export interface RagStatusInfo {
    status: string;
    message: string;
    detail?: string;
    progress?: { current: number; total: number };
}

export interface TaskProgress {
    current: number;
    total: number;
}

export interface FileContent {
    name: string;
    content: string;
}

export type CheckpointMode = 'checking' | 'prompt' | 'normal' | 'error' | 'auto-resume' | 'completed-run-prompt';
export type SystemStatus = 'idle' | 'running' | 'completed';
