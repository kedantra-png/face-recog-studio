'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Search, Filter, ExternalLink, ShieldCheck, CheckCircle2, AlertTriangle, Layers, RefreshCw } from 'lucide-react';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export interface ImageMetadataRecord {
  image_id: str;
  job_id: str;
  original_filename: str;
  relative_folder: str;
  sha256: str;
  file_size: number;
  mime_type: str;
  drive_status: str;
  drive_url?: str;
  embedding_status: str;
  detected_faces: number;
  quality_score: number;
  embedding_model: str;
  created_at: number;
}

export const UploadHistoryTable: React.FC = () => {
  const [images, setImages] = useState<ImageMetadataRecord[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const fetchHistory = useCallback(async () => {
    setIsLoading(true);
    try {
      const url = new URL(`${API_BASE_URL}/api/v2/uploads`);
      url.searchParams.append('page', page.toString());
      url.searchParams.append('limit', '10');
      if (searchQuery) url.searchParams.append('query', searchQuery);
      if (statusFilter) url.searchParams.append('status', statusFilter);

      const res = await fetch(url.toString());
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setImages(data.images);
          setTotal(data.total);
        }
      }
    } catch (err) {
      console.warn('Failed to fetch upload history:', err);
    } finally {
      setIsLoading(false);
    }
  }, [page, searchQuery, statusFilter]);

  useEffect(() => {
    fetchHistory();
    const interval = setInterval(() => {
      fetchHistory();
    }, 2500);
    return () => clearInterval(interval);
  }, [fetchHistory]);


  return (
    <div className="glass-panel p-6 rounded-3xl border border-slate-800/80 shadow-2xl space-y-4">
      {/* Header & Filter Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div className="flex items-center space-x-2">
          <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-100">Processed Image Registry</h2>
            <p className="text-xs text-slate-400">
              InsightFace 512-d embeddings & metadata repository ({total} total)
            </p>
          </div>
        </div>

        {/* Search & Filter Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search filename..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 pr-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-purple-500"
            />
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-purple-500"
          >
            <option value="">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="queued">Queued</option>
            <option value="failed">Failed</option>
          </select>

          <button
            onClick={fetchHistory}
            className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 transition border border-slate-700"
            title="Refresh History"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* History Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
              <th className="py-2.5 px-3">Filename</th>
              <th className="py-2.5 px-3">Quality Score</th>
              <th className="py-2.5 px-3">Detected Faces</th>
              <th className="py-2.5 px-3">Embedding Status</th>
              <th className="py-2.5 px-3">Google Drive</th>
              <th className="py-2.5 px-3 text-right">Processed At</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-mono text-slate-200">
            {images.length > 0 ? (
              images.map((img) => (
                <tr key={img.image_id} className="hover:bg-slate-900/50 transition">
                  <td className="py-3 px-3">
                    <p className="font-semibold text-slate-100 truncate max-w-[200px]">
                      {img.original_filename}
                    </p>
                    <p className="text-[10px] text-slate-500 truncate max-w-[200px]">
                      {img.relative_folder || '/'}
                    </p>
                  </td>

                  <td className="py-3 px-3">
                    <span className="px-2 py-0.5 rounded bg-slate-800 font-bold text-teal-300 border border-slate-700">
                      {(img.quality_score * 100).toFixed(0)}%
                    </span>
                  </td>

                  <td className="py-3 px-3 font-bold text-emerald-400">
                    {img.detected_faces} Face(s)
                  </td>

                  <td className="py-3 px-3">
                    <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold text-[10px]">
                      512-d InsightFace
                    </span>
                  </td>

                  <td className="py-3 px-3">
                    {img.drive_url ? (
                      <a
                        href={img.drive_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1 font-semibold text-[11px]"
                      >
                        <span>View Drive</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    ) : (
                      <span className="text-slate-500 text-[10px]">Pending</span>
                    )}
                  </td>

                  <td className="py-3 px-3 text-right text-slate-400 text-[11px]">
                    {new Date(img.created_at * 1000).toLocaleTimeString()}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="py-8 text-center text-slate-500 font-sans text-xs">
                  No processed images found. Upload photos above to generate InsightFace 512-d embeddings.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
