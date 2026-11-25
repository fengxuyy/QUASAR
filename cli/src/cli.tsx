#!/usr/bin/env node
import React from 'react';
import { render } from 'ink';
import meow from 'meow';
import { createRequire } from 'module';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import App from './app.js';
import { applyDefaultEnv, checkpointDbPath, resolveWorkspaceDir } from './utils/envDefaults.js';
import { normalizeReportCommand, reportCommandHelp } from './utils/reportFiles.js';
import { parseCliCommand } from './utils/commandRegistry.js';

const require = createRequire(import.meta.url);
const { version: packageVersion } = require('../package.json');
const rawArgs = process.argv.slice(2);

const allowedLongFlags = new Set([
	'--help',
	'--version',
	'--resume',
	'--clear',
	'--fresh',
	'--history',
	'--config',
	'--info',
	'--web',
	'--no-rag',
]);

for (const arg of rawArgs) {
	if (!arg.startsWith('--') || arg === '--') {
		continue;
	}

	const flagName = arg.split('=')[0];
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
	  $ quasar --web
	  $ quasar \\execution-overview
	  $ quasar \\usage-report
	  $ quasar \\revert <task>
	  $ quasar --version
	
	Options
	  --resume    Resume from the active checkpoint
	  --clear     Clear the active checkpoint and current workspace state
	  --fresh     Clear everything, including archived runs
	  --history   Show per-task run history
	  --config    Configuration management commands
	  --info      Show system information
	  --web       Launch the QUASAR Web UI
	  --version   Show version information
	  --no-rag    Disable RAG functionality (run)

	Backslash Commands
	  ${reportCommandHelp()}   Show local run reports
	  \\revert <task>          Revert checkpoint/workspace to a task

	Examples
	  $ quasar
	  $ quasar "Calculate bandgap"
	  $ quasar --resume
	  $ quasar --resume "Use a longer check-in interval before deciding again"
	  $ quasar --clear
	  $ quasar --fresh
	  $ quasar --history
	  $ quasar --web
	  $ quasar \\usage-report
	  $ quasar \\revert 2
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
			web: {
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
	{ flag: 'web', command: 'web' },
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
const reportKind = command === 'run' && args.length === 1 ? normalizeReportCommand(args[0]) : null;
if (reportKind) {
	command = 'report';
	args = [reportKind];
}
const inlineCliCommand = command === 'run' ? parseCliCommand(args.join(' ')) : null;

// Early checks for run command
if (command === 'run') {
	const restartFromEnv = ['true', '1', 'yes', 'on'].includes((process.env.IF_RESTART || '').toLowerCase());
	const isRestart = restartFromEnv || resumeFromFlag;
	const workspaceDir = resolveWorkspaceDir();
	const checkpointPath = checkpointDbPath(workspaceDir);
	const hasCheckpoint = fs.existsSync(checkpointPath);
	const resumeSource = resumeFromFlag ? '--resume' : 'IF_RESTART=True';

	// Case 1: resume requested but no checkpoint exists
	if (isRestart && !hasCheckpoint) {
		console.error('\x1b[31m✗ No Checkpoint to Resume\x1b[0m');
		console.error(`\x1b[90m${resumeSource} was set, but no checkpoint found.\x1b[0m`);
		console.error('\x1b[90mRun `quasar` with a new prompt to start a new run.\x1b[0m');
		process.exit(1);
	}
	
	// Case 2: Direct args with existing checkpoint but IF_RESTART=False
	if (!isRestart && args.length > 0 && hasCheckpoint && !inlineCliCommand) {
		console.error('\x1b[31m✗ Cannot Start New Run\x1b[0m');
		console.error('\x1b[90mCheckpoint exists from a previous interrupted run.\x1b[0m');
		console.error('\x1b[90mUse `quasar --resume` to continue, or run `quasar --clear` to start fresh.\x1b[0m');
		process.exit(1);
	}
}

// Determine if we're in non-interactive mode (direct prompt passed)
const isHeadless = command === 'run' && args.length > 0 && !inlineCliCommand;

function firstExistingPath(paths: string[]): string | null {
	return paths.find(candidate => fs.existsSync(candidate)) || null;
}

function launchWebUi() {
	console.log('Starting QUASAR Web UI...');

	const cliFile = fileURLToPath(import.meta.url);
	const cliDir = path.dirname(cliFile);
	const configuredServer = (process.env.QUASAR_WEB_SERVER_ENTRY || '').trim();
	const possibleCompiledServers = [
		configuredServer,
		'/app/web/dist-server/index.js',
		path.join(process.cwd(), 'web/dist-server/index.js'),
		path.join(cliDir, '../../web/dist-server/index.js'),
	].filter(Boolean);
	const possibleSourceServers = [
		path.join(process.cwd(), 'web/server/index.ts'),
		path.join(cliDir, '../../web/server/index.ts'),
	];

	const compiledServer = firstExistingPath(possibleCompiledServers);
	const sourceServer = firstExistingPath(possibleSourceServers);
	let launchCommand = 'node';
	let launchArgs: string[];
	let serverScript: string;

	if (compiledServer) {
		serverScript = compiledServer;
		launchArgs = [serverScript];
	} else {
		if (!sourceServer) {
			console.error('\x1b[31m✗ Web UI Server Not Found\x1b[0m');
			console.error('\x1b[90mExpected web/dist-server/index.js or web/server/index.ts.\x1b[0m');
			console.error('\x1b[90mBuild the web app first, or run this command from the repository root.\x1b[0m');
			process.exit(1);
		}
		serverScript = sourceServer;
		console.log('Compiled web server not found, using the TypeScript source server.');

		const tsxBin = firstExistingPath([
			path.join(process.cwd(), 'web/node_modules/.bin/tsx'),
			path.join(cliDir, '../../web/node_modules/.bin/tsx'),
		]);

		if (tsxBin) {
			launchCommand = tsxBin;
			launchArgs = [serverScript];
		} else {
			launchCommand = 'npx';
			launchArgs = ['tsx', serverScript];
		}
	}

	console.log(`Launching Web UI server from ${serverScript}`);

	const webProcess = spawn(launchCommand, launchArgs, {
		stdio: 'inherit',
		env: {
			...process.env,
			NODE_ENV: 'production',
			SERVE_STATIC: 'true',
		},
	});

	webProcess.on('error', error => {
		console.error('\x1b[31m✗ Failed to Launch Web UI\x1b[0m');
		console.error(`\x1b[90m${error.message}\x1b[0m`);
		process.exit(1);
	});

	webProcess.on('close', code => {
		process.exit(code ?? 0);
	});
}

if (command === 'web') {
	launchWebUi();
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
