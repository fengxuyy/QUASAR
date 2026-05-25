import React from 'react';
import { Box, Text, useApp, useInput, useStdout } from 'ink';
import fs from 'fs';
import path from 'path';
import { spawnSync } from 'child_process';
import { cleanTaskDescription } from '../utils/stateHelpers.js';
import { buildCommittedTimelineItems } from '../handlers/checkpointHandler.js';
import StaticItemRenderer from '../ui/Run/StaticItemRenderer.js';
import type { CommittedItem } from '../hooks/types.js';
import { cliTheme } from '../ui/theme.js';

interface HistoryProps {
    args: string[];
}

interface HistoryData {
    plan?: string[];
    total_tasks?: number;
    current_task?: number;
    completed_steps?: any[];
    ordered_items_by_task?: Record<string, any[]>;
    operator_items_by_task?: Record<string, any[]>;
    evaluator_items_by_task?: Record<string, any[]>;
    step_results?: Record<string, string>;
    strategist_items?: any[];
}

const WORKSPACE_DIR = process.env.WORKSPACE_DIR || '/workspace';

function resolveBridgePath(): string | null {
    const fromEnv = process.env.QUASAR_BRIDGE_PATH;
    if (fromEnv && fs.existsSync(fromEnv)) return fromEnv;

    const candidates = [
        path.resolve(process.cwd(), '../bridge.py'),
        path.resolve(process.cwd(), 'bridge.py'),
        '/app/bridge.py'
    ];

    for (const candidate of candidates) {
        if (fs.existsSync(candidate)) return candidate;
    }
    return null;
}

function loadCheckpointHistory(): { history: HistoryData | null; error: string | null } {
    const bridgePath = resolveBridgePath();
    if (!bridgePath) {
        return { history: null, error: 'Could not find bridge.py.' };
    }

    const script = `
import json
import traceback
import sys

try:
    from src.checkpoint import checkpoint_file_exists, get_thread_config, create_checkpoint_infrastructure
    if not checkpoint_file_exists():
        print(json.dumps({"ok": False, "error": "No checkpoint found. Run quasar first or resume an interrupted session."}))
        sys.exit(0)

    from src.llm_config import initialize_llm
    from src.graph import build_graph
    from bridge_history import extract_checkpoint_history

    llm, _ = initialize_llm()
    graph_builder = build_graph(llm)
    graph = create_checkpoint_infrastructure(graph_builder)
    config = get_thread_config()
    state = graph.get_state(config)
    state_history = list(graph.get_state_history(config))

    history = None
    if state and state.values:
        is_replan = state.values.get("is_replanning", False)
        history = extract_checkpoint_history(
            state.values,
            state.values.get("messages", []),
            is_replan=is_replan,
            state_history=state_history,
        )

    print(json.dumps({"ok": True, "history": history}))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e), "traceback": traceback.format_exc()}))
`;

    const result = spawnSync('python3', ['-c', script], {
        cwd: path.dirname(bridgePath),
        env: { ...process.env },
        encoding: 'utf-8'
    });

    if (result.error) {
        return { history: null, error: result.error.message };
    }

    try {
        const lines = result.stdout
            .split('\n')
            .map(line => line.trim())
            .filter(Boolean);
        const payload = JSON.parse(lines[lines.length - 1] || '{}');
        if (!payload.ok) {
            return { history: null, error: payload.error || 'Failed to load checkpoint history.' };
        }
        return { history: payload.history || null, error: null };
    } catch {
        const stderr = result.stderr?.trim();
        return { history: null, error: stderr || 'Failed to parse checkpoint history output.' };
    }
}

