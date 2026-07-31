'use client';

import React from 'react';
import { Play, Pause, XCircle, RotateCcw, CheckCircle2, Clock, Cpu, HardDrive, AlertTriangle, Layers } from 'lucide-react';
import { UploadQueueItem } from './ResumableUploader';

interface VirtualizedQueueProps {
  queue: UploadQueueItem[];
  onPause: (id: string) => void;
  onResume: (id: string) => void;
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
}

export const VirtualizedQueue: React.FC<VirtualizedQueueProps> = ({
  queue,
  onPause,
  onResume,
  onCancel,
  onRetry,
}) => {
  if (!queue || queue.length === 0) return null;

  // Aggregate Metrics
  const totalSize = queue.reduce((acc, item) => acc + item.size, 0);
  const totalUploadedBytes = queue.reduce((acc, item) => acc + (item.uploadedChunks * (5 * 1024 * 1024)), 0);
  const overallProgress = Math.min(100, Math.round((totalUploadedBytes / (totalSize || 1)) * 100));

  const activeUploading = queue.filter((i) => i.status === 'uploading');
  const currentSpeedBytes = activeUploading.reduce((acc, i) => acc + i.speedBytesPerSec, 0);

  const speedMBps = (currentSpeedBytes / (1024 * 1024)).toFixed(2);
  const remainingBytes = totalSize - totalUploadedBytes;
  const etaSec = currentSpeedBytes > 0 ? Math.ceil(remainingBytes / currentSpeedBytes) : 0;

  const formatEta = (seconds: number) => {
    if (seconds <= 0) return '0s';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  };

  return (
    <div className="glass-panel p-6 rounded-3xl border border-slate-800/80 shadow-2xl space-y-6">
      {/* Aggregate Header & Overall Progress */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div className="flex items-center space-x-2">
          <div className="p-2 rounded-xl bg-teal-500/10 text-teal-400 border border-teal-500/20">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-100">Live Upload & Queue Telemetry</h2>
            <p className="text-xs text-slate-400">
              {queue.length} files in queue • Resumable 5MB Chunk Pipeline
            </p>
          </div>
        </div>

        {/* Speed & ETA Badges */}
        <div className="flex items-center space-x-3 text-xs font-mono">
          <div className="glass-card px-3 py-1.5 rounded-xl border border-slate-800 flex items-center space-x-1.5">
            <Cpu className="w-3.5 h-3.5 text-teal-400" />
            <span className="text-slate-400">Speed:</span>
            <span className="text-teal-300 font-bold">{speedMBps} MB/s</span>
          </div>

          <div className="glass-card px-3 py-1.5 rounded-xl border border-slate-800 flex items-center space-x-1.5">
            <Clock className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-slate-400">ETA:</span>
            <span className="text-indigo-300 font-bold">{formatEta(etaSec)}</span>
          </div>
        </div>
      </div>

      {/* Overall Progress Bar */}
      <div>
        <div className="flex justify-between text-xs font-semibold mb-1.5">
          <span className="text-slate-300">Overall Batch Progress</span>
          <span className="font-mono text-emerald-400">{overallProgress}%</span>
        </div>
        <div className="w-full h-3 bg-slate-950 rounded-full overflow-hidden p-0.5 border border-slate-800">
          <div
            className="h-full bg-gradient-to-r from-emerald-500 via-teal-400 to-cyan-500 rounded-full transition-all duration-300"
            style={{ width: `${overallProgress}%` }}
          />
        </div>
      </div>

      {/* Queue File Items List */}
      <div className="max-h-[350px] overflow-y-auto space-y-2.5 pr-1">
        {queue.map((item) => {
          const isUploading = item.status === 'uploading';
          const isCompleted = item.status === 'completed';
          const isFailed = item.status === 'failed';
          const isPaused = item.status === 'paused';
          const isEmbedding = item.status === 'embedding_processing';

          return (
            <div
              key={item.id}
              className="glass-card p-3 rounded-2xl border border-slate-800/80 flex items-center justify-between gap-4 text-xs font-mono hover:border-slate-700 transition"
            >
              {/* File Info */}
              <div className="flex items-center space-x-3 min-w-0 flex-1">
                <div className="w-8 h-8 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center flex-shrink-0 text-slate-400">
                  <HardDrive className="w-4 h-4" />
                </div>

                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-slate-200 truncate">{item.relativePath}</p>
                  <div className="flex items-center space-x-2 text-[10px] text-slate-400 mt-0.5">
                    <span>{(item.size / (1024 * 1024)).toFixed(1)} MB</span>
                    <span>•</span>
                    <span className="capitalize">{item.status.replace('_', ' ')}</span>
                  </div>
                </div>
              </div>

              {/* Progress Bar & Status Pill */}
              <div className="flex items-center space-x-4">
                <div className="w-28 hidden sm:block">
                  <div className="flex justify-between text-[10px] mb-1">
                    <span className="text-slate-400">{item.progress}%</span>
                    {isUploading && (
                      <span className="text-teal-400">
                        {(item.speedBytesPerSec / (1024 * 1024)).toFixed(1)} MB/s
                      </span>
                    )}
                  </div>
                  <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                    <div
                      className={`h-full rounded-full transition-all ${
                        isCompleted
                          ? 'bg-emerald-500'
                          : isFailed
                          ? 'bg-rose-500'
                          : 'bg-teal-400'
                      }`}
                      style={{ width: `${item.progress}%` }}
                    />
                  </div>
                </div>

                {/* Status Badges */}
                {isCompleted && (
                  <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1 text-[10px]">
                    <CheckCircle2 className="w-3 h-3" /> Done
                  </span>
                )}

                {isEmbedding && (
                  <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center gap-1 text-[10px] animate-pulse">
                    <Cpu className="w-3 h-3" /> Embedding
                  </span>
                )}

                {isFailed && (
                  <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 flex items-center gap-1 text-[10px]">
                    <AlertTriangle className="w-3 h-3" /> Failed
                  </span>
                )}

                {/* Action Controls */}
                <div className="flex items-center space-x-1">
                  {isUploading && (
                    <button
                      onClick={() => onPause(item.id)}
                      className="p-1 rounded bg-slate-800 text-slate-300 hover:text-white"
                      title="Pause Upload"
                    >
                      <Pause className="w-3.5 h-3.5" />
                    </button>
                  )}

                  {isPaused && (
                    <button
                      onClick={() => onResume(item.id)}
                      className="p-1 rounded bg-teal-500/20 text-teal-300 hover:bg-teal-500/30"
                      title="Resume Upload"
                    >
                      <Play className="w-3.5 h-3.5" />
                    </button>
                  )}

                  {isFailed && (
                    <button
                      onClick={() => onRetry(item.id)}
                      className="p-1 rounded bg-amber-500/20 text-amber-300 hover:bg-amber-500/30"
                      title="Retry Upload"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                    </button>
                  )}

                  {!isCompleted && (
                    <button
                      onClick={() => onCancel(item.id)}
                      className="p-1 rounded bg-rose-500/10 text-rose-400 hover:bg-rose-500/20"
                      title="Cancel Upload"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
