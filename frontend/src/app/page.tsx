'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { AlertCircle, RefreshCw, Server, Lock } from 'lucide-react';
import { Header } from '@/components/Header';
import { ConfigDrawer } from '@/components/ConfigDrawer';
import { SecureWebcamScanner } from '@/components/SecureWebcamScanner';
import { RecognitionDashboard } from '@/components/RecognitionDashboard';
import { useRecognitionSession } from '@/hooks/useRecognitionSession';
import { DesktopFrameScrubber } from '@/components/DesktopFrameScrubber';
import { BackendConfig, CandidateFrame } from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export default function Home() {
  const [backendConfig, setBackendConfig] = useState<BackendConfig | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isConfigOpen, setIsConfigOpen] = useState<boolean>(false);

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

  // Connection check with backend
  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/config`);
      if (res.ok) {
        const data = await res.json();
        setBackendConfig(data);
        setIsConnected(true);
      } else {
        setIsConnected(false);
      }
    } catch (err) {
      console.warn('FastAPI connection check warning:', err);
      setIsConnected(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
    initSession();

    const interval = setInterval(fetchConfig, 10000);
    return () => clearInterval(interval);
  }, [fetchConfig, initSession]);

  const handleAutoCaptureFrames = async (best3Frames: CandidateFrame[]) => {
    console.log('Selected best 3 candidate frames for recognition:', best3Frames.length);
    await executeRecognition(best3Frames);
  };

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
                Backend Server Offline — Connecting to FastAPI Gateway at {API_BASE_URL}...
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
              InsightFace buffalo_l 512-d Embeddings • MiniFASNet Anti-Spoofing • Qdrant Vector Search • 2 vCPU VPS Optimized
            </p>
          </div>

          <div className="flex items-center space-x-2 bg-slate-950/80 px-4 py-2 rounded-2xl border border-slate-800 text-xs font-mono text-slate-300">
            <Server className="w-4 h-4 text-cyan-400" />
            <span>Session: {session ? session.session_id.slice(0, 14) + '...' : 'Acquiring Token...'}</span>
          </div>
        </div>

        {/* Primary View Switcher: Result Dashboard OR Live Scanner */}
        {result ? (
          <RecognitionDashboard result={result} onReset={resetSession} />
        ) : (
          <SecureWebcamScanner
            onAutoCaptureFrames={handleAutoCaptureFrames}
            isProcessing={isProcessing}
            stageMessage={currentProgress?.message}
            onReset={resetSession}
          />
        )}

        {/* Interactive 3D Video Frame Showcase */}
        <div className="w-full pt-6 border-t border-slate-800/80">
          <DesktopFrameScrubber />
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 py-6 bg-[#060910]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
          <div className="flex items-center space-x-2">
            <Lock className="w-3.5 h-3.5 text-emerald-400" />
            <span>Secure Webcam Only • Direct Image Upload Restricted</span>
          </div>
          <span>Silent-Face Anti-Spoofing & InsightFace Recognition Gateway</span>
        </div>
      </footer>

      {/* Configuration Drawer Modal */}
      {isConfigOpen && (
        <ConfigDrawer
          config={backendConfig}
          isOpen={isConfigOpen}
          onClose={() => setIsConfigOpen(false)}
        />
      )}
    </div>
  );
}
