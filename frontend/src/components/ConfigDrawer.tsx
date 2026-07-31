'use client';

import React from 'react';
import { Sliders, X, Server, ShieldCheck, Cpu, HardDrive, CheckCircle2 } from 'lucide-react';
import { BackendConfig } from '@/types';

interface ConfigDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  config: BackendConfig | null;
}

export const ConfigDrawer: React.FC<ConfigDrawerProps> = ({
  isOpen,
  onClose,
  config,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-fade-in">
      <div className="glass-panel w-full max-w-xl p-6 rounded-3xl border border-slate-800 shadow-2xl space-y-6 relative overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center space-x-2">
            <div className="p-2 rounded-xl bg-teal-500/10 text-teal-400 border border-teal-500/20">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-100">Backend Environment (.env)</h2>
              <p className="text-xs text-slate-400">Live configuration loaded from FastAPI backend</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        {config ? (
          <div className="space-y-4">
            
            {/* Real Threshold Setting */}
            <div className="glass-card p-4 rounded-2xl border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" /> REAL_THRESHOLD
                </span>
                <span className="px-2.5 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 font-mono font-bold text-sm border border-emerald-500/30">
                  {(config.real_threshold * 100).toFixed(0)}% ({config.real_threshold})
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Determined via <code className="text-slate-400">REAL_THRESHOLD</code> in <code className="text-teal-400">.env</code>. Real face probability equal to or above this percentage is labeled as Real.
              </p>
            </div>

            {/* Device ID & Models */}
            <div className="grid grid-cols-2 gap-3">
              <div className="glass-card p-3 rounded-2xl border border-slate-800">
                <div className="text-xs text-slate-400 flex items-center gap-1.5 mb-1">
                  <Cpu className="w-3.5 h-3.5 text-teal-400" /> DEVICE_ID
                </div>
                <div className="font-mono text-sm font-bold text-slate-200">
                  {config.device_id === 0 ? 'GPU 0 / CPU' : `GPU ${config.device_id}`}
                </div>
              </div>

              <div className="glass-card p-3 rounded-2xl border border-slate-800">
                <div className="text-xs text-slate-400 flex items-center gap-1.5 mb-1">
                  <HardDrive className="w-3.5 h-3.5 text-indigo-400" /> Active Models
                </div>
                <div className="font-mono text-sm font-bold text-slate-200">
                  {config.num_models} Weights Loaded
                </div>
              </div>
            </div>

            {/* Available Model List */}
            <div className="glass-card p-4 rounded-2xl border border-slate-800 space-y-2">
              <div className="text-xs font-semibold text-slate-300">Model Weights Directory</div>
              <div className="text-xs font-mono text-teal-400 bg-slate-950 p-2 rounded-xl border border-slate-900 truncate">
                {config.model_dir}
              </div>

              <div className="pt-2 space-y-1">
                {config.available_models.map((model) => (
                  <div key={model} className="flex items-center space-x-2 text-xs font-mono text-slate-300">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span>{model}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* CORS Origins */}
            <div className="glass-card p-4 rounded-2xl border border-slate-800 space-y-2">
              <div className="text-xs font-semibold text-slate-300">Allowed CORS Origins</div>
              <div className="flex flex-wrap gap-1.5">
                {config.cors_origins.map((origin) => (
                  <span key={origin} className="px-2 py-0.5 rounded bg-slate-800 text-[11px] font-mono text-slate-300 border border-slate-700">
                    {origin}
                  </span>
                ))}
              </div>
            </div>

          </div>
        ) : (
          <div className="p-6 text-center text-xs text-slate-500">
            Unable to fetch configuration from FastAPI server.
          </div>
        )}

        <div className="flex justify-end pt-2">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold text-xs transition"
          >
            Close Settings
          </button>
        </div>
      </div>
    </div>
  );
};
