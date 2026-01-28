/**
 * Hook for Python bridge process management
 */
import { useEffect, useRef, useCallback } from 'react';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import fs from 'fs';

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

    useEffect(() => {
        // Try multiple paths for bridge.py
        let bridgePath = process.env.QUASAR_BRIDGE_PATH;
        
        if (!bridgePath) {
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
        }
        
        if (!bridgePath) {
            onError(`Error: Could not find bridge.py in ${process.cwd()} or ../`);
            return;
        }

        const child = spawn('python3', [bridgePath], {
            cwd: path.dirname(bridgePath),
            stdio: ['pipe', 'pipe', 'inherit'],
            env: {
                ...process.env,
                SKIP_RAG: restartCounter > 0 ? 'true' : 'false'
            }
        });

        bridgeRef.current = child;

        child.stdout.on('data', (data) => {
            const lines = data.toString().split('\n');
            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const msg = JSON.parse(line);
                    onMessage(msg);
                } catch (e) {
                    // Ignore partial lines or non-json
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
