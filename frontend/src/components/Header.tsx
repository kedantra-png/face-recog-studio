'use client';

import React from 'react';
import Link from 'next/link';
import { ShieldCheck, Sliders, Server, UploadCloud } from 'lucide-react';
import { BackendConfig } from '@/types';
import { getApiBaseUrl } from '@/lib/api';

interface HeaderProps {
  config: BackendConfig | null;
  isConnected: boolean;
  onRefreshConfig: () => void;
  onOpenConfig: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  config,
  isConnected,
  onRefreshConfig,
  onOpenConfig,
}) => {
  return (
    <header className="sticky top-0 z-40 w-full glass-panel border-b border-slate-800/80 bg-[#090d16]/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">

        {/* Brand Logo & Title */}
        <div className="flex items-center space-x-3">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-700 text-white shadow-lg shadow-emerald-500/20">
            <ShieldCheck className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-200 to-emerald-400 bg-clip-text text-transparent">
                AuraFace AI
              </h1>
              <span className="px-2 py-0.5 text-[10px] font-semibold tracking-wider uppercase rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                v2.0 FastAPI
              </span>
            </div>
            <p className="text-xs text-slate-400 font-medium">Silent-Face Liveness & Anti-Spoofing Engine</p>
          </div>
        </div>

        {/* System Status & Quick Info */}
        <div className="flex items-center space-x-4">

          {/* Connection Status Badge */}
          <div className={`flex items-center space-x-2 px-3 py-1.5 rounded-full text-xs font-semibold border ${isConnected
              ? 'bg-emerald-950/40 text-emerald-400 border-emerald-500/30'
              : 'bg-rose-950/40 text-rose-400 border-rose-500/30'
            }`}>
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400 animate-ping' : 'bg-rose-500'}`} />
            <Server className="w-3.5 h-3.5" />
            <span>{isConnected ? 'FastAPI Connected' : 'Backend Offline'}</span>
          </div>

          {/* Active Threshold Pill */}
          {config && (
            <div className="hidden sm:flex items-center space-x-2 px-3 py-1.5 rounded-full text-xs font-medium bg-slate-800/60 border border-slate-700/50 text-slate-300">
              <Sliders className="w-3.5 h-3.5 text-teal-400" />
              <span>Threshold:</span>
              <span className="font-mono font-bold text-teal-300">{(config.real_threshold * 100).toFixed(0)}%</span>
            </div>
          )}

          {/* Master Admin Portal Link (FastAPI) */}
          <a
            href={`${getApiBaseUrl()}/master/login`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 hover:text-purple-300 font-semibold text-xs transition border border-purple-500/30"
            title="Master Admin Gateway (FastAPI)"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-purple-400" />
            <span className="hidden md:inline">Master Portal</span>
          </a>

          {/* Studio Pipeline Dashboard Link */}
          <Link
            href="/studio"
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-semibold text-xs transition shadow-md shadow-emerald-500/20"
          >
            <UploadCloud className="w-4 h-4" />
            <span className="hidden sm:inline">Studio Pipeline</span>
          </Link>

          {/* Config Settings Button */}
          <button
            onClick={onOpenConfig}
            className="p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 hover:text-white transition border border-slate-700/60 shadow-sm"
            title="Backend Configuration (.env)"
          >
            <Sliders className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
};
