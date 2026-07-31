'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import Link from 'next/link';
import { ShieldCheck, ArrowLeft, UploadCloud, Layers, Cpu, Server, Activity } from 'lucide-react';
import { UploadDropzone } from '@/components/upload/UploadDropzone';
import { VirtualizedQueue } from '@/components/upload/VirtualizedQueue';
import { UploadHistoryTable } from '@/components/upload/UploadHistoryTable';
import { DirectSearchDebugger } from '@/components/upload/DirectSearchDebugger';
import { MetricsOverview } from '@/components/upload/MetricsOverview';

import { ResumableUploader, UploadQueueItem } from '@/components/upload/ResumableUploader';
import { useWebSocket } from '@/hooks/useWebSocket';

export default function UploadPage() {
  const [queue, setQueue] = useState<UploadQueueItem[]>([]);
  const [systemMetrics, setSystemMetrics] = useState<any>(null);
  const uploaderRef = useRef<ResumableUploader | null>(null);

  // Initialize Resumable Uploader Manager
  useEffect(() => {
    uploaderRef.current = new ResumableUploader((newQueue) => {
      setQueue(newQueue);
    });
  }, []);

  // Handle Real-Time WebSocket Events
  const handleWebSocketMessage = useCallback((event: any) => {
    if (event.event === 'system_metrics') {
      setSystemMetrics(event.data);
    } else if (event.event === 'embedding_completed') {
      const { image_id, job_id, detected_faces, quality_score } = event.data;
      setQueue((prevQueue) =>
        prevQueue.map((item) =>
          item.jobId === job_id || item.id === image_id || item.status === 'embedding_processing'
            ? { ...item, status: 'completed', progress: 100, detectedFaces: detected_faces, qualityScore: quality_score }
            : item
        )
      );
    } else if (event.event === 'embedding_processing') {
      const { image_id, job_id } = event.data;
      setQueue((prevQueue) =>
        prevQueue.map((item) =>
          item.jobId === job_id || item.id === image_id
            ? { ...item, status: 'embedding_processing', progress: 100 }
            : item
        )
      );
    }
  }, []);


  const { isConnected } = useWebSocket(handleWebSocketMessage);

  const handleFilesSelected = (files: File[]) => {
    if (!uploaderRef.current) return;
    const jobId = `job_${Math.random().toString(36).substring(2, 10)}`;
    uploaderRef.current.addFiles(files, jobId);
  };

  const handleZipSelected = async (zipFile: File) => {
    if (!uploaderRef.current) return;
    const jobId = `job_${Math.random().toString(36).substring(2, 10)}`;
    try {
      await uploaderRef.current.uploadZip(zipFile, jobId);
    } catch (err) {
      console.error('ZIP upload failed:', err);
    }
  };

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col justify-between selection:bg-emerald-500 selection:text-white">
      {/* Header Navigation */}
      <header className="sticky top-0 z-40 w-full glass-panel border-b border-slate-800/80 bg-[#090d16]/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <Link
              href="/"
              className="p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 transition border border-slate-700/60"
              title="Back to Main Scanner"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div className="flex items-center space-x-3">
              <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-700 text-white shadow-lg shadow-emerald-500/20">
                <UploadCloud className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-200 to-emerald-400 bg-clip-text text-transparent">
                  Upload & Face Embedding Dashboard
                </h1>
                <p className="text-xs text-slate-400 font-medium">
                  Resumable Chunk Pipeline • InsightFace 512-d Vector Indexing
                </p>
              </div>
            </div>
          </div>

          {/* Connection Pill */}
          <div className="flex items-center space-x-2 px-3 py-1.5 rounded-full text-xs font-semibold border bg-emerald-950/40 text-emerald-400 border-emerald-500/30">
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400 animate-ping' : 'bg-amber-500'}`} />
            <Server className="w-3.5 h-3.5" />
            <span>{isConnected ? 'Pipeline WebSocket Connected' : 'Connecting WebSocket...'}</span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full space-y-8 flex-grow">
        {/* System Hardware & Telemetry Overview */}
        <MetricsOverview metrics={systemMetrics} />

        {/* Universal Dropzone */}
        <UploadDropzone
          onFilesSelected={handleFilesSelected}
          onZipSelected={handleZipSelected}
        />

        {/* Live Upload & Processing Queue */}
        <VirtualizedQueue
          queue={queue}
          onPause={(id) => uploaderRef.current?.pause(id)}
          onResume={(id) => uploaderRef.current?.resume(id)}
          onCancel={(id) => uploaderRef.current?.cancel(id)}
          onRetry={(id) => uploaderRef.current?.retry(id)}
        />

        {/* Direct Vector Search & Match Debugger */}
        <DirectSearchDebugger />

        {/* Processed Metadata & Vector Registry */}
        <UploadHistoryTable />

      </main>

      {/* Footer */}
      <footer className="w-full border-t border-slate-800/80 py-4 bg-[#070a11]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-2">
          <span>AuraFace Enterprise Upload & Embedding Engine • InsightFace 512-d Qdrant Vector Index</span>
          <span>MongoDB: face_recog_db_v2 • Qdrant: faces_embed_v2</span>

        </div>
      </footer>
    </div>
  );
}
