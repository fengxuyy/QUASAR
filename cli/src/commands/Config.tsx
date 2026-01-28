import React, { useEffect, useState } from 'react';
import { Box, Text } from 'ink';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';

dotenv.config();

interface ConfigProps {
    args: string[];
}

const Config: React.FC<ConfigProps> = ({ args }) => {
    const subCommand = args[0] || 'show';

    const configData = {
        "MODEL": process.env.MODEL || "gemini-3-pro-preview",
        "MODEL_API_KEY": process.env.MODEL_API_KEY ? "✓" : null,
        "ACCURACY": process.env.ACCURACY || "eco",
        "GRANULARITY": process.env.GRANULARITY || "medium",
        "ENABLE_RAG": process.env.ENABLE_RAG || "true",
        "IF_RESTART": process.env.IF_RESTART || "false",
        "PMG_MAPI_KEY": process.env.PMG_MAPI_KEY ? "✓" : null,
    };

    if (subCommand === 'validate') {
        const errors: string[] = [];
        if (!process.env.MODEL_API_KEY) errors.push("MODEL_API_KEY is not set (required)");

        return (
             <Box flexDirection="column" padding={1}>
            <Box marginBottom={1}>
                {errors.length > 0 ? (
                    errors.map((err, i) => <Text key={i} color="red">✖ {err}</Text>)
                ) : (
                    <Text color="green">✔ Configuration is valid!</Text>
                )}
            </Box>
             </Box>
        );
    }

    // Default: show
    return (
        <Box flexDirection="column" padding={1}>
             <Box marginBottom={1}>
                <Text bold underline>Current Configuration</Text>
             </Box>
             {Object.entries(configData).map(([key, val]) => (
                 <Box key={key}>
                     <Box width={20}><Text bold>{key}:</Text></Box>
                     <Text color="cyan">{val || <Text color="dim">undefined</Text>}</Text>
                 </Box>
             ))}
        </Box>
    );
};

export default Config;
