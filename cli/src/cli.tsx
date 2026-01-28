#!/usr/bin/env node
import React from 'react';
import { render } from 'ink';
import meow from 'meow';
import fs from 'fs';
import path from 'path';
import App from './app.js';

const cli = meow(
	`
	Usage
	  $ quasar [prompt]
	  $ quasar <command> [options]
	
	Commands
	  config      Configuration management commands
	  checkpoint  Checkpoint management commands
	  info        Show system information
	  version     Show version information

	Options
	  --no-rag    Disable RAG functionality (run)
	  --restart   Resume from checkpoint (run)

	Examples
	  $ quasar
	  $ quasar "Calculate bandgap"
	  $ quasar config show
`,
	{
		importMeta: import.meta,
		flags: {
			noRag: {
				type: 'boolean',
			},
			restart: {
				type: 'boolean',
				shortFlag: 'r',
			},
			web: {
				type: 'boolean',
			},
		},
	},
);

const knownCommands = ['config', 'checkpoint', 'info', 'version'];
let command = cli.input[0];
let args = cli.input.slice(1);

if (!command) {
	// Default to run if no command provided
	command = 'run';
	args = [];
} else if (!knownCommands.includes(command)) {
	// If command is not known, treat it as the first argument to run
	args = [command, ...args];
	command = 'run';
}

// Track if headless mode is forced (e.g., restart with direct args)
let forceHeadless = false;

// Early checks for run command
if (command === 'run') {
	const restartFromEnv = ['true', '1', 'yes', 'on'].includes((process.env.IF_RESTART || '').toLowerCase());
	const restartFromFlag = cli.flags.restart;
	const isRestart = restartFromEnv || restartFromFlag;
	const workspaceDir = process.env.WORKSPACE_DIR || '/workspace';
	const checkpointPath = path.join(workspaceDir, 'checkpoints.sqlite');
	const hasCheckpoint = fs.existsSync(checkpointPath);
	
	// Case 1: IF_RESTART=True but no checkpoint exists
	if (isRestart && !hasCheckpoint) {
		console.error('\x1b[31m✗ No Checkpoint to Resume\x1b[0m');
		console.error('\x1b[90mIF_RESTART=True but no checkpoint found.\x1b[0m');
		console.error('\x1b[90mSet IF_RESTART=False to start a new run.\x1b[0m');
		process.exit(1);
	}
	
	// Case 2: IF_RESTART=True with direct args - warn and ignore the prompt
	if (isRestart && args.length > 0) {
		console.warn('\x1b[33m⚠ Warning: Prompt Ignored\x1b[0m');
		console.warn('\x1b[90mIF_RESTART=True is set - the provided prompt will be ignored.\x1b[0m');
		console.warn('\x1b[90mResuming from checkpoint instead.\x1b[0m');
		console.warn('');
		// Mark for headless mode since a direct command was passed
		forceHeadless = true;
		// Clear args so it proceeds as a checkpoint resume
		args = [];
	}
	
	// Case 3: Direct args with existing checkpoint but IF_RESTART=False
	if (!isRestart && args.length > 0 && hasCheckpoint) {
		console.error('\x1b[31m✗ Cannot Start New Run\x1b[0m');
		console.error('\x1b[90mCheckpoint exists from a previous interrupted run.\x1b[0m');
		console.error('\x1b[90mSet IF_RESTART=True to resume, or run `quasar checkpoint delete` to start fresh.\x1b[0m');
		process.exit(1);
	}
}

// Determine if we're in non-interactive mode (direct prompt passed or forced by restart with direct args)
const isHeadless = command === 'run' && (args.length > 0 || forceHeadless);

// Handle --web flag
if (cli.flags.web) {
	console.log('Starting Quasar Web UI...');
	
	const { spawn } = await import('child_process'); // Dynamic import to avoid top-level require if ESM
    const path = await import('path');
    
    // Assume we are in /usr/local/bin or similar in Docker, need to find the web server
    // In Docker: /app/web/server/index.ts (run with tsx or node if compiled)
    // We'll try to find the web root
    
    // Strategy: Look for /app/web first (Docker standard)
    // Then try relative to this script
    
    // Strategy: Look for compiled server first (production/docker)
    // Then source file (dev)
    
    let command = 'node';
    let args: string[] = [];
    
    // Check for compiled server (Docker / Build)
    // In Docker: /app/web/dist-server/index.js
    
    // ESM safe __dirname
    const { fileURLToPath } = await import('url');
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = path.dirname(__filename);

    const possiblePaths = [
        '/app/web/dist-server/index.js',
        path.join(process.cwd(), 'web/dist-server/index.js'), // Run from root
        path.join(__dirname, '../../web/dist-server/index.js') // Run from cli/dist
    ];
    
    let serverScript = '';
    for (const p of possiblePaths) {
        if (fs.existsSync(p)) {
            serverScript = p;
            break;
        }
    }
    
    if (serverScript) {
        args = [serverScript];
    } else {
        // Fallback to tsx for dev
        console.log('Compiled server not found, falling back to tsx...');
        command = 'npx';
        const devScript = path.resolve(process.cwd(), 'web/server/index.ts');
        args = ['tsx', devScript];
        serverScript = devScript;
    }
    
    console.log(`Launching Web Server from ${serverScript}`);
    
    const webProcess = spawn(command, args, {
        stdio: 'inherit',
        env: {
            ...process.env,
            NODE_ENV: 'production',
            SERVE_STATIC: 'true'
        }
    });
    
    webProcess.on('close', (code) => {
        process.exit(code || 0);
    });
    
} else if (isHeadless) {
	// Use headless mode for direct prompts - simple console output
	import('./commands/HeadlessRun.js').then(({ runHeadless }) => {
		runHeadless(args.join(' '), cli.flags);
	});
} else {
	// Use full Ink UI for interactive mode
	render(<App command={command} args={args} flags={cli.flags} />, {
		exitOnCtrlC: false,
	});
}
