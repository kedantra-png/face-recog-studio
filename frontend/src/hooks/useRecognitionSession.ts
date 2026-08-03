import { useState, useCallback, useRef, useEffect } from 'react';
import { RecognitionSession, RecognitionResult, RecognitionProgressEvent, CandidateFrame } from '@/types';
import { getApiBaseUrl, base64ToBlob } from '@/lib/api';

async function sha256Hex(str: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(str);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

async function hmacSha256Hex(keyStr: string, messageStr: string): Promise<string> {
  try {
    const encoder = new TextEncoder();
    const keyData = encoder.encode(keyStr);
    const msgData = encoder.encode(messageStr);
    const key = await crypto.subtle.importKey('raw', keyData, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const signature = await crypto.subtle.sign('HMAC', key, msgData);
    const hashArray = Array.from(new Uint8Array(signature));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  } catch (err) {
    return sha256Hex(keyStr + messageStr);
  }
}

export function useRecognitionSession() {
  const [session, setSession] = useState<RecognitionSession | null>(null);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [currentProgress, setCurrentProgress] = useState<RecognitionProgressEvent | null>(null);
  const [result, setResult] = useState<RecognitionResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);

  const initSession = useCallback(async (): Promise<RecognitionSession | null> => {
    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/v2/recognition/session`, { method: 'POST' });
      if (!res.ok) {
        throw new Error(`Failed to initialize session: ${res.statusText}`);
      }
      const data = await res.json();
      if (data.success) {
        const newSession: RecognitionSession = {
          session_id: data.session_id,
          client_secret: data.client_secret,
          nonce: data.nonce,
          ttl_seconds: data.ttl_seconds,
          expires_at: data.expires_at,
        };
        setSession(newSession);

        // Open WebSocket connection
        const baseUrl = getApiBaseUrl();
        const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = baseUrl.replace(/^https?:\/\//, '');
        const wsUrl = `${wsProto}//${host}/api/v2/ws/recognition/${newSession.session_id}`;

        if (wsRef.current) {
          wsRef.current.close();
        }

        const ws = new WebSocket(wsUrl);
        ws.onopen = () => {
          console.log(`WebSocket connected for session ${newSession.session_id}`);
        };
        ws.onmessage = (event) => {
          try {
            const parsed = JSON.parse(event.data);
            if (parsed.event === 'recognition_progress' && parsed.data) {
              setCurrentProgress(parsed.data);
              console.info(
                `%c[Recognition Stage] ${parsed.data.stage}%c — ${parsed.data.message}`,
                'color: #06b6d4; font-weight: bold;',
                'color: #94a3b8;'
              );
            }
          } catch (e) {
            // ignore
          }
        };
        ws.onerror = (err) => {
          console.warn('Recognition WebSocket error:', err);
        };
        wsRef.current = ws;

        return newSession;
      }
      return null;
    } catch (err: any) {
      console.error('Session creation failed:', err);
      setError(err.message || 'Session creation failed');
      return null;
    }
  }, []);

  const executeRecognition = useCallback(
    async (candidateFrames: CandidateFrame[]) => {
      setIsProcessing(true);
      setError(null);
      setResult(null);
      setCurrentProgress({ stage: 'VALIDATING', message: 'Initiating security verification & payload encryption' });

      try {
        let activeSession = session;
        if (!activeSession || Date.now() / 1000 > activeSession.expires_at - 5) {
          activeSession = await initSession();
        }

        if (!activeSession) {
          // Fallback session token for smooth local dev / testing
          activeSession = {
            session_id: `sec_sess_${Math.random().toString(36).substring(2, 12)}`,
            client_secret: 'local_dev_secret',
            nonce: Math.random().toString(36).substring(2, 10),
            ttl_seconds: 60,
            expires_at: Date.now() / 1000 + 60,
          };
        }

        const timestamp = Date.now() / 1000;
        const nonce = activeSession.nonce;
        const rawFramesStr = candidateFrames.map((f) => (f.frame_b64 || '').slice(0, 30)).join('');
        const payloadHash = await sha256Hex(rawFramesStr);

        const signature = await hmacSha256Hex(
          activeSession.client_secret,
          `${activeSession.session_id}:${timestamp}:${nonce}:${payloadHash}`
        );

        const baseUrl = getApiBaseUrl();
        const formData = new FormData();
        formData.append('session_id', activeSession.session_id);
        formData.append('timestamp', timestamp.toString());
        formData.append('nonce', nonce);
        formData.append('signature', signature);

        candidateFrames.forEach((f, idx) => {
          const blob = f.frame_blob instanceof Blob ? f.frame_blob : base64ToBlob(f.frame_b64);
          formData.append('files', blob, `frame_${idx}.jpg`);
        });

        const response = await fetch(`${baseUrl}/api/v2/recognition/verify`, {
          method: 'POST',
          body: formData, // Browser sets multipart/form-data boundary automatically
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({ detail: 'HTTP error during verification' }));
          throw new Error(errData.detail || 'Recognition verification failed');
        }

        const resData: RecognitionResult = await response.json();
        setResult(resData);
        setCurrentProgress({ stage: 'FINISHED', message: 'Recognition processing complete', payload: resData });

        // Structured Developer Console Logs
        console.group('%c[Face Recognition Completed]', 'color: #10B981; font-weight: bold; font-size: 13px;');
        console.log('Status:', resData.recognition_status);
        console.log('Match Found:', resData.match_found);
        console.log('Person ID:', resData.person_id || 'N/A');
        console.log('Overall Confidence:', resData.overall_confidence + '%');
        console.log('Cosine Similarity:', Math.round((resData.similarity_score || 0) * 100) + '%');
        console.log('Anti-Spoof Confidence:', Math.round((resData.anti_spoof_confidence || 0) * 100) + '% REAL');
        if (resData.processing_time_ms) {
          console.table(resData.processing_time_ms);
        }
        if (resData.top_matches && resData.top_matches.length > 0) {
          console.table(resData.top_matches);
        }
        console.groupEnd();

      } catch (err: any) {
        console.error('Recognition execution error:', err);
        setError(err.message || 'Recognition execution error');
        setResult({
          success: false,
          match_found: false,
          similarity_score: 0.0,
          overall_confidence: 0.0,
          top_matches: [],
          recognition_status: 'POOR_QUALITY',
          error: err.message || 'Verification error',
        });
      } finally {
        setIsProcessing(false);
      }
    },
    [session, initSession]
  );

  const resetSession = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setSession(null);
    setResult(null);
    setCurrentProgress(null);
    setError(null);
    setIsProcessing(false);
  }, []);

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return {
    session,
    isProcessing,
    currentProgress,
    result,
    error,
    initSession,
    executeRecognition,
    resetSession,
  };
}
