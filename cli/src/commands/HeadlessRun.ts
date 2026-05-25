/**
 * Headless Run - Non-interactive mode for direct prompt execution
 * Uses simple console output instead of Ink UI components
 */
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';

// ANSI color codes
const colors = {
    cyan: '\x1b[36m',
    blue: '\x1b[34m',
    purple: '\x1b[35m',
    accent: '\x1b[38;5;141m',
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    red: '\x1b[31m',
    dim: '\x1b[2m',
    bold: '\x1b[1m',
    reset: '\x1b[0m',
};

function printBanner(): void {
    // Same ASCII logo as Banner.tsx - ensure all lines have same length
    const logoLines = [
        '    ██████    █████  █████   █████████    █████████    █████████   ███████████',
        '  ███░░░░███ ░░███  ░░███   ███░░░░░███  ███░░░░░███  ███░░░░░███ ░░███░░░░░███',
        ' ███    ░░███ ░███   ░███  ░███    ░███ ░███    ░░░  ░███    ░███  ░███    ░███',
        '░███     ░███ ░███   ░███  ░███████████ ░░█████████  ░███████████  ░██████████ ',
        '░███   ██░███ ░███   ░███  ░███░░░░░███  ░░░░░░░░███ ░███░░░░░███  ░███░░░░░███',
        '░░███ ░░████  ░███   ░███  ░███    ░███  ███    ░███ ░███    ░███  ░███    ░███',
        ' ░░░██████░██ ░░████████   █████   █████░░█████████  █████   █████ █████   █████',
        '   ░░░░░░ ░░   ░░░░░░░░   ░░░░░   ░░░░░  ░░░░░░░░░  ░░░░░   ░░░░░ ░░░░░   ░░░░░'
    ];
    
    // Find the maximum line length and use it as the box width
    const maxLen = Math.max(...logoLines.map(l => l.length));
    const boxWidth = maxLen;
    
    const subtitle = 'Quantum Universal Autonomous System for Atomistic Research';
    const version = 'v0.4.0';
    
    // Helper to pad line to exact width
    const padLine = (text: string) => text + ' '.repeat(Math.max(0, boxWidth - text.length));
    
    console.log('');
    const borderColor = colors.accent;
    console.log(`${borderColor}╭${'─'.repeat(boxWidth + 4)}╮${colors.reset}`);
    console.log(`${borderColor}│${' '.repeat(boxWidth + 4)}│${colors.reset}`);
    
    for (let i = 0; i < logoLines.length; i++) {
        console.log(`${borderColor}│  ${colors.accent}${colors.bold}${padLine(logoLines[i])}${colors.reset}${borderColor}  │${colors.reset}`);
    }
    
    console.log(`${borderColor}│${' '.repeat(boxWidth + 4)}│${colors.reset}`);
    
    // Center the subtitle
    const subtitlePadding = Math.floor((boxWidth - subtitle.length) / 2);
    const subtitleLine = ' '.repeat(subtitlePadding) + subtitle;
    console.log(`${borderColor}│  ${colors.accent}${colors.bold}✦${colors.reset} ${padLine(subtitleLine).slice(2)}${borderColor}  │${colors.reset}`);
    
    // Center the version
    const versionPadding = Math.floor((boxWidth - version.length) / 2);
    const versionLine = ' '.repeat(versionPadding) + version;
    console.log(`${borderColor}│  ${colors.dim}${padLine(versionLine)}${borderColor}  │${colors.reset}`);
    
    console.log(`${borderColor}│${' '.repeat(boxWidth + 4)}│${colors.reset}`);
    console.log(`${borderColor}╰${'─'.repeat(boxWidth + 4)}╯${colors.reset}`);
    console.log('');
}

function printStatus(message: string): void {
    console.log(`${colors.cyan}▶${colors.reset} ${message}`);
}

function printSuccess(message: string): void {
    console.log(`${colors.green}✓${colors.reset} ${message}`);
}

function printError(message: string): void {
    console.log(`${colors.red}✗${colors.reset} ${message}`);
}

