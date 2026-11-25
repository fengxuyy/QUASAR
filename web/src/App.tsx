import { lazy, startTransition, Suspense, useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { clsx } from 'clsx';
import { GlassLayout } from './components/Layout/GlassLayout';
import { DetachedSidebar } from './components/Sidebar/DetachedSidebar';
import { DynamicInput } from './components/Input/DynamicInput';
import { ConfirmModal } from './components/UI/ConfirmModal';
import { RevertOverlay } from './components/UI/RevertOverlay';
import { CleanupOverlay } from './components/UI/CleanupOverlay';
import { FreshStartOverlay } from './components/UI/FreshStartOverlay';
import { DashboardWelcome } from './components/Dashboard/DashboardWelcome';
import { useQuasarBridge } from './hooks/useQuasarBridge';
import { Loader2, AlertCircle, X, History as HistoryIcon } from 'lucide-react';
import { parseHistoryToMessages } from './utils/historyHelpers';
import { NavigationProvider } from './contexts/NavigationContext';
import { resolveWorkspaceLinkTarget } from './utils/fileLinkUtils';
import { getStoredSettings, hasConfiguredApiKey, mergeStoredSettings } from './utils/settingsStorage';
import {
  beginTrackedRun,
  canApplyRunCompletion,
  createRunLifecycleState,
  suppressRunCompletion,
} from './utils/runLifecycle';

const AUTO_IMPROVE_MESSAGE = "Please analyze the previous run results and automatically improve the workflow. Review what was accomplished, identify any issues or areas for enhancement, and create an improved execution plan.";
const trimTrailingEllipsis = (text: string) => text.replace(/\.\.\.$/, '');

const TokenTrackerPanel = lazy(() => import('./components/Input/TokenTrackerPanel').then(module => ({ default: module.TokenTrackerPanel })));
const ExecutionLog = lazy(() => import('./components/Dashboard/ExecutionLog').then(module => ({ default: module.ExecutionLog })));
const WorkspaceImpactMap = lazy(() => import('./components/Dashboard/WorkspaceImpactMap').then(module => ({ default: module.WorkspaceImpactMap })));
const SettingsPanel = lazy(() => import('./components/Settings/SettingsPanel').then(module => ({ default: module.SettingsPanel })));
const WorkspacePanel = lazy(() => import('./components/Workspace/WorkspacePanel').then(module => ({ default: module.WorkspacePanel })));
const HistoryPanel = lazy(() => import('./components/History/HistoryPanel').then(module => ({ default: module.HistoryPanel })));
const TerminalPanel = lazy(() => import('./components/Terminal/TerminalPanel').then(module => ({ default: module.TerminalPanel })));

const PanelFallback = () => (
  <div className="flex h-full w-full items-center justify-center text-sm font-medium text-slate-400">
    Loading
  </div>
);

function App() {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'settings' | 'workspace' | 'history' | 'terminal'>('dashboard');
  const [visitedTabs, setVisitedTabs] = useState<Set<'dashboard' | 'settings' | 'workspace' | 'history' | 'terminal'>>(() => new Set(['dashboard']));
  const [hasStarted, setHasStarted] = useState(false);
  const [currentPrompt, setCurrentPrompt] = useState<string>('');
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [showResumeConfirm, setShowResumeConfirm] = useState(false);
  const [showFreshConfirm, setShowFreshConfirm] = useState(false);
  const [showClearArchiveConfirm, setShowClearArchiveConfirm] = useState(false);
  const [showEmptySubmitConfirm, setShowEmptySubmitConfirm] = useState(false);
  const [showRevertConfirm, setShowRevertConfirm] = useState(false);
  const [revertTargetTask, setRevertTargetTask] = useState<number | null>(null);
  const [isReverting, setIsReverting] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isClearingArchiveLoading, setIsClearingArchiveLoading] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [runJustFinished, setRunJustFinished] = useState(false);
  const [hasInterruptedError, setHasInterruptedError] = useState(false);
  const [workspaceRefreshKey, setWorkspaceRefreshKey] = useState(0);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  const [navKey, setNavKey] = useState(0);
  const [fileRedirectError, setFileRedirectError] = useState<string | null>(null);
  const fileRedirectErrorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const planDeclinedRef = useRef(false);
  const completedRunHandledRef = useRef(false);
  const runLifecycleRef = useRef(createRunLifecycleState());
  const [archiveLandingDismissed, setArchiveLandingDismissed] = useState(false);

  // Trace viewing mode state
  const [isViewingTrace, setIsViewingTrace] = useState(false);
  const [traceArchiveId, setTraceArchiveId] = useState<string | null>(null);
  const [traceMessages, setTraceMessages] = useState<any[]>([]);
  const [traceInput, setTraceInput] = useState<string>('');
  const [isLoadingTrace, setIsLoadingTrace] = useState(false);

  const {
    messages,
    sendMessage,
    respondToPlanConfirmation,
    initStatus,
    isInitializing,
    isRunning,
    isAwaitingPlanConfirmation,
    hasCheckpoint,
    hasArchive,
    archiveCount,
    cancelExecution,
    checkForCheckpoint,
    checkpointInfo,
    clearMessages,
    setMessages,
    startFresh,
    isStarting,
    settingsSynced,
    taskProgress,
    setTaskProgress,
    contextUsage,
    sendSettings,
    revertToTask,
    isCleaningUp,
    isInterrupting,
  } = useQuasarBridge();

  const prevIsRunningRef = useRef(isRunning);

  const [activeAgent, setActiveAgent] = useState<'strategist' | 'operator' | 'evaluator' | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<'strategist' | 'operator' | 'evaluator' | null>(null);
  const [initialCheckDone, setInitialCheckDone] = useState(false);
  const initialCheckStartedRef = useRef(false);
  const [pendingArchiveSelection, setPendingArchiveSelection] = useState<string | null>(null);
  const [pendingFileSelection, setPendingFileSelection] = useState<string | null>(null);
  const [isRetrievingCheckpoint, setIsRetrievingCheckpoint] = useState(false);
  const isBusy = isInitializing || isRetrievingCheckpoint;
  // Steering is operator-stage only. After interrupt, metadata can lag (or fail
  // briefly while sqlite unlocks); if a task was in progress and the server has
  // not explicitly denied steering yet, keep the resume box editable.
  const canResumeWithSteering =
    isInterrupting ||
    checkpointInfo?.can_resume_steering === true ||
    (hasCheckpoint &&
      checkpointInfo?.can_resume_steering !== false &&
      !!taskProgress &&
      taskProgress.total > 0 &&
      !isRunning);
  const showCheckpointResumeUi = !isRunning && (hasCheckpoint || hasInterruptedError || isInterrupting);
  const isStrategistStageCheckpoint = useMemo(() => {
    if (!hasCheckpoint || !checkpointInfo) return false;

    const rawNext = checkpointInfo.checkpoint_next;
    const nodes = (Array.isArray(rawNext) ? rawNext : (rawNext ? [rawNext] : []))
      .map(node => String(node).trim().replace(/^['"]|['"]$/g, '').toLowerCase());
    const hasStrategistNode = nodes.some(node =>
      node === 'plan_review_confirm' || node.startsWith('strategist')
    );
    if (!hasStrategistNode) return false;

    const history = checkpointInfo.history || {};
    const completedSteps = Array.isArray(history.completed_steps) ? history.completed_steps : [];
    const stepResults = history.step_results && typeof history.step_results === 'object'
      ? Object.keys(history.step_results)
      : [];
    return completedSteps.length === 0 && stepResults.length === 0;
  }, [checkpointInfo, hasCheckpoint]);

  useEffect(() => {
    setVisitedTabs(prev => {
      if (prev.has(activeTab)) return prev;
      const next = new Set(prev);
      next.add(activeTab);
      return next;
    });
  }, [activeTab]);

  // Refresh the workspace tree as initialization/downloads advance (e.g. docs, RAG index).
  useEffect(() => {
    if (
      initStatus.status === 'downloading_docs' ||
      initStatus.status === 'docs_ready' ||
      initStatus.status === 'downloading_index' ||
      initStatus.status === 'index_ready' ||
      initStatus.status === 'ready'
    ) {
      setWorkspaceRefreshKey(prev => prev + 1);
    }
  }, [initStatus.status, initStatus.message]);

  // Navigation callback for file links in execution log
  const handleNavigateToFile = useCallback((filePath: string, archiveId?: string | null) => {
    const target = resolveWorkspaceLinkTarget(filePath, archiveId);

    setPendingArchiveSelection(target.archiveId);
    setPendingFileSelection(target.filePath);
    setNavKey(prev => prev + 1);
    setActiveTab('workspace');
  }, []);

  const handleFileRedirectNotFound = useCallback((filePath: string) => {
    setFileRedirectError(`File not found in workspace: ${filePath}`);
    if (fileRedirectErrorTimeoutRef.current) {
      clearTimeout(fileRedirectErrorTimeoutRef.current);
    }
    fileRedirectErrorTimeoutRef.current = setTimeout(() => {
      setFileRedirectError(null);
      fileRedirectErrorTimeoutRef.current = null;
    }, 4000);
  }, []);

  // Revert to a specific task - shows confirmation first
  const handleRevertRequest = useCallback(async (taskNumber: number): Promise<void> => {
    setRevertTargetTask(taskNumber);
    setShowRevertConfirm(true);
  }, []);

  // Actually perform the revert after confirmation
  const handleRevertConfirm = useCallback(async () => {
    if (!revertTargetTask) return;

    setShowRevertConfirm(false);
    setIsReverting(true);

    try {
      const result = await revertToTask(revertTargetTask);
      if (result.success) {
        // Reload the page to get fresh checkpoint data
        window.location.reload();
      } else {
        console.error('Revert failed:', result.error);
        alert(`Failed to revert: ${result.error || 'Unknown error'}`);
        setIsReverting(false);
      }
    } catch (error) {
      console.error('Revert error:', error);
      alert(`Revert failed: ${error}`);
      setIsReverting(false);
    }
  }, [revertTargetTask, revertToTask]);

  // Check for checkpoint or live session on app mount
  // Wait for system initialization to complete before loading checkpoint
  useEffect(() => {
    if (initialCheckDone) return;
    // Wait for system to be initialized first
    if (isInitializing) return;
    // Use ref as synchronous guard - prevents duplicate async invocations
    // when dependencies change during the 500ms delay or checkpoint fetch
    if (initialCheckStartedRef.current) return;
    initialCheckStartedRef.current = true;

    const checkOnMount = async () => {
      setIsRetrievingCheckpoint(true);
      // Small delay to allow WebSocket state to synchronize
      await new Promise(resolve => setTimeout(resolve, 500));

      // Always check for checkpoint - even when running
      // This ensures we load execution history on refresh
      const data = await checkForCheckpoint();

      if (data.exists) {
        setHasStarted(true);
        if (data.previous_input) {
          setCurrentPrompt(data.previous_input);
        }
        // Checkpoint resumes should start with an empty steering box.
        setInputValue('');

        // Apply checkpoint's saved settings to localStorage
        // Merge instead of replacing so runtime-only values like API keys survive
        // checkpoint restores (checkpoint_settings.json intentionally excludes them).
        if (data.savedSettings) {
          mergeStoredSettings(data.savedSettings, { ignoreEmptyStrings: true });
          console.log('Merged checkpoint settings into localStorage');
        }

        // Always load checkpoint history - even when running
        // This ensures strategist plan and previous execution log are visible after refresh
        // Live messageBuffer messages from the server will append to this history
        if (data.history) {
            await new Promise(resolve => setTimeout(resolve, 0));
            const historyMessages = parseHistoryToMessages(data.history);

            if (historyMessages.length > 0) {
                // Remove the trailing 'interrupted' status since we might be actively running
                const filteredHistory = (isRunning || data.isRunning)
                    ? historyMessages.filter(m => !(m.type === 'run_status' && m.payload?.status === 'interrupted'))
                    : historyMessages;
                // Use functional form to preserve any live WebSocket messages
                // (agent_event updates, task_progress, thought_stream, text_stream)
                // that were received while checkpoint history was loading
                startTransition(() => setMessages(prev => {
                    const liveMessages = prev.filter(m =>
                        m.type === 'agent_event' ||
                        m.type === 'task_progress' ||
                        m.type === 'thought_stream' ||
                        m.type === 'text_stream'
                    );
                    return liveMessages.length > 0
                        ? [...filteredHistory, ...liveMessages]
                        : filteredHistory;
                }));
            }
        }
      } else if (isRunning) {
        // No checkpoint but running - just mark as started
        setHasStarted(true);
        // Try to recover currentPrompt from buffered messages
        const lastPromptMsg = [...messages].reverse().find(m => m.type === 'log' && m.payload?.text?.startsWith('> '));
        if (lastPromptMsg) {
          setCurrentPrompt(lastPromptMsg.payload.text.substring(2));
        }
      }

      setInitialCheckDone(true);
      setIsRetrievingCheckpoint(false);
    };
    checkOnMount();
  }, [checkForCheckpoint, setMessages, isRunning, initialCheckDone, isInitializing, messages]);

  // Effect to parse messages and update state
  useEffect(() => {
    if (messages.length > 0) {
        const lastMsg = messages[messages.length - 1];

        const isErrorInterruption =
          lastMsg.type === 'error' ||
          (lastMsg.type === 'run_status' &&
            lastMsg.payload?.status === 'interrupted' &&
            messages.length >= 2 &&
            messages[messages.length - 2]?.type === 'error');

        if (isErrorInterruption) {
          suppressRunCompletion(runLifecycleRef.current);
          setActiveAgent(null);
          setHasStarted(true);
          setHasInterruptedError(true);
          setRunJustFinished(false);
          setActiveTab('dashboard');
          void checkForCheckpoint();
          return;
        }

        if (lastMsg.type === 'agent_event' && lastMsg.payload) {
             const { agent, event } = lastMsg.payload;
             if (event === 'start' || event === 'update') {
                 if (agent.toLowerCase().includes('strategist')) setActiveAgent('strategist');
                 else if (agent.toLowerCase().includes('operator')) setActiveAgent('operator');
                 else if (agent.toLowerCase().includes('evaluator')) setActiveAgent('evaluator');
             } else if (event === 'complete') {
                  setActiveAgent(null);
             }
        }
    }
  }, [messages, checkForCheckpoint]);

  useEffect(() => {
    if (!isAwaitingPlanConfirmation) return;
    setActiveTab('dashboard');
  }, [isAwaitingPlanConfirmation]);

  useEffect(() => {
    if (messages.length === 0) return;

    const lastMsg = messages[messages.length - 1];
    if (lastMsg.type !== 'plan_declined') return;

    const restoredPrompt =
      typeof lastMsg.payload?.user_input === 'string' && lastMsg.payload.user_input.trim()
        ? lastMsg.payload.user_input
        : currentPrompt;

    planDeclinedRef.current = true;
    clearMessages();
    setActiveAgent(null);
    setSelectedAgent(null);
    setCurrentPrompt(restoredPrompt);
    setInputValue(restoredPrompt);
    setHasStarted(false);
    setRunJustFinished(false);
    setTaskProgress(null);
    setActiveTab('dashboard');
  }, [messages, clearMessages, currentPrompt, setTaskProgress]);

  useEffect(() => {
    if (messages.length === 0) return;

    const lastMsg = messages[messages.length - 1];
    if (lastMsg.type !== 'done') return;

    const status = lastMsg.payload?.status;
    if (status === 'error' || status === 'interrupted') {
      suppressRunCompletion(runLifecycleRef.current);
      completedRunHandledRef.current = false;
      setActiveAgent(null);
      setHasStarted(true);
      setHasInterruptedError(true);
      setRunJustFinished(false);
      setActiveTab('dashboard');
      void checkForCheckpoint();
      return;
    }
    if (status !== 'completed' && status !== 'gave_up') {
      completedRunHandledRef.current = false;
      return;
    }
    if (!canApplyRunCompletion(runLifecycleRef.current, runLifecycleRef.current.revision)) {
      clearMessages();
      setRunJustFinished(false);
      return;
    }
    if (completedRunHandledRef.current) return;

    completedRunHandledRef.current = true;
    clearMessages();
    setActiveAgent(null);
    setSelectedAgent(null);
    setHasStarted(false);
    setRunJustFinished(true);
    setArchiveLandingDismissed(false);
    setInputValue('');
    setTaskProgress(null);
    setActiveTab('dashboard');
    setWorkspaceRefreshKey(prev => prev + 1);
    setHistoryRefreshKey(prev => prev + 1);

    void checkForCheckpoint();
  }, [messages, clearMessages, checkForCheckpoint, setTaskProgress]);

  // Safeguard: Reset active agent and re-check checkpoint when execution stops
  useEffect(() => {
    // Detect when run just finished
    if (!isRunning && prevIsRunningRef.current === true) {
      const lifecycleRevision = runLifecycleRef.current.revision;
      if (planDeclinedRef.current) {
        planDeclinedRef.current = false;
        setRunJustFinished(false);
      } else if (!canApplyRunCompletion(runLifecycleRef.current, lifecycleRevision)) {
        setRunJustFinished(false);
      } else {
        // Check if the run was interrupted by looking for 'interrupted' status in messages
        const messageIndicatesInterruption = messages.some(msg =>
          msg.type === 'run_status' && msg.payload?.status === 'interrupted'
        );

        // If messages already indicate interruption, handle it immediately
        if (messageIndicatesInterruption) {
          setRunJustFinished(false);
        } else {
          // Otherwise, wait for checkpoint check to determine final state
          // This avoids race condition where hasCheckpoint is stale
          checkForCheckpoint().then((data) => {
            if (
              completedRunHandledRef.current ||
              !canApplyRunCompletion(runLifecycleRef.current, lifecycleRevision)
            ) {
              return;
            }
            if (data?.exists) {
              // Checkpoint exists = interrupted run, keep log visible
              setRunJustFinished(false);
            } else {
              // No checkpoint = completed successfully, hide log and clear input
              setRunJustFinished(true);
              setArchiveLandingDismissed(false);
              setInputValue(''); // Clear input so placeholder shows
            }
          });
        }
      }

      // Trigger refreshes for Workspace and History when a run finishes
      setWorkspaceRefreshKey(prev => prev + 1);
      setHistoryRefreshKey(prev => prev + 1);
    }
    prevIsRunningRef.current = isRunning;

    if (!isRunning) {
      setActiveAgent(null);
    }
  }, [isRunning, checkForCheckpoint, messages]);

  const handleSend = (text: string) => {
    // Validate settings before sending
    const settings = getStoredSettings();
    if (!settings.MODEL?.trim() || !hasConfiguredApiKey(settings, { allowServerMask: true })) {
      setSettingsError('Model Name and API Key are required. Please configure them in Settings.');
      return;
    }

    setSettingsError(null);
    setHasInterruptedError(false);
    beginTrackedRun(runLifecycleRef.current);
    completedRunHandledRef.current = false;
    if (!hasStarted || runJustFinished) {
      clearMessages();
    }
    if (!hasStarted) setHasStarted(true);
    setRunJustFinished(false);
    setCurrentPrompt(text);
    sendMessage({ command: 'prompt', content: text });
    setInputValue('');
  };

  const handleCancelClick = () => {
    setShowCancelModal(true);
  };

  const handleConfirmCancel = async () => {
    setShowCancelModal(false);
    setHasInterruptedError(false);
    suppressRunCompletion(runLifecycleRef.current);
    const checkpoint = await cancelExecution();
    setActiveAgent(null);
    if (!checkpoint?.exists) {
      clearMessages();
      setHasStarted(false);
      setRunJustFinished(false);
      setTaskProgress(null);
      setInputValue(currentPrompt || '');
      setCurrentPrompt('');
    } else {
      setInputValue('');
    }
  };

  const handleResumeFromCheckpoint = () => {
    setShowResumeConfirm(false);
    const settings = getStoredSettings();
    if (!settings.MODEL?.trim() || !hasConfiguredApiKey(settings, { allowServerMask: true })) {
      setSettingsError('Model Name and API Key are required. Please configure them in Settings.');
      return;
    }
    setSettingsError(null);
    setHasInterruptedError(false);
    beginTrackedRun(runLifecycleRef.current);
    completedRunHandledRef.current = false;
    if (hasCheckpoint) {
      const text = canResumeWithSteering && inputValue.trim() ? inputValue : '';
      sendMessage({ command: 'prompt', content: text, restart: false });
    } else {
      const promptToRetry = inputValue.trim() || currentPrompt;
      if (!promptToRetry) return;
      setCurrentPrompt(promptToRetry);
      sendMessage({ command: 'prompt', content: promptToRetry, restart: true });
    }
    setInputValue('');
  };

  const getFreshStartRestoreInput = (isCheckpointReset: boolean) => {
    if (isCheckpointReset) {
      return currentPrompt || '';
    }
    return inputValue.trim() ? inputValue : (currentPrompt || '');
  };

  const resetRunState = async (shouldClearArchive: boolean, restoredInput = '') => {
    suppressRunCompletion(runLifecycleRef.current);
    await startFresh(shouldClearArchive);
    await checkForCheckpoint();

    clearMessages();
    setCurrentPrompt('');
    setInputValue(restoredInput);
    setHasStarted(false);
    setHasInterruptedError(false);
    setRunJustFinished(false);
    setArchiveLandingDismissed(true);
    completedRunHandledRef.current = false;
    setTaskProgress(null);

    setWorkspaceRefreshKey(prev => prev + 1);
    setHistoryRefreshKey(prev => prev + 1);
  };

  const handleStartFreshConfirm = async () => {
    setShowFreshConfirm(false);
    setIsResetting(true);
    const restoredInput = getFreshStartRestoreInput(true);
    try {
      await resetRunState(false, restoredInput);
    } finally {
      setIsResetting(false);
    }
  };

  const handleClearArchiveConfirm = async () => {
    setShowClearArchiveConfirm(false);
    setIsClearingArchiveLoading(true);
    const restoredInput = getFreshStartRestoreInput(false);
    try {
      await resetRunState(true, restoredInput);
    } finally {
      setIsClearingArchiveLoading(false);
    }
  };

  const handleEmptySubmitConfirm = () => {
    setShowEmptySubmitConfirm(false);
    // Send auto-improvement message
    beginTrackedRun(runLifecycleRef.current);
    completedRunHandledRef.current = false;
    if (!hasStarted) setHasStarted(true);
    setRunJustFinished(false); // Ensure execution log is visible
    setCurrentPrompt(AUTO_IMPROVE_MESSAGE);
    clearMessages(); // Clear old messages before starting new run
    sendMessage({ command: 'prompt', content: AUTO_IMPROVE_MESSAGE });
  };

  const handlePlanConfirm = useCallback(() => {
    setInputValue('');
    respondToPlanConfirmation({ action: 'confirm' });
  }, [respondToPlanConfirmation]);

  const handlePlanDecline = useCallback(() => {
    setInputValue('');
    suppressRunCompletion(runLifecycleRef.current);
    respondToPlanConfirmation({ action: 'decline' });
  }, [respondToPlanConfirmation]);

  const handlePlanAdjust = useCallback(() => {
    const feedback = inputValue.trim();
    if (!feedback) return;
    setInputValue('');
    respondToPlanConfirmation({ action: 'revise', feedback });
  }, [inputValue, respondToPlanConfirmation]);

  const handleViewHistory = () => {
    setActiveTab('history');
  };

  const handleViewArchive = (archiveId: string) => {
    setPendingArchiveSelection(archiveId);
    setActiveTab('workspace');
  };

  const handleViewTrace = async (archiveId: string) => {
    console.log('handleViewTrace called with:', archiveId);
    setIsLoadingTrace(true);
    setActiveTab('dashboard');
    try {
      const response = await fetch(`/api/archive/${archiveId}/trace`);
      console.log('Trace response status:', response.status);

      const data = await response.json();
      console.log('Trace data:', data);

      if (!response.ok) {
        console.error('Failed to load trace:', data.error || 'Unknown error');
        alert(`Failed to load trace: ${data.error || 'Unknown error'}`);
        return;
      }

      if (data.history) {
        await new Promise(resolve => setTimeout(resolve, 0));
        const historyMessages = parseHistoryToMessages(data.history);
        console.log('Parsed trace messages:', historyMessages.length);
        startTransition(() => {
          setTraceMessages(historyMessages);
          setTraceInput(data.previousInput || '');
          setTraceArchiveId(archiveId);
          setIsViewingTrace(true);
        });
      } else if (data.error) {
        console.error('Trace extraction error:', data.error, data.traceback);
        alert(`Failed to extract trace: ${data.error}`);
      } else {
        alert('No trace data found for this run');
      }
    } catch (error) {
      console.error('Failed to load trace:', error);
      alert(`Failed to load trace: ${error}`);
    } finally {
      setIsLoadingTrace(false);
    }
  };

  const handleExitTrace = () => {
    setIsViewingTrace(false);
    setTraceArchiveId(null);
    setTraceMessages([]);
    setTraceInput('');
  };

  const canShowViewHistoryBanner =
    !isBusy &&
    !isViewingTrace &&
    !isLoadingTrace &&
    !isRunning &&
    !hasCheckpoint &&
    !isStarting &&
    activeTab !== 'history';
  const showViewHistoryBanner =
    canShowViewHistoryBanner &&
    (runJustFinished || (hasArchive && !archiveLandingDismissed));
  const hasAnyFloatingBanner = isBusy || showViewHistoryBanner || isLoadingTrace || !!settingsError || !!fileRedirectError;

  useEffect(() => {
    return () => {
      if (fileRedirectErrorTimeoutRef.current) {
        clearTimeout(fileRedirectErrorTimeoutRef.current);
      }
    };
  }, []);

  return (
    <NavigationProvider onNavigateToFile={handleNavigateToFile}>
    <GlassLayout>
      <DetachedSidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        isRunning={isRunning}
        taskProgress={taskProgress}
      />

      <main className="relative flex h-full min-h-0 min-w-0 flex-1 flex-col transition-all duration-500">
        {/* Global Floating Banners - visible across all tabs */}
        {hasAnyFloatingBanner && (
          <div className="pointer-events-none fixed left-1/2 top-[max(0.75rem,env(safe-area-inset-top))] z-50 flex w-[min(96vw,40rem)] -translate-x-1/2 flex-col items-center gap-2 px-2 sm:top-4 sm:w-auto sm:px-0">
            {/* Floating Status Banner */}
            {isBusy && (
              <div className="pointer-events-auto animate-in fade-in slide-in-from-top-4 duration-500">
                <div className="glass-panel flex max-w-full items-center gap-2 rounded-full border border-white/40 px-4 py-2 shadow-xl sm:gap-3 sm:px-6 sm:py-2.5">
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin text-blue-500" />
                  <span className="truncate text-sm font-medium text-slate-700">
                    {isRetrievingCheckpoint ? 'Retrieving Checkpoint' : trimTrailingEllipsis(initStatus.message)}
                  </span>
                </div>
              </div>
            )}

            {/* View History Banner - appears when run completes or when viewing completed run from checkpoint */}
            {showViewHistoryBanner && (
              <div className="pointer-events-auto animate-in fade-in slide-in-from-top-4 duration-500">
                <button
                  onClick={handleViewHistory}
                  className="glass-panel flex items-center gap-2 rounded-full border border-white/40 px-4 py-2 text-sm font-medium text-slate-700 shadow-xl transition-all hover:border-blue-200/70 hover:bg-white/70 hover:text-blue-700 sm:gap-3 sm:px-6 sm:py-2.5"
                >
                  <HistoryIcon className="h-4 w-4 text-blue-500" />
                  {runJustFinished && <span className="hidden sm:inline">Run complete</span>}
                  <span className="font-semibold text-blue-600">View History</span>
                </button>
              </div>
            )}

            {/* Loading Trace Banner */}
            {isLoadingTrace && (
              <div className="pointer-events-auto animate-in fade-in slide-in-from-top-4 duration-500">
                <div className="glass-panel flex items-center gap-2 rounded-full border border-white/40 px-4 py-2 shadow-xl sm:gap-3 sm:px-6 sm:py-2.5">
                  <Loader2 className="h-4 w-4 animate-spin text-purple-500" />
                  <span className="text-sm font-medium text-slate-700">Loading Trace</span>
                </div>
              </div>
            )}

            {/* Settings error banner */}
            {settingsError && (
              <div className="pointer-events-auto w-full animate-in fade-in slide-in-from-top-4 duration-300 sm:w-auto">
                <div className="glass-panel flex max-w-[min(96vw,64rem)] items-center gap-2 rounded-2xl border border-red-200/70 bg-red-50/85 px-3 py-2 shadow-xl sm:gap-3 sm:rounded-full sm:px-5 sm:py-2.5">
                  <AlertCircle className="h-4 w-4 shrink-0 text-red-600" />
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-red-700">{settingsError}</span>
                  <button
                    onClick={() => setActiveTab('settings')}
                    className="inline-flex shrink-0 items-center text-sm font-semibold text-red-600 transition-colors hover:text-red-700"
                  >
                    Settings
                  </button>
                  <button
                    onClick={() => setSettingsError(null)}
                    className="shrink-0 text-red-400 transition-colors hover:text-red-500"
                    aria-label="Dismiss settings error"
                  >
                    <X size={18} />
                  </button>
                </div>
              </div>
            )}

            {/* Redirect file not found banner */}
            {fileRedirectError && (
              <div className="pointer-events-auto w-full animate-in fade-in slide-in-from-top-4 duration-300 sm:w-auto">
                <div className="glass-panel flex max-w-full items-center gap-2 rounded-2xl border border-red-200/70 bg-red-50/85 px-3 py-2 shadow-xl sm:rounded-full sm:px-5">
                  <AlertCircle className="h-4 w-4 shrink-0 text-red-600" />
                  <span className="min-w-0 truncate text-sm font-medium text-red-700">{fileRedirectError}</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Main Content Area - All panels stay mounted to preserve state */}
        <div className="relative flex min-w-0 flex-1 flex-col">
            {/* Settings Panel */}
            <div className={clsx(
              "absolute inset-0 px-0 flex flex-col items-stretch justify-start overflow-y-auto scrollbar-glass transition-opacity duration-200",
              activeTab === 'settings' ? "opacity-100 z-10 [content-visibility:visible]" : "opacity-0 z-0 pointer-events-none [content-visibility:hidden]"
            )}>
              {visitedTabs.has('settings') && (
                <Suspense fallback={<PanelFallback />}>
                  <SettingsPanel
                    isRunning={isRunning}
                    isLoading={isBusy}
                    hasCheckpoint={hasCheckpoint}
                    sendSettings={sendSettings}
                  />
                </Suspense>
              )}
            </div>

            {/* Workspace Panel */}
            <div className={clsx(
              "absolute inset-0 px-0 flex flex-col items-stretch justify-start overflow-y-auto scrollbar-glass transition-opacity duration-200",
              activeTab === 'workspace' ? "opacity-100 z-10 [content-visibility:visible]" : "opacity-0 z-0 pointer-events-none [content-visibility:hidden]"
            )}>
              {visitedTabs.has('workspace') && (
                <Suspense fallback={<PanelFallback />}>
                  <WorkspacePanel
                    initialArchive={pendingArchiveSelection ?? undefined}
                    onArchiveChange={() => setPendingArchiveSelection(null)}
                    initialFilePath={pendingFileSelection ?? undefined}
                    onFilePathChange={() => setPendingFileSelection(null)}
                    onFileRedirectNotFound={handleFileRedirectNotFound}
                    navKey={navKey}
                    refreshKey={workspaceRefreshKey}
                    isActive={activeTab === 'workspace'}
                    fastPoll={isInitializing || isRunning}
                  />
                </Suspense>
              )}
            </div>

            {/* History Panel — panel owns scroll so mobile list stays a single scroll surface */}
            <div className={clsx(
              "absolute inset-0 flex min-h-0 flex-col items-stretch justify-start overflow-hidden transition-opacity duration-200",
              activeTab === 'history' ? "opacity-100 z-10 [content-visibility:visible]" : "opacity-0 z-0 pointer-events-none [content-visibility:hidden]"
            )}>
              {visitedTabs.has('history') && (
                <Suspense fallback={<PanelFallback />}>
                  <HistoryPanel
                    refreshKey={historyRefreshKey}
                    onViewArchive={handleViewArchive}
                    onViewTrace={handleViewTrace}
                    onViewCurrentWorkspace={() => setActiveTab('workspace')}
                    isRunning={isRunning}
                    hasCheckpoint={hasCheckpoint}
                    currentPrompt={currentPrompt}
                    isActive={activeTab === 'history'}
                  />
                </Suspense>
              )}
            </div>

            {/* Terminal Panel */}
            <div className={clsx(
              "absolute inset-0 px-0 flex flex-col items-stretch justify-start overflow-y-auto scrollbar-glass transition-opacity duration-200",
              activeTab === 'terminal' ? "opacity-100 z-10 [content-visibility:visible]" : "opacity-0 z-0 pointer-events-none [content-visibility:hidden]"
            )}>
              {visitedTabs.has('terminal') && (
                <Suspense fallback={<PanelFallback />}>
                  <TerminalPanel
                    shouldConnect={settingsSynced}
                    isVisible={activeTab === 'terminal'}
                  />
                </Suspense>
              )}
            </div>

            {/* Dashboard Panel */}
            <div className={clsx(
              "absolute inset-0 px-0 flex flex-col items-stretch justify-start overflow-hidden transition-opacity duration-200",
              activeTab === 'dashboard' ? "opacity-100 z-10 [content-visibility:visible]" : "opacity-0 z-0 pointer-events-none [content-visibility:hidden]"
            )}>
              {/* Designed empty state around the centered input */}
              {!isViewingTrace && !isLoadingTrace && !hasStarted && !isBusy && !isStarting && (
                <DashboardWelcome onSuggest={setInputValue} />
              )}

              {/* Trace Execution Log - shows archived run trace */}
              {isViewingTrace && !isLoadingTrace && traceMessages.length > 0 && (
                <div className="animate-fade-in-up h-full min-h-0 w-full min-w-0">
                  <Suspense fallback={<PanelFallback />}>
                    <ExecutionLog
                      messages={traceMessages}
                      activeAgent={null}
                      selectedAgent={selectedAgent}
                      onAgentSelect={setSelectedAgent}
                      archiveId={traceArchiveId}
                      reserveBottomSpace
                    />
                  </Suspense>
                </div>
              )}

              {!isViewingTrace && !isLoadingTrace && hasStarted && !isBusy && !(isStarting && messages.length === 0) && !runJustFinished && (
                <div className="animate-fade-in-up flex h-full min-h-0 w-full min-w-0 flex-col items-stretch overflow-hidden lg:flex-row lg:gap-4">
                  {/* Execution log — full-bleed on mobile */}
                  <div className="h-full min-h-0 min-w-0 flex-1 lg:basis-0 lg:flex-[2.15]">
                    <Suspense fallback={<PanelFallback />}>
                      <ExecutionLog
                        messages={messages}
                        activeAgent={activeAgent}
                        selectedAgent={selectedAgent}
                        onAgentSelect={setSelectedAgent}
                        isRunning={isRunning}
                        onRevert={handleRevertRequest}
                        reserveBottomSpace
                        className="max-lg:rounded-none max-lg:border-0 max-lg:shadow-none"
                      />
                    </Suspense>
                  </div>
                  {/* Side panels — desktop only; mobile uses compact Ctx chip in the input bar */}
                  <div className="hidden min-w-0 shrink-0 lg:flex lg:h-full lg:min-w-[20rem] lg:basis-0 lg:flex-[1] lg:flex-col">
                    <Suspense fallback={null}>
                      <div className="flex h-full flex-col gap-4">
                        <TokenTrackerPanel contextUsage={contextUsage} className="h-fit shrink-0" />
                        <WorkspaceImpactMap messages={messages} className="min-h-0 flex-1" />
                      </div>
                    </Suspense>
                  </div>
                </div>
              )}
            </div>
        </div>

        {/* Input Area - only show on dashboard, hide while loading trace */}
        {activeTab === 'dashboard' && !isLoadingTrace && (
          <DynamicInput
            onSend={handleSend}
            onCancel={handleCancelClick}
            onPlanConfirm={handlePlanConfirm}
            onPlanDecline={handlePlanDecline}
            onPlanAdjust={handlePlanAdjust}
            onResume={() => setShowResumeConfirm(true)}
            onResumeWithMessage={handleResumeFromCheckpoint}
            onStartFresh={() => setShowFreshConfirm(true)}
            onClearArchive={() => setShowClearArchiveConfirm(true)}
            onEmptySubmit={() => setShowEmptySubmitConfirm(true)}
            hasStarted={hasStarted}
            isRunning={isRunning}
            isAwaitingPlanConfirmation={isAwaitingPlanConfirmation && !isBusy}
            hasCheckpoint={showCheckpointResumeUi}
            isErrorInterrupted={hasInterruptedError && !hasCheckpoint}
            allowResumeSteering={canResumeWithSteering}
            isInterrupting={isInterrupting}
            hasArchive={hasArchive && !archiveLandingDismissed}
            archiveCount={archiveCount}
            currentPrompt={currentPrompt}
            value={inputValue}
            onChange={setInputValue}
            isStarting={isStarting}
            isInitializing={isBusy && !isInterrupting}
            justLoadedCheckpoint={
              (initialCheckDone && hasCheckpoint && hasStarted && !isRetrievingCheckpoint && !isInitializing) ||
              hasInterruptedError ||
              isInterrupting
            }
            runJustFinished={runJustFinished}
            isViewingTrace={isViewingTrace}
            traceInput={traceInput}
            traceArchiveId={traceArchiveId}
            onExitTrace={handleExitTrace}
            contextUsage={contextUsage}
          />
        )}

      </main>

      {/* Cancel Confirmation Modal */}
      <ConfirmModal
        isOpen={showCancelModal}
        title="Stop Execution?"
        message="This will terminate the current computation. You may be able to resume from a checkpoint if one exists."
        confirmText="Stop"
        cancelText="Continue Running"
        variant="danger"
        onConfirm={handleConfirmCancel}
        onCancel={() => setShowCancelModal(false)}
      />

      {/* Resume Confirmation Modal */}
      <ConfirmModal
        isOpen={showResumeConfirm}
        title={hasCheckpoint ? "Resume from Checkpoint?" : "Continue Run?"}
        message={
          hasCheckpoint
            ? "Would you like to continue from where you left off? Previous history will be preserved."
            : "Retry your request using the current settings?"
        }
        confirmText={hasCheckpoint ? "Resume" : "Continue"}
        cancelText="Cancel"
        variant="info"
        onConfirm={handleResumeFromCheckpoint}
        onCancel={() => setShowResumeConfirm(false)}
      />

      {/* Start Fresh Confirmation Modal */}
      <ConfirmModal
        isOpen={showFreshConfirm}
        title="Start Fresh?"
        message={isStrategistStageCheckpoint
          ? "This will clear the strategist checkpoint and keep workspace files unchanged. Previous run history in the archive will be preserved."
          : "This will permanently delete the current workspace and checkpoint. Previous run history in the archive will be preserved."
        }
        confirmText="Start Fresh"
        cancelText="Keep Existing"
        variant="danger"
        onConfirm={handleStartFreshConfirm}
        onCancel={() => setShowFreshConfirm(false)}
      />

      {/* Clear Archive Confirmation Modal */}
      <ConfirmModal
        isOpen={showClearArchiveConfirm}
        title="Clear All History?"
        message="This will permanently delete all previous run archives and the current workspace. This action cannot be undone."
        confirmText="Clear Everything"
        cancelText="Keep archives"
        variant="danger"
        onConfirm={handleClearArchiveConfirm}
        onCancel={() => setShowClearArchiveConfirm(false)}
      />

      {/* Empty Submit Confirmation Modal */}
      <ConfirmModal
        isOpen={showEmptySubmitConfirm}
        title="Auto-Improve Previous Results?"
        message="Submit without a new request? The system will attempt to automatically improve the previous results based on its evaluation."
        confirmText="Auto-Improve"
        cancelText="Cancel"
        variant="info"
        onConfirm={handleEmptySubmitConfirm}
        onCancel={() => setShowEmptySubmitConfirm(false)}
      />

      {/* Revert Confirmation Modal */}
      <ConfirmModal
        isOpen={showRevertConfirm}
        title="Revert to Earlier Task?"
        message={`This will restore the checkpoint to the start of Task ${revertTargetTask}. All progress after this point will be permanently deleted. This action cannot be undone.`}
        confirmText="Revert"
        cancelText="Cancel"
        variant="danger"
        onConfirm={handleRevertConfirm}
        onCancel={() => setShowRevertConfirm(false)}
      />

      {/* Cleanup/Archiving Overlay - blocks all interaction during workspace cleanup */}
      <CleanupOverlay isVisible={isCleaningUp} />

      {/* Revert Overlay - blocks all interaction during revert operation */}
      <RevertOverlay isVisible={isReverting} targetTask={revertTargetTask ?? undefined} />

      {/* Fresh Start / Clear Archive Overlay */}
      <FreshStartOverlay
        isVisible={isResetting || isClearingArchiveLoading}
        isClearingArchive={isClearingArchiveLoading}
        preserveWorkspace={isResetting && isStrategistStageCheckpoint}
      />
    </GlassLayout>
    </NavigationProvider>
  );
}

export default App;
