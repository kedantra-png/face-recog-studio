'use client';

import React from 'react';
import { Cpu, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { PerModelScore } from '@/types';

interface ModelBreakdownTableProps {
  scores?: Record<string, PerModelScore>;
}

export const ModelBreakdownTable: React.FC<ModelBreakdownTableProps> = ({ scores }) => {
  if (!scores || Object.keys(scores).length === 0) return null;

  return (
    <div className="glass-panel p-5 rounded-3xl border border-slate-800/80 shadow-2xl space-y-4">
      <div className="flex items-center space-x-2">
        <div className="p-2 rounded-xl bg-teal-500/10 text-teal-400 border border-teal-500/20">
          <Cpu className="w-5 h-5" />
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-100">Ensemble Model Breakdown</h3>
          <p className="text-xs text-slate-400">Individual MiniFASNet neural net output probabilities</p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
              <th className="py-2.5 px-3">Model Weights File</th>
              <th className="py-2.5 px-3">Architecture</th>
              <th className="py-2.5 px-3">Scale</th>
              <th className="py-2.5 px-3">Real Score</th>
              <th className="py-2.5 px-3">Spoof Score</th>
              <th className="py-2.5 px-3 text-right">Latency</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-mono text-slate-200">
            {Object.entries(scores).map(([modelName, data]) => {
              const isRealWinning = data.real_score >= 50;

              return (
                <tr key={modelName} className="hover:bg-slate-900/50 transition">
                  <td className="py-3 px-3 font-semibold text-slate-100 truncate max-w-[200px]">
                    {modelName}
                  </td>
                  <td className="py-3 px-3">
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-teal-300 text-[10px]">
                      {data.model_type}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-slate-400">
                    {data.scale !== null ? `${data.scale}x` : 'Full'}
                  </td>
                  <td className="py-3 px-3">
                    <span
                      className={`px-2 py-0.5 rounded font-bold ${
                        isRealWinning
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : 'text-slate-400'
                      }`}
                    >
                      {data.real_score.toFixed(1)}%
                    </span>
                  </td>
                  <td className="py-3 px-3">
                    <span
                      className={`px-2 py-0.5 rounded font-bold ${
                        !isRealWinning
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                          : 'text-slate-400'
                      }`}
                    >
                      {data.fake_score.toFixed(1)}%
                    </span>
                  </td>
                  <td className="py-3 px-3 text-right text-slate-400">
                    <span className="flex items-center justify-end space-x-1">
                      <Clock className="w-3 h-3 text-slate-500" />
                      <span>{data.latency_ms} ms</span>
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