export function runHeadless(prompt: string, flags: any): void {
    printBanner();
    printStatus('Initializing...');

    const restartFromEnv = ['true', '1', 'yes', 'on'].includes((process.env.IF_RESTART || '').toLowerCase());
    const isResume = Boolean(flags.resume || flags.restart || restartFromEnv);
    
    // Find bridge.py
    let bridgePath: string | undefined;
    const candidates = [
        path.resolve(process.cwd(), '../bridge.py'),
        path.resolve(process.cwd(), 'bridge.py'),
        '/app/bridge.py'
    ];
    for (const p of candidates) {
        if (fs.existsSync(p)) {
            bridgePath = p;
            break;
        }
    }
    
    if (!bridgePath) {
        printError('Could not find bridge.py');
        process.exit(1);
    }

    const child = spawn('python3', [bridgePath], {
        cwd: path.dirname(bridgePath),
        stdio: ['pipe', 'pipe', 'pipe'],
        env: {
            ...process.env,
            IF_RESTART: isResume ? 'true' : (process.env.IF_RESTART || 'false')
        }
    });

    let runCompleted = false;
    let stdoutBuffer = '';

    child.stdout.on('data', (data) => {
        stdoutBuffer += data.toString();
        const lines = stdoutBuffer.split('\n');
        stdoutBuffer = lines.pop() || '';
        for (const line of lines) {
            if (!line.trim()) continue;
            try {
                const msg = JSON.parse(line);
                
                // Handle different message types
                if (msg.type === 'model_name') {
                    // Model info received
                } else if (msg.type === 'init') {
                    // Check if model initialized successfully
                    if (!msg.payload?.model) {
                        const warning = msg.payload?.warning || 'MODEL and MODEL_API_KEY environment variables are required.';
                        printError(`Model not configured: ${warning}`);
                        child.stdin.end();
                        process.exit(1);
                    }
                } else if (msg.type === 'rag_status') {
                    if (msg.payload?.status === 'done') {
                        printSuccess('RAG initialized');
                    }
                } else if (msg.type === 'plan_awaiting_confirm') {
                    child.stdin.write(JSON.stringify({ command: 'plan_confirm', action: 'confirm', feedback: '' }) + '\n');
                } else if (msg.type === 'system_ready') {
                    // Don't print anything for system ready, print "System Running..." instead
                    printStatus('System Running...');
                    // Resume reuses the existing checkpoint. A direct prompt becomes steering text.
                    child.stdin.write(JSON.stringify({
                        command: 'prompt',
                        content: prompt,
                        restart: false
                    }) + '\n');
                } else if (msg.type === 'agent_event') {
                    // Don't print agent events in headless mode - keep it minimal
                } else if (msg.type === 'done' || msg.type === 'final_summary') {
                    // Run completed - print success and terminate
                    if (!runCompleted) {
                        runCompleted = true;
                        printSuccess('Run Complete');
                        // Send exit command and close stdin to signal Python to exit
                        try {
                            child.stdin.write(JSON.stringify({ command: 'exit' }) + '\n');
                        } catch (e) {
                            // stdin might already be closed
                        }
                        child.stdin.end();
                        // Exit after a brief delay to allow cleanup
                        setTimeout(() => {
                            process.exit(0);
                        }, 100);
                    }
                } else if (msg.type === 'error') {
                    printError(msg.payload?.message || 'Unknown error');
                }
            } catch (e) {
                // Non-JSON output - ignore in headless mode
            }
        }
    });

    child.stderr.on('data', (data) => {
        // Log errors to stderr - but suppress verbose output
        const errStr = data.toString().trim();
        // Only log critical errors, suppress warnings and info
        if (errStr && (errStr.includes('Error') || errStr.includes('error') || errStr.includes('Traceback'))) {
            console.error(`${colors.dim}${errStr}${colors.reset}`);
        }
    });

    child.on('close', (code) => {
        if (!runCompleted) {
            if (code === 0) {
                printSuccess('Run Complete');
            } else {
                printError(`Process exited with code ${code}`);
            }
        }
        process.exit(code || 0);
    });

    child.on('error', (err) => {
        printError(`Bridge error: ${err.message}`);
        process.exit(1);
    });
}
