'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { getApiBaseUrl } from '@/lib/api';

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
      const baseUrl = getApiBaseUrl();
      const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = baseUrl.replace(/^https?:\/\//, '');
      const wsUrl = `${wsProto}//${host}/ws/upload/${clientIdRef.current}`;
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
        const ws = wsRef.current;
        ws.onerror = null;
        ws.onclose = null;
        ws.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { isConnected, lastEvent };
};
