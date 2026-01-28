import React from 'react';
import { Box, Text } from 'ink';
import os from 'os';

const Info: React.FC = () => {
    const infoData = {
        "Workspace": process.cwd(),
        "Node Version": process.version,
        "Platform": os.platform(),
        "Arch": os.arch(),
        "CPUs": os.cpus().length,
    };

	return (
		<Box flexDirection="column" padding={1}>
            <Box marginBottom={1}>
			    <Text bold underline>System Information</Text>
            </Box>
            {Object.entries(infoData).map(([key, value]) => (
                <Box key={key}>
                    <Box width={20}>
                        <Text bold>{key}:</Text>
                    </Box>
                    <Text color="cyan">{value}</Text>
                </Box>
            ))}
		</Box>
	);
};

export default Info;
