import React, { useEffect, useRef, useCallback } from 'react';
import { ShieldAlert, Terminal as TerminalIcon, Loader2 } from 'lucide-react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { withAuthWebSocketUrl } from '../../utils/apiAuth';

interface TerminalPanelProps {
  className?: string;
  shouldConnect?: boolean;
  isVisible?: boolean;
}

export const TerminalPanel: React.FC<TerminalPanelProps> = ({ className, shouldConnect = true, isVisible = true }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<HTMLDivElement>(null);
  const terminalInstance = useRef<Terminal | null>(null);
  const fitAddon = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const isVisibleRef = useRef(isVisible);
  const shouldConnectRef = useRef(shouldConnect);
  const pendingOutputRef = useRef('');
  const outputFlushRef = useRef<number | null>(null);
  const lastSentSizeRef = useRef<{ cols: number; rows: number } | null>(null);
  const [isConnecting, setIsConnecting] = React.useState(true);
  const [connectionError, setConnectionError] = React.useState<string | null>(null);

  useEffect(() => {
    isVisibleRef.current = isVisible;
  }, [isVisible]);

  useEffect(() => {
    shouldConnectRef.current = shouldConnect;
  }, [shouldConnect]);

  const flushTerminalOutput = useCallback(() => {
    if (outputFlushRef.current !== null) {
      window.cancelAnimationFrame(outputFlushRef.current);
      outputFlushRef.current = null;
    }
    if (!pendingOutputRef.current || !terminalInstance.current) return;
    const data = pendingOutputRef.current;
    pendingOutputRef.current = '';
    terminalInstance.current.write(data);
  }, []);

  const closeWebSocket = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      const ws = wsRef.current;
      ws.onclose = null;
      ws.close();
      wsRef.current = null;
    }
    pendingOutputRef.current = '';
    lastSentSizeRef.current = null;
    if (outputFlushRef.current !== null) {
      window.cancelAnimationFrame(outputFlushRef.current);
      outputFlushRef.current = null;
    }
    setIsConnecting(false);
  }, []);

  const fitTerminal = useCallback(() => {
    const terminal = terminalInstance.current;
    if (!terminal || !fitAddon.current) return null;

    try {
      fitAddon.current.fit();
    } catch (err) {
      console.warn('[Terminal] Failed to fit terminal:', err);
    }

    return { cols: terminal.cols, rows: terminal.rows };
  }, []);

  const sendTerminalResize = useCallback(() => {
    const ws = wsRef.current;
    const terminal = terminalInstance.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !terminal) return;

    const nextSize = { cols: terminal.cols, rows: terminal.rows };
    const previousSize = lastSentSizeRef.current;
    if (
      previousSize &&
      previousSize.cols === nextSize.cols &&
      previousSize.rows === nextSize.rows
    ) {
      return;
    }

    lastSentSizeRef.current = nextSize;
    ws.send(JSON.stringify({
      command: 'terminal_resize',
      cols: nextSize.cols,
      rows: nextSize.rows
    }));
  }, []);

  const connectWebSocket = useCallback(() => {
    // Don't connect if not allowed or already connected
    if (!shouldConnectRef.current || wsRef.current?.readyState === WebSocket.CONNECTING || wsRef.current?.readyState === WebSocket.OPEN) return;

    setIsConnecting(true);
    setConnectionError(null);

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws`;
    
    console.log('[Terminal] Connecting to:', wsUrl);
    const ws = new WebSocket(withAuthWebSocketUrl(wsUrl));
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[Terminal] WebSocket connected, sending terminal_start');
      setIsConnecting(false);
      const initialSize = fitTerminal() ?? { cols: terminalInstance.current?.cols ?? 80, rows: terminalInstance.current?.rows ?? 24 };
      lastSentSizeRef.current = initialSize;
      // Request terminal session
      ws.send(JSON.stringify({
        command: 'terminal_start',
        cols: initialSize.cols,
        rows: initialSize.rows
      }));
      
      // Focus terminal after connection
      setTimeout(() => {
        if (terminalInstance.current) {
          fitTerminal();
          sendTerminalResize();
          // Hidden terminal reconnects after settings changes; avoid stealing
          // focus from forms elsewhere in the app while it refreshes itself.
          if (isVisibleRef.current) {
            terminalInstance.current.focus();
          }
        }
      }, 100);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'terminal_output' && terminalInstance.current) {
          pendingOutputRef.current += data.payload.data;
          if (outputFlushRef.current === null) {
            outputFlushRef.current = window.requestAnimationFrame(flushTerminalOutput);
          }
        } else if (data.type === 'terminal_error') {
          console.error('[Terminal] Server error:', data.payload.error);
          setConnectionError(data.payload.error);
          if (terminalInstance.current) {
            terminalInstance.current.write(`\r\n\x1b[31mError: ${data.payload.error}\x1b[0m\r\n`);
          }
        } else if (data.type === 'terminal_settings_updated') {
          // Settings changed - restart terminal session to pick up new environment variables
          console.log('[Terminal] Settings updated, restarting session...');
          if (terminalInstance.current) {
            terminalInstance.current.write(`\r\n\x1b[36m[Settings updated - restarting terminal session]\x1b[0m\r\n`);
          }
          // Close and reconnect to spawn new PTY with updated settings
          ws.close();
        }
      } catch {
        // Non-JSON message, ignore
      }
    };

    ws.onclose = () => {
      wsRef.current = null;
      if (!shouldConnectRef.current) {
        setIsConnecting(false);
        return;
      }
      console.log('[Terminal] WebSocket closed, reconnecting in 2s...');
      setIsConnecting(true);
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connectWebSocket();
      }, 2000);
    };

    ws.onerror = (err) => {
      console.error('[Terminal] WebSocket error:', err);
      setConnectionError('Failed to connect to terminal');
    };
  }, [fitTerminal, flushTerminalOutput, sendTerminalResize]);

  useEffect(() => {
    if (!terminalRef.current || terminalInstance.current) return;

    // Create terminal instance
    const terminal = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      theme: {
        background: '#fafafa', // neutral-50
        foreground: '#1e293b', // slate-800
        cursor: '#334155',     // slate-700
        cursorAccent: '#fafafa',
        selectionBackground: 'rgba(99, 102, 241, 0.2)',
        black: '#0f172a',
        red: '#ef4444',
        green: '#22c55e',
        yellow: '#eab308',
        blue: '#3b82f6',
        magenta: '#a855f7',
        cyan: '#06b6d4',
        white: '#64748b',
        brightBlack: '#475569',
        brightRed: '#f87171',
        brightGreen: '#4ade80',
        brightYellow: '#facc15',
        brightBlue: '#60a5fa',
        brightMagenta: '#c084fc',
        brightCyan: '#22d3ee',
        brightWhite: '#94a3b8',
      },
      scrollback: 5000,
    });

    fitAddon.current = new FitAddon();
    terminal.loadAddon(fitAddon.current);

    terminal.open(terminalRef.current);
    
    // Delay fit to ensure container has proper dimensions
    setTimeout(() => {
      fitTerminal();
    }, 50);

    terminalInstance.current = terminal;

    // Handle terminal input
    terminal.onData((data) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          command: 'terminal_data',
          data: data
        }));
      }
    });

    // Handle resize
    const handleResize = () => {
      if (fitAddon.current && terminalRef.current) {
        // Small timeout to let the container settle
        setTimeout(() => {
          fitTerminal();
          sendTerminalResize();
        }, 50);
      }
    };

    window.addEventListener('resize', handleResize);
    const resizeObserver = new ResizeObserver(handleResize);
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }
    resizeObserver.observe(terminalRef.current);

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize);
      resizeObserver.disconnect();
      closeWebSocket();
      terminal.dispose();
      terminalInstance.current = null;
    };
  }, [closeWebSocket, fitTerminal, sendTerminalResize]);

  useEffect(() => {
    if (shouldConnect) {
      connectWebSocket();
      return;
    }
    closeWebSocket();
  }, [closeWebSocket, connectWebSocket, shouldConnect]);

  // Handle re-fitting when the panel becomes visible
  useEffect(() => {
    if (isVisible && fitAddon.current) {
      // Small delay to ensure the DOM has updated and dimensions are correct
      const timer = setTimeout(() => {
        fitTerminal();
        // Also notify the backend about the new size
        sendTerminalResize();
        if (terminalInstance.current) {
          terminalInstance.current.focus();
        }
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [fitTerminal, isVisible, sendTerminalResize]);

  return (
    <div 
      ref={containerRef}
      className={`flex flex-col w-full h-full min-w-0 glass-panel rounded-2xl overflow-hidden border border-white/50 animate-fade-in ${className || ''}`}
    >
      {/* Header - matching ExecutionLog style */}
      <div className="px-4 py-3 border-b border-white/20 flex items-center gap-2 flex-shrink-0">
        <TerminalIcon size={16} className="text-cyan-500" />
        <span className="font-medium text-slate-700">Terminal</span>
        <div
          className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50/80 px-2.5 py-1 text-xs font-semibold text-amber-700"
          title="The QUASAR CLI is disabled in this terminal to avoid conflicts with the Web UI session."
        >
          <ShieldAlert size={12} />
          QUASAR CLI disabled
        </div>
        {isConnecting && (
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Loader2 size={12} className="animate-spin" />
            <span>Connecting</span>
          </div>
        )}
        {connectionError && (
          <span className="text-xs text-red-500">{connectionError}</span>
        )}
      </div>
      
      {/* Terminal Container */}
      <div 
        ref={terminalRef} 
        className="flex-1 w-full min-w-0 overflow-hidden bg-[#fafafa]"
        style={{ 
          minHeight: '200px',
          maxWidth: '100%',
          padding: '8px'
        }}
      />
    </div>
  );
};
