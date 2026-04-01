#!/usr/bin/env node
import React from 'react';
import { render } from 'ink';
import meow from 'meow';
import { createRequire } from 'module';
import fs from 'fs';
import path from 'path';
import App from './app.js';
import { applyDefaultEnv, resolveWorkspaceDir } from './utils/envDefaults.js';

const require = createRequire(import.meta.url);
const { version: packageVersion } = require('../package.json');
const rawArgs = process.argv.slice(2);
const removedLongFlags = new Set([
	'--web',
]);
const allowedLongFlags = new Set([
	'--help',
	'--version',
	'--resume',
	'--clear',
	'--fresh',
	'--history',
	'--config',
	'--info',
	'--no-rag',
]);

for (const arg of rawArgs) {
	if (!arg.startsWith('--') || arg === '--') {
		continue;
	}

	const flagName = arg.split('=')[0];
	if (removedLongFlags.has(flagName)) {
		console.error('\x1b[31m✗ Web UI Removed\x1b[0m');
		console.error('\x1b[90mBrowser-based web support is no longer available.\x1b[0m');
		console.error('\x1b[90mUse `quasar` for the interactive CLI or pass a prompt for headless runs.\x1b[0m');
		process.exit(1);
	}
	if (!allowedLongFlags.has(flagName)) {
		console.error('\x1b[31m✗ Unknown Flag\x1b[0m');
		console.error(`\x1b[90m${flagName} is not a supported option.\x1b[0m`);
		console.error('\x1b[90mRun `quasar --help` to see available flags.\x1b[0m');
		process.exit(1);
	}
}

// Apply default environment variables early so they are available everywhere
applyDefaultEnv();

const cli = meow(
	`
	Usage
	  $ quasar [prompt]
	  $ quasar --resume
	  $ quasar --clear
	  $ quasar --fresh
	  $ quasar --history
	  $ quasar --config [show|validate]
	  $ quasar --info
	  $ quasar --version
	
	Options
	  --resume    Resume from the active checkpoint
	  --clear     Clear the active checkpoint and current workspace state
	  --fresh     Clear everything, including archived runs
	  --history   Show per-task run history
	  --config    Configuration management commands
	  --info      Show system information
	  --version   Show version information
	  --no-rag    Disable RAG functionality (run)

	Examples
	  $ quasar
	  $ quasar "Calculate bandgap"
	  $ quasar --resume
	  $ quasar --clear
	  $ quasar --fresh
	  $ quasar --history
	  $ quasar --config validate
`,
	{
		importMeta: import.meta,
		version: packageVersion,
		flags: {
			resume: {
				type: 'boolean',
				shortFlag: 'r',
			},
			clear: {
				type: 'boolean',
			},
			fresh: {
				type: 'boolean',
			},
			history: {
				type: 'boolean',
			},
			config: {
				type: 'boolean',
			},
			info: {
				type: 'boolean',
			},
			noRag: {
				type: 'boolean',
			},
		},
	},
);

const resumeFromFlag = Boolean(cli.flags.resume);
if (resumeFromFlag) {
	process.env.IF_RESTART = 'true';
}
cli.flags.restart = resumeFromFlag;

const commandFlags = [
	{ flag: 'clear', command: 'clear' },
	{ flag: 'fresh', command: 'fresh' },
	{ flag: 'history', command: 'history' },
	{ flag: 'config', command: 'config' },
	{ flag: 'info', command: 'info' },
] as const;

const selectedCommands = commandFlags.filter(({ flag }) => Boolean(cli.flags[flag]));
if (selectedCommands.length > 1) {
	console.error('\x1b[31m✗ Conflicting Commands\x1b[0m');
	console.error('\x1b[90mUse only one command flag at a time.\x1b[0m');
	process.exit(1);
}

let command: string = selectedCommands[0]?.command || 'run';
let args = cli.input;

// Track if headless mode is forced (e.g., restart with direct args)
let forceHeadless = false;

// Early checks for run command
if (command === 'run') {
	const restartFromEnv = ['true', '1', 'yes', 'on'].includes((process.env.IF_RESTART || '').toLowerCase());
	const isRestart = restartFromEnv || resumeFromFlag;
	const workspaceDir = resolveWorkspaceDir();
	const checkpointPath = path.join(workspaceDir, 'checkpoints.sqlite');
	const hasCheckpoint = fs.existsSync(checkpointPath);
	const resumeSource = resumeFromFlag ? '--resume' : 'IF_RESTART=True';

	if (resumeFromFlag) {
		forceHeadless = true;
	}
	
	// Case 1: resume requested but no checkpoint exists
	if (isRestart && !hasCheckpoint) {
		console.error('\x1b[31m✗ No Checkpoint to Resume\x1b[0m');
		console.error(`\x1b[90m${resumeSource} was set, but no checkpoint found.\x1b[0m`);
		console.error('\x1b[90mRun `quasar` with a new prompt to start a new run.\x1b[0m');
		process.exit(1);
	}
	
	// Case 2: resume requested with direct args - warn and ignore the prompt
	if (isRestart && args.length > 0) {
		console.warn('\x1b[33m⚠ Warning: Prompt Ignored\x1b[0m');
		console.warn(`\x1b[90m${resumeSource} is set - the provided prompt will be ignored.\x1b[0m`);
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
		console.error('\x1b[90mUse `quasar --resume` to continue, or run `quasar --clear` to start fresh.\x1b[0m');
		process.exit(1);
	}
}

// Determine if we're in non-interactive mode (direct prompt passed or forced by resume flow)
const isHeadless = command === 'run' && (args.length > 0 || forceHeadless);

if (isHeadless) {
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
