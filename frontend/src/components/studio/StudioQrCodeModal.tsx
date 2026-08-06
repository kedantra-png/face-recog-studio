'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { X, QrCode, Copy, Check, Download, ExternalLink } from 'lucide-react';
import { getApiBaseUrl } from '@/lib/api';

interface StudioQrCodeModalProps {
  isOpen: boolean;
  onClose: () => void;
  studioName?: string;
  studioId?: string;
}

export default function StudioQrCodeModal({ isOpen, onClose, studioName, studioId }: StudioQrCodeModalProps) {
  const [shareUrl, setShareUrl] = useState<string>('');
  const [isCopied, setIsCopied] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch or generate persistent share link
  const fetchShareLink = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const token = localStorage.getItem('studio_token');
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/v2/studio/share-link`, {
        method: 'POST',
        headers: {
          Authorization: token ? `Bearer ${token}` : '',
        },
        credentials: 'include',
      });

      const data = await res.json();
      if (res.ok && data.success && data.share_url) {
        setShareUrl(data.share_url);
      } else {
        throw new Error(data.detail || 'Failed to generate studio share link');
      }
    } catch (err: any) {
      console.error('Share link error:', err);
      const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000';
      setShareUrl(`${origin}/?studio=${studioId || 'default'}`);
    } finally {
      setIsLoading(false);
    }
  }, [studioId]);

  useEffect(() => {
    if (isOpen) {
      fetchShareLink();
    }
  }, [isOpen, fetchShareLink]);

  const handleCopyLink = () => {
    if (!shareUrl) return;
    navigator.clipboard.writeText(shareUrl);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  // High-Definition Payment App Style Black & White QR Code URL
  const qrImageUrl = shareUrl
    ? `https://api.qrserver.com/v1/create-qr-code/?size=400x400&data=${encodeURIComponent(shareUrl)}&color=0-0-0&bgcolor=255-255-255&margin=1`
    : '';

  const handleDownloadPNG = async () => {
    if (!qrImageUrl) return;

    try {
      const response = await fetch(qrImageUrl);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `Studio_QR_${studioId || 'access'}.png`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download QR error:', err);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fadeIn">
      <div className="w-full max-w-md bg-[#0f1523] border border-slate-800 rounded-3xl p-6 md:p-8 shadow-2xl relative overflow-hidden flex flex-col items-center space-y-6">
        {/* Top Decorative Glow */}
        <div className="absolute top-0 right-0 w-48 h-48 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

        {/* Modal Header */}
        <div className="w-full flex items-center justify-between pb-4 border-b border-slate-800/80">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-700 flex items-center justify-center text-white shadow-lg shadow-emerald-500/20">
              <QrCode className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">Studio Access QR Code</h2>
              <p className="text-xs text-slate-400">Payment-app style scannable black & white QR pass</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-400 hover:text-white flex items-center justify-center transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="w-full p-3 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
            {error}
          </div>
        )}

        {/* Payment App Style Crisp White QR Image Container */}
        <div className="p-4 rounded-3xl bg-white border border-slate-200 shadow-2xl flex flex-col items-center justify-center relative min-h-[272px]">
          {isLoading || !qrImageUrl ? (
            <div className="w-64 h-64 flex flex-col items-center justify-center space-y-2 text-slate-400 text-xs">
              <div className="w-8 h-8 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin" />
              <span>Generating QR Code...</span>
            </div>
          ) : (
            <img
              src={qrImageUrl}
              alt="Studio Access QR Code"
              className="w-64 h-64 rounded-xl object-contain bg-white block shadow-sm border border-slate-100"
            />
          )}
        </div>

        {/* Studio Info Label */}
        <div className="text-center space-y-0.5">
          <div className="text-sm font-bold text-white tracking-tight">{studioName || 'Studio Access Pass'}</div>
          <div className="text-xs font-mono text-emerald-400">ID: {studioId}</div>
        </div>

        {/* Persistent Access URL Field */}
        <div className="w-full space-y-1.5">
          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Persistent Share URL
          </label>
          <div className="flex items-center space-x-2">
            <input
              type="text"
              readOnly
              value={shareUrl || 'Loading persistent link...'}
              className="flex-1 px-3.5 py-2.5 rounded-2xl bg-slate-950/90 border border-slate-800 text-slate-300 text-xs font-mono select-all focus:outline-none"
            />
            <button
              onClick={handleCopyLink}
              disabled={!shareUrl}
              className="px-4 py-2.5 rounded-2xl bg-emerald-500 hover:bg-emerald-400 text-white text-xs font-bold transition flex items-center space-x-1.5 shadow-lg shadow-emerald-500/20 disabled:opacity-50 shrink-0"
            >
              {isCopied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              <span>{isCopied ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="w-full flex items-center space-x-3 pt-2 border-t border-slate-800/80">
          <button
            onClick={onClose}
            className="flex-1 py-3 rounded-2xl bg-slate-900 hover:bg-slate-800 text-slate-300 font-semibold text-xs transition"
          >
            Close
          </button>
          <button
            onClick={handleDownloadPNG}
            disabled={!shareUrl}
            className="flex-1 py-3 rounded-2xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-bold text-xs transition shadow-lg shadow-emerald-500/25 flex items-center justify-center space-x-2 disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            <span>Download PNG</span>
          </button>
        </div>
      </div>
    </div>
  );
}
