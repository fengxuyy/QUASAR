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
          'checkpoint-resume' | 'active-task-panel' | 'final-summary' | 'model-text' | 'code-result' |
          'interrupt-reason';
    content: any;
    agentName?: string;
    isError?: boolean;  // For styling tool messages red on error
    taskNum?: number;
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

export interface ContextUsage {
    agent: string;
    model: string;
    threshold_level: 'low' | 'medium' | 'high';
    threshold_ratio: number;
    threshold_percent: number;
    max_context_tokens: number | null;
    threshold_tokens: number | null;
    input_tokens: number;
    usage_percent: number | null;
    max_context_percent: number | null;
    remaining_tokens: number | null;
    is_supported_model: boolean;
    is_over_limit: boolean;
}

export interface FileContent {
    name: string;
    content: string;
}

export type CheckpointMode = 'checking' | 'prompt' | 'normal' | 'error' | 'auto-resume' | 'completed-run-prompt' | 'confirm-delete-archive' | 'confirm-start-prompt' | 'plan-awaiting-confirm';
export type SystemStatus = 'idle' | 'running' | 'completed';
