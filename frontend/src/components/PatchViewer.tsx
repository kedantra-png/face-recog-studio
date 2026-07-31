'use client';

import React from 'react';
import { Layers, ZoomIn } from 'lucide-react';

interface PatchViewerProps {
  patches?: Record<string, string>;
}

export const PatchViewer: React.FC<PatchViewerProps> = ({ patches }) => {
  if (!patches || Object.keys(patches).length === 0) return null;

  return (
    <div className="glass-panel p-5 rounded-3xl border border-slate-800/80 shadow-2xl space-y-4">
      <div className="flex items-center space-x-2">
        <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
          <Layers className="w-5 h-5" />
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-100">Multi-Scale Crop Inspector</h3>
          <p className="text-xs text-slate-400">Patches extracted for MiniFASNet feature evaluation</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {Object.entries(patches).map(([key, b64]) => {
          const scaleLabel = key.replace('scale_', 'Scale ');

          return (
            <div
              key={key}
              className="glass-card p-3 rounded-2xl border border-slate-800 flex flex-col items-center space-y-2 group"
            >
              <div className="relative w-full aspect-[3/4] rounded-xl overflow-hidden bg-slate-950 border border-slate-800">
                <img
                  src={b64}
                  alt={scaleLabel}
                  className="w-full h-full object-cover group-hover:scale-110 transition duration-300"
                />
                <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-black/70 backdrop-blur text-[10px] font-mono text-indigo-300 border border-indigo-500/20">
                  {scaleLabel}
                </div>
              </div>
              <span className="text-[11px] font-medium text-slate-400 font-mono">80x80 Input Patch</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
