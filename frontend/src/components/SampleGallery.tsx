'use client';

import React from 'react';
import { Image as ImageIcon, Sparkles, CheckCircle2, AlertTriangle } from 'lucide-react';
import { SampleImage } from '@/types';

interface SampleGalleryProps {
  samples: SampleImage[];
  onSelectSample: (sampleUrl: string, filename: string) => Promise<void>;
  selectedFilename: string | null;
  isAnalyzing: boolean;
}

export const SampleGallery: React.FC<SampleGalleryProps> = ({
  samples,
  onSelectSample,
  selectedFilename,
  isAnalyzing,
}) => {
  if (!samples || samples.length === 0) return null;

  return (
    <div className="glass-panel p-5 rounded-3xl border border-slate-800/80 shadow-2xl">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-100">Preloaded Evaluation Samples</h2>
            <p className="text-xs text-slate-400">Click any image to test anti-spoofing prediction instantly</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
        {samples.map((sample) => {
          const isSelected = selectedFilename === sample.filename;
          const isRealHint = sample.hint === 'Real';
          const fullImgUrl = sample.url.startsWith('http')
            ? sample.url
            : `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}${sample.url}`;

          return (
            <button
              key={sample.filename}
              onClick={() => onSelectSample(sample.url, sample.filename)}
              disabled={isAnalyzing}
              className={`relative aspect-[3/4] rounded-xl overflow-hidden border-2 transition group flex flex-col justify-between p-1.5 ${
                isSelected
                  ? 'border-purple-500 ring-4 ring-purple-500/20 scale-105 z-10'
                  : 'border-slate-800 bg-slate-950 hover:border-slate-700 hover:scale-102'
              }`}
            >
              <img
                src={fullImgUrl}
                alt={sample.filename}
                className="absolute inset-0 w-full h-full object-cover group-hover:scale-110 transition duration-300"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-black/30" />


              {/* Real / Fake Hint Pill */}
              <div className="relative z-10 flex justify-between items-start">
                <span
                  className={`px-1.5 py-0.5 rounded text-[9px] font-extrabold uppercase tracking-wider ${
                    isRealHint
                      ? 'bg-emerald-500/90 text-white'
                      : 'bg-rose-500/90 text-white'
                  }`}
                >
                  {sample.hint}
                </span>
              </div>

              {/* Filename */}
              <div className="relative z-10 text-left">
                <p className="text-[10px] font-mono text-slate-200 truncate font-semibold">
                  {sample.filename}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
