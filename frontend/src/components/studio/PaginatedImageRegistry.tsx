'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Search, RefreshCw, ChevronLeft, ChevronRight, Image as ImageIcon, CheckCircle, AlertCircle, Clock, ExternalLink } from 'lucide-react';
import { getApiBaseUrl } from '@/lib/api';

export interface ImageRecord {
  image_id: string;
  job_id: string;
  event_id: string;
  original_filename: string;
  status: string;
  quality_score: number;
  detected_faces: number;
  google_drive: string;
  drive_url?: string;
  created_at: number;
}

interface PaginatedImageRegistryProps {
  eventId: string;
  refreshTrigger?: number;
}

export default function PaginatedImageRegistry({ eventId, refreshTrigger }: PaginatedImageRegistryProps) {
  const [images, setImages] = useState<ImageRecord[]>([]);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchImages = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const token = localStorage.getItem('studio_token');
      const baseUrl = getApiBaseUrl();
      const params = new URLSearchParams({
        page: page.toString(),
        limit: limit.toString(),
      });
      if (search.trim()) params.append('search', search.trim());
      if (statusFilter !== 'all') params.append('status', statusFilter);

      const res = await fetch(`${baseUrl}/api/v2/studio/events/${eventId}/images?${params.toString()}`, {
        headers: {
          Authorization: token ? `Bearer ${token}` : '',
        },
        credentials: 'include',
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || 'Failed to fetch event images');
      }

      setImages(data.images || []);
      setTotal(data.total || 0);
      setTotalPages(data.total_pages || 1);
    } catch (err: any) {
      console.error('Error fetching event images:', err);
      setError(err.message || 'Error loading image registry');
    } finally {
      setIsLoading(false);
    }
  }, [eventId, page, limit, search, statusFilter]);

  useEffect(() => {
    fetchImages();
  }, [fetchImages, refreshTrigger]);

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value);
    setPage(1); // reset to page 1 on search
  };

  const handleStatusFilterChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setStatusFilter(e.target.value);
    setPage(1); // reset to page 1 on filter change
  };

  const handleLimitChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setLimit(Number(e.target.value));
    setPage(1);
  };

  return (
    <div className="bg-[#0b0f19]/90 border border-slate-800/80 rounded-3xl p-6 md:p-8 shadow-2xl space-y-6">
      {/* Top Section Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-400">
              <ImageIcon className="w-4 h-4" />
            </div>
            <h3 className="text-lg font-extrabold text-white tracking-tight">Event Photo Registry</h3>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Server-side paginated InsightFace 512-d vector index • {total} total photo(s)
          </p>
        </div>

        {/* Filter Bar Controls */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Search Input */}
          <div className="relative flex-1 md:w-64">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={handleSearchChange}
              placeholder="Search filename or ID..."
              className="w-full pl-9 pr-3 py-2 rounded-xl bg-slate-950/80 border border-slate-800 text-white placeholder-slate-500 text-xs focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition"
            />
          </div>

          {/* Status Filter Dropdown */}
          <select
            value={statusFilter}
            onChange={handleStatusFilterChange}
            className="px-3 py-2 rounded-xl bg-slate-950/80 border border-slate-800 text-slate-300 text-xs font-medium focus:outline-none focus:border-emerald-500 transition"
          >
            <option value="all">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="processing">Processing</option>
            <option value="failed">Failed</option>
          </select>

          {/* Page Size Selector */}
          <select
            value={limit}
            onChange={handleLimitChange}
            className="px-3 py-2 rounded-xl bg-slate-950/80 border border-slate-800 text-slate-300 text-xs font-medium focus:outline-none focus:border-emerald-500 transition"
          >
            <option value={10}>10 / page</option>
            <option value={20}>20 / page</option>
            <option value={50}>50 / page</option>
            <option value={100}>100 / page</option>
          </select>

          {/* Refresh Button */}
          <button
            onClick={fetchImages}
            disabled={isLoading}
            className="p-2 rounded-xl bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 transition flex items-center justify-center disabled:opacity-50"
            title="Refresh Table"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="p-3 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
          {error}
        </div>
      )}

      {/* Registry Table */}
      <div className="overflow-x-auto rounded-2xl border border-slate-800/80 bg-slate-950/50">
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="bg-slate-900/90 text-slate-400 uppercase font-mono text-[10px] tracking-wider border-b border-slate-800">
            <tr>
              <th className="py-3 px-4">Filename</th>
              <th className="py-3 px-4">Quality Score</th>
              <th className="py-3 px-4 text-center">Detected Faces</th>
              <th className="py-3 px-4">Embedding Status</th>
              <th className="py-3 px-4">Drive Sync</th>
              <th className="py-3 px-4 text-right">Uploaded At</th>
            </tr>
          </thead>

          <tbody className="divide-y divide-slate-800/50">
            {isLoading && images.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-12 text-center text-slate-500 font-medium">
                  Loading event images...
                </td>
              </tr>
            ) : images.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-12 text-center text-slate-500 font-medium">
                  No images found for this event. Upload photos or ZIP archives above to generate embeddings.
                </td>
              </tr>
            ) : (
              images.map((img) => (
                <tr key={img.image_id || Math.random()} className="hover:bg-slate-900/60 transition">
                  <td className="py-3 px-4 font-mono font-medium text-white max-w-xs truncate">
                    <div className="flex items-center space-x-2">
                      <div className="w-6 h-6 rounded-lg bg-slate-800 flex items-center justify-center text-slate-400 text-[10px] shrink-0 font-sans">
                        📷
                      </div>
                      <span className="truncate">{img.original_filename}</span>
                    </div>
                  </td>
                  <td className="py-3 px-4 font-mono">
                    <span className="px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 text-[10px] font-bold border border-emerald-500/20">
                      {img.quality_score}%
                    </span>
                  </td>
                  <td className="py-3 px-4 text-center font-mono font-bold text-slate-200">
                    {img.detected_faces}
                  </td>
                  <td className="py-3 px-4">
                    {img.status === 'completed' ? (
                      <span className="inline-flex items-center space-x-1 text-emerald-400 font-bold text-[10px]">
                        <CheckCircle className="w-3.5 h-3.5" />
                        <span>Indexed (512-d)</span>
                      </span>
                    ) : img.status === 'failed' ? (
                      <span className="inline-flex items-center space-x-1 text-rose-400 font-bold text-[10px]">
                        <AlertCircle className="w-3.5 h-3.5" />
                        <span>Failed</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center space-x-1 text-amber-400 font-bold text-[10px]">
                        <Clock className="w-3.5 h-3.5 animate-spin" />
                        <span>Processing</span>
                      </span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-slate-400 text-[11px]">
                    {img.drive_url ? (
                      <a
                        href={img.drive_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-teal-400 hover:text-teal-300 font-medium inline-flex items-center space-x-1"
                      >
                        <span>Synced</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    ) : (
                      <span className="text-slate-500">Local</span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-right text-slate-400 font-mono text-[11px]">
                    {new Date(img.created_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer Controls */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-2 border-t border-slate-800/80">
        <div className="text-xs text-slate-400">
          Showing page <span className="font-bold text-white">{page}</span> of{' '}
          <span className="font-bold text-white">{totalPages}</span> ({total} items)
        </div>

        <div className="flex items-center space-x-2">
          {/* Previous Page Button */}
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1 || isLoading}
            className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 text-xs font-semibold disabled:opacity-40 disabled:hover:bg-slate-900 transition flex items-center space-x-1"
          >
            <ChevronLeft className="w-4 h-4" />
            <span>Previous</span>
          </button>

          {/* Page Indicators */}
          <div className="flex items-center space-x-1 px-2">
            <span className="px-3 py-1 rounded-xl bg-emerald-500/20 text-emerald-400 font-bold text-xs border border-emerald-500/40">
              {page}
            </span>
          </div>

          {/* Next Page Button */}
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages || isLoading}
            className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 text-xs font-semibold disabled:opacity-40 disabled:hover:bg-slate-900 transition flex items-center space-x-1"
          >
            <span>Next</span>
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
