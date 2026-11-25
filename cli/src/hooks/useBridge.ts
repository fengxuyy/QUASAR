/**
 * Hook for Python bridge process management
 */
import { useEffect, useRef, useCallback } from 'react';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import { resolveBridgePath, resolvePythonCommand } from '../utils/runtimePaths.js';

interface BridgeOptions {
    onMessage: (msg: any) => void;
    onError: (message: string) => void;
    restartCounter: number;
}

interface BridgeResult {
    bridgeRef: React.MutableRefObject<ChildProcess | null>;
    sendCommand: (command: object) => void;
}

export function useBridge({ onMessage, onError, restartCounter }: BridgeOptions): BridgeResult {
    const bridgeRef = useRef<ChildProcess | null>(null);
    const stdoutBufferRef = useRef<string>('');

    useEffect(() => {
        const bridgePath = resolveBridgePath();
        
        if (!bridgePath) {
            onError(`Error: Could not find bridge.py in ${process.cwd()} or configured runtime root`);
            return;
        }

        const child = spawn(resolvePythonCommand(), [bridgePath], {
            cwd: path.dirname(bridgePath),
            stdio: ['pipe', 'pipe', 'inherit'],
            env: {
                ...process.env,
                SKIP_RAG: restartCounter > 0 ? 'true' : 'false'
            }
        });

        bridgeRef.current = child;

        child.stdout.on('data', (data) => {
            stdoutBufferRef.current += data.toString();
            const lines = stdoutBufferRef.current.split('\n');
            stdoutBufferRef.current = lines.pop() || '';

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const msg = JSON.parse(line);
                    onMessage(msg);
                } catch (e) {
                    // Ignore malformed JSON frames
                }
            }
        });

        child.on('error', (err) => {
            onError(`Bridge Error: ${err.message}`);
        });

        return () => {
            child.kill();
        };
    }, [restartCounter, onMessage, onError]);

    const sendCommand = useCallback((command: object) => {
        if (bridgeRef.current && bridgeRef.current.stdin) {
            const payload = JSON.stringify(command);
            bridgeRef.current.stdin.write(payload + "\n");
        }
    }, []);

    return {
        bridgeRef,
        sendCommand
    };
}
