import React from 'react';
import { Text, Box } from 'ink';
import Run from './commands/Run.js';
import Config from './commands/Config.js';
import Checkpoint from './commands/Checkpoint.js';
import History from './commands/History.js';
import Info from './commands/Info.js';
import Report from './commands/Report.js';
import Banner from './ui/Banner.js';
import { cliTheme } from './ui/theme.js';

type AppProps = {
	command?: string;
	args: string[];
	flags: any;
};

const App: React.FC<AppProps> = ({ command, args, flags }) => {
	// If no command, show help (handled by meow usually, but we can show banner)
    if (!command) {
        return (
            <Box flexDirection="column">
                <Banner />
                <Text>Please specify a command. Run <Text color={cliTheme.ink.primary}>quasar --help</Text> for usage.</Text>
            </Box>
        );
    }

	switch (command) {
		case 'run':
			return <Run args={args} flags={flags} />;
		case 'clear':
			return <Checkpoint args={['clear', ...args]} />;
		case 'fresh':
			return <Checkpoint args={['fresh', ...args]} />;
		case 'config':
			return <Config args={args} />;
		case 'history':
			return <History args={args} />;
		case 'report':
			return <Report args={args} />;
		case 'info':
			return <Info />;
		case 'version':
			return (
                <Box flexDirection="column" padding={1}>
                    <Text>
                        <Text color={cliTheme.ink.primary} bold>QUASAR-CHEM</Text>{' '}
                        <Text dimColor>version</Text>{' '}
                        <Text color={cliTheme.ink.warning}>0.4.0 (Node.js)</Text>
                    </Text>
                </Box>
            );
		default:
			return (
				<Box flexDirection="column">
					<Text color={cliTheme.ink.danger}>Unknown command: {command}</Text>
                    <Text>Run <Text color={cliTheme.ink.primary}>quasar --help</Text> for usage.</Text>
				</Box>
			);
	}
};

export default App;
