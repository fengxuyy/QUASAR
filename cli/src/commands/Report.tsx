import React from 'react';
import { Box, Text, useApp, useInput, useStdout } from 'ink';
import { loadReport, normalizeReportCommand, reportCommandHelp } from '../utils/reportFiles.js';
import { ReportPanel } from '../ui/Run/renderers/index.js';
import { cliTheme } from '../ui/theme.js';

interface ReportProps {
    args: string[];
}

const Report: React.FC<ReportProps> = ({ args }) => {
    const { exit } = useApp();
    const { stdout } = useStdout();
    const terminalWidth = stdout?.columns || 100;
    const availableWidth = Math.max(20, terminalWidth - 14);
    const leftMargin = Math.max(0, Math.floor((terminalWidth - availableWidth) / 2));
    const kind = normalizeReportCommand(args[0]);

    useInput((input, key) => {
        if ((key.ctrl && input === 'c') || input === '\x04' || input === 'q') {
            exit();
        }
    }, { isActive: true });

    if (!kind) {
        return (
            <Box flexDirection="column" marginLeft={leftMargin} paddingX={1}>
                <Text color={cliTheme.ink.danger}>Unknown report command.</Text>
                <Text dimColor>Available: {reportCommandHelp()}</Text>
            </Box>
        );
    }

    const report = loadReport(kind);

    return (
        <Box flexDirection="column">
            <ReportPanel
                id={`report-${kind}`}
                title={report.title}
                content={report.error ? `${report.content}\n\n${report.error}` : report.content}
                sourcePath={report.sourcePath}
                isError={Boolean(report.error)}
                leftMargin={leftMargin}
                terminalWidth={terminalWidth}
                availableWidth={availableWidth}
            />
            <Box marginLeft={leftMargin} paddingX={1} marginTop={1}>
                <Text dimColor>q / Ctrl+C / Ctrl+D exit</Text>
            </Box>
        </Box>
    );
};

export default Report;
