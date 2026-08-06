'use client';

import React, { useState, useEffect, useCallback, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { AlertCircle, RefreshCw, ShieldCheck, ShieldAlert, Lock, Camera, CheckCircle2 } from 'lucide-react';
import { Header } from '@/components/Header';
import { ConfigDrawer } from '@/components/ConfigDrawer';
import { SecureWebcamScanner } from '@/components/SecureWebcamScanner';
import { RecognitionDashboard } from '@/components/RecognitionDashboard';
import { useRecognitionSession } from '@/hooks/useRecognitionSession';
import { BackendConfig, CandidateFrame } from '@/types';
import { fetchBackendConfigWithFallback, getApiBaseUrl } from '@/lib/api';

function HomeContent() {
  const searchParams = useSearchParams();
  const studioTokenParam = searchParams.get('studio') || searchParams.get('access');

  const [backendConfig, setBackendConfig] = useState<BackendConfig | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isConfigOpen, setIsConfigOpen] = useState<boolean>(false);
  const [activeApiUrl, setActiveApiUrl] = useState<string>('http://127.0.0.1:8000');

  // Studio Token Validation States
  const [isValidatingStudio, setIsValidatingStudio] = useState<boolean>(true);
  const [isStudioValid, setIsStudioValid] = useState<boolean>(false);
  const [studioInfo, setStudioInfo] = useState<{ studio_id: string; studio_name: string } | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const {
    session,
    isProcessing,
    currentProgress,
    result,
    error,
    initSession,
    executeRecognition,
    resetSession,
  } = useRecognitionSession();

function sanitizeToken(val: string | null): string {
  if (!val) return '';
  return val
    .replace(/[\x00-\x1f\x7f-\x9f\s]/g, '')
    .replace(/[^a-zA-Z0-9_\-=]/g, '')
    .slice(0, 256);
}

  // Exchange URL token for Public Visitor JWT Session Token
  const validateStudioToken = useCallback(async () => {
    const sanitizedParam = sanitizeToken(studioTokenParam);
    if (!sanitizedParam) {
      setIsValidatingStudio(false);
      setIsStudioValid(false);
      setValidationError('No valid Studio Access Token provided in URL.');
      return;
    }

    setIsValidatingStudio(true);
    setValidationError(null);

    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/v2/public/studio/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: sanitizedParam }),
      });

      const data = await res.json();
      if (res.ok && data.success && data.valid && data.visitor_jwt) {
        setIsStudioValid(true);
        setStudioInfo({
          studio_id: data.studio.studio_id,
          studio_name: data.studio.studio_name,
        });

        // Store Visitor JWT Session Token
        if (typeof window !== 'undefined') {
          sessionStorage.setItem('studio_visitor_jwt', data.visitor_jwt);
          localStorage.setItem('studio_visitor_jwt', data.visitor_jwt);
        }
      } else {
        throw new Error(data.detail || 'Studio access token invalid or expired');
      }
    } catch (err: any) {
      console.error('Studio token validation error:', err);
      setIsStudioValid(false);
      setValidationError(err.message || 'Invalid or revoked Studio URL');
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('studio_visitor_jwt');
      }
    } finally {
      setIsValidatingStudio(false);
    }
  }, [studioTokenParam]);

  // Connection check with backend fallback support
  const fetchConfig = useCallback(async () => {
    const res = await fetchBackendConfigWithFallback();
    if (res) {
      setBackendConfig(res.config);
      setActiveApiUrl(res.baseUrl);
      setIsConnected(true);
    } else {
      setIsConnected(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
    validateStudioToken();

    const interval = setInterval(fetchConfig, 10000);
    return () => clearInterval(interval);
  }, [fetchConfig, validateStudioToken]);

  useEffect(() => {
    if (isStudioValid) {
      initSession();
    }
  }, [isStudioValid, initSession]);

  const handleAutoCaptureFrames = async (best3Frames: CandidateFrame[]) => {
    console.log('Selected best 3 candidate frames for recognition:', best3Frames.length);
    await executeRecognition(best3Frames);
  };

  // 1. Loading State
  if (isValidatingStudio) {
    return (
      <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col items-center justify-center space-y-4">
        <div className="w-12 h-12 rounded-full border-4 border-emerald-500/20 border-t-emerald-400 animate-spin" />
        <p className="text-sm text-slate-400 font-medium font-mono">Validating Studio Access Token & Visitor JWT...</p>
      </div>
    );
  }

  // 2. Standard Clean 404 Page (No extra data or debug details)
  if (!isStudioValid) {
    return (
      <div className="min-h-screen bg-[#090d16] text-slate-100 flex items-center justify-center font-sans selection:bg-emerald-500 selection:text-white">
        <div className="flex items-center space-x-6">
          <h1 className="text-3xl font-extrabold text-white border-r border-slate-700 pr-6 py-2">404</h1>
          <p className="text-sm font-medium text-slate-400">This page could not be found.</p>
        </div>
      </div>
    );
  }

  // 3. Validated Studio Search Interface
  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col justify-between selection:bg-emerald-500 selection:text-white">
      {/* Header Navigation */}
      <Header
        config={backendConfig}
        isConnected={isConnected}
        onRefreshConfig={fetchConfig}
        onOpenConfig={() => setIsConfigOpen(true)}
      />

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full space-y-8 flex-grow flex flex-col items-center">
        
        {/* Offline Warning Banner */}
        {!isConnected && (
          <div className="w-full max-w-4xl p-4 rounded-2xl bg-amber-950/80 border border-amber-500/50 shadow-xl flex items-center justify-between">
            <div className="flex items-center space-x-3 text-amber-200">
              <AlertCircle className="w-5 h-5 text-amber-400 animate-pulse" />
              <span className="text-sm font-medium">
                Backend Server Offline — Connecting to FastAPI Gateway at {activeApiUrl}...
              </span>
            </div>
            <button
              onClick={fetchConfig}
              className="px-3.5 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 text-xs font-semibold border border-amber-500/40 transition-all flex items-center space-x-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry Connection</span>
            </button>
          </div>
        )}

        {/* Studio Active Session Badge */}
        <div className="w-full max-w-4xl flex items-center justify-between p-4 rounded-2xl bg-emerald-950/40 border border-emerald-500/30 shadow-lg">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="text-sm font-bold text-white flex items-center space-x-2">
                <span>{studioInfo?.studio_name}</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                  Verified Studio
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Isolated Multi-Tenant Vector Index • ID: <span className="font-mono text-emerald-400">{studioInfo?.studio_id}</span>
              </p>
            </div>
          </div>
          <div className="hidden sm:flex items-center space-x-1.5 text-xs text-emerald-400 font-mono bg-emerald-900/30 px-3 py-1.5 rounded-xl border border-emerald-500/20">
            <CheckCircle2 className="w-4 h-4" />
            <span>JWT Visitor Session Active</span>
          </div>
        </div>

        {/* System Status Pipeline Header */}
        <div className="w-full max-w-4xl flex flex-col md:flex-row items-center justify-between p-6 rounded-3xl bg-slate-900/60 border border-slate-800 shadow-xl backdrop-blur-xl gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-2xl font-black tracking-tight text-white flex items-center space-x-2">
                <span>Production Face Recognition Pipeline</span>
              </h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                v2.0 Gateway
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Direct Landmark Liveness Engine • InsightFace buffalo_l 512-d Embeddings • Qdrant Vector Search • 2 vCPU VPS Optimized
            </p>
          </div>

          <div className="flex items-center space-x-3 shrink-0">
            <div className="px-3.5 py-2 rounded-2xl bg-slate-950/80 border border-slate-800 text-xs font-mono text-slate-300 flex items-center space-x-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              <span>Session: {session?.session_id.substring(0, 14)}...</span>
            </div>
          </div>
        </div>

        {/* Main Interface: Webcam Scanner vs Recognition Results */}
        {!result ? (
          <SecureWebcamScanner
            onAutoCaptureFrames={handleAutoCaptureFrames}
            onAutoCapture={handleAutoCaptureFrames}
            isProcessing={isProcessing}
            currentProgress={currentProgress}
          />
        ) : (
          <RecognitionDashboard
            result={result}
            onReset={() => {
              resetSession();
              initSession();
            }}
          />
        )}
      </main>

      {/* Config Drawer */}
      <ConfigDrawer
        isOpen={isConfigOpen}
        onClose={() => setIsConfigOpen(false)}
        config={backendConfig}
        onConfigSaved={fetchConfig}
      />

      {/* Footer */}
      <footer className="w-full border-t border-slate-800/80 py-4 bg-[#070a11]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-2">
          <span>AuraFace AI Anti-Spoofing & Vector Search Engine • v2.0</span>
          <span>MongoDB: face_recog_db_v2 • Qdrant: faces_embed_v2</span>
        </div>
      </footer>
    </div>
  );
}

export default function Home() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#090d16] text-slate-100 flex items-center justify-center font-mono text-sm">
          Loading AuraFace Gateway...
        </div>
      }
    >
      <HomeContent />
    </Suspense>
  );
}