function getAvailableTaskNumbers(history: HistoryData): number[] {
    const taskNumbers = new Set<number>();
    const addTaskIndex = (value: unknown) => {
        const idx = Number(value);
        if (Number.isInteger(idx) && idx >= 0) {
            taskNumbers.add(idx + 1);
        }
    };

    for (let i = 0; i < (history.total_tasks || 0); i++) {
        taskNumbers.add(i + 1);
    }
    for (let i = 0; i < (history.plan?.length || 0); i++) {
        taskNumbers.add(i + 1);
    }

    Object.keys(history.ordered_items_by_task || {}).forEach(addTaskIndex);
    Object.keys(history.operator_items_by_task || {}).forEach(addTaskIndex);
    Object.keys(history.evaluator_items_by_task || {}).forEach(addTaskIndex);
    Object.keys(history.step_results || {}).forEach(addTaskIndex);

    return Array.from(taskNumbers).sort((a, b) => a - b);
}

function isTaskCompleted(history: HistoryData, taskNum: number): boolean {
    const completedCount = history.completed_steps?.length || 0;
    return taskNum <= completedCount || history.step_results?.[String(taskNum - 1)] != null;
}

const History: React.FC<HistoryProps> = ({ args: _args }) => {
    const { exit } = useApp();
    const { stdout } = useStdout();
    const terminalWidth = stdout?.columns || 100;
    const availableWidth = Math.max(20, terminalWidth - 14);
    const leftMargin = Math.max(0, Math.floor((terminalWidth - availableWidth) / 2));
    const listPanelWidth = Math.max(36, Math.min(availableWidth, 90));
    const listInnerWidth = Math.max(20, listPanelWidth - 4);
    const rule = '─'.repeat(listPanelWidth);

    const { history, error } = React.useMemo(() => loadCheckpointHistory(), []);
    const [selectedTaskNum, setSelectedTaskNum] = React.useState<number | null>(null);
    const [cursorIndex, setCursorIndex] = React.useState(0);

    if (error) {
        return (
            <Box flexDirection="column" padding={1}>
                <Text color={cliTheme.ink.danger}>Failed to load history</Text>
                <Text dimColor>{error}</Text>
            </Box>
        );
    }

    if (!history) {
        return (
            <Box flexDirection="column" padding={1}>
                <Text color={cliTheme.ink.warning}>No checkpoint history available.</Text>
            </Box>
        );
    }

    const availableTasks = getAvailableTaskNumbers(history);
    const isSelectorMode = selectedTaskNum === null;

    useInput((input, key) => {
        if ((key.ctrl && input === 'c') || input === '\x04') {
            exit();
            return;
        }

        if (isSelectorMode && availableTasks.length > 0) {
            if (key.upArrow) {
                setCursorIndex(prev => (prev <= 0 ? availableTasks.length - 1 : prev - 1));
                return;
            }

            if (key.downArrow) {
                setCursorIndex(prev => (prev + 1) % availableTasks.length);
                return;
            }

            if (key.return) {
                const selected = availableTasks[cursorIndex];
                if (selected) setSelectedTaskNum(selected);
            }
            return;
        }

        if (selectedTaskNum !== null && key.escape) {
            setSelectedTaskNum(null);
        }
    }, { isActive: true });

    if (isSelectorMode) {
        return (
            <Box flexDirection="column" marginLeft={leftMargin} paddingX={1}>
                <Text color={cliTheme.ink.primary}>{rule}</Text>
                <Text bold color={cliTheme.ink.primary}>QUASAR History</Text>
                <Text color={cliTheme.ink.primary}>{rule}</Text>
                {availableTasks.length === 0 ? (
                    <Text color={cliTheme.ink.warning}>No task history found in checkpoint.</Text>
                ) : (
                    <Box flexDirection="column" marginTop={1}>
                        <Text color={cliTheme.ink.success} bold>Select a task</Text>
                        {availableTasks.map((taskNum, idx) => (
                            <Text key={taskNum}>
                                {idx === cursorIndex ? <Text color={cliTheme.ink.primary} bold>❯ </Text> : <Text dimColor>  </Text>}
                                <Text>{`task_${taskNum}`.padEnd(Math.min(18, Math.max(10, listInnerWidth - 20)))}</Text>
                                {isTaskCompleted(history, taskNum) ? (
                                    <Text color={cliTheme.ink.success}>completed</Text>
                                ) : (
                                    <Text color={cliTheme.ink.warning}>in progress</Text>
                                )}
                            </Text>
                        ))}
                    </Box>
                )}
                <Box marginTop={1} flexDirection="column">
                    <Text dimColor>↑/↓ move  •  Enter open</Text>
                    <Text dimColor>Ctrl+C / Ctrl+D exit</Text>
                </Box>
            </Box>
        );
    }

    const taskNumToShow = selectedTaskNum;

    if (!availableTasks.includes(taskNumToShow)) {
        return (
            <Box flexDirection="column" padding={1}>
                <Text color={cliTheme.ink.danger}>Task not found: task_{taskNumToShow}</Text>
                {availableTasks.length > 0 && (
                    <Text dimColor>Available: {availableTasks.map(n => `task_${n}`).join(', ')}</Text>
                )}
            </Box>
        );
    }

    const taskKey = String(taskNumToShow - 1);
    const orderedItems = history.ordered_items_by_task?.[taskKey] || [];
    const fallbackItems = [
        ...(history.operator_items_by_task?.[taskKey] || []),
        ...(history.evaluator_items_by_task?.[taskKey] || [])
    ];
    const taskItemsRaw = orderedItems.length > 0 ? orderedItems : fallbackItems;
    const evalSummary = history.step_results?.[taskKey];
    const rawTask = history.plan?.[taskNumToShow - 1] || '';
    const taskDescription = rawTask ? cleanTaskDescription(rawTask) : '';

    const renderItems: CommittedItem[] = [];
    renderItems.push({
        id: `history-operator-header-${taskNumToShow}`,
        type: 'agent-header',
        content: 'operator',
        agentName: 'operator',
        taskNum: taskNumToShow
    });

    if (taskDescription) {
        renderItems.push({
            id: `history-task-panel-${taskNumToShow}`,
            type: 'active-task-panel',
            content: { description: taskDescription, taskNum: taskNumToShow },
            agentName: 'operator',
            taskNum: taskNumToShow
        });
    }

    renderItems.push(
        ...buildCommittedTimelineItems(taskItemsRaw, {
            idPrefix: `history-task${taskNumToShow}`,
            defaultAgentName: 'operator',
            taskNum: taskNumToShow
        })
    );

    if (evalSummary) {
        renderItems.push({
            id: `history-summary-${taskNumToShow}`,
            type: 'evaluation-summary',
            content: String(evalSummary),
            agentName: 'evaluator',
            taskNum: taskNumToShow
        });
    }

    return (
        <Box flexDirection="column">
            <Box marginLeft={leftMargin} paddingX={1} flexDirection="column" marginBottom={1}>
                <Text color={cliTheme.ink.primary}>{rule}</Text>
                <Text>
                    <Text bold color={cliTheme.ink.primary}>Task History</Text>
                    <Text> </Text>
                    <Text bold>{`task_${taskNumToShow}`}</Text>
                </Text>
                <Text color={cliTheme.ink.primary}>{rule}</Text>
            </Box>
            {renderItems.length <= (taskDescription ? 2 : 1) ? (
                <Box marginLeft={leftMargin} paddingX={1}>
                    <Text dimColor>No tool-call items captured for this task.</Text>
                </Box>
            ) : (
                renderItems.map(item => (
                    <StaticItemRenderer
                        key={item.id}
                        item={item}
                        leftMargin={leftMargin}
                        terminalWidth={terminalWidth}
                        availableWidth={availableWidth}
                    />
                ))
            )}
            <Box marginLeft={leftMargin} paddingX={1} marginTop={1}>
                <Text dimColor>ESC back • Ctrl+C / Ctrl+D exit</Text>
            </Box>
        </Box>
    );
};

export default History;
