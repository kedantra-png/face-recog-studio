'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

export interface WebSocketEvent {
  event: string;
  data: any;
}

export const useWebSocket = (onMessageReceived?: (event: WebSocketEvent) => void) => {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [lastEvent, setLastEvent] = useState<WebSocketEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const clientIdRef = useRef<string>(`client_${Math.random().toString(36).substring(2, 9)}`);

  const connect = useCallback(() => {
    try {
      const wsUrl = `${WS_BASE_URL}/ws/upload/${clientIdRef.current}`;
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const parsed: WebSocketEvent = JSON.parse(event.data);
          setLastEvent(parsed);
          if (onMessageReceived) {
            onMessageReceived(parsed);
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        // Retry connection after 3s
        setTimeout(connect, 3000);
      };

      ws.onerror = (error) => {
        console.warn('WebSocket error:', error);
        ws.close();
      };

      wsRef.current = ws;
    } catch (err) {
      console.error('WebSocket initialization error:', err);
    }
  }, [onMessageReceived]);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { isConnected, lastEvent };
};
