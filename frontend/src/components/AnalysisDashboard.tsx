'use client';

import React from 'react';
import { ShieldCheck, ShieldAlert, AlertTriangle, Clock, Target, Gauge, Cpu, CheckCircle2, XCircle } from 'lucide-react';
import { PredictionResult } from '@/types';

interface AnalysisDashboardProps {
  result: PredictionResult | null;
  isAnalyzing: boolean;
}

export const AnalysisDashboard: React.FC<AnalysisDashboardProps> = ({
  result,
  isAnalyzing,
}) => {
  if (isAnalyzing) {
    return (
      <div className="glass-panel p-8 rounded-3xl border border-slate-800/80 shadow-2xl flex flex-col items-center justify-center min-h-[350px] space-y-4">
        <div className="relative">
          <div className="w-16 h-16 rounded-full border-4 border-emerald-500/20 border-t-emerald-500 animate-spin" />
          <Gauge className="w-8 h-8 text-emerald-400 absolute inset-0 m-auto" />
        </div>
        <div className="text-center">
          <h3 className="text-lg font-bold text-slate-100">Evaluating Face Liveness...</h3>
          <p className="text-xs text-slate-400 max-w-sm mt-1">
            Applying 80x80 multi-scale crops across MiniFASNet convolutional models...
          </p>
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="glass-panel p-8 rounded-3xl border border-slate-800/80 shadow-2xl flex flex-col items-center justify-center min-h-[350px] space-y-3 text-center">
        <div className="p-4 rounded-full bg-slate-900 border border-slate-800 text-slate-500">
          <Target className="w-10 h-10" />
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-200">Awaiting Input</h3>
          <p className="text-xs text-slate-500 max-w-xs mt-1">
            Start the webcam, upload a photo, or choose a sample image to view liveness evaluation.
          </p>
        </div>
      </div>
    );
  }

  if (!result.success) {
    return (
      <div className="glass-panel p-6 rounded-3xl border border-rose-500/30 bg-rose-950/20 shadow-2xl space-y-4">
        <div className="flex items-center space-x-3 text-rose-400">
          <AlertTriangle className="w-8 h-8 flex-shrink-0" />
          <div>
            <h3 className="text-base font-bold">Detection Error</h3>
            <p className="text-xs text-rose-300/80">{result.error || 'Failed to analyze frame'}</p>
          </div>
        </div>
      </div>
    );
  }

  const isReal = result.is_real;
  const realProb = result.real_probability ?? 0;
  const fakeProb = result.fake_probability ?? 0;
  const threshold = (result.threshold_used ?? 0.5) * 100;

  return (
    <div className="space-y-6">
      {/* Verdict Banner Card */}
      <div
        className={`relative glass-panel p-6 rounded-3xl border transition-all duration-500 overflow-hidden shadow-2xl ${
          isReal
            ? 'border-emerald-500/50 bg-gradient-to-br from-emerald-950/40 via-slate-900/90 to-slate-950 shadow-emerald-500/10'
            : 'border-rose-500/50 bg-gradient-to-br from-rose-950/40 via-slate-900/90 to-slate-950 shadow-rose-500/10'
        }`}
      >
        {/* Glow backdrop */}
        <div
          className={`absolute -right-10 -bottom-10 w-48 h-48 rounded-full blur-3xl opacity-20 pointer-events-none ${
            isReal ? 'bg-emerald-500' : 'bg-rose-500'
          }`}
        />

        <div className="relative z-10 flex flex-col md:flex-row items-center justify-between gap-6">
          {/* Main Status & Badge */}
          <div className="flex items-center space-x-4">
            <div
              className={`flex items-center justify-center w-16 h-16 rounded-2xl shadow-xl border ${
                isReal
                  ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400 shadow-emerald-500/20'
                  : 'bg-rose-500/20 border-rose-500/40 text-rose-400 shadow-rose-500/20'
              }`}
            >
              {isReal ? <ShieldCheck className="w-10 h-10" /> : <ShieldAlert className="w-10 h-10" />}
            </div>

            <div>
              <div className="flex items-center space-x-2">
                <span
                  className={`px-2.5 py-0.5 rounded-full text-[10px] font-extrabold tracking-wider uppercase border ${
                    isReal
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                      : 'bg-rose-500/20 text-rose-300 border-rose-500/30'
                  }`}
                >
                  {isReal ? 'AUTHENTIC FACE' : 'SPOOF ATTACK DETECTED'}
                </span>
                <span className="text-xs text-slate-400 font-mono">Threshold: {threshold.toFixed(0)}%</span>
              </div>
              <h2 className="text-2xl md:text-3xl font-extrabold tracking-tight text-white mt-1">
                {result.label_str}
              </h2>
            </div>
          </div>

          {/* Confidence Score Pill */}
          <div className="flex flex-col items-center md:items-end">
            <span className="text-xs text-slate-400 font-medium">Confidence Score</span>
            <div className="flex items-baseline space-x-1">
              <span className={`text-4xl font-extrabold font-mono tracking-tight ${isReal ? 'text-emerald-400' : 'text-rose-400'}`}>
                {result.score?.toFixed(1)}%
              </span>
            </div>
          </div>
        </div>

        {/* Probability Bars */}
        <div className="mt-6 pt-6 border-t border-slate-800/80 grid grid-cols-1 sm:grid-cols-2 gap-4">
          
          {/* Real Probability */}
          <div>
            <div className="flex justify-between text-xs font-semibold mb-1.5">
              <span className="text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> Real Face Probability
              </span>
              <span className="font-mono text-emerald-300">{realProb.toFixed(1)}%</span>
            </div>
            <div className="w-full h-3 bg-slate-950 rounded-full overflow-hidden p-0.5 border border-slate-800">
              <div
                className="h-full bg-gradient-to-r from-emerald-600 to-teal-400 rounded-full transition-all duration-700"
                style={{ width: `${Math.min(100, Math.max(0, realProb))}%` }}
              />
            </div>
          </div>

          {/* Fake / Spoof Probability */}
          <div>
            <div className="flex justify-between text-xs font-semibold mb-1.5">
              <span className="text-rose-400 flex items-center gap-1">
                <XCircle className="w-3.5 h-3.5" /> Spoof / Fake Probability
              </span>
              <span className="font-mono text-rose-300">{fakeProb.toFixed(1)}%</span>
            </div>
            <div className="w-full h-3 bg-slate-950 rounded-full overflow-hidden p-0.5 border border-slate-800">
              <div
                className="h-full bg-gradient-to-r from-rose-600 to-pink-500 rounded-full transition-all duration-700"
                style={{ width: `${Math.min(100, Math.max(0, fakeProb))}%` }}
              />
            </div>
          </div>

        </div>
      </div>

      {/* Grid: Annotated Output + Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Annotated Bounding Box Visualizer */}
        <div className="glass-panel p-5 rounded-3xl border border-slate-800/80 shadow-2xl flex flex-col justify-between">
          <h3 className="text-sm font-bold text-slate-200 mb-3 flex items-center space-x-2">
            <Target className="w-4 h-4 text-emerald-400" />
            <span>Face Detection & Bounding Box</span>
          </h3>

          <div className="relative aspect-[4/3] w-full rounded-2xl overflow-hidden bg-slate-950 border border-slate-800 flex items-center justify-center">
            {result.annotated_image_b64 ? (
              <img
                src={result.annotated_image_b64}
                alt="Annotated Detection"
                className="w-full h-full object-contain"
              />
            ) : (
              <span className="text-xs text-slate-500">No image preview</span>
            )}
          </div>
        </div>

        {/* Diagnostic Metrics */}
        <div className="glass-panel p-5 rounded-3xl border border-slate-800/80 shadow-2xl flex flex-col justify-between space-y-4">
          <h3 className="text-sm font-bold text-slate-200 flex items-center space-x-2">
            <Cpu className="w-4 h-4 text-teal-400" />
            <span>Execution Telemetry & Bounding Box</span>
          </h3>

          <div className="grid grid-cols-2 gap-3">
            <div className="glass-card p-3 rounded-2xl border border-slate-800">
              <div className="flex items-center space-x-2 text-slate-400 text-xs mb-1">
                <Clock className="w-3.5 h-3.5 text-teal-400" />
                <span>Total Latency</span>
              </div>
              <p className="text-lg font-mono font-bold text-slate-100">
                {result.total_latency_ms} <span className="text-xs font-sans text-slate-400">ms</span>
              </p>
            </div>

            <div className="glass-card p-3 rounded-2xl border border-slate-800">
              <div className="flex items-center space-x-2 text-slate-400 text-xs mb-1">
                <Target className="w-3.5 h-3.5 text-emerald-400" />
                <span>Bounding Box Size</span>
              </div>
              <p className="text-lg font-mono font-bold text-slate-100">
                {result.bbox ? `${result.bbox.width}x${result.bbox.height}` : 'N/A'}
              </p>
            </div>
          </div>

          {/* BBox Details */}
          {result.bbox && (
            <div className="glass-card p-4 rounded-2xl border border-slate-800 text-xs space-y-2">
              <div className="text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
                Face Location Coordinates
              </div>
              <div className="grid grid-cols-4 gap-2 font-mono text-center">
                <div className="bg-slate-900 p-2 rounded-xl border border-slate-800">
                  <div className="text-slate-500 text-[10px]">X</div>
                  <div className="text-slate-200 font-bold">{result.bbox.x}</div>
                </div>
                <div className="bg-slate-900 p-2 rounded-xl border border-slate-800">
                  <div className="text-slate-500 text-[10px]">Y</div>
                  <div className="text-slate-200 font-bold">{result.bbox.y}</div>
                </div>
                <div className="bg-slate-900 p-2 rounded-xl border border-slate-800">
                  <div className="text-slate-500 text-[10px]">WIDTH</div>
                  <div className="text-slate-200 font-bold">{result.bbox.width}</div>
                </div>
                <div className="bg-slate-900 p-2 rounded-xl border border-slate-800">
                  <div className="text-slate-500 text-[10px]">HEIGHT</div>
                  <div className="text-slate-200 font-bold">{result.bbox.height}</div>
                </div>
              </div>
            </div>
          )}
        </div>

      </div>
    </div>
  );
};
