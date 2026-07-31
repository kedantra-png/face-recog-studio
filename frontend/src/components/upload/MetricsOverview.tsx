'use client';

import React from 'react';
import { Cpu, HardDrive, Server, Activity, CheckCircle2, AlertTriangle } from 'lucide-react';

interface MetricsOverviewProps {
  metrics: {
    cpu_percent?: number;
    ram_percent?: number;
    disk_free_gb?: number;
    queue?: {
      queued: number;
      processing: number;
      completed: number;
      failed: number;
    };
  } | null;
}

export const MetricsOverview: React.FC<MetricsOverviewProps> = ({ metrics }) => {
  if (!metrics) return null;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      {/* CPU Usage */}
      <div className="glass-panel p-4 rounded-2xl border border-slate-800 flex items-center space-x-3">
        <div className="p-2.5 rounded-xl bg-teal-500/10 text-teal-400 border border-teal-500/20">
          <Cpu className="w-5 h-5" />
        </div>
        <div>
          <p className="text-xs text-slate-400 font-medium">CPU Utilization</p>
          <p className="text-lg font-mono font-bold text-slate-100">
            {metrics.cpu_percent ?? 0}%
          </p>
        </div>
      </div>

      {/* RAM Usage */}
      <div className="glass-panel p-4 rounded-2xl border border-slate-800 flex items-center space-x-3">
        <div className="p-2.5 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
          <Server className="w-5 h-5" />
        </div>
        <div>
          <p className="text-xs text-slate-400 font-medium">RAM Utilization</p>
          <p className="text-lg font-mono font-bold text-slate-100">
            {metrics.ram_percent ?? 0}%
          </p>
        </div>
      </div>

      {/* Disk Space */}
      <div className="glass-panel p-4 rounded-2xl border border-slate-800 flex items-center space-x-3">
        <div className="p-2.5 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
          <HardDrive className="w-5 h-5" />
        </div>
        <div>
          <p className="text-xs text-slate-400 font-medium">Disk Free</p>
          <p className="text-lg font-mono font-bold text-slate-100">
            {metrics.disk_free_gb ?? 0} <span className="text-xs font-sans text-slate-400">GB</span>
          </p>
        </div>
      </div>

      {/* Queue Depth */}
      <div className="glass-panel p-4 rounded-2xl border border-slate-800 flex items-center space-x-3">
        <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <Activity className="w-5 h-5" />
        </div>
        <div>
          <p className="text-xs text-slate-400 font-medium">Queue Tasks</p>
          <p className="text-lg font-mono font-bold text-slate-100">
            {metrics.queue?.processing ?? 0} <span className="text-xs font-sans text-slate-400">active</span>
          </p>
        </div>
      </div>
    </div>
  );
};
