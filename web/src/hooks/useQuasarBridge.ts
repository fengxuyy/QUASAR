import { useEffect, useRef, useState, useCallback } from 'react';
import {
  getStoredSettings,
  mergeSettingsPreservingMaskedValues,
  setStoredSettings,
} from '../utils/settingsStorage';
import { mergeTextStreamChunks } from '../utils/messageHelpers';
import { withAuthWebSocketUrl } from '../utils/apiAuth';

interface BridgeMessage {
  type?: string;
  payload?: any;
  [key: string]: any;
}

type PlanConfirmationResponse = {
  action: 'confirm' | 'decline' | 'revise';
  feedback?: string;
};

const MESSAGE_BATCH_DELAY_MS = 33;
const MAX_BATCHED_MESSAGES = 40;

export interface ContextUsage {
  agent: string;
  model: string;
  threshold_level: 'low' | 'medium' | 'hard';
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

const getPayloadAgent = (message: BridgeMessage): string => {
  const agent = message.payload?.agent;
  return typeof agent === 'string' ? agent.toLowerCase() : 'unknown';
};

const canCoalesceMessage = (previous: BridgeMessage, incoming: BridgeMessage): boolean => {
  if (previous.type !== incoming.type) return false;

  if (incoming.type === 'text_stream' || incoming.type === 'thought_stream') {
    return getPayloadAgent(previous) === getPayloadAgent(incoming);
  }

  if (incoming.type === 'plan_stream') {
    return previous.payload?._isReplanning === incoming.payload?._isReplanning;
  }

  return false;
};

const coalescePayload = (previous: BridgeMessage, incoming: BridgeMessage): BridgeMessage => {
  const previousContent = String(previous.payload?.content || '');
  const incomingContent = String(incoming.payload?.content || '');

  return {
    ...previous,
    ...incoming,
    payload: {
      ...(previous.payload || {}),
      ...(incoming.payload || {}),
      content: mergeTextStreamChunks(previousContent, incomingContent),
    },
  };
};

const appendCompactedMessages = (messages: BridgeMessage[], incomingBatch: BridgeMessage[]): BridgeMessage[] => {
  if (incomingBatch.length === 0) return messages;

  const next = [...messages];
  for (const incoming of incomingBatch) {
    const previous = next[next.length - 1];
    if (previous && canCoalesceMessage(previous, incoming)) {
      next[next.length - 1] = coalescePayload(previous, incoming);
    } else {
      next.push(incoming);
    }
  }
  return next;
};

/**
 * Interface representing the return value of the useQuasarBridge hook.
 */
interface UseQuasarBridgeReturn {
  /** Whether the WebSocket connection is active */
  isConnected: boolean;
  /** Whether the system is currently executing a task */
  isRunning: boolean;
  /** Whether execution is paused waiting for user approval of the plan */
  isAwaitingPlanConfirmation: boolean;
  /** Status of the RAG system */
  ragStatus: 'initializing' | 'ready' | 'disabled' | 'error';
  /** Initialization status message */
  initStatus: { status: string; message: string };
  /** Whether the system is in the initialization phase */
  isInitializing: boolean;
  /** Whether a checkpoint exists */
  hasCheckpoint: boolean;
  /** Whether valid archives exist */
  hasArchive: boolean;
  /** Number of archived runs */
  archiveCount: number;
  /** List of messages received from the bridge */
  messages: BridgeMessage[];
  /** Function to send a message to the bridge */
  sendMessage: (msg: object) => void;
  /** Respond to the execution-plan confirmation gate */
  respondToPlanConfirmation: (response: PlanConfirmationResponse) => void;
  /** Function to update system settings */
  sendSettings: (settings: Record<string, string>) => void;
  /** Function to cancel the current execution */
  cancelExecution: () => Promise<any>;
  /** Function to check for existing checkpoints */
  checkForCheckpoint: () => Promise<any>;
  /** Checkpoint information if available */
  checkpointInfo: any | null;
  /** Function to clear all messages */
  clearMessages: () => void;
  /** Function to manually set messages */
  setMessages: (messages: BridgeMessage[] | ((prev: BridgeMessage[]) => BridgeMessage[])) => void;
  /** Function to start a fresh session, clearing workspace */
  startFresh: (includeArchive?: boolean) => Promise<{ success: boolean }>;
  /** Whether the system is starting up */
  isStarting: boolean;
  /** Whether the initial terminal settings have been synchronized */
  settingsSynced: boolean;
  /** Current task progress (current/total/title) */
  taskProgress: { current: number; total: number; title?: string } | null;
  /** Function to set task progress (for checkpoint restoration) */
  setTaskProgress: (progress: { current: number; total: number; title?: string } | null) => void;
  /** Current restricted context-window usage */
  contextUsage: ContextUsage | null;
  /** Function to revert to a specific task (time travel) */
  revertToTask: (targetTask: number) => Promise<{ success: boolean; error?: string; deletedFiles?: string[] }>;
  /** Whether the system is currently archiving/cleaning up workspace */
  isCleaningUp: boolean;
  /** True while cancel/interrupt is in flight (before checkpoint metadata settles). */
  isInterrupting: boolean;
}

/**
 * Hook to manage the WebSocket bridge connection to the Quasar server.
 * Handles state synchronization, messaging, and system control.
 */
export function useQuasarBridge(): UseQuasarBridgeReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isAwaitingPlanConfirmation, setIsAwaitingPlanConfirmation] = useState(false);
  const [ragStatus, setRagStatus] = useState<'initializing' | 'ready' | 'disabled' | 'error'>('initializing');
  const [initStatus, setInitStatus] = useState<{ status: string; message: string }>({ status: 'initializing', message: 'Initializing system' });
  const [hasCheckpoint, setHasCheckpoint] = useState(false);
  const [hasArchive, setHasArchive] = useState(false);
  const [archiveCount, setArchiveCount] = useState(0);
  const [checkpointInfo, setCheckpointInfo] = useState<any | null>(null);
  const [messages, setMessages] = useState<BridgeMessage[]>([]);
  const [isStarting, setIsStarting] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const [settingsSynced, setSettingsSynced] = useState(false);
  const [taskProgress, setTaskProgress] = useState<{ current: number; total: number; title?: string } | null>(null);
  const [contextUsage, setContextUsage] = useState<ContextUsage | null>(null);
  const [isCleaningUp, setIsCleaningUp] = useState(false);
  const [isInterrupting, setIsInterrupting] = useState(false);
  const settingsSentRef = useRef(false);
  const shouldReconnectRef = useRef(true);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingMessagesRef = useRef<BridgeMessage[]>([]);
  const messageFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const checkpointRequestIdRef = useRef(0);

  const cancelMessageFlush = useCallback(() => {
    if (messageFlushTimerRef.current) {
      clearTimeout(messageFlushTimerRef.current);
      messageFlushTimerRef.current = null;
    }
  }, []);

  const flushPendingMessages = useCallback(() => {
    cancelMessageFlush();
    if (pendingMessagesRef.current.length === 0) return;
    const batch = pendingMessagesRef.current;
    pendingMessagesRef.current = [];
    setMessages(prev => appendCompactedMessages(prev, batch));
  }, [cancelMessageFlush]);

  const appendMessage = useCallback((message: BridgeMessage) => {
    pendingMessagesRef.current.push(message);
    if (
      message.type === 'error' ||
      message.type === 'done' ||
      message.type === 'run_status' ||
      message.type === 'plan_declined'
    ) {
      flushPendingMessages();
      return;
    }
    if (pendingMessagesRef.current.length >= MAX_BATCHED_MESSAGES) {
      flushPendingMessages();
      return;
    }
    if (!messageFlushTimerRef.current) {
      messageFlushTimerRef.current = setTimeout(flushPendingMessages, MESSAGE_BATCH_DELAY_MS);
    }
  }, [flushPendingMessages]);

  const applyCheckpointSnapshot = useCallback((data: any) => {
    const exists = data?.exists === true;
    setHasCheckpoint(exists);
    setHasArchive(data?.hasArchive === true);
    setArchiveCount(data?.archiveCount || 0);
    setCheckpointInfo(exists ? data : null);
    return data;
  }, []);

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws`;

    // Clear any existing connection before starting a new one
    if (wsRef.current) {
      wsRef.current.close();
    }
    
    const ws = new WebSocket(withAuthWebSocketUrl(wsUrl));
    wsRef.current = ws;

    ws.onopen = async () => {
      console.log('Bridge WebSocket Connected');
      setIsConnected(true);
      
      try {
        // Fetch server environment settings first
        const response = await fetch('/api/settings');
        let serverSettings = {};
        if (response.ok) {
          serverSettings = await response.json();
        }

        // Get stored settings and merge (server-side environment variables take precedence)
        const localSettings = getStoredSettings();
        const mergedSettings = mergeSettingsPreservingMaskedValues(
          localSettings,
          serverSettings
        );
        
        // Filter out empty values
        const finalSettings = Object.fromEntries(
          Object.entries(mergedSettings).filter(([_, v]) => v != null && v !== '')
        ) as Record<string, string>;

        if (Object.keys(finalSettings).length > 0 && !settingsSentRef.current) {
          // Update local storage so settings UI picks it up
          setStoredSettings(finalSettings);
          
          ws.send(JSON.stringify({ command: 'update_settings', settings: finalSettings }));
          settingsSentRef.current = true;
        }
        // Mark settings as synced (either because we sent them, or because there were none to send)
        setSettingsSynced(true);
      } catch (e) {
        console.error('Failed to sync settings on connect:', e);
        
        // Fallback to just stored settings if fetch fails
        const settings = getStoredSettings();
        if (Object.keys(settings).length > 0 && !settingsSentRef.current) {
          ws.send(JSON.stringify({ command: 'update_settings', settings }));
          settingsSentRef.current = true;
        }
        setSettingsSynced(true);
      }
    };

    ws.onclose = () => {
      console.log('Bridge WebSocket Disconnected');
      setIsConnected(false);
      setIsRunning(false);
      setIsAwaitingPlanConfirmation(false);
      settingsSentRef.current = false;
      
      // Clean up ref if this was the current websocket
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
      
      // Only reconnect if we haven't unmounted and this wasn't an intentional close
      if (shouldReconnectRef.current) {
        if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = setTimeout(connect, 3000);
      }
    };

    ws.onerror = (err) => {
      console.error('Bridge WebSocket Error:', err);
      ws.close();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // Handle initialization status updates
        if (data.type === 'init_status' && data.payload) {
          setInitStatus(prev => {
            const nextStatus = data.payload.status || 'initializing';
            const nextMessage = data.payload.message || 'Initializing';
            // Once ready, ignore deferred background steps so they cannot re-lock the dashboard.
            if (prev.status === 'ready' && nextStatus !== 'error' && nextStatus !== 'ready') {
              return prev;
            }
            return { status: nextStatus, message: nextMessage };
          });
          return;
        }
        
        // Handle RAG status updates
        if (data.type === 'rag_status' && data.payload?.status) {
          setRagStatus(data.payload.status);
          return;
        }
        
        // Handle settings confirmation
        if (data.type === 'settings_updated') {
          return;
        }

        // The bridge uses status events for transient CLI loading text. The web
        // UI has its own loading state, so do not add these to the execution log.
        if (data.type === 'status') {
          return;
        }

        // Handle checkpoint detection
        if (data.type === 'checkpoint_status') {
          const payload = data.payload || {};
          const exists = 'exists' in payload
            ? payload.exists === true
            : payload.is_resuming === true;
          setHasCheckpoint(exists);
          if (!exists) {
            setCheckpointInfo(null);
          } else if ('can_resume_steering' in payload || 'checkpoint_next' in payload) {
            setCheckpointInfo((prev: any) => ({
              ...(prev || {}),
              exists: true,
              ...payload,
            }));
          }
          return;
        }

        // Handle execution status
        if (data.type === 'execution_status') {
          setIsRunning(data.payload?.running === true);
          return;
        }

        // Handle bridge restart
        if (data.type === 'bridge_restarted') {
          setIsRunning(false);
          setIsAwaitingPlanConfirmation(false);
          return;
        }

        // Handle system status
        if (data.type === 'system_status') {
          if (data.payload?.status === 'running') {
            setIsStarting(false);
          } else if (data.payload?.status === 'completed') {
            setIsStarting(false);
            setIsRunning(false);
            setIsAwaitingPlanConfirmation(false);
          }
          return;
        }

        // Handle system_ready - execution has finished or just started
        if (data.type === 'system_ready') {
          setIsStarting(false);
          return;
        }

        if (data.type === 'plan_awaiting_confirm') {
          setIsStarting(false);
          setIsAwaitingPlanConfirmation(true);
          appendMessage(data);
          return;
        }

        if (data.type === 'plan_declined') {
          setIsStarting(false);
          setIsRunning(false);
          setIsAwaitingPlanConfirmation(false);
          setHasCheckpoint(false);
          setCheckpointInfo(null);
          setTaskProgress(null);
          appendMessage(data);
          return;
        }

        // Handle task progress updates - also add to messages for log display
        if (data.type === 'task_progress' && data.payload) {
          setTaskProgress({ current: data.payload.current, total: data.payload.total, title: data.payload.title });
          // Don't return - let it fall through to be added to messages
        }

        if (data.type === 'context_usage' && data.payload) {
          setContextUsage(data.payload);
          return;
        }

        if (data.type === 'final_summary') {
          return;
        }

        // Handle done - end execution UI state
        if (data.type === 'done') {
          setTaskProgress(null);
          setIsRunning(false);
          setIsStarting(false);
          setIsAwaitingPlanConfirmation(false);
          setIsInterrupting(false);
        }

        // Handle cleanup status - show/hide archiving overlay
        if (data.type === 'cleanup_status' && data.payload) {
          if (data.payload.status === 'starting') {
            setIsCleaningUp(true);
          } else if (data.payload.status === 'complete' || data.payload.status === 'error') {
            setIsCleaningUp(false);
          }
          // Don't add cleanup_status to messages - it's just for UI state
          return;
        }
        
        appendMessage(data);
      } catch (e) {
        // Silently ignore non-JSON messages to reduce noise
      }
    };

    wsRef.current = ws;
  }, [appendMessage]);

  useEffect(() => {
    shouldReconnectRef.current = true;
    connect();
    
    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      cancelMessageFlush();
      pendingMessagesRef.current = [];
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [cancelMessageFlush, connect]);

  const sendMessage = useCallback((msg: object) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
      // If sending a prompt, mark as running and add starting/resuming message
      if ('command' in msg && (msg as any).command === 'prompt') {
        const isResuming = (msg as any).restart === false;
        setIsRunning(true);
        setIsStarting(true);
        setIsAwaitingPlanConfirmation(false);
        // Add a run status message - resuming if restart is false, otherwise starting
        appendMessage({
          type: 'run_status', 
          payload: { status: isResuming ? 'resumed' : 'starting' } 
        });
      }
    } else {
      console.warn('Cannot send message, WebSocket not connected');
    }
  }, [appendMessage]);

  const respondToPlanConfirmation = useCallback((response: PlanConfirmationResponse) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      setIsAwaitingPlanConfirmation(false);
      wsRef.current.send(JSON.stringify({
        command: 'plan_confirm',
        action: response.action,
        feedback: response.feedback ?? '',
      }));
    } else {
      console.warn('Cannot send plan confirmation, WebSocket not connected');
    }
  }, []);

  const sendSettings = useCallback((settings: Record<string, string>) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ command: 'update_settings', settings }));
    }
  }, []);

  const fetchCheckpointSnapshot = useCallback(async () => {
    const requestId = ++checkpointRequestIdRef.current;
    const response = await fetch('/api/checkpoint');
    const data = await response.json();
    if (requestId === checkpointRequestIdRef.current) {
      applyCheckpointSnapshot(data);
    }
    return data;
  }, [applyCheckpointSnapshot]);

  const fetchCheckpointSnapshotWithRetry = useCallback(async (attempts = 4, delayMs = 350) => {
    let lastData: any = { exists: false };
    for (let attempt = 0; attempt < attempts; attempt++) {
      if (attempt > 0) {
        await new Promise(resolve => setTimeout(resolve, delayMs * attempt));
      }
      lastData = await fetchCheckpointSnapshot();
      // Success paths: no checkpoint, or we got the steering flag.
      if (!lastData?.exists || typeof lastData?.can_resume_steering === 'boolean') {
        return lastData;
      }
      // Transient extract failures (sqlite lock during interrupt) leave exists=true
      // without can_resume_steering — retry a few times.
    }
    return lastData;
  }, [fetchCheckpointSnapshot]);

  const cancelExecution = useCallback(async () => {
    // Optimistically flip UI to the post-interrupt resume shell so we never
    // flash the empty "Send a message" composer between Stop and checkpoint load.
    setIsInterrupting(true);
    setIsRunning(false);
    setIsStarting(false);
    setIsAwaitingPlanConfirmation(false);
    setHasCheckpoint(true);
    try {
      // Add interrupted status message before stopping
      appendMessage({
        type: 'run_status', 
        payload: { status: 'interrupted' } 
      });
      const response = await fetch('/api/cancel', { method: 'POST' });
      await response.json().catch(() => null);
      // Server waits for the bridge to exit; still retry metadata load so
      // operator-stage checkpoints reliably unlock resume steering.
      return await fetchCheckpointSnapshotWithRetry();
    } catch (e) {
      console.error("Failed to cancel execution", e);
    } finally {
      setIsInterrupting(false);
    }
  }, [appendMessage, fetchCheckpointSnapshotWithRetry]);

  const checkForCheckpoint = useCallback(async () => {
    try {
      return await fetchCheckpointSnapshot();
    } catch (e) {
      console.error("Failed to check checkpoint", e);
      return { exists: false };
    }
  }, [fetchCheckpointSnapshot]);

  const clearMessages = useCallback(() => {
    cancelMessageFlush();
    pendingMessagesRef.current = [];
    setMessages([]);
  }, [cancelMessageFlush]);

  const startFresh = useCallback(async (includeArchive = false) => {
    try {
      // Any checkpoint response started before this reset describes the old run.
      checkpointRequestIdRef.current += 1;
      const response = await fetch('/api/fresh', { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ includeArchive })
      });
      const data = await response.json();
      if (data.success) {
        setHasCheckpoint(false);
        setCheckpointInfo(null);
        if (includeArchive) {
          setHasArchive(false);
          setArchiveCount(0);
        }
        cancelMessageFlush();
        pendingMessagesRef.current = [];
        setMessages([]);
      }
      return data;
    } catch (e) {
      console.error("Failed to start fresh", e);
      return { success: false };
    }
  }, [cancelMessageFlush]);

  const revertToTask = useCallback(async (targetTask: number) => {
    try {
      const response = await fetch('/api/revert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ targetTask })
      });
      const data = await response.json();
      
      if (data.success) {
        // Clear messages since we're reverting
        cancelMessageFlush();
        pendingMessagesRef.current = [];
        setMessages([]);
        // Trigger checkpoint reload
        await checkForCheckpoint();
      }
      
      return data;
    } catch (e) {
      console.error('Failed to revert to task', e);
      return { success: false, error: String(e) };
    }
  }, [cancelMessageFlush, checkForCheckpoint]);

  // Compute isInitializing from initStatus
  const isInitializing = initStatus.status !== 'ready' && initStatus.status !== 'error';

  return { 
    isConnected, 
    isRunning,
    isAwaitingPlanConfirmation,
    ragStatus,
    initStatus,
    isInitializing,
    hasCheckpoint,
    hasArchive,
    archiveCount,
    checkpointInfo,
    messages, 
    sendMessage, 
    respondToPlanConfirmation,
    sendSettings, 
    cancelExecution,
    checkForCheckpoint,
    clearMessages,
    setMessages,
    startFresh,
    isStarting,
    settingsSynced,
    taskProgress,
    setTaskProgress,
    contextUsage,
    revertToTask,
    isCleaningUp,
    isInterrupting,
  };
}
