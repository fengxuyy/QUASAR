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
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    red: '\x1b[31m',
    dim: '\x1b[2m',
    bold: '\x1b[1m',
    reset: '\x1b[0m',
};

function printBanner(): void {
    const model = process.env.MODEL || 'unknown';
    const pmgConfigured = !!process.env.PMG_MAPI_KEY;
    
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
    const separator = '─'.repeat(boxWidth);
    
    // Helper to pad line to exact width
    const padLine = (text: string) => text + ' '.repeat(Math.max(0, boxWidth - text.length));
    
    console.log('');
    console.log(`${colors.cyan}╭${'─'.repeat(boxWidth + 4)}╮${colors.reset}`);
    console.log(`${colors.cyan}│${' '.repeat(boxWidth + 4)}│${colors.reset}`);
    
    for (const line of logoLines) {
        console.log(`${colors.cyan}│  ${colors.bold}${padLine(line)}${colors.reset}${colors.cyan}  │${colors.reset}`);
    }
    
    console.log(`${colors.cyan}│${' '.repeat(boxWidth + 4)}│${colors.reset}`);
    
    // Center the subtitle
    const subtitlePadding = Math.floor((boxWidth - subtitle.length) / 2);
    const subtitleLine = ' '.repeat(subtitlePadding) + subtitle;
    console.log(`${colors.cyan}│  ${colors.reset}${padLine(subtitleLine)}${colors.cyan}  │${colors.reset}`);
    
    console.log(`${colors.cyan}│${' '.repeat(boxWidth + 4)}│${colors.reset}`);
    console.log(`${colors.cyan}│  ${colors.dim}${separator}${colors.reset}${colors.cyan}  │${colors.reset}`);
    
    const modelLine = `Model: ${model}`;
    console.log(`${colors.cyan}│  ${colors.dim}Model: ${colors.reset}${colors.cyan}${model}${' '.repeat(Math.max(0, boxWidth - modelLine.length))}${colors.cyan}  │${colors.reset}`);
    
    if (pmgConfigured) {
        const mpLine = 'Materials Project API: Configured';
        console.log(`${colors.cyan}│  ${colors.dim}Materials Project API: ${colors.reset}${colors.green}Configured${' '.repeat(Math.max(0, boxWidth - mpLine.length))}${colors.cyan}  │${colors.reset}`);
    }
    
    console.log(`${colors.cyan}│  ${colors.dim}${separator}${colors.reset}${colors.cyan}  │${colors.reset}`);
    console.log(`${colors.cyan}│${' '.repeat(boxWidth + 4)}│${colors.reset}`);
    console.log(`${colors.cyan}╰${'─'.repeat(boxWidth + 4)}╯${colors.reset}`);
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
        env: { ...process.env }
    });

    let runCompleted = false;

    child.stdout.on('data', (data) => {
        const lines = data.toString().split('\n');
        for (const line of lines) {
            if (!line.trim()) continue;
            try {
                const msg = JSON.parse(line);
                
                // Handle different message types
                if (msg.type === 'model_name') {
                    // Model info received
                } else if (msg.type === 'rag_status') {
                    if (msg.payload?.status === 'done') {
                        printSuccess('RAG initialized');
                    }
                } else if (msg.type === 'system_ready') {
                    // Don't print anything for system ready, print "System Running..." instead
                    printStatus('System Running...');
                    // Send the prompt
                    const restartFromEnv = ['true', '1', 'yes', 'on'].includes((process.env.IF_RESTART || '').toLowerCase());
                    child.stdin.write(JSON.stringify({ 
                        command: 'prompt', 
                        content: prompt, 
                        restart: flags.restart || restartFromEnv 
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
