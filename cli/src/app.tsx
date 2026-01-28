import React from 'react';
import { Text, Box } from 'ink';
import Run from './commands/Run.js';
import Config from './commands/Config.js';
import Checkpoint from './commands/Checkpoint.js';
import Info from './commands/Info.js';
import Banner from './ui/Banner.js';

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
                <Text>Please specify a command. Run <Text color="cyan">quasar --help</Text> for usage.</Text>
            </Box>
        );
    }

	switch (command) {
		case 'run':
			return <Run args={args} flags={flags} />;
		case 'config':
			return <Config args={args} />;
		case 'checkpoint':
			return <Checkpoint args={args} />;
		case 'info':
			return <Info />;
		case 'version':
			return (
                <Box flexDirection="column" padding={1}>
                    <Text>
                        <Text color="cyan" bold>QUASAR-CHEM</Text>{' '}
                        <Text dimColor>version</Text>{' '}
                        <Text color="yellow">1.0.0 (Node.js)</Text>
                    </Text>
                </Box>
            );
		default:
			return (
				<Box flexDirection="column">
					<Text color="red">Unknown command: {command}</Text>
                    <Text>Run <Text color="cyan">quasar --help</Text> for usage.</Text>
				</Box>
			);
	}
};

export default App;
